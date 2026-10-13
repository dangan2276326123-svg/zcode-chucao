# -*- coding: utf-8 -*-
"""手操档（TELEOP）的行为钉住——spec `docs/superpowers/specs/2026-10-13-pc-manual-channel-design.md`。

这批测试钉的是四件**别的测试钉不住**的事：
  1. 手操的进档门槛比无人少一道（不查视觉信心）——少错这道就变成"台架上永远进不去"；
  2. 手操期间**视觉瞎了不许抽走方向盘**（锁零速度是给无人用的，不是给人用的）；
  3. 0.1 m/s 与"第一阶段负值钳成 0"这两条钳位必须在发帧层，不靠调用方自觉；
  4. 手操绑门 N：permit 配成门 F 也不许落刀、不许横移。
"""
import struct

from common import protocol as P
from pc import wire
from pc.state_machine import StateMachine

TOL = 1e-9


# ---- 1. 状态机：门槛比无人少一道 ----------------------------------------

def test_teleop_entry_does_not_require_confidence():
    """进手操**不看视觉信心**：台架上没有行墙，信心永远不够，
    把无人的信心判据套到手操上等于这条档位在台架上不可达。"""
    sm = StateMachine()
    assert sm.go_teleop() is True
    assert sm.state == StateMachine.TELEOP


def test_teleop_refused_only_by_estop_latch():
    """急停是状态不是告警（与 confirm_continue 的 I-2 裁定同一口径）。"""
    sm = StateMachine()
    sm.estop('sw')
    assert sm.go_teleop() is False
    assert sm.state == StateMachine.ESTOP


def test_manual_to_teleop_to_manual_round_trip():
    sm = StateMachine()
    assert sm.go_teleop() and sm.state == StateMachine.TELEOP
    assert sm.go_manual() and sm.state == StateMachine.MANUAL


def test_vision_loss_does_not_move_teleop():
    """**手操时丢墙不该抽走方向盘**：AUTO 下失视觉降 LIFT 是对的，
    人在开车时降 LIFT（并锁零）就是把方向盘从他手里抢走。"""
    sm = StateMachine()
    sm.go_teleop()
    sm.vision_loss(no_boundary_evidence=True)
    assert sm.state == StateMachine.TELEOP
    # AUTO 的既有行为不许被这条改动带走
    sm2 = StateMachine()
    sm2.go_auto(confidence_ok=True)
    sm2.vision_loss(no_boundary_evidence=True)
    assert sm2.state == StateMachine.LIFT


def test_teleop_holds_authority():
    """持权名单里没 TELEOP 的话，PC 会在手操时发 HEARTBEAT，
    固件收心跳就把权限交回遥控——那正是 codex 新发现一的形状。"""
    sm = StateMachine()
    sm.go_teleop()
    assert sm.holds_authority is True
    assert 'TELEOP' in wire.HOLDING


# ---- 2/3/4. 发帧层：不锁零、钳位、绑门 N --------------------------------

def test_teleop_frames_are_nav_plus_tool_even_when_vision_is_blind():
    frames = dict((t, p) for t, p in
                  wire.frames_for_state('TELEOP', False, 0.05, 0.05, 0.0))
    assert P.TYPE_NAV in frames and P.TYPE_TOOL in frames
    assert P.TYPE_HEARTBEAT not in frames


def test_teleop_keeps_operator_speed_when_not_usable():
    """`usable=False` 在 AUTO 下锁零是对的，在手操下不许锁——
    这一条如果被写反，人在按着前进、墙一断车就自己停，现场会读成"板子抽风"。"""
    frames = dict((t, p) for t, p in
                  wire.frames_for_state('TELEOP', False, 0.07, 0.07, 0.0))
    vl, vr = struct.unpack('<ff', frames[P.TYPE_NAV][:8])
    assert abs(vl - 0.07) < TOL and abs(vr - 0.07) < TOL


def test_teleop_clamps_to_0p1_on_both_sides():
    frames = dict((t, p) for t, p in
                  wire.frames_for_state('TELEOP', True, 3.0, -3.0, 0.0))
    vl, vr = struct.unpack('<ff', frames[P.TYPE_NAV][:8])
    # 线上是 float32（`<ff`），0.1 进去回来是 0.10000000149…——
    # 这里比的是"钳到位没有"，不是字面相等；拿 == 比 float32 会红得莫名其妙。
    assert abs(vl - wire.TELEOP_MAX_MPS) < 1e-6
    # 第一阶段：负值钳成 0（后退要等四轮行走方向那张表填完才放开）
    assert vr == 0.0


def test_teleop_never_drops_the_knife_even_under_gate_f():
    """手操绑门 N（B3）：permit 配成门 F 也不许落刀、不许横移。"""
    frames = dict((t, p) for t, p in
                  wire.frames_for_state('TELEOP', True, 0.05, 0.05, 42.0,
                                        permit=wire.GATE_F))
    off, lift = frames[P.TYPE_TOOL][0], frames[P.TYPE_TOOL][4]
    assert lift == 0x07
    assert off == 0


def test_teleop_tools_raised_flag_is_true_even_under_gate_f():
    """状态机那一侧也要一致：手操的 `tools_raised` 恒真，与 permit 无关。"""
    sm = StateMachine(permit=wire.GATE_F)
    sm.go_teleop()
    assert sm.tools_raised is True
    assert sm.wheels_enabled is True


def test_teleop_rejects_unknown_permit_like_everyother_state():
    for bad in (0, None, '', 'gate_f'):
        try:
            wire.frames_for_state('TELEOP', True, 0.05, 0.05, 0.0, permit=bad)
        except ValueError:
            continue
        raise AssertionError('未知许可位 %r 不许静默通过' % (bad,))


def test_auto_and_lift_behaviour_is_unchanged_by_teleop():
    """回归钉：手操这条分支不许顺手改掉 AUTO/LIFT 的既有语义。"""
    frames = dict((t, p) for t, p in
                  wire.frames_for_state('AUTO', False, 0.3, 0.3, 5.0))
    assert P.TYPE_NAV in frames
    vl, vr = struct.unpack('<ff', frames[P.TYPE_NAV][:8])
    assert vl == 0.0 and vr == 0.0          # AUTO 瞎了仍锁零
    assert dict((t, p) for t, p in
                wire.frames_for_state('LIFT', True, 0.3, 0.3, 5.0))[P.TYPE_TOOL][4] == 0x07


# ---- 输入层：键位映射与松手归零 -----------------------------------------

def test_teleop_speed_keys_map_to_forward_and_differential():
    assert wire.teleop_speeds('w', 0.02) == (wire.TELEOP_MAX_MPS, wire.TELEOP_MAX_MPS)
    assert wire.teleop_speeds('s', 0.02) == (0.0, wire.TELEOP_MAX_MPS)   # 左转
    assert wire.teleop_speeds('d', 0.02) == (wire.TELEOP_MAX_MPS, 0.0)   # 右转


def test_teleop_releases_to_zero_after_the_hold_window():
    """松手归零靠**超时**不靠"松开事件"：cv2.waitKey 的松开没有可靠事件，
    拿它当存在性判据会让车多走一段，而那一段在田间是压苗。"""
    assert wire.teleop_speeds('w', wire.TELEOP_HOLD_S + 0.05) == (0.0, 0.0)
    assert wire.teleop_speeds(None, 0.01) == (0.0, 0.0)


def test_no_backward_key_is_bound_in_phase_one():
    """第一阶段不给后退配键——按了不动比"能按"更容易被误读成坏了。"""
    assert wire.teleop_speeds('x', 0.01) == (0.0, 0.0)
