# -*- coding: utf-8 -*-
import pytest
from pc.control import (MiddleToolPID, LatencyCompensator, DifferentialDrive,
                        LatErrorRate)
from pc.state_machine import StateMachine
from common import protocol as P
from vehicle.bridge import decide_forward, extract_one_stream


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


# ---- bridge watchdog ------------------------------------------------------

def test_watchdog_injects_estop_after_timeout():
    now = 1000
    # 1000-600=400 ms <= 500 -> no inject
    fwd, inject, last = decide_forward(None, now, last_pc_ms=600, auto_on=True)
    assert fwd is None and not inject
    # 1000-400=600 ms > 500 -> inject once, timer reset
    fwd, inject, last = decide_forward(None, now, last_pc_ms=400, auto_on=True)
    assert fwd is None and inject and last == now


def test_watchdog_idle_when_not_auto():
    fwd, inject, last = decide_forward(None, 10000, last_pc_ms=100, auto_on=False)
    assert fwd is None and not inject


def test_watchdog_resets_on_pc_frame():
    fwd, inject, last = decide_forward(b'frame', 10000, last_pc_ms=100, auto_on=True)
    assert fwd == b'frame' and not inject and last == 10000


def test_extract_one_stream_helper():
    f1 = P.pack_frame(P.TYPE_HEARTBEAT, b'', 1)
    assert extract_one_stream(f1) == f1
