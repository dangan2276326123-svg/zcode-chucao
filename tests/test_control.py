# -*- coding: utf-8 -*-
import csv
import os
import sys

import pytest
from pc.control import (MiddleToolPID, LatencyCompensator, DifferentialDrive,
                        LatErrorRate)
from pc.state_machine import StateMachine
from pc.status_rx import StatusReceiver
from pc import wire
from common import protocol as P
from vehicle.bridge import decide_forward, extract_one_stream, poll_serial_frames


# ---- control ---------------------------------------------------------

def test_pid_zero_error_zero_output():
    pid = MiddleToolPID()
    assert pid.update(0.0, 0.05) == pytest.approx(0.0, abs=1e-6)


def test_pid_proportional_and_limit():
    pid = MiddleToolPID(kp=1.0, ki=0, kd=0, out_limit=10)
    assert pid.update(5.0, 0.05) == pytest.approx(5.0)
    assert pid.update(100.0, 0.05) == pytest.approx(10.0)  # clamped


def test_pid_anti_windup():
    pid = MiddleToolPID(kp=0.0, ki=1.0, kd=0, out_limit=5)
    for _ in range(200):
        u = pid.update(50.0, 0.1)
    assert abs(u) <= 5.0
    # after sign flip the integrator must unwind quickly (not stuck at sat)
    for _ in range(200):
        u = pid.update(-50.0, 0.1)
    assert u < 0


def test_pid_step_settles_within_300ms():
    pid = MiddleToolPID(kp=1.5, ki=0.05, kd=0.02)  # kd kept small: actuator lag + raw D on error oscillates (see bench tuning note)
    err = 20.0
    pending = 0.0
    for _ in range(60):  # 60 * 5ms = 300 ms
        u = pid.update(err, 0.005)
        err -= pending * 0.05   # actuator lag: command applies one tick later
        pending = u
    assert abs(err) <= 1.0


def test_latency_compensator():
    lc = LatencyCompensator()
    for d in [0.05] * 10 + [0.09]:
        lc.report(d)
    assert lc.p50() == pytest.approx(0.05)
    assert lc.p95() == pytest.approx(0.09)
    # err + rate*delay: moving away at 0.2 m/s with 50 ms delay adds 1 cm
    assert lc.compensate(0.10, 0.2) == pytest.approx(0.11)


def test_differential_drive_clamp_and_direction():
    dd = DifferentialDrive(v_nominal=0.14, v_max=0.2)
    vl, vr = dd.wheel_speeds(0.0)
    assert (vl, vr) == (pytest.approx(0.14), pytest.approx(0.14))
    vl, vr = dd.wheel_speeds(0.05)      # err>0 = robot left of line -> steer right
    assert vl < vr
    vl, vr = dd.wheel_speeds(10.0)      # huge error saturates opposite
    assert vl == pytest.approx(-0.2) and vr == pytest.approx(0.2)


def test_wheel_speeds_kd_zero_is_p_only():
    """H4.6-A: default k_d=0 => err_rate has NO effect (backward compatible,
    no invented gain active until bench tuning)."""
    dd = DifferentialDrive()                     # k_d defaults 0.0
    assert dd.wheel_speeds(0.05, err_rate=2.0) == dd.wheel_speeds(0.05)


def test_wheel_speeds_kd_adds_derivative_differential():
    """k_d>0: lateral rate ė contributes a real differential (PD damping).
    v_max raised so the clamp doesn't mask the term."""
    dd = DifferentialDrive(v_max=1.0, k_lat=0.0, k_heading=0.0, k_d=0.5)
    vl0, vr0 = dd.wheel_speeds(0.0, err_rate=0.0)
    vl1, vr1 = dd.wheel_speeds(0.0, err_rate=0.2)              # dv += 0.5*0.2=0.1
    assert vl1 == pytest.approx(vl0 - 0.1)
    assert vr1 == pytest.approx(vr0 + 0.1)


def test_lat_rate_estimator():
    r = LatErrorRate(alpha=1.0)
    r.update(0.0, 0.05)
    assert r.update(0.01, 0.05) == pytest.approx(0.2)  # 1cm/50ms


# ---- state machine -----------------------------------------------------

def test_manual_to_auto_and_back():
    sm = StateMachine()
    assert sm.go_auto() and sm.state == 'AUTO'
    sm.go_manual()
    assert sm.state == 'MANUAL'


def test_estop_latch():
    sm = StateMachine()
    sm.go_auto()
    sm.estop()
    assert sm.state == 'ESTOP'
    # nothing below may clear it
    assert not sm.go_auto()
    assert not sm.go_manual()
    assert sm.state == 'ESTOP'
    assert sm.clear_estop()
    assert sm.state == 'MANUAL'


def test_vision_loss_lift_and_recover():
    sm = StateMachine()
    sm.go_auto()
    sm.vision_loss()
    assert sm.state == 'LIFT'
    assert sm.tools_raised and not sm.wheels_enabled
    sm.vision_ok()
    assert sm.state == 'MANUAL'  # never auto-resumes AUTO


def test_tools_raised_depends_on_permit():
    """E3 §5.3：门 N 下 AUTO 也提刀；只有门 F 的 AUTO 才允许落刀。"""
    sm = StateMachine()                       # 默认 permit = GATE_N
    assert sm.tools_raised
    sm.go_auto()
    assert sm.tools_raised                    # <- 契约变更：过去这里是 False
    sm.estop()
    assert sm.tools_raised

    sm_f = StateMachine(permit=wire.GATE_F)
    assert sm_f.tools_raised
    sm_f.go_auto()
    assert not sm_f.tools_raised              # 门 F 的 AUTO 才落刀


# ---- protocol stream extraction -----------------------------------------

def test_extract_one():
    f1 = P.pack_frame(P.TYPE_NAV, P.pack_nav(0.1, 0.1), 1)
    f2 = P.pack_frame(P.TYPE_HEARTBEAT, b'', 2)
    junk = b'\x00\x01\xa5\x00'
    chunk, rest = P.extract_one(junk + f1 + f2)
    assert chunk == f1
    assert rest == f2


def test_extract_one_incomplete():
    f1 = P.pack_frame(P.TYPE_NAV, P.pack_nav(0.1, 0.1), 1)
    chunk, rest = P.extract_one(f1[:-3])
    assert chunk is None and rest == f1[:-3]


def test_extract_one_skips_corrupt():
    f1 = bytearray(P.pack_frame(P.TYPE_NAV, P.pack_nav(0.1, 0.1), 1))
    f1[8] ^= 0xFF
    f2 = P.pack_frame(P.TYPE_HEARTBEAT, b'', 2)
    chunk, rest = P.extract_one(bytes(f1) + f2)
    assert chunk == f2 and rest == b''


# ---- serial frame reassembly ---------------------------------------------

def test_poll_serial_frames_split_boundary():
    f1 = P.pack_frame(P.TYPE_NAV, P.pack_nav(0.1, 0.1), 1)
    f2 = P.pack_frame(P.TYPE_HEARTBEAT, b'', 2)
    frames, acc = poll_serial_frames(b'', f1[:10])
    assert frames == [] and acc == f1[:10]
    frames, acc = poll_serial_frames(acc, f1[10:] + f2)
    assert frames == [f1, f2] and acc == b''


def test_poll_serial_frames_header_straddles_boundary():
    f1 = P.pack_frame(P.TYPE_NAV, P.pack_nav(0.1, 0.1), 1)
    frames, acc = poll_serial_frames(b'', b'\x00\xa5')
    assert frames == [] and acc == b'\xa5'
    frames, acc = poll_serial_frames(acc, f1[1:])
    assert frames == [f1] and acc == b''


def test_poll_serial_frames_garbage_does_not_accumulate():
    frames, acc = poll_serial_frames(b'', b'\x01\x02\x03\x04\x05')
    assert frames == [] and acc == b'\x05'
    frames, acc = poll_serial_frames(acc, b'\x06\x07')
    assert frames == [] and acc == b'\x07'


def test_poll_serial_frames_corrupt_frame_is_skipped():
    f1 = bytearray(P.pack_frame(P.TYPE_NAV, P.pack_nav(0.1, 0.1), 1))
    f1[8] ^= 0xFF
    f2 = P.pack_frame(P.TYPE_HEARTBEAT, b'', 2)
    frames, acc = poll_serial_frames(b'', bytes(f1) + f2)
    assert frames == [f2] and acc == b''


def test_poll_serial_frames_garbage_prefix_keeps_half_frame():
    """Review 2026-09-09 #6: garbage + half frame must NOT collapse to the
    last byte — the partial frame has to survive into the next read."""
    f1 = P.pack_frame(P.TYPE_NAV, P.pack_nav(0.1, 0.1), 1)
    frames, acc = poll_serial_frames(b'', b'\x11\x22\x33' + f1[:8])
    assert frames == [] and acc == f1[:8]
    frames, acc = poll_serial_frames(acc, f1[8:])
    assert frames == [f1] and acc == b''


def test_poll_serial_frames_garbage_prefix_partial_header():
    """Garbage + only the 2-byte header: a5 5a must be kept and the frame
    completed on the next read (protocol.extract_one remainder fix)."""
    f1 = P.pack_frame(P.TYPE_NAV, P.pack_nav(0.1, 0.1), 1)
    frames, acc = poll_serial_frames(b'', b'\x11\x22\xa5\x5a')
    assert frames == [] and acc == b'\xa5\x5a'
    frames, acc = poll_serial_frames(acc, f1[2:])
    assert frames == [f1] and acc == b''


# ---- bridge watchdog ------------------------------------------------------

def test_watchdog_injects_estop_after_timeout():
    now = 1000
    # 1000-600=400 ms <= 500 -> no inject
    fwd, inject, last, li = decide_forward(None, now, last_pc_ms=600, auto_on=True)
    assert fwd is None and not inject
    # 1000-400=600 ms > 500 -> inject once; last_real NOT touched (H2.5)
    fwd, inject, last, li = decide_forward(None, now, last_pc_ms=400, auto_on=True)
    assert fwd is None and inject and last == 400 and li == now


def test_watchdog_idle_when_not_auto():
    fwd, inject, last, li = decide_forward(None, 10000, last_pc_ms=100, auto_on=False)
    assert fwd is None and not inject


def test_watchdog_resets_on_pc_frame():
    fwd, inject, last, li = decide_forward(b'frame', 10000, last_pc_ms=100, auto_on=True)
    assert fwd == b'frame' and not inject and last == 10000


def test_extract_one_stream_helper():
    f1 = P.pack_frame(P.TYPE_HEARTBEAT, b'', 1)
    assert extract_one_stream(f1) == f1


# ---- P0-5 regression: bridge cold start must not arm the watchdog ----

def test_bridge_cold_start_pure_rc_no_inject():
    # last_pc=0 means "no PC ever seen": even with auto_on, never inject
    fwd, inject, last, li = decide_forward(None, 5000, last_pc_ms=0, auto_on=True)
    assert fwd is None and not inject and last == 0


def test_bridge_inject_only_after_pc_seen_then_lost():
    # PC seen 10 s ago, silent 10 s (>500 ms) -> inject exactly once
    fwd, inject, last, li = decide_forward(None, 20000, last_pc_ms=10000, auto_on=True)
    assert fwd is None and inject and last == 10000 and li == 20000


def test_bridge_seen_window_expiry_stops_injection():
    # PC seen 70 s ago (window 60 s expired) -> no injection
    fwd, inject, last, li = decide_forward(None, 100000, last_pc_ms=30000, auto_on=True)
    assert fwd is None and not inject


# ---- P0-8 regression: bridge drops non-frame garbage ----

def test_bridge_valid_frame_accepts_crc_ok():
    from vehicle.bridge import valid_frame
    f = P.pack_frame(P.TYPE_NAV, P.pack_nav(0.1, 0.1), 7)
    assert valid_frame(f) == f


def test_bridge_valid_frame_drops_garbage():
    from vehicle.bridge import valid_frame
    assert valid_frame(None) is None
    assert valid_frame(b'\xa5\x5a' + b'\x00' * 40) is None   # bad crc
    assert valid_frame(b'hello from a random LAN host' * 2) is None


# ---- review r5: exact-length + trailing-byte smuggling ----

def test_bridge_valid_frame_rejects_trailing_bytes():
    from vehicle.bridge import valid_frame
    f = P.pack_frame(P.TYPE_NAV, P.pack_nav(0.1, 0.1), 7)
    assert valid_frame(f + b'\x00') is None          # smuggled tail
    assert valid_frame(f) == f                        # exact frame ok


# ---- H2.1: vision_loss authority contract (review 2026-09-14) -------------

def test_vision_loss_in_manual_stays_manual():
    """MANUAL is RC control: vision loss must NOT route to LIFT (whose wire
    form NAV(0,0) makes the MCU enter AUTO = silent loss of RC authority)."""
    sm = StateMachine()
    sm.vision_loss()
    assert sm.state == 'MANUAL'          # unchanged, RC keeps authority
    # (in MANUAL the PC sends HEARTBEAT only — no NAV/TOOL leaves the wire)


def test_vision_loss_in_auto_goes_lift():
    sm = StateMachine()
    sm.go_auto()
    sm.vision_loss()
    assert sm.state == 'LIFT'
    assert sm.tools_raised


def test_vision_loss_in_lift_stays_lift():
    sm = StateMachine()
    sm.go_auto()
    sm.vision_loss()
    sm.vision_loss()                     # repeated event: no change
    assert sm.state == 'LIFT'


def test_vision_loss_in_estop_stays_estop():
    sm = StateMachine()
    sm.go_auto()
    sm.estop()
    sm.vision_loss()
    assert sm.state == 'ESTOP'           # latched state is never downgraded


# ---- H2.5 (review 2026-09-14): injection must not extend the PC window ----

def test_bridge_continuous_polling_throttles_injection():
    """The old bug: inject refreshed last_pc_ms, so a polled loop kept
    re-arming its own window forever (review measured 139 injections in
    70 s with no stop).  Now: injections start after 500 ms silence, are
    rate-limited to one per 500 ms, STOP at the 60 s seen-window expiry,
    and the real-PC timestamp is never advanced by an injection."""
    last_real, last_inj = 10000, 0
    inj_times = []
    for now in range(10600, 70639, 2):          # ~60 s of polling, no PC frame
        fwd, inject, last_real, last_inj = decide_forward(
            None, now, last_real, auto_on=True, last_inject_ms=last_inj)
        if inject:
            inj_times.append(now)
    assert last_real == 10000                   # never extended by injections
    assert inj_times                            # watchdog did fire...
    assert inj_times[0] >= 10501                # ...only after 500 ms silence
    assert all(t < 70000 for t in inj_times)    # ...and STOPPED at window expiry
    gaps = [b - a for a, b in zip(inj_times, inj_times[1:])]
    assert all(g >= 500 for g in gaps)          # rate-limited


def test_bridge_real_frame_never_losing_window():
    """A real PC frame still refreshes the watchdog window (semantics kept)."""
    fwd, inject, last, li = decide_forward(None, 50000, last_pc_ms=49000,
                                           auto_on=True, last_inject_ms=49900)
    assert fwd is None and not inject           # silence 1 s < 500 ms


# ---- E3 批 1b Task 3: permit / needs_confirm / authority -------------------

def test_holds_authority_matches_wire_holding():
    sm = StateMachine()
    assert not sm.holds_authority             # MANUAL
    sm.go_auto()
    assert sm.holds_authority
    sm.vision_loss()
    assert sm.holds_authority                 # LIFT 仍持权
    assert sm.state == 'LIFT'
    sm.go_manual()
    assert not sm.holds_authority


def test_vision_loss_sets_needs_confirm_and_vision_ok_does_not_clear_it():
    """L2.5：无墙且无独立边界依据 -> 停车 + 必须人工确认，视觉回来也不自动放行。"""
    sm = StateMachine()
    sm.go_auto()
    sm.vision_loss()                          # 默认 no_boundary_evidence=True
    assert sm.needs_confirm
    sm.vision_ok()
    assert sm.state == 'MANUAL'
    assert sm.needs_confirm                   # 标志不被视觉恢复清掉
    assert not sm.go_auto()                   # 未确认前不许再进无人
    assert sm.confirm_continue()
    assert not sm.needs_confirm
    assert sm.go_auto() and sm.state == 'AUTO'


def test_vision_loss_with_boundary_evidence_does_not_need_confirm():
    sm = StateMachine()
    sm.go_auto()
    sm.vision_loss(no_boundary_evidence=False)
    assert sm.state == 'LIFT' and not sm.needs_confirm
    sm.vision_ok()
    assert sm.go_auto()                       # 有边界依据时允许直接恢复


def test_manual_vision_loss_still_does_not_change_state():
    """H2.1 旧契约保留：MANUAL 下失视觉不改状态（否则 NAV(0,0) 会被当成进 AUTO）。"""
    sm = StateMachine()
    sm.vision_loss()
    assert sm.state == 'MANUAL'


def test_state_machine_names_are_all_known_to_wire():
    """集合钉桩（Task 2 审查发现的同一失效类）：wire.frames_for_state() 对**未知
    状态名**一律回 HEARTBEAT，也就是静默把权限交回遥控。状态机每加一个新模式
    （批 2 的 TELEOP 等）都必须先在 wire 侧登记它是否持权，否则这条红。
    只钉集合关系，不改 wire 的行为。

    两条都要：第一条钉"当前四态"，第二条从类上枚举**全部**大写字符串常量——
    只写第一条的话，新增 TELEOP 不会让它变红（它只看那四个名字）。"""
    names = {StateMachine.MANUAL, StateMachine.AUTO,
             StateMachine.LIFT, StateMachine.ESTOP}
    known = set(wire.HOLDING) | {'MANUAL', 'ESTOP'}
    assert names <= known, ('wire.frames_for_state() would silently send '
                            'HEARTBEAT for %s' % sorted(names - known))

    declared = {v for k, v in vars(StateMachine).items()
                if not k.startswith('_') and k.isupper() and isinstance(v, str)}
    assert declared <= known, ('new state machine mode not classified as '
                               'holding/non-holding in wire.HOLDING: %s'
                               % sorted(declared - known))


# ---- E3 批 1b Task 3 fix round 1（任务审查 I-1 / I-2）--------------------

def test_tools_raised_is_fail_closed_for_unknown_permit():
    """I-1：未知许可位不得被当成"允许落刀"。

    brief 的字面表达式 `permit == GATE_N` 对配错的值（0 / None / 直接传 yaml
    字符串 'gate_f' 而没经 wire.PERMIT_BY_NAME 映射）返回 tools_raised=False，
    也就是 fail-open——而 tools_raised 从 Task 4/5 起就是 HUD/联锁的"刀已提"读数源。
    收口理由不是改契约：`docs/superpowers/plans/2026-10-08-e3-batch-1a-firmware.md:18`
    写着"任何拿不到的量都不得当作满足"（那条是给**固件**写的，批 1b 计划的
    Global Constraints 里没有它；PC 侧照搬是 E3 批 1b 的任务内决定），
    且这与 pc/wire.py 里"未知许可位一律 ValueError"（Task 2 审查
    Important #1 已就地收口）是同一个洞的两半。合法值行为一条都不变。
    """
    for bad in (0, None, 'gate_f', ''):
        sm = StateMachine(permit=bad)
        assert sm.go_auto(), 'permit validation is not go_auto\'s job'
        assert sm.tools_raised, ('unknown permit %r must NOT read as '
                                 '"tools may be lowered"' % bad)

    # 合法值不受影响：门 N 的 AUTO 也提刀，门 F 的 AUTO 才允许落刀。
    sm_n = StateMachine(permit=wire.GATE_N)
    sm_n.go_auto()
    assert sm_n.tools_raised
    sm_f = StateMachine(permit=wire.GATE_F)
    sm_f.go_auto()
    assert not sm_f.tools_raised


def test_estop_does_not_consume_the_confirm_gate():
    """I-2：急停不是"确认告警"，不得把 L2.5 的人工闸门消费掉。

    真实可达序列：进无人 -> 失视觉（needs_confirm 置位、LIFT）-> 急停
    -> 操作员把确认键当"告警消除"按下 -> 复归 -> 再进无人。旧实现里
    confirm_continue() 在 ESTOP 态照样返回 True 并清标志，于是"无墙且无独立
    边界依据必须人工确认"这道闸门在急停里被白白用掉；ESTOP 与 L2.5 是两个
    不同问题，复归后必须重新确认一次。
    """
    sm = StateMachine()
    sm.go_auto()
    sm.vision_loss()                          # 默认无独立边界依据
    assert sm.needs_confirm and sm.state == 'LIFT'

    sm.estop()
    assert sm.state == 'ESTOP'
    assert not sm.confirm_continue()          # ESTOP 下确认键无效
    assert sm.needs_confirm                   # 闸门必须还在
    assert sm.clear_estop() and sm.state == 'MANUAL'
    assert not sm.go_auto()                   # 复归后仍不许无确认进无人
    assert sm.confirm_continue()              # 此时才真正确认
    assert sm.go_auto() and sm.state == 'AUTO'


# ---- E3 批 1b Task 6：pc/main.py 的接线（状态优先 / 档案 / E3 列 / 按键语义）----
#
# 这个 harness 在内存里空跑 pc.main.main()，只换掉四类东西，被验的仍是 main 自己：
#   感知     —— 不加载权重，按拍返回预先写好的结果（可用/不可用由测试决定）；
#   档案     —— 把 permit / profile_id 换成本次要验的那一档；
#   socket   —— 不占端口、不发真包，把**发出去的帧**按 (拍, 类型, 载荷) 记下来；
#              状态口按顺序回放 STATUS v2 报文，所以 run_log 的那五个 E3 列是
#              **真的 StatusReceiver** 解出来的，不是替身喂的常数；
#   cv2      —— GUI 路径才需要：waitKey 按剧本给键，putText 的字符串就是 HUD 证据。
# 为什么值得搭这个 harness：单测里 wire/state_machine 各自成立，不等于控制循环里
# 成立（codex 新发现一的原始症状就在 main 的分支编排里），而回放冒烟走不到按键与
# HUD 那一半代码。

_USABLE = {'status': 'dual', 'lateral_px': 0.0, 'confidence': 0.9,
           'tool_offset_px': 12.0, 'nav_far': {}, 'nav_near': {}}
_BLIND = {'status': 'no_frame', 'lateral_px': None, 'confidence': 0.0,
          'tool_offset_px': None, 'nav_far': {}, 'nav_near': {}}
# 单侧墙（spec §5.2 的 L1）：usable 的门槛（>0.01）过得了，进无人的门槛（>0.05）
# 过不了——两条用例分别用它的高/低置信度版本。
_LEFT = {'status': 'left_only', 'lateral_px': 0.0, 'confidence': 0.9,
         'tool_offset_px': 0.0, 'nav_far': {}, 'nav_near': {}}
_LEFT_LOW = {'status': 'left_only', 'lateral_px': 0.0, 'confidence': 0.03,
             'tool_offset_px': 0.0, 'nav_far': {}, 'nav_near': {}}

# STATUS v2 报文里的 MCU 回显值：profile=2 与下面 PC 侧的 profile_id=1 **故意不同**，
# 这样 CSV 的 profile 列（来自 MCU）与 permit 列（来自 PC 档案）不会互相冒充。
_MCU_STATUS = dict(speed=0.0, current=0.0, battery_v=48.0, limits=0, mode=1,
                   profile=2, authority=1, loop_alive=7, build_id=0x3A,
                   reject=P.REJECT_PERMIT)

# HUD 每行的字符预算。**这里写死数字**是故意的：它是测试自己的牙，不能跟着
# pc/main.py 里的常量一起漂（那样把预算调大就同时把断言调松了）。推导与测量
# （画布宽 960 px、字号 0.7、笔画 2、平均 11.19 px/字符）在 pc/main.py 的
# HUD_MAX_CHARS 注释里；两边一致性由 test_hud_lines_are_short_and_ascii 钉。
_HUD_MAX_CHARS = 85


class _FakeCv2:
    """只够 main 的 GUI 分支用：记录 HUD 文本、按剧本给键。

    I-4（fix round 1）之后 HUD 是**多行**的，所以这里按拍收集：putText 攒着，
    imshow 落一格——`hud[拍]` 就是那一拍画的所有行（坐标另存在 hud_orgs，
    都画在同一个 y 上等于叠在一起，仍然看不见）。
    """

    FONT_HERSHEY_SIMPLEX = 0

    def __init__(self, keys, hud, orgs):
        self._keys = list(keys)
        self._beat = 0
        self.hud = hud
        self.orgs = orgs
        self._cur = []

    def putText(self, img, text, org, fontface, fscale, color, thickness):
        self._cur.append((org, fscale, text))

    def imshow(self, name, img):
        self.hud.append([t for _o, _s, t in self._cur])
        self.orgs.append([o for o, _s, _t in self._cur])
        self._cur = []

    def waitKey(self, delay):
        k = self._keys[self._beat] if self._beat < len(self._keys) else -1
        self._beat += 1
        return k


def _hud_text(r, beat):
    """某一拍所有 HUD 行拼成一条（给"这串字在 HUD 上出现过"这类断言用）。"""
    return ' | '.join(r['hud'][beat])


def _data_frames(sent, profile_id=1):
    """去掉上电握手的 MODE(0x20)：握手由 I-5 的用例单独钉，别的用例只关心
    "这一拍往线上发的控制帧是什么"，别让握手把帧序断言搅浑。"""
    out = []
    for beat, ftype, payload, addr in sent:
        if ftype == P.TYPE_MODE and \
                P.unpack_mode(payload) == (P.MODE_REQ_PROFILE, profile_id):
            continue
        out.append((beat, ftype, payload, addr))
    return out


class _RebootingStatusReceiver(StatusReceiver):
    """第 3 个有效帧之后把 `resynced` 翻成 1 = "检测到 MCU 重启"。
    main 只承诺"rx.resynced 变了就重发握手"，所以这里翻计数器，不伪造序号回退。"""

    def handle(self, raw, now=None):
        out = StatusReceiver.handle(self, raw, now)
        if self.good >= 3:
            self.resynced = 1
        return out


def _drive_main(tmp_path, monkeypatch, results, states=None, keys=(), n_status=None,
                permit=wire.GATE_N, profile_id=1, gui=False,
                vision_loss_beat=None, status_factory=None):
    """跑 n=len(results) 拍，返回 {'sent','header','rows','sm','hud','permits','holder'}。"""
    import numpy as np
    import pc.main as M

    holder = {'beat': 0, 'cur': 0, 'sm': None, 'permits': [], 'loaded': False,
              'gates': [], 'resets': 0, 'updates': 0, 'perception_built': False}
    script = list(states) if states else []
    results = list(results)

    class _CountingPID(MiddleToolPID):
        """工具 PID 的调用计数：main 什么时候清积分、什么时候算刀位，是可观测的。"""

        def reset(self):
            holder['resets'] += 1
            MiddleToolPID.reset(self)

        def update(self, err_mm, dt):
            holder['updates'] += 1
            return MiddleToolPID.update(self, err_mm, dt)

    class _FakePerception:
        def process(self, frame):
            b = holder['beat']
            holder['beat'] = b + 1
            if script:
                holder['sm'].state = script.pop(0)   # 拍首写状态，跳变仍由 main 自己发现
            if vision_loss_beat is not None and b == vision_loss_beat:
                holder['sm'].vision_loss()           # = main 满 VISION_LOSS_S 后自己会做的调用
            # 每拍开头取一次样：拍 N 的取样点在拍 N-1 的按键处理**之后**，
            # 所以"上一拍的误按有没有消费闸门"这件事在这里是可见的。
            holder['gates'].append((b, holder['sm'].state, holder['sm'].needs_confirm))
            return dict(results[b])

    def _perception_factory(*a, **k):
        holder['perception_built'] = True
        return _FakePerception()

    class _FakeFeed:
        def snapshot(self):
            return ({'recv_timeouts': 2, 'link_drops': 1}, 42, 0.05)

        def close(self):
            pass

    class _FakeSource:
        def __init__(self, *a, **k):
            self.feed = _FakeFeed()

        def frames(self):
            for i in range(len(results)):
                # 拍号在循环体执行**之前**就确定：握手帧、ESTOP 跳变帧这些都发生在
                # process() 之前，用 holder['beat']-1 会把它们标到上一拍去。
                holder['cur'] = i
                yield i + 1               # 非 None：这一拍有帧，走 per.process()

    # 没有默认值：main 必须**显式**把档案里的 permit 传进状态机。退回无参
    # `StateMachine()` 会让"permit 来自档案"这条断言失去意义（fix round 1 Minor）。
    def _sm_factory(permit):
        holder['permits'].append(permit)
        holder['sm'] = StateMachine(permit=permit)
        return holder['sm']

    def _profile_loader(path=None):
        holder['loaded'] = True
        return {'profile_id': profile_id, 'permit': permit,
                'path': 'X:/fake/vehicle_profile.yaml'}

    sent = []
    n_status = len(results) if n_status is None else n_status
    queue = [P.pack_frame(P.TYPE_STATUS, P.pack_status_v2(
        _MCU_STATUS['speed'], _MCU_STATUS['current'], _MCU_STATUS['battery_v'],
        _MCU_STATUS['limits'], _MCU_STATUS['mode'], _MCU_STATUS['profile'],
        _MCU_STATUS['authority'], _MCU_STATUS['loop_alive'],
        _MCU_STATUS['build_id'], _MCU_STATUS['reject']), seq=1 + i)
        for i in range(n_status)]
    served = set()          # 每拍最多交付一帧，否则 drain_status 会在第 0 拍清空队列

    class _Socket:
        def __init__(self, kind):
            self.kind = kind

        def bind(self, addr):
            assert self.kind == 'status', addr

        def setblocking(self, flag):
            assert self.kind == 'status', flag

        def sendto(self, data, addr):
            assert self.kind == 'ctrl', 'the status socket must never send'
            ftype, _seq, payload = P.unpack_frame(data)
            sent.append((holder['cur'], ftype, payload, addr))

        def recvfrom(self, _maxlen):
            beat = holder['cur']            # drain 发生在 process() 之前 = 当前拍号
            if queue and beat not in served:
                served.add(beat)
                return queue.pop(0), ('127.0.0.1', 9100)
            raise BlockingIOError

        def close(self):
            pass

    class _SocketModule:
        AF_INET = 2
        SOCK_DGRAM = 2

        def __init__(self):
            self.made = []

        def socket(self, *a, **k):
            kind = 'ctrl' if not self.made else 'status'
            self.made.append(kind)
            return _Socket(kind)

    hud = []
    hud_orgs = []
    monkeypatch.setattr('pc.perception.Perception', _perception_factory)
    monkeypatch.setattr('pc.vehicle_profile.load', _profile_loader)
    monkeypatch.setattr(M, 'StateMachine', _sm_factory)
    monkeypatch.setattr(M, 'MiddleToolPID', _CountingPID)
    monkeypatch.setattr(M, 'FrameSource', _FakeSource)
    monkeypatch.setattr(M, 'socket', _SocketModule())
    monkeypatch.setattr(M, 'draw_overlay', lambda res: np.zeros((8, 8, 3), 'uint8'))
    if status_factory is not None:      # I-5：模拟"检测到 MCU 重启"的接收器
        monkeypatch.setattr(M, 'StatusReceiver', status_factory)
    if gui:
        monkeypatch.setitem(sys.modules, 'cv2', _FakeCv2(keys, hud, hud_orgs))

    argv = ['pc/main.py', '--live', '--pi-ip', '127.0.0.1', '--source', 'fake',
            '--out', str(tmp_path)]
    if not gui:
        argv.append('--no-gui')
    monkeypatch.setattr(sys, 'argv', argv)

    M.main()
    with open(os.path.join(str(tmp_path), 'run_log.csv'), encoding='utf-8') as f:
        rows = list(csv.reader(f))
    return {'sent': sent, 'header': rows[0], 'rows': rows[1:], 'sm': holder['sm'],
            'permits': holder['permits'], 'hud': hud, 'hud_orgs': hud_orgs,
            'holder': holder, 'gates': holder['gates']}


def _kinds_by_beat(sent):
    out = {}
    for beat, ftype, _payload, _addr in sent:
        out.setdefault(beat, []).append(ftype)
    return out


def test_auto_request_goes_out_as_a_mode_frame_not_nav():
    """E3 §3.1：NAV 只给速度，权限只能用 MODE 帧申请。"""
    frames = wire.frames_for_state('MANUAL', True, 0.0, 0.0, 0.0)
    assert all(t != P.TYPE_NAV for t, _ in frames)      # MANUAL 不会顺带发 NAV
    req = P.pack_frame(P.TYPE_MODE, P.pack_mode(P.MODE_REQ_AUTO, 1), seq=1)
    t, _seq, payload = P.unpack_frame(req)
    assert t == P.TYPE_MODE
    assert P.unpack_mode(payload) == (P.MODE_REQ_AUTO, 1)


def test_main_frame_sequence_holds_authority_and_stays_silent_in_estop(tmp_path, monkeypatch):
    """spec §5.1 的三行，在主循环里一次跑完：AUTO+可用 / AUTO+不可用 / ESTOP 稳态。

    原始症状（codex 新发现一）：第 2 拍"这一帧不可用但未满 2 秒"在旧 main.py 里掉进
    else 分支发 HEARTBEAT，固件收心跳就把权限交回遥控，而 PC 状态与 run_log 仍写 AUTO。
    """
    r = _drive_main(tmp_path, monkeypatch,
                    results=[_USABLE, _BLIND, _USABLE, _USABLE, _USABLE],
                    states=['AUTO', 'AUTO', 'ESTOP', 'ESTOP', 'MANUAL'],
                    permit=wire.GATE_N, profile_id=1)
    kinds = _kinds_by_beat(_data_frames(r['sent']))

    assert kinds[0] == [P.TYPE_NAV, P.TYPE_TOOL]        # 持权：NAV+TOOL
    assert kinds[1] == [P.TYPE_NAV, P.TYPE_TOOL]        # 同一状态、这一拍瞎了：仍是 NAV+TOOL
    assert kinds[2] == [P.TYPE_ESTOP]                   # 跳变那一拍只发一次 ESTOP
    assert 3 not in kinds, kinds[3]                     # ESTOP 稳态：PC 在线上完全静默
    assert kinds[4] == [P.TYPE_HEARTBEAT]               # MANUAL 才交回权限
    assert [f[1] for f in _data_frames(r['sent'])].count(P.TYPE_HEARTBEAT) == 1
    assert [f[1] for f in _data_frames(r['sent'])].count(P.TYPE_ESTOP) == 1

    nav0 = [f for f in _data_frames(r['sent']) if f[0] == 0 and f[1] == P.TYPE_NAV][0]
    # 可用这一拍才真的有速度（v_nominal 0.14 走 float32，与 test_wire 同一口径）
    assert P.unpack_nav(nav0[2])[:2] == pytest.approx((0.14, 0.14))
    tool0 = [f for f in _data_frames(r['sent']) if f[0] == 0 and f[1] == P.TYPE_TOOL][0]
    off, lift = P.unpack_tool(tool0[2])
    assert (off, lift) == (0.0, 0x07)      # 门 N：AUTO 且视觉可用也不许落刀/横移

    blind_nav = [f for f in _data_frames(r['sent']) if f[0] == 1 and f[1] == P.TYPE_NAV][0]
    assert P.unpack_nav(blind_nav[2])[:2] == (0.0, 0.0)       # 瞎了 = 速度锁零
    blind_tool = [f for f in _data_frames(r['sent']) if f[0] == 1 and f[1] == P.TYPE_TOOL][0]
    assert P.unpack_tool(blind_tool[2]) == (0.0, 0x07)        # 瞎了 = 提刀
    assert r['permits'] == [wire.GATE_N]   # 状态机拿到的 permit 来自档案，不是默认值

    # 工具 PID 的积分：不驱动那一拍必须清（旧代码在 MANUAL/ESTOP 也清，
    # brief 的片段只覆盖了持权那一半）。
    assert r['holder']['updates'] == 1, '只有 AUTO 且可用的那一拍该算刀位'
    assert r['holder']['resets'] == 4, '瞎了/急停/手动三态每一拍都该清积分'


def test_main_run_log_writes_the_full_header_and_the_e3_fields(tmp_path, monkeypatch):
    """CSV 不能被接线写坏：表头 = wire.RUN_LOG_COLUMNS，每行与表头等长，
    五个 E3 列来自**真解出来**的 STATUS v2，permit 列每行都是档案里那一档。

    25 列（原 24 + `l1_events`）是控制器批准的偏差，理由见 fix round 1 的 I-6：
    spec §5.2 的降级事件必须落到时间轴上，24 是计划正文里的旧数。

    10-12 又追加了一列 `tx_frames`（T2）。这一条**不再写死列数**——列名与位置由
    `tests/test_wire.py` 的 `_PRE_TX_FRAMES_COLUMNS` 快照钉，这里只比"表头 == 现场那张列表"
    与"每行与表头等长"。（AGENTS 清单第 8 条：抄进来的数字下一批就变成待检查内容。）

    另外钉住一件事：不可用那一拍的 lat_m 必须是**空**，不是 '0.0000'——
    日志里的 0.0000 读起来像"实测正好压在行上"，那是伪造证据（旧实现就是这个
    写法，brief 的片段直接传 lat_m 会把它改成 0.0000）。
    """
    r = _drive_main(tmp_path, monkeypatch,
                    results=[_USABLE, _BLIND, _USABLE],
                    states=['AUTO', 'AUTO', 'AUTO'], permit=wire.GATE_N, profile_id=1)
    assert r['header'] == list(wire.RUN_LOG_COLUMNS)
    assert all(len(row) == len(r['header']) for row in r['rows']), \
        [len(x) for x in r['rows']]

    idx = {c: i for i, c in enumerate(r['header'])}
    assert [row[idx['permit']] for row in r['rows']] == ['1', '1', '1']
    assert [row[idx['profile']] for row in r['rows']] == ['2', '2', '2']   # MCU 回显
    assert [row[idx['authority']] for row in r['rows']] == ['1', '1', '1']
    assert [row[idx['loop_alive']] for row in r['rows']] == ['7', '7', '7']
    assert [row[idx['build_id']] for row in r['rows']] == ['58', '58', '58']
    assert [row[idx['reject']] for row in r['rows']] == ['8', '8', '8']
    assert [row[idx['mcu_mode']] for row in r['rows']] == ['1', '1', '1']
    assert [row[idx['state']] for row in r['rows']] == ['AUTO', 'AUTO', 'AUTO']
    assert [row[idx['recv_timeouts']] for row in r['rows']] == ['2', '2', '2']
    assert [row[idx['link_drops']] for row in r['rows']] == ['1', '1', '1']
    # 双墙/瞎了都不是 L1 ⇒ 计数恒 0（不是空串：这一列必须是可求和的数）
    assert [row[idx['l1_events']] for row in r['rows']] == ['0', '0', '0']
    assert r['rows'][0][idx['lat_m']] == '0.0000'
    assert r['rows'][1][idx['lat_m']] == ''                 # 瞎了这拍不写测量值
    assert r['rows'][1][idx['lat_comp_m']] == ''
    assert r['rows'][1][idx['status']] == 'no_frame'


def test_main_run_log_tx_frames_equals_what_the_socket_actually_saw(tmp_path, monkeypatch):
    """T2 的**接线**判据：`tx_frames` 那一列必须等于这一拍真的过 socket 的帧型。

    为什么单独立一条，而不是靠 `tests/test_wire.py` 里 `tx_frames_text()` 的单元测试：
    那三条只证明"函数会拼字符串"。`pc/main.py` 少写一个 `tx_frames=` 实参时，
    `run_log_row()` 用缺省 `'-'`，行长仍与表头相等、既有断言一个字都不会红；
    少写每拍的 `del tx_this_beat[:]` 时，上一拍的帧型会漂进这一拍，把 ESTOP 稳态
    写成 `MODE+NAV+TOOL`——两种都是"列在表里但说的是假话"，而这正是 §4B 的 C2／C18
    要拿它当字节级证据的前提（spec §6.1 点名的形状：工具伪装成被测机制）。

    所以判据取自 `_drive_main` 记下的 `sent`（socket 的真收发记录，带拍号），
    不去从状态推"应该发什么"。第三拍故意设成 ESTOP：那一拍线上只有跳变帧。
    """
    r = _drive_main(tmp_path, monkeypatch,
                    results=[_USABLE, _BLIND, _USABLE],
                    states=['AUTO', 'AUTO', 'ESTOP'], permit=wire.GATE_N,
                    profile_id=1)
    idx = {c: i for i, c in enumerate(r['header'])}
    col = idx['tx_frames']
    by_beat = {}
    for beat, ftype, _payload, _addr in r['sent']:
        by_beat.setdefault(beat, []).append(ftype)
    for row in r['rows']:
        fid = int(row[idx['frame_id']])
        assert row[col] == wire.tx_frames_text(by_beat.get(fid, [])), (fid, row[col])
    # 反向闸：整列都是 '-' 就说明根本没接上（上面那条比对会一起绿，看不出问题）
    assert [row[col] for row in r['rows']] != ['-', '-', '-'], \
        [row[col] for row in r['rows']]
    # 逐拍清零真的在起作用：第一拍带开机握手，后两拍不许再出现 MODE
    assert by_beat[0] and P.TYPE_MODE in by_beat[0]
    assert P.TYPE_MODE not in by_beat.get(1, [])
    assert r['rows'][1][col] == 'NAV+TOOL' and r['rows'][2][col] == 'ESTOP'


def test_main_permit_and_profile_id_come_from_the_loaded_profile(tmp_path, monkeypatch):
    """把档案换成门 F / 档案 2：主循环必须跟着变（证明它读的是档案而不是硬编码门 N）。"""
    r = _drive_main(tmp_path, monkeypatch,
                    results=[_USABLE], states=['AUTO'],
                    permit=wire.GATE_F, profile_id=2)
    assert r['permits'] == [wire.GATE_F]
    tool = [f for f in r['sent'] if f[1] == P.TYPE_TOOL][0]
    off, lift = P.unpack_tool(tool[2])
    assert lift == 0x00                        # 门 F 的 AUTO + 视觉可用才允许落刀
    assert off != 0.0                          # 横移 PID 这时才真的接进线上
    idx = {c: i for i, c in enumerate(r['header'])}
    assert r['rows'][0][idx['permit']] == '2'


def test_main_refuses_to_start_when_the_profile_cannot_be_read(tmp_path, monkeypatch):
    """spec §6：档案读不到就停下，**不许带错参数进无人**。
    停下必须发生在加载感知权重之前，也不许留下一个空 run_log。"""
    import pc.main as M
    built = []

    def _perception_factory(*a, **k):
        built.append(1)
        return object()

    def _boom(path=None):
        raise ValueError('vehicle profile missing')

    monkeypatch.setattr('pc.perception.Perception', _perception_factory)
    monkeypatch.setattr('pc.vehicle_profile.load', _boom)
    monkeypatch.setattr(sys, 'argv', ['pc/main.py', '--no-gui', '--source', 'fake',
                                      '--out', str(tmp_path)])
    with pytest.raises(ValueError):
        M.main()
    assert built == []
    assert not os.path.exists(os.path.join(str(tmp_path), 'run_log.csv'))


def test_main_keys_send_mode_frames_and_confirm_gate_needs_blind_vision(
        tmp_path, monkeypatch):
    """按键语义 + L2.5 闸门的最小收口（Task 3 审查缺口 B）。

    剧本（每拍一键；拍 N 的按键发生在该拍发帧**之后**、写 CSV 之前）：
      拍0 无键，MANUAL -> 只发 HEARTBEAT（拍首还有一发上电握手 MODE(0x20)，见 I-5 用例）
      拍1 'a' 申请无人 -> MODE(0x01)
      拍2 视觉丢失事件把状态机送进 LIFT 并置闸门；这一拍视觉**已恢复**，误按 'c'
          —— 闸门不许被消费
      拍3 视觉仍不可用时按 'c' 才生效
      拍4 'm' 交回 -> MODE(0x00)；拍5 'e' -> ESTOP 帧；拍6 'r' -> MODE(0x10)
    """
    r = _drive_main(tmp_path, monkeypatch,
                    results=[_USABLE, _USABLE, _USABLE, _BLIND, _USABLE,
                             _USABLE, _USABLE],
                    keys=[-1, ord('a'), ord('c'), ord('c'), ord('m'), ord('e'),
                          ord('r')],
                    vision_loss_beat=2, permit=wire.GATE_N, profile_id=1, gui=True)
    sm = r['sm']
    kinds = _kinds_by_beat(_data_frames(r['sent']))
    mode = {}
    for beat, ftype, payload, _addr in _data_frames(r['sent']):
        if ftype == P.TYPE_MODE:
            mode[beat] = P.unpack_mode(payload)

    assert kinds[0] == [P.TYPE_HEARTBEAT]              # 没进无人之前不发 NAV：
    #   旧代码里"进 AUTO"是靠开始发 NAV 帧隐含发生的，权限语义从没上过线。
    assert kinds[1] == [P.TYPE_HEARTBEAT, P.TYPE_MODE]
    assert mode[1] == (P.MODE_REQ_AUTO, 1)             # A = 申请无人，走 MODE 帧
    assert mode[4] == (P.MODE_REQ_MANUAL, 1)           # M = 交回人工
    assert mode[6] == (P.MODE_REQ_CLEAR_ESTOP, 1)      # R = 解除急停（A3 单确认）
    assert kinds[2] == [P.TYPE_NAV, P.TYPE_TOOL]       # LIFT 仍持权：NAV+TOOL，不是心跳
    assert kinds[5] == [P.TYPE_HEARTBEAT, P.TYPE_ESTOP]   # 键盘急停也得上线（P0-4）
    assert kinds[6] == [P.TYPE_MODE]                   # ESTOP 稳态静默，只有 R 的 MODE 帧

    # 闸门取样（每拍开头，= 上一拍按键处理之后）：
    #   拍2/拍3 起点闸门都为真 => 拍2 那次"视觉已恢复"的误按**没有**消费闸门
    #   拍4 起点变假          => 拍3 那次（视觉仍不可用）的按才生效
    gates = {b: (st, nc) for b, st, nc in r['gates']}
    assert gates[2] == ('LIFT', True)
    assert gates[3] == ('LIFT', True)
    assert gates[4] == ('LIFT', False)
    assert sm.needs_confirm is False

    states = [row[2] for row in r['rows']]
    assert states == ['MANUAL', 'AUTO', 'LIFT', 'LIFT', 'MANUAL', 'ESTOP', 'MANUAL']

    # HUD（spec §5.4：权限、档案号、build、loop_alive 是否在动、reject 短码）
    # I-4：HUD 是**多行**的，所以这里按拍拼接；"看得见"由
    # test_hud_lines_are_short_and_ascii 那一条钉（行长 + 纯 ASCII + 行不重叠）。
    assert len(r['hud']) == 7
    last = _hud_text(r, -1)
    assert 'permit:1' in last and 'cfg:1' in last
    assert 'prof:2' in last and 'auth:1' in last
    assert 'build:3A' in last
    assert '!!LOOP-STALLED!!' in last             # queue 里 loop_alive 恒 7 = 停摆
    assert 'rej:PERMIT' in last                   # ASCII 短码，putText 画得出来
    assert P.REJECT_TEXT[P.REJECT_PERMIT] not in last   # 中文画不出，不许进 HUD
    hud2 = _hud_text(r, 2)
    assert 'L2.5' in hud2 and 'CONFIRM' in hud2
    assert 'L2.5' not in _hud_text(r, 4)         # 闸门清掉之后不该继续催


# ---- E3 批 1b Task 6 fix round 1（审查 I-1 / I-2 / I-3 / I-4 / I-5 / I-6 + 两条 Minor）----

def test_confirm_gate_can_be_cleared_after_vision_recovers(tmp_path, monkeypatch):
    """I-1 第一支：**视野恢复了闸门也必须能被消费掉**。

    原始症状（审查者内存复现 "LOCKED OUT: 200 拍内 AUTO 不可达"）：旧按键层写的是
    `if sm.needs_confirm and not usable`，而 confirm_continue() 只在 needs_confirm
    为真时有效、go_auto() 在 needs_confirm 为真时直接 False——一旦
    AUTO→(满 2 s)vision_loss→LIFT+needs_confirm 而之后视觉一直健康，
    C 被拒（usable 为真）、A 也被拒（闸门还在），闸门只能靠"视觉再坏一次"来清。
    这条链是可达的：main 从不主动调 vision_ok()，视觉回来时 usable 立刻为真。

    剧本：拍1 'a' 进无人 -> 拍2 vision_loss 置闸门后 'm' 交回人工 -> 拍3 视觉健康时
    按 'c'（此时 PC 不持权、操作员已在驾驶位，不可能是误按）-> 拍4 'a' 才进得去。
    """
    r = _drive_main(tmp_path, monkeypatch,
                    results=[_USABLE] * 6,
                    keys=[-1, ord('a'), ord('m'), ord('c'), ord('a'), -1],
                    vision_loss_beat=2, permit=wire.GATE_N, profile_id=1, gui=True)
    gates = {b: (st, nc) for b, st, nc in r['gates']}
    assert gates[3] == ('MANUAL', True)      # 'm' 不消费闸门，只是交回权限
    assert gates[4] == ('MANUAL', False)     # 视觉健康时的 'c' 把闸门消费掉了
    states = [row[2] for row in r['rows']]
    assert states == ['MANUAL', 'AUTO', 'MANUAL', 'MANUAL', 'AUTO', 'AUTO']
    autos = [b for b, _t, p, _a in r['sent']
             if _t == P.TYPE_MODE and P.unpack_mode(p) == (P.MODE_REQ_AUTO, 1)]
    assert autos == [1, 4]                   # 两次申请都真线上过线
    kinds = _kinds_by_beat(_data_frames(r['sent']))
    assert kinds[5] == [P.TYPE_NAV, P.TYPE_TOOL]     # 拍4 真进了无人 => 拍5 在跑


def test_confirm_gate_still_clears_while_blind(tmp_path, monkeypatch):
    """I-1 第二支：L2.5 自己的现场（视觉仍不可用）按 'c' 照常生效。

    修法把条件写成 `needs_confirm and (not usable or state == 'MANUAL')`，两个分支
    都要有牙：这条钉 `not usable` 那一半——把条件改成只认 MANUAL（另一种"顺手"的
    写法）就让 L2.5 的现场按不动了，而它才是这条闸门当初要管的场景。

    gui=True 是**必需的**，不是装饰：按键是从 cv2.waitKey 读的（main 的按键分支在
    GUI 块里），不开 GUI 那剧本里的 'a'/'c' 根本不会被按下，测试会变成空转。
    """
    r = _drive_main(tmp_path, monkeypatch,
                    results=[_USABLE, _USABLE, _BLIND, _BLIND],
                    keys=[-1, ord('a'), ord('c'), -1],
                    vision_loss_beat=2, permit=wire.GATE_N, profile_id=1, gui=True)
    gates = {b: (st, nc) for b, st, nc in r['gates']}
    assert gates[2] == ('LIFT', True)        # 瞎了这拍的起点：闸门在
    assert gates[3] == ('LIFT', False)       # 瞎着按 'c' 生效
    assert [row[2] for row in r['rows']] == ['MANUAL', 'AUTO', 'LIFT', 'LIFT']


def test_auto_needs_more_than_the_usable_floor(tmp_path, monkeypatch):
    """I-2：进无人的门槛不许跟着"继续跑"的门槛一起降到 0.01。

    `confidence = min(1.0, support * 10)`（pc/perception.py:154,163），support 是
    两侧墙的行像素占比：>0.01 只要 0.1% 的像素，而 base 的进无人判据是 0.5%，
    并且单侧墙也算数。要害是 L2.5 闸门是一次性的、而这道判据是闸门之后**唯一**
    剩下的东西——"进无人"和"继续跑"是两个风险等级，不能共用一个变量。
    单侧墙 + conf=0.03：usable 为真（继续跑没问题），进无人必须被拒。
    （gui=True：按键只在 GUI 分支里从 cv2.waitKey 读，见上面两条用例的注。）

    本条钉的是 **PC 侧**"被拒就锁零、但仍持权"的语义，**批 1a 之前它不等于台架安全**：
    持权时发出去的那条 `NAV(0,0)` 会被现在烧在板上的固件读成"进 AUTO"
    （`firmware/retrofit.c:102`，早退 `:93` 只管长度与急停锁存），于是操作员按了一个
    被明确拒绝的键、权柄却从遥控手里走了（`main.c:553-557`：AUTO 分支下四轮 veloc 由
    PC 的 NAV 覆盖）。走掉的是权柄不是速度——速度确实在这里被钉成 0.0。
    现场口径与自保动作见 `docs/X5验机与接入执行清单.md` §4A 第 7 条；
    烧了批 1a 之后的原始症状复验收据在批 1a 计划 Task 9。**这条测试通过不关闭 F1。**
    """
    r = _drive_main(tmp_path, monkeypatch,
                    results=[_USABLE, _LEFT_LOW, _LEFT_LOW],
                    keys=[-1, ord('a'), -1], permit=wire.GATE_N, profile_id=1,
                    gui=True)
    assert r['gates'][1][1:] == ('MANUAL', False)
    states = [row[2] for row in r['rows']]
    assert states[1] != 'AUTO', states            # 被 go_auto 拒了
    assert [f for f in r['sent'] if f[1] == P.TYPE_MODE and
            P.unpack_mode(f[2])[0] == P.MODE_REQ_AUTO] == []   # 兼 I-3：没上线
    kinds = _kinds_by_beat(_data_frames(r['sent']))
    assert kinds[2] == [P.TYPE_NAV, P.TYPE_TOOL]  # 拒进无人 => 持权锁零（LIFT）
    blind_nav = [f for f in _data_frames(r['sent'])
                 if f[0] == 2 and f[1] == P.TYPE_NAV][0]
    assert P.unpack_nav(blind_nav[2])[:2] == (0.0, 0.0)    # 速度锁零、刀提


def test_no_auto_request_leaves_the_pc_while_it_does_not_hold_authority(
        tmp_path, monkeypatch):
    """I-3：申请帧必须在状态机点头**之后**才上线。

    旧写法是 `send(MODE_REQ_AUTO)` 无条件、且在 `go_auto()` 之前。ESTOP 下
    go_auto() 必 return False ⇒ PC 停在 ESTOP 一帧不发，而 MCU 已经收到申请 ⇒
    批 1a 的四条件若成立就授权（10-10 作者改判：撤销"现场拨档"那条，原五条件里的 ③ 编号保留
    不复用），PC 静默 ⇒ 500 ms 链路看门狗把 MCU 闩死
    （retrofit.c:316-318）。这正是报告 Concern 1 那条"自锁分叉"的真实触发路径。
    """
    r = _drive_main(tmp_path, monkeypatch,
                    results=[_USABLE] * 5,
                    keys=[-1, ord('e'), ord('a'), ord('a'), ord('c')],
                    permit=wire.GATE_N, profile_id=1, gui=True)
    autos = [b for b, _t, _p, _a in r['sent']
             if _t == P.TYPE_MODE and P.unpack_mode(_p) == (P.MODE_REQ_AUTO, 1)]
    assert autos == [], 'ESTOP 下不许把进无人申请发到线上'
    assert [row[2] for row in r['rows']] == ['MANUAL', 'ESTOP', 'ESTOP',
                                             'ESTOP', 'ESTOP']
    # 被拒要看得见：HUD 上有拒绝原因（否则操作员只会看到"按了没反应"）
    assert 'AUTO' in _hud_text(r, 4) and 'REFUSED' in _hud_text(r, 4)
    assert 'ESTOP' in _hud_text(r, 4)


def test_confirm_refusal_names_the_state(tmp_path, monkeypatch, capsys):
    """Minor 2：'c' 被拒的原因不止"视觉已恢复"那一种。

    ESTOP 下 needs_confirm 也可以是 True（LIFT→急停，闸门还在），此时按 'c' 同样被
    拒，但原因完全不同（confirm_continue() 在 ESTOP 里无效，见 state_machine 的
    fail-closed 契约）。提示语必须带上状态，否则现场会照着"等视觉坏掉再按"去排障。
    （gui=True：按键只在 GUI 分支里从 cv2.waitKey 读，见上面两条用例的注。）
    """
    r = _drive_main(tmp_path, monkeypatch,
                    results=[_USABLE, _USABLE, _USABLE, _USABLE],
                    keys=[-1, ord('a'), ord('e'), ord('c')],
                    vision_loss_beat=2, permit=wire.GATE_N, profile_id=1, gui=True)
    out = capsys.readouterr().out
    assert 'L2.5 confirm ignored' in out
    assert 'state=ESTOP' in out, out
    assert r['gates'][3][1:] == ('ESTOP', True)     # 闸门没被消费，也没被清
    # 剧本里拍1 那次 [A] 是**合法**的进无人申请（它必须先成立，拍2 的 vision_loss
    # 才能把闸门立起来），所以这里钉的是"之后一帧 AUTO 申请都没再上过线"——
    # 也就是被拒的 [C] 不许顺手把车交出去。写法比"从来没有 AUTO 申请"更紧。
    autos = [f[0] for f in r['sent'] if f[1] == P.TYPE_MODE and
             P.unpack_mode(f[2])[0] == P.MODE_REQ_AUTO]
    assert autos == [1], autos


def test_hud_lines_are_short_and_ascii(tmp_path, monkeypatch):
    """I-4：spec §5.4 点名的那几个字段必须真的**看得见**。

    三件事一起钉：
      1. 每行长度 <= 画布能放下的字符数（旧实现是一整行 297 个字符，尾部
         prof/auth/loop/build、!!LOOP-STALLED!!、MCU:STALE、reject 全被挤出画面）；
      2. 每一行都是纯 ASCII——cv2.putText 画不出 CJK，中文进了 HUD 就是一串方框，
         比不显示更难排障；CSV 的 reject 列存数字码，中文全文在
         `common/protocol.py:REJECT_TEXT`（`tools/link_probe.py` 的 stdout 打整句，
         `pc/main.py` 的 stdout 不打——`status_rx.reject_text()` 没有生产调用点）；
      3. 各行坐标互不相同（都画在同一个 y 上等于叠在一起，仍然看不见）。
    """
    import pc.main as M
    r = _drive_main(tmp_path, monkeypatch,
                    results=[_USABLE, _USABLE, _USABLE, _BLIND, _BLIND, _BLIND],
                    keys=[-1, ord('a'), ord('e'), ord('c'), ord('a'), -1],
                    vision_loss_beat=2, permit=wire.GATE_N, profile_id=1, gui=True)
    lines = [ln for beat in r['hud'] for ln in beat]
    assert lines, 'HUD 一行都没画'
    too_long = [(len(ln), ln) for ln in lines if len(ln) > M.HUD_MAX_CHARS]
    assert not too_long, too_long
    assert M.HUD_MAX_CHARS == _HUD_MAX_CHARS, 'main 的预算与测试的预算漂移了'
    non_ascii = [ln for ln in lines if not all(ord(c) < 128 for c in ln)]
    assert not non_ascii, non_ascii
    assert 'rej:PERMIT' in _hud_text(r, 5)          # 短码在位（不是方框也不是 0x08）
    assert len(r['hud'][5]) >= 2, r['hud'][5]       # 真的拆成了多行
    assert len(set(r['hud_orgs'][5])) == len(r['hud'][5]), r['hud_orgs'][5]


def test_profile_handshake_precedes_the_first_control_frame(tmp_path, monkeypatch):
    """I-5：`MODE(0x20)` 握手在批 1a 之后是进无人的**第一道条件**，全仓必须有发送点。

    固件 `enter_unmanned()` 的第一条件就是 handshake_ok，而它只由 MODE_REQ_PROFILE
    置位（spec §4.2 第一条 / §6）。Python 侧原本零调用 ⇒ 门 N 步 4 逻辑上不可能通过，
    而且会被 B2 那道 fail-closed 遮住，第一次排障会误判成"档案不匹配"。
    位置也要钉：握手必须在**任何控制帧之前**，否则同一个拍里先发了 NAV 就还是没握手。
    """
    r = _drive_main(tmp_path, monkeypatch, results=[_USABLE], states=['MANUAL'],
                    permit=wire.GATE_N, profile_id=1)
    modes = [P.unpack_mode(f[2]) for f in r['sent'] if f[1] == P.TYPE_MODE]
    assert modes == [(P.MODE_REQ_PROFILE, 1)], modes
    assert r['sent'][0][1] == P.TYPE_MODE and r['sent'][0][0] == 0
    assert [f[1] for f in r['sent']] == [P.TYPE_MODE, P.TYPE_HEARTBEAT]


def test_profile_handshake_resent_after_the_mcu_rebooted(tmp_path, monkeypatch):
    """I-5 第二半：MCU 重启（`rx.resynced` 变了）之后握手必须重发。

    固件的 handshake_ok 是 RAM 位，重启即清零；PC 不重发就一直 reject=0x01。
    这里翻的是**检测信号本身**（StatusReceiver.resynced），main 承诺的判据就是它。
    """
    r = _drive_main(tmp_path, monkeypatch, results=[_USABLE] * 6,
                    states=['MANUAL'] * 6, permit=wire.GATE_N, profile_id=1,
                    status_factory=_RebootingStatusReceiver)
    hand = [b for b, _t, p, _a in r['sent'] if _t == P.TYPE_MODE and
            P.unpack_mode(p) == (P.MODE_REQ_PROFILE, 1)]
    assert len(hand) == 2, hand
    assert hand[0] == 0 and hand[1] >= 1, hand


def test_single_wall_runs_at_l1_speed_and_counts_the_event(tmp_path, monkeypatch):
    """I-6：spec §5.2 的 L1（仅单侧墙）在 main 里必须有落点——降速 + 记事件。

    原来 left_only/right_only 都算 usable 并按 v_nominal **全速**走，也没有任何
    降级记录；A10 定的是"本批 L1 只做降速 + 记事件"。系数 0.5 是初始值（台架整定），
    接线与计数不可延后。计数按**事件**（进入 L1 的边缘）而不是按拍，否则一次
    10 秒的单侧墙会在日志里读成 125 次降级。
    """
    r = _drive_main(tmp_path, monkeypatch,
                    results=[_LEFT, _LEFT, _USABLE, _LEFT, _USABLE],
                    states=['AUTO'] * 5, permit=wire.GATE_N, profile_id=1, gui=True)
    idx = {c: i for i, c in enumerate(r['header'])}
    navs = {b: P.unpack_nav(p)[:2] for b, t, p, _a in r['sent'] if t == P.TYPE_NAV}
    assert navs[0] == pytest.approx((0.07, 0.07))    # 0.5 x 0.14
    assert navs[1] == pytest.approx((0.07, 0.07))    # 还在 L1 里，速度仍是降的
    assert navs[2] == pytest.approx((0.14, 0.14))    # 双墙恢复 => 全速
    assert navs[3] == pytest.approx((0.07, 0.07))
    assert [row[idx['l1_events']] for row in r['rows']] == ['1', '1', '1', '2', '2']
    assert 'l1:2' in _hud_text(r, 4), r['hud'][4]    # HUD 也看得见计数
    assert 'L1' in _hud_text(r, 3)                   # 正处于降级时标明 x0.5





def test_fresh_out_dir_refuses_to_overwrite_a_run_log(tmp_path):
    """`run_log.csv` 是 `'w'` 打开的 —— 复用 `--out` 会整份冲掉上一轮证据。

    10-14 台架实测一天内连续覆盖三次，其中一份是唯一记录 `mcu_mode` 3→1 的读数。
    这道闸把"忘了换目录"从一次不可恢复的数据丢失，变成一句会告诉你该做什么的报错。
    """
    import pytest

    from pc.main import fresh_out_dir

    out = str(tmp_path / 'run1')
    path = fresh_out_dir(out)                      # 新目录：放行并建好
    assert os.path.isdir(out) and path.endswith('run_log.csv')
    open(path, 'w').write('t\n')                  # 假装已经有上一轮
    with pytest.raises(SystemExit) as got:
        fresh_out_dir(out)
    assert 'overwrite' in str(got.value).lower()   # 报错要说出补救办法
    assert fresh_out_dir(out, allow_overwrite=True) == path   # 明知故犯仍要能走
