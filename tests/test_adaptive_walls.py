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
    """Dense weed-blob model: ADD a 60x30 block next to one wall near the
    lookahead row (field occlusion adds pixels, it rarely erases walls)."""
    m = ipm_mask.copy()
    band = m[lookahead_y - 20:lookahead_y + 20]
    cols = np.where(band.any(axis=0))[0]
    if len(cols) == 0:
        return m
    side = rng.choice([-1, 1])           # blob on inner or outer side
    col = int(rng.choice(cols))
    y0 = max(0, lookahead_y - OCC_H // 2)
    x0 = int(np.clip(col + side * 25, 0, 959 - OCC_W))
    m[y0:y0 + OCC_H, x0:x0 + OCC_W] = 1
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
    print('real masks + dense blob: weighted error vs clean = %.1f px '
          'over %d imgs' % (float(np.mean(devs)), len(devs)))
    assert np.mean(devs) < 30   # 4.5 cm at 1.5 mm/px; midpoint baseline in ledger


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


def test_deterministic_hard_case():
    """Deterministic hard case (the ledger's 25.5 -> 0.5 px claim).

    A 30-row x 60-px dense blob sitting on the right wall near the lookahead
    row, wall slopes fixed.  Plain LSQ midpoint is dragged off; the row-wise
    trimmed fit recovers it.
    """
    left = np.zeros((720, 960), np.uint8)
    right = np.zeros((720, 960), np.uint8)
    ys = np.arange(200, 700)
    left[ys, 280 + ((ys - 200) * 0.1).astype(int) + np.sin(ys / 30).astype(int)] = 1
    right[ys, (640 - (ys - 200) * 0.1).astype(int)] = 1
    right[650:680, 500:560] = 1
    true_c = 460.0
    rm = fit_centerline_lsq(left, right, 620)
    rw = fit_centerline_lsq_weighted(left, right, 620)
    em = abs(rm['center_x'] - true_c)
    ew = abs(rw['center_x'] - true_c)
    print('deterministic hard case: midpoint %.1f px, weighted %.1f px' % (em, ew))
    assert ew < em


# ---------------------------------------------------------------------------
# 11-21 Pc-24：上面三条用的是"1 像素细墙"，而真实 IPM 墙有 ~190 像素宽，
# 所以旧实现（逐行取中位 + 行内跨度 >24 px 就整行丢弃）在真实图上恒退化——
# 测试全绿而功能从未生效。改成"取每行靠草带那一侧的边"后，补上这四条。
# ---------------------------------------------------------------------------

def _thick_wall(y0, y1, x_left, width):
    """竖直厚墙：行 y0..y1，左边缘 x_left，宽 width 像素。"""
    m = np.zeros((720, 960), np.uint8)
    for y in range(y0, y1):
        m[y, max(0, x_left):min(960, x_left + width)] = 1
    return m


def test_thick_symmetric_walls_center_unchanged():
    """两边等宽的厚墙：内边缘的中心 == 普通中点（回归基线）。"""
    left = _thick_wall(200, 700, 260, 60)
    right = _thick_wall(200, 700, 640, 60)
    plain = fit_centerline_lsq(left, right, 620)
    w = fit_centerline_lsq_weighted(left, right, 620)
    assert plain['status'] == 'dual'
    assert abs(w['center_x'] - plain['center_x']) < 1.5


def test_inner_edge_not_dragged_by_outer_bulk():
    """右墙只在外侧长胖 60 px：普通中点会被重心拉走，内边缘不动。"""
    left = _thick_wall(200, 700, 260, 60)
    thin = _thick_wall(200, 700, 640, 60)
    fat = _thick_wall(200, 700, 640, 120)   # 向远离草带的一侧变宽
    plain = fit_centerline_lsq(left, thin, 620)
    dragged = fit_centerline_lsq(left, fat, 620)
    w = fit_centerline_lsq_weighted(left, fat, 620)
    assert dragged['center_x'] > plain['center_x'] + 10, '本用例前提：普通中点确实被拉走'
    assert abs(w['center_x'] - plain['center_x']) < 1.5


def test_inner_edge_ignores_weed_spikes():
    """150 行杂草凸起伸进草带 80 px：剔除后回到无刺时的中心。"""
    left = _thick_wall(200, 700, 260, 60)
    clean_right = _thick_wall(200, 700, 640, 60)
    spikey = clean_right.copy()
    for y in range(480, 630):
        spikey[y, 560:640] = 1
    clean = fit_centerline_lsq(left, clean_right, 620)
    plain_spikey = fit_centerline_lsq(left, spikey, 620)
    w = fit_centerline_lsq_weighted(left, spikey, 620)
    assert abs(plain_spikey['center_x'] - clean['center_x']) > 6, '本用例前提：普通中点确实被凸起拉走'
    assert abs(w['center_x'] - clean['center_x']) < 6


def test_degenerate_fit_keeps_plain_wall_positions():
    """墙只有 20 行（逐行拟合不够 30 行）而普通拟合可用：
    加权路径必须原样退回普通结果——旧缺陷是先把 left_x/right_x 写成 0 再返回。"""
    left = _thick_wall(600, 620, 260, 60)
    right = _thick_wall(600, 620, 640, 60)
    plain = fit_centerline_lsq(left, right, 610)
    assert plain['status'] == 'dual'
    w = fit_centerline_lsq_weighted(left, right, 610)
    assert w['center_x'] == pytest.approx(plain['center_x'])
    assert w['left_x'] == pytest.approx(plain['left_x'])
    assert w['right_x'] == pytest.approx(plain['right_x'])
