"""Navigation control stack: Kalman filter, PD controller, 4WS Ackermann, serial TX.

Usage (in local_single_station.py loop):
    from nav_control import NavController
    ctrl = NavController()
    ...
    steer, speeds = ctrl.update(lateral_m, lateral_rate, dt)

Units: all physical quantities in SI (meters, radians, seconds).
"""

import numpy as np
import struct
import time
from collections import deque

# ============================================================
# 1-D Kalman filter for lateral position
# ============================================================
# State: [position, velocity]
# Measurement: raw visual lateral position


class KalmanLateral:
    def __init__(self, dt=0.05, process_noise=0.001, measure_noise=0.005):
        self.dt = dt
        self.x = np.zeros(2)  # [pos, vel]
        self.P = np.eye(2) * 0.1

        # State transition: pos += vel*dt, vel unchanged
        self.F = np.array([[1, dt],
                           [0,  1]])

        self.Q = np.eye(2) * process_noise  # process noise
        self.R = np.array([[measure_noise]]) # measurement noise
        self.H = np.array([[1, 0]])           # observe pos only

        self.initialized = False

    def update(self, z):
        """z: measured lateral position (meters). Returns (filtered_pos, filtered_vel)."""
        if z is None:
            # Prediction only
            self.x = self.F @ self.x
            self.P = self.F @ self.P @ self.F.T + self.Q
            return self.x[0], self.x[1]

        if not self.initialized:
            self.x[0] = z
            self.x[1] = 0.0
            self.initialized = True
            return self.x[0], self.x[1]

        # Predict
        x_pred = self.F @ self.x
        P_pred = self.F @ self.P @ self.F.T + self.Q

        # Update
        y = z - self.H @ x_pred
        S = self.H @ P_pred @ self.H.T + self.R
        K = P_pred @ self.H.T / S[0, 0]

        self.x = x_pred + K.flatten() * y
        self.P = P_pred - np.outer(K, self.H @ P_pred)

        return float(self.x[0]), float(self.x[1])


# ============================================================
# PD controller with safety bounds
# ============================================================
class PDController:
    def __init__(self, Kp=0.4, Kd=0.15, max_steer_deg=30.0, safety_limit_m=0.15):
        self.Kp = Kp          # proportional gain
        self.Kd = Kd          # derivative gain
        self.max_steer = np.radians(max_steer_deg)
        self.safety_limit = safety_limit_m

        self._prev_err = 0.0
        self._prev_t = None

    def compute(self, lateral_error_m, lateral_rate_ms, dt_s):
        """Compute steering angle (radians). Returns None if E-STOP triggered."""
        if abs(lateral_error_m) > self.safety_limit:
            return None  # E-STOP

        steer = -(self.Kp * lateral_error_m + self.Kd * lateral_rate_ms)
        steer = np.clip(steer, -self.max_steer, self.max_steer)
        return float(steer)


# ============================================================
# 4WS Ackermann steering geometry
# ============================================================
class Ackermann4WS:
    """Four-wheel independent steering (4WS) geometry.

    Assumes:
      - Front and rear axles steer independently (crab steering not used).
      - Instantaneous center of rotation lies on the rear axle extension
        for front-steer, and similarly for rear-steer.
      - Speed is low (< 2 m/s), so tire slip angles are negligible.
    """

    def __init__(self, wheelbase=1.2, track_front=0.8, track_rear=0.8):
        """
        wheelbase:   distance between front and rear axles (m)
        track_front: distance between left and right front wheels (m)
        track_rear:  distance between left and right rear wheels (m)
        """
        self.L = wheelbase
        self.tf = track_front
        self.tr = track_rear

    def compute(self, steer_center, speed_ms):
        """Given center-equivalent steer angle and speed, return wheel angles and speeds.

        steer_center: average steer angle (radians). Positive = left turn.
        speed_ms:     desired center speed (m/s).

        Returns:
            angles: dict with keys fl, fr, rl, rr (radians, +left)
            speeds: dict with same keys (m/s equivalent; actual RPM requires wheel radius)
        """
        # In low-speed Ackermann, all wheels rotate around the same ICC.
        # ICC distance from rear axle along the perpendicular:
        if abs(steer_center) < 1e-6:
            # Straight line
            return (
                {"fl": 0.0, "fr": 0.0, "rl": 0.0, "rr": 0.0},
                {"fl": speed_ms, "fr": speed_ms, "rl": speed_ms, "rr": speed_ms},
            )

        R = self.L / np.tan(abs(steer_center))  # turn radius at rear axle center

        # Front axle center turn radius
        R_front = np.hypot(R, self.L)

        # Inner/outer radii
        R_rear_inner  = R - self.tr / 2
        R_rear_outer  = R + self.tr / 2
        R_front_inner = np.hypot(R_rear_inner, self.L)
        R_front_outer = np.hypot(R_rear_outer, self.L)

        # Steer angles (all positive magnitude, sign applied later)
        ang_fl = np.arctan(self.L / (R - self.tf / 2))
        ang_fr = np.arctan(self.L / (R + self.tf / 2))
        ang_rl = -np.arctan(self.L / (R - self.tr / 2))  # rear counter-steer
        ang_rr = -np.arctan(self.L / (R + self.tr / 2))

        # Apply direction sign (positive steer = left turn)
        if steer_center > 0:
            angles = {"fl":  ang_fl, "fr":  ang_fr, "rl": ang_rl, "rr": ang_rr}
            # Wheel speeds proportional to turn radius
            base = speed_ms / R
            speeds = {
                "fl": float(R_front_inner * base),
                "fr": float(R_front_outer * base),
                "rl": float(R_rear_inner  * base),
                "rr": float(R_rear_outer  * base),
            }
        else:
            angles = {"fl": -ang_fr, "fr": -ang_fl, "rl": -ang_rr, "rr": -ang_rl}
            base = speed_ms / R
            speeds = {
                "fl": float(R_front_outer * base),
                "fr": float(R_front_inner * base),
                "rl": float(R_rear_outer  * base),
                "rr": float(R_rear_inner  * base),
            }

        return angles, speeds


# ============================================================
# Serial frame builder (STM32 protocol)
# ============================================================
class SerialFrame:
    """Builds a binary frame for STM32 communication.

    Frame format (PACKED = 'BBfffffffffh'):
      Header: 0xAA 0x55
      fl_angle_rad, fr_angle_rad, rl_angle_rad, rr_angle_rad
      fl_speed_ms, fr_speed_ms, rl_speed_ms, rr_speed_ms
      e_stop: 1 if triggered, 0 if normal
      crc8: XOR of all bytes except header
    """

    HEADER = b'\xAA\x55'

    @staticmethod
    def _crc8(data):
        crc = 0
        for b in data:
            crc ^= b
        return crc & 0xFF

    @classmethod
    def pack(cls, angles, speeds, e_stop=False):
        """Pack into binary frame. Returns bytes."""
        payload = struct.pack(
            "ffffffffB",
            angles["fl"], angles["fr"], angles["rl"], angles["rr"],
            speeds["fl"], speeds["fr"], speeds["rl"], speeds["rr"],
            1 if e_stop else 0,
        )
        crc = cls._crc8(payload)
        return cls.HEADER + payload + bytes([crc])


# ============================================================
# Top-level NavController
# ============================================================
class NavController:
    """Unified navigation controller combining KF, PD, Ackermann, and serial.

    Usage per frame:
        steer_deg, speed_ms = ctrl.update(lateral_m, dt)
        if steer_deg is None:   # E-STOP
            ctrl.send_estop()
        else:
            ctrl.send_command(steer_deg, speed_ms)
    """

    def __init__(self, wheelbase=1.2, track_f=0.8, track_r=0.8,
                 Kp=0.4, Kd=0.15, max_steer_deg=30.0,
                 safety_m=0.15, serial_port=None):
        self.kf = KalmanLateral()
        self.pd = PDController(Kp=Kp, Kd=Kd, max_steer_deg=max_steer_deg,
                                safety_limit_m=safety_m)
        self.ackermann = Ackermann4WS(wheelbase=wheelbase,
                                       track_front=track_f, track_rear=track_r)
        self.speed_ms = 0.56        # default operating speed
        self.e_stop = False

        # Serial port (lazy init)
        self.serial = None
        if serial_port is not None:
            try:
                import serial
                self.serial = serial.Serial(serial_port, 115200, timeout=0.02)
            except Exception:
                self.serial = None

    def update(self, lateral_raw_m, dt_s):
        """Process one visual measurement. Returns (steer_deg, lateral_filtered_m) or (None, lat_m) if E-STOP."""
        # Kalman filter
        lat_filt, lat_rate = self.kf.update(lateral_raw_m)

        # PD control
        steer_rad = self.pd.compute(lat_filt, lat_rate, dt_s)
        if steer_rad is None:
            self.e_stop = True
            return None, lat_filt

        steer_deg = np.degrees(steer_rad)
        self.e_stop = False
        return float(steer_deg), float(lat_filt)

    def get_ackermann(self, steer_deg):
        """Convert center steer angle to 4-wheel commands."""
        steer_rad = np.radians(steer_deg)
        return self.ackermann.compute(steer_rad, self.speed_ms)

    def send_frame(self, angles, speeds):
        """Send binary frame over serial."""
        frame = SerialFrame.pack(angles, speeds, self.e_stop)
        if self.serial is not None:
            self.serial.write(frame)
        return frame

    def send_estop(self):
        """Send E-STOP frame."""
        zero = {"fl": 0.0, "fr": 0.0, "rl": 0.0, "rr": 0.0}
        frame = SerialFrame.pack(zero, zero, e_stop=True)
        if self.serial is not None:
            self.serial.write(frame)
        return frame
