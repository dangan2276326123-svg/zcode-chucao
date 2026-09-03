# -*- coding: utf-8 -*-
"""F5 ablation: midpoint vs adaptive-weighted centerline under occlusion.

Two validation layers:
1. real-image no-regression — on real masks (thin walls), gated weighting
   must be a no-op (within 10 px);
2. synthetic dense-occlusion — dense weed blobs corrupting one wall must be
   corrected by the row-wise trimmed fit (midpoint of raw LSQ fails badly).

Run: pytest tests/test_adaptive_walls.py -s
"""
import glob
import os
import sys

import numpy as np
import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from tools.morph_process import (peony_postprocess,           # noqa: E402
                                 fit_centerline_lsq,
                                 fit_centerline_lsq_weighted)
from pc.perception import Perception, LOOKAHEAD_FAR_Y  # noqa: E402

TEST_IMG_DIR = r'D:\JetBrains\chucao_prj\model_data\test\images'
OCC_W, OCC_H = 60, 30


def center_midpoint(ipm_mask, y):
    nav, _, _ = peony_postprocess(ipm_mask.copy(), lookahead_y=y)
    return nav


def center_weighted(ipm_mask, y):
    from tools.morph_process import (build_walls, filter_noise,
                                     extract_dual_walls)
    wall = filter_noise(build_walls(ipm_mask))
    left, right = extract_dual_walls(wall)
    return fit_centerline_lsq_weighted(left, right, y)


def occlude_one_wall(ipm_mask, lookahead_y, rng):
    m = ipm_mask.copy()
    band = m[lookahead_y - 20:lookahead_y + 20]
    cols = np.where(band.any(axis=0))[0]
    if len(cols) == 0:
        return m
    col = int(rng.choice(cols))
    y0 = max(0, lookahead_y - OCC_H // 2)
    x0 = max(0, min(959 - OCC_W, col - OCC_W // 2))
    m[y0:y0 + OCC_H, x0:x0 + OCC_W] = 0
    return m


@pytest.mark.skipif(not os.path.isdir(TEST_IMG_DIR),
                    reason='training-domain test images not available')
def test_real_images_no_regression():
    import cv2
    files = sorted(glob.glob(os.path.join(TEST_IMG_DIR, '*.jpg')))[:15]
    assert files
    per = Perception()
    rng = np.random.default_rng(42)
    devs = []
    for f in files:
        img = cv2.imread(f)
        if img is None:
            continue
        clean = per.process(img)['ipm_mask']
        if clean.sum() == 0:
            continue
        occ = occlude_one_wall(clean, LOOKAHEAD_FAR_Y, rng)
        nav_c = center_midpoint(clean, LOOKAHEAD_FAR_Y)
        nav_w = center_weighted(occ, LOOKAHEAD_FAR_Y)
        if nav_c.get('center_x') is None or nav_w.get('center_x') is None:
            continue
        devs.append(abs(nav_w['center_x'] - nav_c['center_x']))
    assert len(devs) >= 5, 'usable images too few: %d' % len(devs)
    print('real masks: weighted-vs-clean mean |dx| = %.1f px over %d imgs'
          % (float(np.mean(devs)), len(devs)))
    assert np.mean(devs) < 10   # 1.5 cm at 1.5 mm/px


def test_synthetic_dense_occlusion_improvement():
    """Dense weed-blob on one wall: row-wise trimmed fit must beat raw LSQ."""
    rng = np.random.default_rng(7)
    errs_m, errs_w = [], []
    for _ in range(10):
        left = np.zeros((720, 960), np.uint8)
        right = np.zeros((720, 960), np.uint8)
        ys = np.arange(200, 700)
        a_l = rng.uniform(0.05, 0.15) * rng.choice([-1, 1])
        a_r = rng.uniform(0.05, 0.15) * rng.choice([-1, 1])
        xl = 300 + (ys - 200) * a_l + rng.normal(0, 2, len(ys))
        xr = 660 + (ys - 200) * a_r + rng.normal(0, 2, len(ys))
        left[ys, np.clip(xl.astype(int), 0, 959)] = 1
        right[ys, np.clip(xr.astype(int), 0, 959)] = 1
        y0 = int(rng.integers(560, 660))
        x0 = int(np.interp(650, ys, xr)) - 30
        right[y0:y0 + 30, max(0, x0):max(0, x0) + 60] = 1
        true_c = (np.interp(620, ys, xl) + np.interp(620, ys, xr)) / 2
        rm = fit_centerline_lsq(left, right, 620)
        rw = fit_centerline_lsq_weighted(left, right, 620)
        errs_m.append(abs(rm['center_x'] - true_c))
        errs_w.append(abs(rw['center_x'] - true_c))
    em, ew = float(np.mean(errs_m)), float(np.mean(errs_w))
    print('synthetic dense occlusion (10 trials): midpoint %.1f px, '
          'weighted %.1f px' % (em, ew))
    assert ew < em, 'weighted must beat plain midpoint under dense occlusion'
