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
STALE_S = 1.0            # no fresh STATUS within this -> link down / MCU hung
RESYNC_RUN = 50          # 连续这么多帧"序号互不相同且递增"且已判 stale -> MCU 重启，重新同步


def _seq_newer(a, b):
    """True if seq a is newer than b under u16 wraparound (forward half-range)."""
    return 1 <= ((a - b) & 0xFFFF) <= 0x7FFF


class StatusReceiver:
    """Pure logic, no socket: feed datagrams in, get status dicts out."""

    def __init__(self):
        self.last = None        # dict from the latest good STATUS frame
        self.good = 0
        self.bad = 0
        self.out_of_order = 0   # valid frames rejected for a stale sequence no.
        self.resynced = 0       # reboots detected via a monotonic rejected run
        self.last_good_time = None
        self._last_seq = None
        self._rej_run = 0       # consecutive rejected frames with increasing seq
        self._rej_last = None   # last rejected seq, to require distinct+increasing
        self._bad_times = deque(maxlen=64)

    def _note_rejection(self, seq):
        """E1② 判据（09-21 复审修正）：只有**互不相同且单调递增**的被拒序号才累计。

        旧帧被重复投递（同一 seq 来 50 次）不是重启证据，一次都不算。
        """
        if self._rej_last is not None and _seq_newer(seq, self._rej_last):
            self._rej_run += 1
        elif self._rej_last == seq:
            pass                       # 重复旧帧：不累计也不清零
        else:
            self._rej_run = 1
        self._rej_last = seq
        return self._rej_run >= RESYNC_RUN

    def handle(self, raw, now=None):
        """Parse one datagram. Returns the status dict on a good, fresh STATUS
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
        # R5: never let an old sequence number overwrite fresher state.
        if self._last_seq is not None and not _seq_newer(seq, self._last_seq):
            # E1① 修复：MCU 重启后序号回退，旧逻辑会一直拒到对方追平
            # （最坏约 27 min，取决于重启前序号在 16 位环上的位置）。
            # 重新同步**只恢复状态显示**；是否恢复 AUTO、急停是否解除由调用方
            # 决定，这里绝不代为放行（复审 E3/R1 口径）。
            if self._note_rejection(seq) and self.stale(now):
                self.resynced += 1
                self._rej_run, self._rej_last = 0, None
            else:
                self.out_of_order += 1     # 只统计真正被丢掉的那帧
                return None
        self._rej_run, self._rej_last = 0, None
        self._last_seq = seq
        self.good += 1
        self.last_good_time = now
        self.last = {
            'seq': seq, 'speed_mps': speed, 'current_a': current_a,
            'battery_v': battery_v, 'limits': limits, 'mode': mode,
        }
        return dict(self.last)

    def age_s(self, now=None):
        """Seconds since the last fresh STATUS frame; None if never received."""
        now = time.monotonic() if now is None else now
        if self.last_good_time is None:
            return None
        return now - self.last_good_time

    def stale(self, now=None, timeout=STALE_S):
        """True when no fresh STATUS within timeout — total silence, which the
        bad-frame burst alarm cannot catch (R5)."""
        age = self.age_s(now)
        return age is None or age > timeout

    def alarm(self, now=None):
        """True while bad frames arrive at >= ALARM_BAD_PER_S per second."""
        now = time.monotonic() if now is None else now
        while self._bad_times and now - self._bad_times[0] > 1.0:
            self._bad_times.popleft()
        return len(self._bad_times) >= ALARM_BAD_PER_S
