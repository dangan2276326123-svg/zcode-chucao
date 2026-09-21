# -*- coding: utf-8 -*-
"""Bounded-read MJPEG feed (E2④, review 2026-09-21 §E2).

Why the plain generator was not enough: ``iter_frames`` set
``sock.settimeout(None)`` and reconnected *inside* the generator, and
``pc/main.py`` consumes it synchronously.  A connection that stays up but
stops delivering bytes therefore blocks the whole control loop — no STATUS
polling, no GUI, and ``VISION_LOSS_S`` can never fire because the loop is
parked in ``recv``.  "有界 recv" alone does not fix that either: if the
timeout is caught in the same inner loop that retries forever, the caller
still never gets a beat.

So the read side gets its own thread and the control loop polls it:

* ``StreamFeed.get(max_age_s)`` returns ``(frame, age_s)`` or
  ``(None, age_s_since_last_frame)`` **immediately** — the caller always
  gets a beat and can decide what "no fresh frame" means.
* Reconnects happen in the reader thread, with counters, so a link that is
  merely silent is distinguishable from one that is down.

Timestamp source, stated plainly because the number depends on it:
``age_s`` is measured from **the local monotonic time of the last byte read
from the socket**, not from anything the camera stamped (this stream carries
no capture timestamps).  It is therefore a *lower bound* on glass-to-PC
latency: queueing inside the encoder, the bridge, and the kernel send buffers
is invisible to it.  Do not report it as end-to-end latency (B8 keeps those
four measurements separate).
"""
import socket
import threading
import time


def latest_jpeg(buf):
    """Return (jpeg_bytes, consumed_upto) of the LAST complete JPEG in buf.

    'Last' means last in *arrival* order — TCP preserves ordering, so this is
    the newest frame the receiver has been sent, which is not the same claim
    as 'newest frame the camera captured'.
    """
    end = buf.rfind(b'\xff\xd9')                 # EOI
    if end < 0:
        return None, 0
    start = buf.rfind(b'\xff\xd8', 0, end)       # SOI before that EOI
    if start < 0:
        return None, end + 2
    return bytes(buf[start:end + 2]), end + 2


def _default_decoder(jpeg):
    """Decode JPEG bytes to BGR.  Imported lazily so the parser stays usable
    (and testable) without OpenCV."""
    import cv2
    import numpy as np
    return cv2.imdecode(np.frombuffer(jpeg, dtype='uint8'), cv2.IMREAD_COLOR)


class StreamFeed(object):
    """Background TCP-MJPEG reader that never blocks the control loop.

    ``connect``/``decode``/``monotonic``/``sleep`` are injectable so the
    state machine is unit-testable without a socket, without OpenCV, and
    without wall-clock waits.
    """

    def __init__(self, host, port, recv_timeout=0.5, connect_timeout=5.0,
                 reconnect_s=1.0, recv_chunk=65536, max_buf=1 << 22,
                 connect=None, decode=None, monotonic=None, sleep=None,
                 start=True):
        self.host = host
        self.port = port
        self.recv_timeout = recv_timeout
        self.connect_timeout = connect_timeout
        self.reconnect_s = reconnect_s
        self.recv_chunk = recv_chunk
        self.max_buf = max_buf
        self._decode = decode or _default_decoder
        self._clock = monotonic or time.monotonic
        self._sleep = sleep or time.sleep
        self._connect = connect or self._socket_connect

        self._lock = threading.Lock()
        self._latest = None          # decoded frame
        self._latest_t = None        # monotonic time its LAST BYTE arrived
        self._seq = 0
        self._stop = threading.Event()
        # Counters are deliberately separated: "the link is silent" and "the
        # link is down" need different actions, and one blended number hides
        # both.  Reported every beat through main.py's HUD/CSV.
        self._stats = {'connect_fails': 0, 'link_drops': 0, 'recv_timeouts': 0,
                      'decode_fail': 0, 'bytes': 0,
                      'frames': 0, 'buf_trims': 0}
        self._thread = None
        if start:
            self.start()

    # ---- lifecycle -------------------------------------------------------
    def start(self):
        self._thread = threading.Thread(target=self._run,
                                        name='mjpeg-feed', daemon=True)
        self._thread.start()
        return self

    def close(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.recv_timeout * 4 + 1.0)
        return dict(self._stats)

    def _socket_connect(self, host, port):
        sock = socket.create_connection((host, port),
                                        timeout=self.connect_timeout)
        # BOUNDED.  The old settimeout(None) is the bug this class exists for.
        sock.settimeout(self.recv_timeout)
        return sock

    # ---- reader thread ---------------------------------------------------
    def _run(self):
        while not self._stop.is_set():
            try:
                sock = self._connect(self.host, self.port)
            except OSError:
                with self._lock:
                    self._stats['connect_fails'] += 1
                self._sleep(self.reconnect_s)
                continue
            try:
                self._pump(sock)
            finally:
                try:
                    sock.close()
                except OSError:
                    pass
                with self._lock:
                    self._stats['link_drops'] += 1
            self._sleep(self.reconnect_s)

    def _pump(self, sock):
        """Read one session until the link ends.  Split out of ``_run`` so the
        byte/timeout/reconnect logic is testable without a thread or a socket.
        """
        buf = bytearray()
        while not self._stop.is_set():
            try:
                data = sock.recv(self.recv_chunk)
            except socket.timeout:
                # Connection is ALIVE but silent.  That is deliberately NOT the
                # same bucket as a drop: the caller has to decide what a
                # frameless beat means, and reconnecting would not help.
                with self._lock:
                    self._stats['recv_timeouts'] += 1
                continue
            except OSError:
                return                              # peer reset -> reconnect
            if not data:
                return                              # peer closed -> reconnect
            now = self._clock()
            with self._lock:
                self._stats['bytes'] += len(data)
            buf += data
            if len(buf) > self.max_buf:
                # A stream that never delivers an EOI must not be able to grow
                # the receive buffer without bound.
                with self._lock:
                    self._stats['buf_trims'] += 1
                del buf[:len(buf) - self.max_buf // 2]
            self._drain(buf, now)

    def _drain(self, buf, now):
        """Publish the newest complete frame in buf, dropping everything older.

        Note ``now`` is when the *chunk* landed, which is at or after this
        frame's own last byte — so the age we report is, again, a lower bound.
        """
        jpeg, consumed = latest_jpeg(buf)
        if jpeg is None:
            if consumed:
                del buf[:consumed]          # stray EOI / header junk: drop it
            return
        del buf[:consumed]
        frame = self._decode(jpeg)
        with self._lock:
            self._stats['frames'] += 1
            if frame is None:
                self._stats['decode_fail'] += 1
            else:
                self._latest = frame
                self._latest_t = now
                self._seq += 1

    # ---- consumer API ----------------------------------------------------
    def get(self, max_age_s=None):
        """Return ``(frame, age_s)``; ``frame`` is None when there is nothing
        usable this beat.  Never blocks.

        ``max_age_s`` drops a frame that is older than the caller's control
        period instead of steering from a stale image.  A returned ``age_s``
        of ``None`` means "no frame has EVER arrived", which the caller should
        treat differently from "the last frame went stale".
        """
        with self._lock:
            frame, stamp, seq = self._latest, self._latest_t, self._seq
        if frame is None:
            return None, None
        age = self._clock() - stamp
        if max_age_s is not None and age > max_age_s:
            return None, age
        return frame, age

    def snapshot(self):
        with self._lock:
            return dict(self._stats), self._seq, (None if self._latest_t is None
                                                 else self._clock() - self._latest_t)


def iter_frames(*a, **kw):
    """REMOVED by E2④ (review 2026-09-21).  Kept only as a loud error.

    The old version was a generator that set ``sock.settimeout(None)`` and
    reconnected inside itself.  ``pc/main.py`` consumed it synchronously, so a
    link that stayed open but went silent parked the whole control loop in
    ``recv``: no STATUS polling, no GUI, and ``VISION_LOSS_S`` could never
    fire.  A bounded ``recv`` inside that same infinite inner loop would not
    have helped either -- the caller still gets no beat.

    Use :class:`StreamFeed` and poll ``get()`` from the control loop.  If you
    genuinely want a blocking generator for an offline tool, wrap
    ``StreamFeed`` yourself so the trade-off is written down somewhere.
    """
    raise NotImplementedError(
        'iter_frames 已被 E2④ 删除：它会静默阻塞控制循环。改用 StreamFeed.get()')

