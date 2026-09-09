# -*- coding: utf-8 -*-
"""MCU STATUS reception for the PC (D7 in docs/缺口清单.md).

The Pi bridge relays STM32 STATUS (0x10) frames over UDP, one datagram
per frame, to PC_PORT 9100.  Each datagram already passed extract_one's
CRC gate on the Pi, but nothing here is trusted: any malformation
(firmware/Python field drift, corrupted datagram) raises ValueError and
MUST be caught — a bare unpack_status would kill the control loop.

Bad frames are counted, not silently swallowed: >=5 bad frames in a
rolling 1 s window is almost always a firmware/Python protocol
desync — a bug to fix, so StatusReceiver.alarm() flags it.
"""
import time
from collections import deque

from common import protocol as P

STATUS_UDP_PORT = 9100   # keep in sync with vehicle.bridge.PC_PORT
ALARM_BAD_PER_S = 5.0


class StatusReceiver:
    """Pure logic, no socket: feed datagrams in, get status dicts out."""

    def __init__(self):
        self.last = None        # dict from the latest good STATUS frame
        self.good = 0
        self.bad = 0
        self._bad_times = deque(maxlen=64)

    def handle(self, raw, now=None):
        """Parse one datagram. Returns the status dict on a good STATUS
        frame, else None. Never raises on malformed input."""
        now = time.monotonic() if now is None else now
        try:
            ftype, seq, payload = P.unpack_frame(raw)
            if ftype != P.TYPE_STATUS:
                raise ValueError('unexpected frame type %d on status port' % ftype)
            speed, current_a, battery_v, limits, mode = P.unpack_status(payload)
        except ValueError:
            self.bad += 1
            self._bad_times.append(now)
            return None
        self.good += 1
        self.last = {
            'seq': seq, 'speed_mps': speed, 'current_a': current_a,
            'battery_v': battery_v, 'limits': limits, 'mode': mode,
        }
        return dict(self.last)

    def alarm(self, now=None):
        """True while bad frames arrive at >= ALARM_BAD_PER_S per second."""
        now = time.monotonic() if now is None else now
        while self._bad_times and now - self._bad_times[0] > 1.0:
            self._bad_times.popleft()
        return len(self._bad_times) >= ALARM_BAD_PER_S
