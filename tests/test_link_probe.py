# -*- coding: utf-8 -*-
"""tools/link_probe.py 里 `--serial` 那条新路的测试（不需要硬件）。

钉的是两件事：
1. `_read_status` 能**跨读边界**把帧拼出来并认出 mode 变化（现场用的是 USB-TTL，
   一次 read 给半帧是常态）；
2. 它记的是"模式跳变序列"，不是"最后一帧"——B2 那些场景要的正是跳变的时刻与顺序。
"""
import threading
import time

from common import protocol as P
from tools import link_probe as lp


class _FakeSer:
    """按脚本给字节，喂完就返回空（模拟"对端暂时没发东西"）。"""

    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.i = 0

    def read(self, n):
        if self.i >= len(self.chunks):
            time.sleep(0.01)
            return b''
        c = self.chunks[self.i]
        self.i += 1
        return c


def _status(seq, mode):
    return P.pack_frame(P.TYPE_STATUS, P.pack_status(0.0, 0.0, 48.0, 0, mode), seq)


def _run(chunks, wait=0.35):
    out = {'good': 0, 'changes': [], 't0': time.time()}
    stop = threading.Event()
    th = threading.Thread(target=lp._read_status, args=(_FakeSer(chunks), stop, out),
                          daemon=True)
    th.start()
    time.sleep(wait)
    stop.set()
    th.join(timeout=2.0)
    return out


def test_read_status_sees_the_mode_sequence():
    out = _run([_status(1, 0), _status(2, 1), _status(3, 1), _status(4, 2)])
    assert out['good'] == 4
    assert [c[2] for c in out['changes']] == [0, 1, 2]      # MANUAL -> AUTO -> ESTOP
    assert out['changes'][0][1] is None                     # 第一条没有"上一个状态"
    assert out['changes'][1][1] == 0


def test_read_status_survives_a_frame_split_across_reads():
    """USB-TTL 一次 read 给半帧是常态：拼不上就不许算一帧，拼上了必须算。"""
    whole = _status(7, 1)
    out = _run([whole[:9], whole[9:]])
    assert out['good'] == 1
    assert [c[2] for c in out['changes']] == [1]


def test_stale_seq_is_not_counted_as_a_frame():
    """序号回退的帧（MCU 重启的旁证）不许当成新帧计进 good——判据与生产同一套。"""
    out = _run([_status(50, 0), _status(1, 0), _status(2, 0)])
    assert out['good'] == 1
