# -*- coding: utf-8 -*-
"""common/mjpeg.py — the parser plus the bounded-read feed (E2④).

Review 2026-09-21 §E2 said two things that these tests exist to answer:

1. "有界 recv 不等于主循环能继续跑" — a socket timeout caught inside the same
   retry-forever loop still never hands the caller a beat.  ``StreamFeed``
   therefore puts the read side on its own thread and gives the control loop a
   non-blocking ``get()``; ``_pump``/``_run`` are exercised here with a scripted
   fake socket and a hand-pumped clock, so no test needs a socket or a thread.
2. "缓冲内取最新 JPEG 不等于采集端最新帧" — the parser returns the newest frame
   *in arrival order*, and the feed's age clock starts at the moment the last
   byte was read locally.  Both are stated as such below, not oversold.
"""
import socket

import pytest

from common.mjpeg import StreamFeed, iter_frames, latest_jpeg


# ---------- parser ----------
def test_no_eoi_returns_none():
    assert latest_jpeg(b'\xff\xd8abc') == (None, 0)


def test_eoi_without_soi_consumes_through():
    # a lone EOI with no preceding SOI: nothing decodable, but drop up to it
    assert latest_jpeg(b'xyz\xff\xd9') == (None, 5)


def test_single_complete_frame():
    frame = b'\xff\xd8' + b'A' * 4 + b'\xff\xd9'
    jpeg, consumed = latest_jpeg(frame + b'trailing')
    assert jpeg == frame
    assert consumed == len(frame)


def test_two_frames_returns_last_and_drops_first():
    f1 = b'\xff\xd8X\xff\xd9'
    f2 = b'\xff\xd8YY\xff\xd9'
    jpeg, consumed = latest_jpeg(f1 + f2)
    assert jpeg == f2
    assert consumed == len(f1) + len(f2)


# ---------- StreamFeed harness ----------
class FakeSock:
    """Scripted recv().  An empty list ends the session like a peer reset."""

    def __init__(self, script=()):
        self.script = list(script)
        self.closed = False

    def recv(self, _n):
        if not self.script:
            raise ConnectionResetError('script exhausted')
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    def close(self):
        self.closed = True


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


def make_feed(script=(), **kw):
    """A feed whose reader thread never starts; returns (feed, clock)."""
    clk = Clock()
    kw.setdefault('decode', lambda b: ('FRAME', len(b)))
    kw.setdefault('connect', lambda h, p: FakeSock(script))
    f = StreamFeed('h', 1, start=False, monotonic=clk, sleep=lambda s: None,
                   **kw)
    if script:
        f._pump(FakeSock(script))
    return f, clk


def stats_of(f):
    return f.snapshot()[0]


# ---------- the original symptom: "no frame" has to be reportable ----------
def test_no_frame_ever_is_distinct_from_a_stale_frame():
    f, _ = make_feed()
    assert f.get() == (None, None)          # nothing has ever arrived
    assert f.snapshot()[1:] == (0, None)    # seq 0, no age to report


def test_alive_but_silent_is_a_timeout_not_a_drop():
    """The case the old generator could not surface: TCP stays up, bytes stop.
    main.py needs a beat here so VISION_LOSS_S can actually fire."""
    f, _ = make_feed()
    f._pump(FakeSock([socket.timeout()] * 3))
    st = stats_of(f)
    assert st['recv_timeouts'] == 3
    assert st['link_drops'] == 0            # silent != disconnected
    assert st['connect_fails'] == 0
    assert f.snapshot()[1] == 0             # and still nothing to steer by


def test_peer_close_is_a_link_drop_and_run_reconnects():
    socks = [FakeSock([b'']), FakeSock([b''])]

    def connect(_h, _p):
        if not socks:
            f._stop.set()                   # end the otherwise-endless loop
            raise OSError('test over')
        return socks.pop(0)

    f, _ = make_feed(connect=connect)
    f._run()                                # runs inline, no thread
    assert stats_of(f)['link_drops'] == 2


def test_connect_failure_is_its_own_bucket():
    n = []

    def boom(_h, _p):
        n.append(1)
        if len(n) >= 3:
            f._stop.set()
        raise OSError('connection refused')

    f, _ = make_feed(connect=boom)
    f._run()
    st = stats_of(f)
    assert st['connect_fails'] == 3
    assert st['link_drops'] == 0            # never got a socket, so no "drop"


# ---------- newest-wins, staleness, and failure accounting ----------
def test_newest_frame_wins_and_backlog_is_dropped():
    """Slow consumer: two frames in one chunk, only the newest is published."""
    f, _ = make_feed([b'\xff\xd8A\xff\xd9' + b'\xff\xd8BB\xff\xd9'])
    st, seq, _age = f.snapshot()
    assert st['frames'] == 1 and seq == 1
    assert f.get()[0] == ('FRAME', 6)       # that is the SECOND frame's byte length
    assert st['bytes'] == 11                # 5 + 6: both arrived, one discarded


def test_max_age_rejects_stale_frame_instead_of_steering_by_it():
    f, clk = make_feed([b'\xff\xd8A\xff\xd9'])
    clk.advance(0.9)
    frame, age = f.get(max_age_s=0.5)
    assert frame is None and 0.85 < age < 0.95, (frame, age)
    assert f.get(max_age_s=5.0)[0] is not None


def test_age_is_measured_from_local_byte_arrival_not_capture():
    """Documented lower bound: this stream carries no capture timestamps, so
    whatever the encoder/bridge queued before us is invisible in the number."""
    f, clk = make_feed([b'\xff\xd8A\xff\xd9'])
    assert f.get()[1] == pytest.approx(0.0)
    clk.advance(2.0)
    assert f.get()[1] == pytest.approx(2.0)


def test_decode_failure_is_counted_and_the_previous_good_frame_survives():
    out = ['OK', None]
    f, _ = make_feed([b'\xff\xd8A\xff\xd9'],
                     decode=lambda b: out.pop(0) if out else 'OK')
    assert f.snapshot()[1] == 1                        # good frame published
    f._pump(FakeSock([b'\xff\xd8BBBB\xff\xd9']))       # this one fails to decode
    st, seq, _ = f.snapshot()
    assert st['decode_fail'] == 1 and seq == 1
    assert f.get()[0] == 'OK'


def test_receive_buffer_cannot_grow_without_bound():
    """A header-only stream (never an EOI) must not eat all RAM."""
    f, _ = make_feed(max_buf=4096)
    f._pump(FakeSock([b'\xff\xd8' + b'z' * 3000] * 6))
    st, seq, _ = f.snapshot()
    assert st['buf_trims'] >= 1 and seq == 0


# ---------- the real claim: the control loop must not inherit socket stalls --
def test_consumer_gets_beats_even_while_the_reader_is_stuck_connecting():
    """E2-4 crux: a black-holed bridge (SYN dropped, no RST) parks the reader
    thread inside connect for seconds.  That must not become the control loop's
    problem -- get() still answers immediately with "no frame"."""
    import threading
    import time

    gate = threading.Event()

    def slow_connect(_h, _p):
        gate.wait(5.0)
        raise OSError('never got through')

    clk = Clock()
    f = StreamFeed('h', 1, connect=slow_connect, decode=lambda b: 'X',
                   monotonic=clk, sleep=lambda s: None, start=True)
    try:
        t0 = time.monotonic()
        got = [f.get(max_age_s=0.5) for _ in range(200)]
        spent = time.monotonic() - t0
    finally:
        gate.set()
        f.close()
    assert all(x == (None, None) for x in got)
    assert spent < 0.5, spent                 # 200 polls, zero socket waiting
    assert stats_of(f)['connect_fails'] <= 1  # still parked in connect, not retried


# ---------- the removed footgun ----------
def test_blocking_iter_frames_raises_instead_of_stalling_the_loop():
    with pytest.raises(NotImplementedError):
        iter_frames()
