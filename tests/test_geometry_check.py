# -*- coding: utf-8 -*-
"""geometry_check 的回归测试。

重点不是"输出好看"，而是**把 09-21 被推翻的那条推论钉死在原地**：
跨 N 个行距 ≠ 压 N−1 行作物。反例进测试，防止将来又被"顺手推一步"。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from tools.geometry_check import (required_outer_span, band_capacity, track_span,
                                  slide_reach_verdict, knife_lift_rate, lift_time_s,
                                  ACTUATOR_SPEED_CM_S)


def test_three_band_envelope_needs_95cm_not_60cm():
    """ch02:14 的 ≤60 cm 与"3 条带"在包络上矛盾——这条依然成立（它只讲包络）。"""
    for s in (30.0, 35.0, 40.0):
        assert required_outer_span(s, 25.0, bands=3) > 60.0


def test_band_capacity_on_the_real_machine():
    assert band_capacity(215.0, 35.0, 25.0) == 6
    assert band_capacity(60.0, 35.0, 25.0) == 2


# ---- 撤回的推论：跨行距数不等于压苗数 -----------------------------------
def test_track_span_reports_facts_and_never_concludes_crushing():
    """复审反例：行距 38.2、轮距 191 = 5×38.2 → 轮心可正好落在两行中间。"""
    t = track_span(191.0, 38.2)
    assert t['pitches'] == pytest.approx(5.0, abs=0.01)
    assert t['residual_off_cm'] == pytest.approx(0.0, abs=0.5)
    assert t['furrow_aligned_possible'] is True
    # 关键：这个函数不再返回任何"压在作物行上"的断言
    assert set(t.keys()) == {'pitches', 'furrow_aligned_possible', 'residual_off_cm'}


def test_non_integer_alignment_is_flagged_not_resolved():
    t = track_span(191.0, 35.0)
    assert t['pitches'] == pytest.approx(5.46, abs=0.01)
    assert t['furrow_aligned_possible'] is False     # 整数对齐也差 ~16 cm，得实测轮迹


# ---- 单位错误：总行程 vs 单侧需求 ---------------------------------------
def test_slide_verdict_doubles_the_one_sided_need():
    """旧实现拿总行程 30 去比单侧 22.5 判"够"；居中滑台 30 总行程只有每侧 15。"""
    v = slide_reach_verdict(residual_cm=12.5, envelope_cm=10.0, slide_travel_cm=30.0)
    assert v['need_one_side_cm'] == pytest.approx(22.5)
    assert v['need_total_cm'] == pytest.approx(45.0)
    assert v['ok'] is False                          # 30 < 45，旧代码在这里判成"够"
    assert slide_reach_verdict(12.5, 10.0, 46.0)['ok'] is True


def test_knife_lift_rate_refuses_to_guess_the_ratio():
    assert knife_lift_rate(ACTUATOR_SPEED_CM_S, 0, 20) is None
    assert knife_lift_rate(ACTUATOR_SPEED_CM_S, 20, 20) == pytest.approx(1.0)
    assert knife_lift_rate(ACTUATOR_SPEED_CM_S, 20, 10) == pytest.approx(0.5)


def test_lift_time_scales_with_mechanism_ratio():
    assert lift_time_s(10.0, 1.0) == pytest.approx(10.0)
    assert lift_time_s(10.0, 0.5) == pytest.approx(20.0)
    assert lift_time_s(10.0, None) is None
