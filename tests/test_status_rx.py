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
