# -*- coding: utf-8 -*-
"""IPM 标定加载器的测试。

最有价值的一条是 test_rejects_the_smoke_artifact：它断言仓库里那份
"看起来像标定"的冒烟输出**进不了生产链路**。那份文件的源图是全黑的。
"""
import json
import os
import sys

import cv2
import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pc.ipm_io import load_ipm_params, IpmRejected, MIN_IMAGE_STD  # noqa: E402

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _make_good(tmp_path, **over):
    """造一份**通过全部校验**的标定：真实非纯色源图 + field 来源 + 档案匹配。"""
    img = (np.random.default_rng(7).random((720, 960)) * 255).astype(np.uint8)
    src = str(tmp_path / 'field_frame.jpg')
    cv2.imwrite(src, img)
    px = np.float32([[480, 700], [100, 700], [860, 700], [480, 300]])
    gm = np.float32([[0.0, 0.5], [-0.4, 0.5], [0.4, 0.5], [0.0, 2.0]])
    H = cv2.getPerspectiveTransform(px, gm)
    d = {'H_img2ground': H.tolist(), 'scale_px_per_m': 100.0, 'reproj_mean_m': 0.004,
         'lookahead': {'far_m': 1.8, 'near_m': 0.45}, 'source_image': src,
         'points_source': 'field', 'vehicle_profile': 'REAL',
         'calib_date': '2026-09-21', 'n_points': 4}
    d.update(over)
    p = str(tmp_path / 'ipm_params.json')
    json.dump(d, open(p, 'w', encoding='utf-8'))
    return p


def test_rejects_the_smoke_artifact():
    """results/smoke_ipm 那份是全黑图上解出来的，必须被拒。"""
    p = os.path.join(WS, 'results', 'smoke_ipm', 'ipm_params.json')
    if not os.path.isfile(p):
        pytest.skip('冒烟产物不在本地')
    with pytest.raises(IpmRejected) as e:
        load_ipm_params(p, 'REAL')
    assert '来源' in str(e.value)          # 缺 source_image/points_source 等字段


def test_accepts_a_real_field_calibration(tmp_path):
    c = load_ipm_params(_make_good(tmp_path), 'REAL')
    assert c.m_per_px == pytest.approx(0.01)
    assert c.provenance['vehicle_profile'] == 'REAL'
    assert 'REAL' in c.describe()


def test_bev_grid_is_isotropic_and_origin_at_bottom_center(tmp_path):
    """旧占位用 0.0015/0.0030 各向异性；真标定下横纵向必须是同一个 m/px。"""
    c = load_ipm_params(_make_good(tmp_path), 'REAL')
    assert c.m_per_px == pytest.approx(1.0 / c.scale_px_per_m)
    x, y = c.ground_to_bev(0.0, 0.0)
    assert x == pytest.approx(480.0) and y == pytest.approx(720.0)
    # lookahead 由米换算成行号，不再是拍脑袋的像素行
    assert c.far_row_px == pytest.approx(720.0 - 1.8 * 100.0)
    assert c.near_row_px == pytest.approx(720.0 - 0.45 * 100.0)


def test_rejects_synthetic_points_source(tmp_path):
    with pytest.raises(IpmRejected) as e:
        load_ipm_params(_make_good(tmp_path, points_source='synthetic'), 'REAL')
    assert '不是标定' in str(e.value)


def test_rejects_blank_source_image(tmp_path):
    """全黑源图 = 当年那份冒烟产物的病根，加载器要能自己抓出来。"""
    black = np.zeros((720, 960), np.uint8)
    p = _make_good(tmp_path)
    d = json.load(open(p, encoding='utf-8'))
    cv2.imwrite(str(tmp_path / 'black.jpg'), black)
    d['source_image'] = str(tmp_path / 'black.jpg')
    json.dump(d, open(p, 'w', encoding='utf-8'))
    with pytest.raises(IpmRejected) as e:
        load_ipm_params(p, 'REAL')
    assert '标准差' in str(e.value)
    assert MIN_IMAGE_STD > 0


def test_rejects_bad_reprojection_and_profile_mismatch(tmp_path):
    with pytest.raises(IpmRejected):
        load_ipm_params(_make_good(tmp_path, reproj_mean_m=0.15), 'REAL')
    with pytest.raises(IpmRejected) as e:
        load_ipm_params(_make_good(tmp_path), 'PREV')     # 文件是 REAL 的，请求 PREV
    assert '跨车' in str(e.value)


def test_rejects_degenerate_homography(tmp_path):
    bad = np.zeros((3, 3)); bad[0, 0] = 1; bad[1, 1] = 1
    with pytest.raises(IpmRejected):
        load_ipm_params(_make_good(tmp_path, H_img2ground=bad.tolist()), 'REAL')


def test_px_ground_roundtrip_is_consistent(tmp_path):
    """像素→米→像素必须回到原点；且 M_img2bev 等于"先解到米再仿射到 BEV"。"""
    c = load_ipm_params(_make_good(tmp_path), 'REAL')
    px = np.float32([[480, 700], [100, 700], [860, 700], [480, 300], [300, 500]])
    gm = cv2.perspectiveTransform(px.reshape(-1, 1, 2), c.H_img2ground).reshape(-1, 2)
    back = cv2.perspectiveTransform(gm.reshape(-1, 1, 2), c.H_ground2img).reshape(-1, 2)
    assert np.allclose(back, px[:, :2], atol=1e-6)
    step = c.A_ground2bev @ np.hstack([gm, np.ones((len(gm), 1))]).T
    step = (step[:2] / step[2]).T
    composed = cv2.perspectiveTransform(px.reshape(-1, 1, 2), c.M_img2bev).reshape(-1, 2)
    assert np.allclose(composed, step, atol=1e-6)
