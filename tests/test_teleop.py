# -*- coding: utf-8 -*-
"""手操档（TELEOP）的行为钉住——spec `docs/superpowers/specs/2026-10-13-pc-manual-channel-design.md`。

这批测试钉的是四件**别的测试钉不住**的事：
  1. 手操的进档门槛比无人少一道（不查视觉信心）——少错这道就变成"台架上永远进不去"；
  2. 手操期间**视觉瞎了不许抽走方向盘**（锁零速度是给无人用的，不是给人用的）；
  3. 0.1 m/s 与"第一阶段负值钳成 0"这两条钳位必须在发帧层，不靠调用方自觉；
  4. 手操绑门 N：permit 配成门 F 也不许落刀、不许横移。
"""
import os
import re
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


# ---- 按键有效期跟着节拍走（10-28 台架暴露：慢节拍把 W 静默吃掉） ------------

def test_hold_window_tracks_the_beat_and_stays_capped():
    """窗口 = min(max(0.1, 2×拍间隔), 0.6)：地板保原行为，天花板是安全量。"""
    assert wire.teleop_hold_window(0.045) == wire.TELEOP_HOLD_S == 0.1   # 10-21 那种快节拍
    assert wire.teleop_hold_window(0.20) == 0.40
    assert wire.teleop_hold_window(0.391) == 0.60                          # 10-28 实测值 → 撞顶
    assert wire.teleop_hold_window(3.0) == wire.TELEOP_HOLD_CAP_S == 0.6   # 不许为"能动"抬顶
    # 地板不是摆设：快节拍若也跟着 2× 缩，松手归零会提前到几十毫秒，那不是标定值
    assert wire.teleop_hold_window(0.001) == wire.TELEOP_HOLD_S
    for bad in (None, 0.0, -1.0):
        assert wire.teleop_hold_window(bad) == wire.TELEOP_HOLD_S, bad      # 缺数不放大窗口


def test_slow_beat_no_longer_silences_a_held_key():
    """这一条就是 10-28 那个症状本身：拍间隔 0.391 s 时按住 W 必须还能出速度。

    两边都钉：窗口按节拍放宽 ⇒ 非零；仍按老的固定 0.1 判 ⇒ 归零。
    后一半是防"把窗口干脆取消"——归零机制必须还在，否则丢事件时车会一直走。
    """
    beat = 0.391
    win = wire.teleop_hold_window(beat)
    assert wire.teleop_speeds('w', beat, win) == (wire.TELEOP_MAX_MPS, wire.TELEOP_MAX_MPS)
    assert wire.teleop_speeds('w', beat) == (0.0, 0.0), '固定窗口那一档必须仍然归零'
    assert wire.teleop_speeds('w', win + 0.05) == (0.0, 0.0), '超出放宽后的窗口仍要归零'


def test_main_loop_asks_for_the_beat_tracking_window():
    """缺陷现场在主循环：它原来传两参（固定 0.1）。这里钉它确实传了窗口。

    只读源码文本，不跑 GUI——单测起不了 cv2 按键那条路，能钉的是"调用点了窗口"。
    """
    import io
    src = io.open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               'pc', 'main.py'), encoding='utf-8').read()
    assert src.count('wire.teleop_speeds(') == 1, '主循环只该有一处手操取值'
    i = src.find('wire.teleop_speeds(')
    call = src[i:i + 200]
    assert 'teleop_hold_window(beat_gap)' in call, call
    assert 'tele_key_t' in call, call


# ---- 5. 两层限速值不许各说一套（10-13 晚 0.1 -> 0.2 这次改判时补） ----------

FIRMWARE_RETROFIT_H = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'firmware', '大车proj', '大车', 'HARDWARE', 'retrofit', 'retrofit.h')


def test_teleop_cap_matches_the_firmware_constant():
    """PC 的 `TELEOP_MAX_MPS` 与固件的 `RETRO_TELEOP_MAX` 必须是同一个数。

    这条钉的不是数值本身，是**只改一层**那个错法。手操限速在两侧各写一份，固件那一份
    是编译期钳位（`retrofit_on_nav_frame` 里 `cmd_v* > RETRO_TELEOP_MAX` 就压回去），
    所以"改了 PC、忘了固件"的症状最阴：CSV 的 `vL`/`vR` 会老老实实写着 0.200（那是
    PC 自己算的给定值），车上却还是 0.1 —— 读数看起来"改生效了"，实际没改。
    10-13 晚这次 0.1 -> 0.2 就是两层同改，本测试当场先红（PC=0.2 / 固件=0.1）再绿。
    """
    with open(FIRMWARE_RETROFIT_H, 'rb') as f:      # 字节级读：firmware/ 下不按文本编码假设
        text = f.read().decode('latin-1')           # 只找 ASCII 的 #define，中文注释不参与
    hits = re.findall(r'#\s*define\s+RETRO_TELEOP_MAX\s+([0-9]*\.?[0-9]+)f?', text)
    assert len(hits) == 1, '固件里 RETRO_TELEOP_MAX 应当只有一份定义，实测 %r' % (hits,)
    assert abs(float(hits[0]) - wire.TELEOP_MAX_MPS) < 1e-9, (
        '限速两层不一致：PC=%.3f 固件=%.3f —— 只改一层等于没改'
        % (wire.TELEOP_MAX_MPS, float(hits[0])))
