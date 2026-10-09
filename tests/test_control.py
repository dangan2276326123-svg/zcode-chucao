# -*- coding: utf-8 -*-
import csv
import os
import sys

import pytest
from pc.control import (MiddleToolPID, LatencyCompensator, DifferentialDrive,
                        LatErrorRate)
from pc.state_machine import StateMachine
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
    收口理由不是改契约：计划自己的 Global Constraints 写着"任何拿不到的量都不得
    当作满足"，且这与 pc/wire.py 里"未知许可位一律 ValueError"（Task 2 审查
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

# STATUS v2 报文里的 MCU 回显值：profile=2 与下面 PC 侧的 profile_id=1 **故意不同**，
# 这样 CSV 的 profile 列（来自 MCU）与 permit 列（来自 PC 档案）不会互相冒充。
_MCU_STATUS = dict(speed=0.0, current=0.0, battery_v=48.0, limits=0, mode=1,
                   profile=2, authority=1, loop_alive=7, build_id=0x3A,
                   reject=P.REJECT_PERMIT)


class _FakeCv2:
    """只够 main 的 GUI 分支用：记录 HUD 文本、按剧本给键。"""

    FONT_HERSHEY_SIMPLEX = 0

    def __init__(self, keys, hud):
        self._keys = list(keys)
        self._beat = 0
        self.hud = hud

    def putText(self, img, text, org, fontface, fscale, color, thickness):
        self.hud.append(text)

    def imshow(self, name, img):
        pass

    def waitKey(self, delay):
        k = self._keys[self._beat] if self._beat < len(self._keys) else -1
        self._beat += 1
        return k


def _drive_main(tmp_path, monkeypatch, results, states=None, keys=(), n_status=None,
                permit=wire.GATE_N, profile_id=1, gui=False,
                vision_loss_beat=None):
    """跑 n=len(results) 拍，返回 {'sent','header','rows','sm','hud','permits','holder'}。"""
    import numpy as np
    import pc.main as M

    holder = {'beat': 0, 'sm': None, 'permits': [], 'loaded': False,
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
                yield i + 1                 # 非 None：这一拍有帧，走 per.process()

    def _sm_factory(permit=wire.GATE_N):
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
            sent.append((holder['beat'] - 1, ftype, payload, addr))

        def recvfrom(self, _maxlen):
            beat = holder['beat']          # drain 发生在 process() 之前 = 当前拍号
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
    monkeypatch.setattr('pc.perception.Perception', _perception_factory)
    monkeypatch.setattr('pc.vehicle_profile.load', _profile_loader)
    monkeypatch.setattr(M, 'StateMachine', _sm_factory)
    monkeypatch.setattr(M, 'MiddleToolPID', _CountingPID)
    monkeypatch.setattr(M, 'FrameSource', _FakeSource)
    monkeypatch.setattr(M, 'socket', _SocketModule())
    monkeypatch.setattr(M, 'draw_overlay', lambda res: np.zeros((8, 8, 3), 'uint8'))
    if gui:
        monkeypatch.setitem(sys.modules, 'cv2', _FakeCv2(keys, hud))

    argv = ['pc/main.py', '--live', '--pi-ip', '127.0.0.1', '--source', 'fake',
            '--out', str(tmp_path)]
    if not gui:
        argv.append('--no-gui')
    monkeypatch.setattr(sys, 'argv', argv)

    M.main()
    with open(os.path.join(str(tmp_path), 'run_log.csv'), encoding='utf-8') as f:
        rows = list(csv.reader(f))
    return {'sent': sent, 'header': rows[0], 'rows': rows[1:], 'sm': holder['sm'],
            'permits': holder['permits'], 'hud': hud, 'holder': holder,
            'gates': holder['gates']}


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
    kinds = _kinds_by_beat(r['sent'])

    assert kinds[0] == [P.TYPE_NAV, P.TYPE_TOOL]        # 持权：NAV+TOOL
    assert kinds[1] == [P.TYPE_NAV, P.TYPE_TOOL]        # 同一状态、这一拍瞎了：仍是 NAV+TOOL
    assert kinds[2] == [P.TYPE_ESTOP]                   # 跳变那一拍只发一次 ESTOP
    assert 3 not in kinds, kinds[3]                     # ESTOP 稳态：PC 在线上完全静默
    assert kinds[4] == [P.TYPE_HEARTBEAT]               # MANUAL 才交回权限
    assert [f[1] for f in r['sent']].count(P.TYPE_HEARTBEAT) == 1
    assert [f[1] for f in r['sent']].count(P.TYPE_ESTOP) == 1

    nav0 = [f for f in r['sent'] if f[0] == 0 and f[1] == P.TYPE_NAV][0]
    # 可用这一拍才真的有速度（v_nominal 0.14 走 float32，与 test_wire 同一口径）
    assert P.unpack_nav(nav0[2])[:2] == pytest.approx((0.14, 0.14))
    tool0 = [f for f in r['sent'] if f[0] == 0 and f[1] == P.TYPE_TOOL][0]
    off, lift = P.unpack_tool(tool0[2])
    assert (off, lift) == (0.0, 0x07)      # 门 N：AUTO 且视觉可用也不许落刀/横移

    blind_nav = [f for f in r['sent'] if f[0] == 1 and f[1] == P.TYPE_NAV][0]
    assert P.unpack_nav(blind_nav[2])[:2] == (0.0, 0.0)       # 瞎了 = 速度锁零
    blind_tool = [f for f in r['sent'] if f[0] == 1 and f[1] == P.TYPE_TOOL][0]
    assert P.unpack_tool(blind_tool[2]) == (0.0, 0x07)        # 瞎了 = 提刀
    assert r['permits'] == [wire.GATE_N]   # 状态机拿到的 permit 来自档案，不是默认值

    # 工具 PID 的积分：不驱动那一拍必须清（旧代码在 MANUAL/ESTOP 也清，
    # brief 的片段只覆盖了持权那一半）。
    assert r['holder']['updates'] == 1, '只有 AUTO 且可用的那一拍该算刀位'
    assert r['holder']['resets'] == 4, '瞎了/急停/手动三态每一拍都该清积分'


def test_main_run_log_writes_24_columns_and_the_e3_fields(tmp_path, monkeypatch):
    """CSV 不能被接线写坏：表头 = wire.RUN_LOG_COLUMNS，每行 24 项，
    五个 E3 列来自**真解出来**的 STATUS v2，permit 列每行都是档案里那一档。

    另外钉住一件事：不可用那一拍的 lat_m 必须是**空**，不是 '0.0000'——
    日志里的 0.0000 读起来像"实测正好压在行上"，那是伪造证据（旧实现就是这个
    写法，brief 的片段直接传 lat_m 会把它改成 0.0000）。
    """
    r = _drive_main(tmp_path, monkeypatch,
                    results=[_USABLE, _BLIND, _USABLE],
                    states=['AUTO', 'AUTO', 'AUTO'], permit=wire.GATE_N, profile_id=1)
    assert r['header'] == list(wire.RUN_LOG_COLUMNS)
    assert len(r['header']) == 24
    assert all(len(row) == 24 for row in r['rows']), [len(x) for x in r['rows']]

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
    assert r['rows'][0][idx['lat_m']] == '0.0000'
    assert r['rows'][1][idx['lat_m']] == ''                 # 瞎了这拍不写测量值
    assert r['rows'][1][idx['lat_comp_m']] == ''
    assert r['rows'][1][idx['status']] == 'no_frame'


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
      拍0 无键，MANUAL -> 只发 HEARTBEAT
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
    kinds = _kinds_by_beat(r['sent'])
    mode = {}
    for beat, ftype, payload, _addr in r['sent']:
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

    # HUD（spec §5.4：权限、档案号、build、loop_alive 是否在动、reject 人话）
    assert len(r['hud']) == 7
    assert 'permit:1' in r['hud'][-1] and 'cfg:1' in r['hud'][-1]
    assert 'prof:2' in r['hud'][-1] and 'auth:1' in r['hud'][-1]
    assert 'build:3A' in r['hud'][-1]
    assert '!!LOOP-STALLED!!' in r['hud'][-1]      # queue 里 loop_alive 恒 7 = 停摆
    assert P.REJECT_TEXT[P.REJECT_PERMIT] in r['hud'][-1]   # 人话，不是十六进制
    assert 'L2.5' in r['hud'][2] and 'CONFIRM' in r['hud'][2]
    assert 'L2.5' not in r['hud'][4]               # 闸门清掉之后不该继续催



