"""Camera calibration adapter for the weeding robot.

Loads pre-computed calibration from calib_params.npz and provides
undistortion + IPM (Inverse Perspective Mapping) for the 960x720 pipeline.
"""
import os
import numpy as np
import cv2

# ---------------------------------------------------------------
# Paths
# ---------------------------------------------------------------
CALIB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "calib_params.npz")

# Model working resolution
MODEL_W, MODEL_H = 960, 720

# ---------------------------------------------------------------
# Load calibration on import
# ---------------------------------------------------------------
_loaded = np.load(CALIB_PATH)
_mtx_full = _loaded["mtx"]        # original 1920x1080
_dist_full = _loaded["dist"]

# Scale camera matrix to 960x720
_scale_x = MODEL_W / 1920.0
_scale_y = MODEL_H / 1080.0
K = _mtx_full.copy()
K[0, 0] *= _scale_x
K[1, 1] *= _scale_y
K[0, 2] *= _scale_x
K[1, 2] *= _scale_y

D = _dist_full

# Precompute undistortion maps
_mapx, _mapy = cv2.initUndistortRectifyMap(
    _mtx_full, _dist_full, None,
    K, (MODEL_W, MODEL_H), 5)


def undistort(img_bgr):
    """Undistort a BGR image to 960x720."""
    if img_bgr.shape[1] != MODEL_W or img_bgr.shape[0] != MODEL_H:
        img_bgr = cv2.resize(img_bgr, (MODEL_W, MODEL_H))
    return cv2.remap(img_bgr, _mapx, _mapy, cv2.INTER_LINEAR)


# ---------------------------------------------------------------
# IPM: Inverse Perspective Mapping
# ---------------------------------------------------------------
# Source points (trapezoid) in pixel space (960x720).
# These define the region of interest on the ground ahead of the tractor.
# Adjust these based on actual camera mounting (height, pitch angle, lens).
IPM_SRC = np.float32([
    [ 80, 540],    # bottom-left  of trapezoid
    [880, 540],    # bottom-right of trapezoid
    [320, 200],    # top-left     of trapezoid
    [640, 200],    # top-right    of trapezoid
])

# Destination points in bird's-eye view (output size = input size for simplicity).
IPM_DST = np.float32([
    [  0, 720],
    [960, 720],
    [  0,   0],
    [960,   0],
])

# Physical scale: how many meters per pixel in the bird's-eye view
# This must be calibrated by measuring a known distance on the ground.
IPM_SCALE_X = 0.0015   # m/pixel (lateral)
IPM_SCALE_Y = 0.0030   # m/pixel (longitudinal)

M_IPM = cv2.getPerspectiveTransform(IPM_SRC, IPM_DST)
M_IPM_INV = cv2.getPerspectiveTransform(IPM_DST, IPM_SRC)


def apply_ipm(img_or_mask):
    """Project an image or mask to bird's-eye view using IPM matrix."""
    return cv2.warpPerspective(img_or_mask, M_IPM, (MODEL_W, MODEL_H),
                               flags=cv2.INTER_LINEAR)


def ipm_mask_to_physical(x_pixel, y_pixel):
    """Convert IPM pixel coordinates to physical meters (relative to center-bottom)."""
    dx = (x_pixel - MODEL_W / 2) * IPM_SCALE_X
    dy = (MODEL_H - y_pixel) * IPM_SCALE_Y
    return dx, dy


def print_calib_summary():
    print("=" * 50)
    print("Camera Calibration Summary (960x720)")
    print("=" * 50)
    print(f"K =\n{K}")
    print(f"Distortion = {D}")
    print(f"IPM src pts:\n{IPM_SRC}")
    print(f"IPM dst pts:\n{IPM_DST}")
    print(f"IPM scale: {IPM_SCALE_X:.4f} m/px (X), {IPM_SCALE_Y:.4f} m/px (Y)")
    print("=" * 50)


if __name__ == "__main__":
    print_calib_summary()
