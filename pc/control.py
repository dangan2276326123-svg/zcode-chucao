# -*- coding: utf-8 -*-
"""Control layer: middle-tool PID, latency compensation, differential drive.

Pure-python, unit-tested; no torch/cv2 imports.
Units: lateral errors in meters, speeds m/s, tool offset in mm.
"""
from collections import deque


class MiddleToolPID:
    """PID for the middle-tool slide. Input near-field lateral error (mm,
    positive = tool right of crop-band center), output slide offset (mm).

    Clamped output ±out_limit, integral anti-windup via conditional integration.
    """

    def __init__(self, kp=0.8, ki=0.05, kd=0.1, out_limit=50.0):
        self.kp, self.ki, self.kd = kp, ki, kd
        self.out_limit = out_limit
        self.integral = 0.0
        self.prev_err = None

    def reset(self):
        self.integral = 0.0
        self.prev_err = None

    def update(self, err_mm, dt):
        if dt <= 0:
            dt = 1e-3
        p = self.kp * err_mm
        cand = self.integral + err_mm * dt
        # saturate check on the CURRENT output (before candidate integration):
        # block integration only while output is saturated and the error
        # would push further in the same direction
        u_now = p + self.ki * self.integral
        saturated_high = u_now >= self.out_limit
        saturated_low = u_now <= -self.out_limit
        if not ((saturated_high and err_mm > 0) or
                (saturated_low and err_mm < 0)):
            self.integral = cand
        d = 0.0
        if self.prev_err is not None:
            d = self.kd * (err_mm - self.prev_err) / dt
        self.prev_err = err_mm
        u = p + self.ki * self.integral + d
        return max(-self.out_limit, min(self.out_limit, u))


class LatencyCompensator:
    """Estimates link latency and shifts lateral error to actuation time:
    err_comp = err + rate * delay, where rate is lateral change rate (m/s).

    Maintains rolling p50/p95 of measured delays.
    """

    def __init__(self, window=100):
        self.delays = deque(maxlen=window)

    def report(self, delay_s):
        self.delays.append(delay_s)

    def p50(self):
        if not self.delays:
            return 0.0
        s = sorted(self.delays)
        return s[len(s) // 2]

    def p95(self):
        if not self.delays:
            return 0.0
        s = sorted(self.delays)
        return s[int(len(s) * 0.95)]

    def compensate(self, err_m, lateral_rate_mps, delay_s=None):
        if delay_s is None:
            delay_s = self.p50()
        return err_m + lateral_rate_mps * delay_s


class DifferentialDrive:
    """Skid-steer chassis: lateral error -> (vL, vR).

    v = nominal forward speed; correction dv = k * err (+ heading damping).
    vL = v - dv, vR = v + dv, both clamped to [-v_max, v_max].
    E-stop condition |err| > estop_limit handled by caller via .estop().
    """

    def __init__(self, v_nominal=0.14, v_max=0.2, k_lat=1.5, k_heading=0.3):
        self.v_nominal = v_nominal   # 0.5 km/h
        self.v_max = v_max
        self.k_lat = k_lat           # 1/s lateral gain
        self.k_heading = k_heading

    def wheel_speeds(self, err_m, heading_err_rad=0.0, speed_mps=None):
        v = self.v_nominal if speed_mps is None else speed_mps
        dv = self.k_lat * err_m + self.k_heading * heading_err_rad
        vl = max(-self.v_max, min(self.v_max, v - dv))
        vr = max(-self.v_max, min(self.v_max, v + dv))
        return vl, vr


class LatErrorRate:
    """Rolling lateral-error rate estimator (finite difference with smoothing)."""

    def __init__(self, alpha=0.3):
        self.alpha = alpha
        self.prev = None
        self.rate = 0.0

    def update(self, err_m, dt):
        if self.prev is None or dt <= 0:
            self.prev = err_m
            return self.rate
        raw = (err_m - self.prev) / dt
        self.rate = self.alpha * raw + (1 - self.alpha) * self.rate
        self.prev = err_m
        return self.rate
