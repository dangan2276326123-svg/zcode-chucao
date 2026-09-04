# -*- coding: utf-8 -*-
"""Perception pipeline for the peony inter-row weeder.

Chain: undistort -> DeepLabV3+ inference -> IPM -> dual-wall extraction
-> far-field centerline (chassis nav) + near-field centerline (middle tool PID).

Refactored from network/predict_demo.py + network/camera_calib.py +
morph_process.py. Known pitfalls of the originals avoided:
- calibration loads lazily from a configurable path (no import-time crash)
- single weight source: model_data/weights/best_model.pth
- near/far lookahead rows are explicit parameters (no ±200 px magic offset).
"""
import os
import sys

import cv2
import numpy as np

# workspace root (and tools/) on sys.path so morph_process / network are importable
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TOOLS = os.path.join(_ROOT, 'tools')
for _p in (_ROOT, _TOOLS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from morph_process import peony_postprocess  # noqa: E402
from tools.morph_process import fit_centerline_lsq_weighted  # noqa: E402

MODEL_W, MODEL_H = 960, 720
NUM_CLASSES = 2
WEIGHT_PATH = os.path.join(_ROOT, 'model_data', 'weights', 'best_model.pth')
CALIB_PATH = os.path.join(_ROOT, 'data', 'calib_params.npz')

# IPM trapezoid (960x720 image space) — placeholder until low-mount recalibration
IPM_SRC = np.float32([[80, 540], [880, 540], [320, 200], [640, 200]])
IPM_DST = np.float32([[0, 720], [960, 720], [0, 0], [960, 0]])
IPM_SCALE_X = 0.0015   # m/px lateral (to be recalibrated in field)
IPM_SCALE_Y = 0.0030   # m/px longitudinal

# lookahead rows in IPM space: far -> chassis nav, near -> middle tool
LOOKAHEAD_FAR_Y = 180
LOOKAHEAD_NEAR_Y = 620

MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


class Calib:
    """Lazy calibration holder; builds undistort maps on first use."""

    def __init__(self, path=CALIB_PATH, out_size=(MODEL_W, MODEL_H)):
        self.path = path
        self.out_size = out_size
        self._maps = None

    def _load(self):
        if not os.path.exists(self.path):
            raise FileNotFoundError(
                'calibration file not found: %s' % self.path)
        data = np.load(self.path)
        mtx_full = data['mtx'].astype(np.float64)
        dist_full = data['dist'].astype(np.float64)
        sx, sy = self.out_size[0] / 1920.0, self.out_size[1] / 1080.0
        K = mtx_full.copy()
        K[0, 0] *= sx
        K[1, 1] *= sy
        K[0, 2] *= sx
        K[1, 2] *= sy
        self._maps = cv2.initUndistortRectifyMap(
            mtx_full, dist_full, None, K, self.out_size, 5)

    @property
    def maps(self):
        if self._maps is None:
            self._load()
        return self._maps

    def undistort(self, img_bgr):
        # maps are built in 1920x1080 source space and already produce
        # out_size output — never resize before remap
        h, w = img_bgr.shape[:2]
        if w != 1920 or h != 1080:
            img_bgr = cv2.resize(img_bgr, (1920, 1080))
        return cv2.remap(img_bgr, self.maps[0], self.maps[1],
                         cv2.INTER_LINEAR)


class Perception:
    """One object per camera; process() is the per-frame entry point."""

    def __init__(self, weight_path=WEIGHT_PATH, calib=None, device=None):
        import torch
        from network.modeling import deeplabv3plus_mobilenet
        self.torch = torch
        self.device = device or torch.device(
            'cuda' if torch.cuda.is_available() else 'cpu')
        self.calib = calib or Calib()
        model = deeplabv3plus_mobilenet(
            num_classes=NUM_CLASSES, output_stride=16,
            pretrained_backbone=False)
        if not os.path.exists(weight_path):
            raise FileNotFoundError('weights not found: %s' % weight_path)
        model.load_state_dict(
            torch.load(weight_path, map_location=self.device))
        self.model = model.to(self.device).eval()
        self.ipm = cv2.getPerspectiveTransform(IPM_SRC, IPM_DST)

    # -- internals ---------------------------------------------------------

    def _infer_mask(self, undistorted_bgr):
        """BGR (960x720) -> binary mask (0 bg / 1 peony), same size."""
        rgb = cv2.cvtColor(undistorted_bgr, cv2.COLOR_BGR2RGB)
        x = ((rgb.astype(np.float32) - MEAN) / STD).transpose(2, 0, 1)
        tensor = self.torch.from_numpy(x).unsqueeze(0).to(self.device)
        with self.torch.no_grad():
            logits = self.model(tensor)
        return (logits.argmax(dim=1).squeeze(0).cpu()
                .numpy().astype(np.uint8))

    # -- public API ---------------------------------------------------------

    def process(self, frame_bgr):
        """Full per-frame pipeline.

        Returns dict with keys: undistorted, mask, ipm_mask, nav_far,
        nav_near, lateral_px (far-field, px), tool_offset_px (near-field px),
        confidence (wall pixel support 0-1), status.
        """
        und = self.calib.undistort(frame_bgr)
        mask = self._infer_mask(und)
        ipm_mask = cv2.warpPerspective(mask, self.ipm, (MODEL_W, MODEL_H),
                                       flags=cv2.INTER_LINEAR)
        nav_far, left_w, right_w = peony_postprocess(
            ipm_mask.copy(), lookahead_y=LOOKAHEAD_FAR_Y)
        if nav_far.get('status') == 'dual':
            nav_w = fit_centerline_lsq_weighted(left_w, right_w,
                                                LOOKAHEAD_FAR_Y)
            cx = nav_w.get('center_x')
            if cx is not None and np.isfinite(cx):
                nav_far = nav_w   # gated: no-op unless a wall is degraded
        nav_near, _, _ = peony_postprocess(
            ipm_mask.copy(), lookahead_y=LOOKAHEAD_NEAR_Y)

        support = float((left_w > 0).sum() + (right_w > 0).sum()) / mask.size
        out = {
            'undistorted': und,
            'mask': mask,
            'ipm_mask': ipm_mask,
            'nav_far': nav_far,
            'nav_near': nav_near,
            'lateral_px': nav_far.get('lateral_error'),
            'tool_offset_px': nav_near.get('lateral_error'),
            'confidence': min(1.0, support * 10.0),
            'status': nav_far.get('status'),
        }
        return out


def px_to_meters(dx_px, scale=IPM_SCALE_X):
    """Horizontal IPM pixel offset -> meters."""
    if dx_px is None:
        return None
    return dx_px * scale
