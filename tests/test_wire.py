# -*- coding: utf-8 -*-
"""E3 §5.1/§5.3：线上语义由"是否持权"决定，不由视觉决定。"""
import pytest

from common import protocol as P
from pc import wire


def _kinds(frames):
    return [f[0] for f in frames]


def test_manual_emits_only_heartbeat():
    frames = wire.frames_for_state('MANUAL', True, 0.2, 0.2, 5.0)
    assert _kinds(frames) == [P.TYPE_HEARTBEAT]


def test_auto_with_vision_emits_nav_and_tool():
    frames = wire.frames_for_state('AUTO', True, 0.14, 0.14, 3.0, wire.GATE_F)
    assert _kinds(frames) == [P.TYPE_NAV, P.TYPE_TOOL]
    # 线上 NAV 是 float32（pack_nav '<ff'），0.14 落不进精确值，故用 approx
    # ——与 tests/test_protocol.py:25 同一口径。
    assert P.unpack_nav(frames[0][1])[:2] == pytest.approx((0.14, 0.14))


def test_auto_without_vision_still_holds_authority():
    """codex 新发现一的正解：这一拍不许掉到 HEARTBEAT。"""
    frames = wire.frames_for_state('AUTO', False, 0.14, 0.14, 3.0)
    assert P.TYPE_HEARTBEAT not in _kinds(frames)
    assert _kinds(frames) == [P.TYPE_NAV, P.TYPE_TOOL]
    vl, vr, _flags = P.unpack_nav(frames[0][1])
    assert (vl, vr) == (0.0, 0.0)          # 速度锁零
    off, lift = P.unpack_tool(frames[1][1])
    assert off == 0.0 and lift == 0x07     # 提刀


def test_gate_n_forces_knives_up_and_no_lateral_even_in_auto():
    """Pc-8 的正解：门 N 下 AUTO 也只发提刀、横移恒 0。"""
    frames = wire.frames_for_state('AUTO', True, 0.14, 0.12, -8.0, wire.GATE_N)
    off, lift = P.unpack_tool(frames[1][1])
    assert off == 0.0 and lift == 0x07


def test_gate_f_allows_knives_down_only_when_auto_and_usable():
    down = wire.frames_for_state('AUTO', True, 0.1, 0.1, 2.0, wire.GATE_F)
    assert P.unpack_tool(down[1][1]) == (2.0, 0x00)
    # 同样 GATE_F，但视觉不可用 -> 仍然提刀、速度零
    up = wire.frames_for_state('AUTO', False, 0.1, 0.1, 2.0, wire.GATE_F)
    assert P.unpack_nav(up[0][1])[:2] == (0.0, 0.0)
    assert P.unpack_tool(up[1][1]) == (0.0, 0x07)


def test_lift_state_holds_authority_with_zero_speed():
    frames = wire.frames_for_state('LIFT', False, 0.0, 0.0, 0.0, wire.GATE_F)
    assert _kinds(frames) == [P.TYPE_NAV, P.TYPE_TOOL]
    assert P.unpack_tool(frames[1][1]) == (0.0, 0x07)


def test_estop_emits_nothing_every_beat():
    """ESTOP 帧只在状态跳变那一拍由 main.py 发一次，稳态不发帧。"""
    assert wire.frames_for_state('ESTOP', True, 0.0, 0.0, 0.0) == []


def test_run_log_columns_cover_the_e3_fields():
    for col in ('profile', 'mcu_mode', 'authority', 'reject',
                'loop_alive', 'build_id', 'permit'):
        assert col in wire.RUN_LOG_COLUMNS


def test_run_log_row_matches_column_count():
    st = {'seq': 3, 'speed_mps': 0.0, 'current_a': 0.0, 'battery_v': 48.0,
          'limits': 0, 'mode': 1, 'profile': 2, 'authority': 1,
          'loop_alive': 9, 'build_id': 0x3A, 'reject': 0, 'v': 2}
    res = {'status': 'dual', 'confidence': 0.5, 'lateral_px': 3.0}
    row = wire.run_log_row(1.0, 7, 'AUTO', res, 0.01, 0.02, 0.1, 0.1, 0.0,
                           12.0, st, ({}, 0, None), wire.GATE_N)
    assert len(row) == len(wire.RUN_LOG_COLUMNS)


def test_run_log_row_tolerates_v1_status_and_no_status():
    res = {'status': 'none', 'confidence': 0.0, 'lateral_px': None}
    row_none = wire.run_log_row(1.0, 1, 'MANUAL', res, 0.0, 0.0, 0.0, 0.0,
                                0.0, 5.0, None, ({}, 0, None), wire.GATE_N)
    row_v1 = wire.run_log_row(1.0, 2, 'MANUAL', res, 0.0, 0.0, 0.0, 0.0,
                              0.0, 5.0, {'seq': 1, 'mode': 0, 'v': 1},
                              ({}, 0, None), wire.GATE_N)
    assert len(row_none) == len(row_v1) == len(wire.RUN_LOG_COLUMNS)
