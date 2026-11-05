# -*- coding: utf-8 -*-
"""pc/replay.py 的显示判据（台账 Pc-21）。

钉的是 11-05 实车首跑那个崩溃的**原始症状**，不是"函数返回对不对"：
    python -B pc/main.py --live --stream-host 127.0.0.1 --out results/crab_24
    KeyError: 'undistorted'   ← pc/main.py 里 `if frame is not None: draw_overlay(res)`
根因在 Pc-17 把感知挪到后台线程之后：**帧到了 != 结果到了**。第一份结果出来之前，
`res` 还是 `NO_FRAME_RESULT`（只有 status/lateral 那几格），拿它去画 mask 就炸。
"""
import numpy as np

from pc import replay


def _frame(h=720, w=960):
    f = np.zeros((h, w, 3), 'uint8')
    f[:, :, 1] = 40
    return f


def _result(h=720, w=960):
    """真跑完一次感知才会有的那套键（draw_overlay 逐个用）。"""
    return {
        'undistorted': np.zeros((h, w, 3), 'uint8'),
        'mask': np.zeros((h, w), 'uint8'),
        'ipm_mask': np.zeros((360, 480), 'uint8'),
        'nav_far': {'center_x': 120.0},
        'nav_near': {'center_x': 300.0},
        'status': 'dual',
        'lateral_px': 12.0,
        'tool_offset_px': -3.0,
        'confidence': 0.88,
    }


def test_no_frame_result_with_live_frame_does_not_crash():
    """原症状：有帧、没结果 ⇒ 旧代码 KeyError。现在必须退回"只显示原帧"。"""
    frame = _frame()
    placeholder = {'status': 'no_frame', 'lateral_px': None, 'confidence': 0.0,
                   'tool_offset_px': None, 'nav_far': {}, 'nav_near': {}}
    out = replay.update_display(frame, placeholder, None)
    assert out.shape == frame.shape
    assert not replay.has_overlay(placeholder)
    # 原帧要原样给出（不是黑屏、也不是叠了假的结果）
    assert np.array_equal(out, frame)


def test_stale_before_any_result_shows_the_live_frame():
    """还没有任何结果时，stale 只可能出现在别的拍上；这一拍给原帧，开机别黑屏。"""
    frame = _frame()
    stale = {'status': 'stale', 'lateral_px': None, 'confidence': 0.0,
             'tool_offset_px': None, 'nav_far': {}, 'nav_near': {}}
    out = replay.update_display(frame, stale, None)
    assert np.array_equal(out, frame)


def test_stale_after_a_result_freezes_the_last_overlay():
    """作者 11-05 报的"图片在闪"：异步丢帧时 overlay 与原帧交替上屏。

    出过结果之后，占位/断流那几拍必须**冻结上一张叠加图**，不能退回原帧——
    否则每几拍闪一次，且"没叠加的画面"会被误读成感知正常。
    """
    frame = _frame()
    frame[:, :, 2] = 200                      # 原帧与上一张明显不同
    last = _frame()
    stale = {'status': 'stale', 'lateral_px': None, 'confidence': 0.0,
             'tool_offset_px': None, 'nav_far': {}, 'nav_near': {}}
    out = replay.update_display(frame, stale, last)
    assert out is last
    assert not np.array_equal(out, frame)


def test_real_result_draws_the_overlay():
    res = _result()
    out = replay.update_display(_frame(), res, None)
    assert out.shape == res['undistorted'].shape
    assert out.sum() > 0, 'overlay 应该画上 status 行与 IPM 小图'
    assert replay.has_overlay(res)


def test_no_frame_keeps_the_last_picture():
    """E2-4：无帧的那几拍不能把画面清空——操作员还要在那一拍上按 [M]/[E]。"""
    last = _frame()
    assert replay.update_display(None, None, last) is last
    assert replay.update_display(None, {'status': 'no_frame'}, last) is last


def test_main_placeholders_are_not_drawable():
    """把 main 里那两个占位常量也钉住：以后谁给它们塞画面键，这里会提醒他先想清楚。"""
    from pc import main as pm
    assert not replay.has_overlay(pm.NO_FRAME_RESULT)
    assert not replay.has_overlay(pm.STALE_RESULT)
    out = replay.update_display(_frame(), pm.NO_FRAME_RESULT, None)
    assert out.shape == _frame().shape
