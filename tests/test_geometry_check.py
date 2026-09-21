# -*- coding: utf-8 -*-
"""geometry_check 的回归测试：把"文档口径互相矛盾"这件事变成可复算的断言。"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from tools.geometry_check import (required_outer_span, candidate_configs,
                                  band_capacity, traffic_mode,
                                  slide_reach_verdict, knife_lift_rate,
                                  lift_time_s, ACTUATOR_SPEED_CM_S)


def test_three_band_span_exceeds_the_60cm_body_limit():
    """ch02:14 的 ≤60 cm 与"跨 4 行清 3 带"在 30~40 cm 行距下不可能同时成立。"""
    for s in (30.0, 35.0, 40.0):
        assert required_outer_span(s, 25.0, bands=3) > 60.0


def test_single_band_needs_body_narrower_than_row_pitch():
    assert required_outer_span(35.0, 10.0, bands=1) == pytest.approx(10.0)


def test_60cm_machine_at_35cm_pitch_reaches_two_bands_not_three():
    """文档口径下最要命的一条：60 cm 车宽最多放 2 把刀，且必须跨着作物行走。"""
    assert band_capacity(60.0, 35.0, 25.0) == 2
    assert traffic_mode(60.0, 35.0) == ('straddle_rows', 1)


def test_narrow_machine_stays_inside_one_band():
    assert traffic_mode(30.0, 35.0) == ('in_band', 0)
    assert band_capacity(30.0, 35.0, 25.0) == 1


def test_three_bands_become_reachable_only_above_95cm():
    got = {name: (need, ok) for name, need, ok, note in candidate_configs(35.0, 60.0, 25.0)}
    assert got['2 条带'][0] == pytest.approx(60.0) and got['2 条带'][1]
    assert got['3 条带'][0] == pytest.approx(95.0) and not got['3 条带'][1]
    wide = {name: ok for name, need, ok, note in candidate_configs(35.0, 100.0, 25.0)}
    assert wide['3 条带'] and not wide['4 条带']


def test_slide_travel_verdict_uses_half_pitch_plus_guard():
    v = slide_reach_verdict(35.0, 30.0, guard_band_cm=5.0)
    assert v['need_cm'] == pytest.approx(22.5) and v['ok']
    assert not slide_reach_verdict(40.0, 15.0, guard_band_cm=5.0)['ok']


def test_knife_lift_rate_refuses_to_guess_the_ratio():
    """没实测 M10 就不给刀尖速度——不能拿推杆 10 mm/s 当刀具离地速度。"""
    assert knife_lift_rate(ACTUATOR_SPEED_CM_S, 0, 20) is None
    assert knife_lift_rate(ACTUATOR_SPEED_CM_S, 20, 20) == pytest.approx(1.0)
    assert knife_lift_rate(ACTUATOR_SPEED_CM_S, 20, 10) == pytest.approx(0.5)


def test_lift_time_scales_with_mechanism_ratio():
    """同样 10 mm/s 的推杆，2:1 与 1:1 机构的离土时间差一倍。"""
    assert lift_time_s(10.0, 1.0) == pytest.approx(10.0)
    assert lift_time_s(10.0, 0.5) == pytest.approx(20.0)
    assert lift_time_s(10.0, None) is None
