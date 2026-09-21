# -*- coding: utf-8 -*-
"""D7 constraint tests: STATUS reception must never raise, bad frames
counted and alarmed, not silently swallowed."""
import pytest
from common import protocol as P
from pc.status_rx import StatusReceiver


def good_status(seq=1):
    return P.pack_frame(P.TYPE_STATUS,
                        P.pack_status(0.12, 1.5, 25.9, 0b010, 1), seq)


def test_good_status_parsed():
    rx = StatusReceiver()
    st = rx.handle(good_status(7), now=0.0)
    assert st['seq'] == 7 and st['limits'] == 0b010 and st['mode'] == 1
    assert st['speed_mps'] == pytest.approx(0.12, abs=1e-6)
    assert st['battery_v'] == pytest.approx(25.9, abs=1e-3)
    assert rx.good == 1 and rx.bad == 0 and rx.last == st


def test_bad_length_never_raises():
    # firmware sent a STATUS payload of the wrong length -> ValueError
    # inside handle(), counted, no exception escapes (D7 hard constraint)
    rx = StatusReceiver()
    raw = P.pack_frame(P.TYPE_STATUS, b'\x00' * 13, 1)   # 14 expected
    assert rx.handle(raw, now=0.0) is None
    assert rx.bad == 1 and rx.good == 0 and rx.last is None


def test_corrupt_and_wrong_type_counted():
    rx = StatusReceiver()
    f = bytearray(good_status())
    f[10] ^= 0xFF                       # CRC mismatch
    assert rx.handle(bytes(f), now=0.0) is None
    assert rx.handle(P.pack_frame(P.TYPE_NAV, P.pack_nav(0, 0), 2), now=0.1) is None
    assert rx.bad == 2


def test_garbage_datagram_never_raises():
    rx = StatusReceiver()
    assert rx.handle(b'\x01\x02\x03', now=0.0) is None
    assert rx.handle(b'', now=0.0) is None
    assert rx.bad == 2


def test_alarm_window_rate():
    rx = StatusReceiver()
    t = 100.0
    # 4 bad frames within the trailing 1 s window -> no alarm
    for i in range(4):
        rx.handle(b'\x00', now=t + 0.5 + i * 0.1)
    assert not rx.alarm(now=t + 1.0)
    # a 5th inside the window crosses the threshold
    rx.handle(b'\x00', now=t + 1.1)
    assert rx.alarm(now=t + 1.2)
    # window slides: 1 s after the burst it clears
    assert not rx.alarm(now=t + 2.5)


def test_good_frames_do_not_trigger_alarm():
    rx = StatusReceiver()
    for i in range(20):
        rx.handle(good_status(i), now=i * 0.01)
    assert not rx.alarm(now=0.5)
    assert rx.good == 20


# ---- R5 (2026-09-14 re-review): freshness & sequence monotonicity --------

def test_stale_before_any_frame():
    rx = StatusReceiver()
    assert rx.stale(now=0.0)          # never received -> link considered down


def test_stale_on_silence_and_fresh_on_receipt():
    rx = StatusReceiver()
    rx.handle(good_status(1), now=0.0)
    assert not rx.stale(now=0.5)
    assert rx.stale(now=2.0)          # > STALE_S with no new frame


def test_old_seq_does_not_overwrite_fresh_state():
    rx = StatusReceiver()
    rx.handle(good_status(20), now=0.0)
    assert rx.handle(good_status(19), now=0.1) is None   # stale seq rejected
    assert rx.last['seq'] == 20
    assert rx.out_of_order == 1 and rx.good == 1


# ---- E1① MCU 重启后的序号重新同步（09-21 复审修正判据）----------------
def test_reboot_monotonic_run_resyncs_after_stale_window():
    """seq1000 后 MCU 重启回到 1..N：旧逻辑要一直拒到对方追平（最坏约 27 min）。
    现在连续 50 帧"互不相同且递增"且已判 stale，即重新同步。"""
    rx = StatusReceiver()
    assert rx.handle(good_status(1000), now=0.0) is not None
    accepted = None
    t = 1.0
    for s in range(1, 60):
        r = rx.handle(good_status(s), now=t)
        t += 0.05
        if r is not None:
            accepted = (s, r['seq'])
            break
    assert accepted is not None, '重启后一直没有重新同步'
    assert accepted[1] == 50 and rx.resynced == 1
    assert rx.good == 2 and rx.out_of_order == 49


def test_repeated_identical_old_frame_never_resyncs():
    """复审指出的关键反例：同一旧帧重复 50 次不是重启证据。"""
    rx = StatusReceiver()
    rx.handle(good_status(1000), now=0.0)
    for i in range(200):
        assert rx.handle(good_status(7), now=10.0 + i * 0.05) is None
    assert rx.resynced == 0 and rx.good == 1


def test_descending_garbage_run_never_resyncs():
    rx = StatusReceiver()
    rx.handle(good_status(1000), now=0.0)
    for i, s in enumerate(range(999, 799, -1)):
        assert rx.handle(good_status(s), now=1.0 + i * 0.05) is None
    assert rx.resynced == 0


def test_resync_does_not_happen_while_status_is_still_fresh():
    """还没判 stale 就不该认定重启。"""
    rx = StatusReceiver()
    rx.handle(good_status(1000), now=0.0)
    for i in range(1, 40):
        assert rx.handle(good_status(i), now=0.2) is None   # now 一直停在新鲜窗口内
    assert rx.resynced == 0


def test_normal_wraparound_still_accepted_without_resync():
    rx = StatusReceiver()
    rx.handle(good_status(65535), now=0.0)
    assert rx.handle(good_status(0), now=0.05) is not None
    assert rx.resynced == 0 and rx.out_of_order == 0
