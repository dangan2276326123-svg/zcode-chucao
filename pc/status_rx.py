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

STATUS payloads come in two shapes (E3 spec §3.5): 14 B before E3, 19 B
after.  handle() dispatches on payload length through
protocol.unpack_status_any(), so an old firmware keeps working (its five
E3 keys read as None) and any other length is counted as a bad frame.
This dispatch is the reason the PC side must merge BEFORE the 19 B
firmware is flashed: with the old 14 B-only unpacker every single frame
would be counted bad and alarm() would cry "link desync" about our own
parser, not the radio.
"""
import time
from collections import deque

from common import protocol as P

STATUS_UDP_PORT = 9100   # keep in sync with vehicle.bridge.PC_PORT
ALARM_BAD_PER_S = 5.0
STALE_S = 1.0            # no fresh STATUS within this -> link down / MCU hung
RESYNC_RUN = 50          # 连续这么多帧"序号互不相同且递增"且已判 stale -> MCU 重启，重新同步
STALL_FRAMES = 5         # 主循环约 80 ms 一圈、STATUS 20 Hz：250 ms 内应有约 3 次自增，
                         # 连续 5 帧读到同一个值 = 执行面停摆（spec §3.2 loop_alive）


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
        self._loop_hist = deque(maxlen=STALL_FRAMES)   # loop_alive of accepted frames

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
            st = P.unpack_status_any(payload)      # 按载荷长度分派 14/19（A8）
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
        st['seq'] = seq
        self.last = st
        la = st.get('loop_alive')
        if la is None:
            self._loop_hist.clear()      # v1 固件：没有这个字段，不猜、也不留着旧账
        else:
            self._loop_hist.append(la)
        return dict(self.last)

    @property
    def status_version(self):
        """STATUS 载荷形态：1 = E3 之前的 14 B，2 = E3 的 19 B，None = 还没收到。"""
        return None if self.last is None else self.last.get('v')

    def loop_stalled(self, frames=STALL_FRAMES):
        """True = 执行面停摆（Fw-21 的探测手段，也是固件 reject=0x05 的 PC 侧对应物）。

        判据是**连续 frames 帧读到同一个 loop_alive 值**。主循环约 80 ms 一圈、
        STATUS 20 Hz，250 ms 内应有约 3 次自增，所以 5 帧不变不是"采样凑巧"而是真停摆；
        u8 回绕（...253,254,255,0,1）时 5 个值互不相同，不会被误判。
        v1 固件没有这个字段 ⇒ 历史被清空 ⇒ 恒 False：**绝不谎报停摆**。

        frames 的合法区间是 **1..STALL_FRAMES**，两个方向都收窄了（旧 docstring
        把"收紧/放宽"说反了，Task 4 审查点给 Task 6）：
          - 调小 = **提前**判停摆（更敏感、也更容易误报），只给探针用；
            控制循环里必须用默认的 STALL_FRAMES。
          - 调大在物理上不可能：历史窗口的长度就是 STALL_FRAMES，旧实现里
            `len(hist) > 5` 永不成立 ⇒ 本函数**永远返回 False**，真停摆也不报
            （fail-open），所以这里直接 ValueError，不给它静默的机会。
          - frames < 1 按 1 处理：旧实现 frames=0 的 `[-0:]` 等于 `[0:]`，取的是
            **整个窗口**而不是"零帧"，与 frames=1 不同义；clamp 之后两者同义
            （= 最后一帧自比，恒真）。HUD 里那个调用点用的是默认值。
        """
        if frames > STALL_FRAMES:
            raise ValueError('frames=%r 超出历史窗口长度 %d：判据永远不成立'
                             % (frames, STALL_FRAMES))
        frames = max(1, int(frames))
        if len(self._loop_hist) < frames:
            return False
        vals = list(self._loop_hist)[-frames:]
        return len(set(vals)) == 1

    def reject_text(self):
        """最近一次拒绝原因的人话（spec §5.4：HUD 不显示十六进制）。

        没有 STATUS / v1 帧 / reject 为 None ⇒ 空串；未知码 ⇒ 带数字的兜底文案。
        这里**不抛异常**：它在控制循环里被每帧调用，固件将来加的原因码不该让 PC 停。
        """
        if not self.last or self.last.get('reject') is None:
            return ''
        code = self.last['reject']
        return P.REJECT_TEXT.get(code, '未知拒绝码 %d' % code)

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
