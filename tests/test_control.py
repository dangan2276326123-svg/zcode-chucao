# -*- coding: utf-8 -*-
import pytest
from pc.control import (MiddleToolPID, LatencyCompensator, DifferentialDrive,
                        LatErrorRate)
from pc.state_machine import StateMachine
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


def test_tools_raised_outside_auto():
    sm = StateMachine()
    assert sm.tools_raised
    sm.go_auto()
    assert not sm.tools_raised
    sm.estop()
    assert sm.tools_raised


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

