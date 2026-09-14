# -*- coding: utf-8 -*-
"""Shared TCP multipart-MJPEG helpers (R3, 2026-09-14).

The settled video chain is TCP multipart MJPEG (X5 tcpserversink -> PC
connects OUT); OpenCV's FFMPEG backend cannot open a mid-stream UDP TS on
this machine, and MJPEG frames exceed the UDP datagram limit.  Both
tools/stream_view.py and pc/main.py read from this one place so the parser
is unit-tested rather than duplicated.
"""
import socket
import time


def latest_jpeg(buf):
    """Return (jpeg_bytes, consumed_upto) of the LAST complete JPEG in buf.

    Drops everything up to and including that frame's EOI, so a slow decoder
    always shows the newest frame instead of a stale backlog.
    """
    end = buf.rfind(b'\xff\xd9')                 # EOI
    if end < 0:
        return None, 0
    start = buf.rfind(b'\xff\xd8', 0, end)       # SOI before that EOI
    if start < 0:
        return None, end + 2
    return bytes(buf[start:end + 2]), end + 2


def iter_frames(host, port, connect_timeout=10, recv_chunk=65536,
                reconnect_s=1.0):
    """Yield decoded BGR frames from a TCP multipart-MJPEG server.

    Reconnects on drop.  Imports cv2 lazily so the parser stays testable
    without OpenCV.  Never yields a partial frame.
    """
    import cv2
    import numpy as np
    while True:
        try:
            sock = socket.create_connection((host, port),
                                             timeout=connect_timeout)
        except OSError:
            time.sleep(reconnect_s)
            continue
        sock.settimeout(None)
        buf = bytearray()
        try:
            while True:
                data = sock.recv(recv_chunk)
                if not data:
                    break                       # peer closed -> reconnect
                buf += data
                jpeg, consumed = latest_jpeg(buf)
                if jpeg is None:
                    continue
                del buf[:consumed]
                frame = cv2.imdecode(np.frombuffer(jpeg, dtype='uint8'),
                                     cv2.IMREAD_COLOR)
                if frame is not None:
                    yield frame
        except OSError:
            pass
        finally:
            try:
                sock.close()
            except OSError:
                pass
        time.sleep(reconnect_s)
