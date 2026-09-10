# -*- coding: utf-8 -*-
"""Low-latency MJPEG-over-TCP viewer for X5 streaming tests (B7/B8).

Replaces the UDP+FFMPEG path: OpenCV 5.0's FFMPEG wrapper cannot open a
mid-stream UDP TS on this machine, and MJPEG frames exceed the 64 KiB
UDP datagram limit.  TCP multipart has neither problem, needs no
firewall inbound rule (PC connects OUT to the board), and decodes with
plain cv2.imdecode — lowest-latency path available.

Sender (X5, waits for one client):
  gst-launch-1.0 v4l2src device=/dev/video0 ! \
    image/jpeg,width=1280,height=720,framerate=30/1 ! jpegparse ! \
    multipartmux ! tcpserversink host=0.0.0.0 port=5000

Usage:
  python tools/stream_view.py                # default 192.168.127.10:5000
  python tools/stream_view.py 192.168.1.50 6000

Keys: q quit, s save a timestamped screenshot (stopwatch latency photos:
on-screen clock vs wall clock delta IS the latency).
"""
import socket
import sys
import time

import cv2
import numpy as np

DEFAULT_HOST, DEFAULT_PORT = '192.168.127.10', 5000
RECV_CHUNK = 65536


def latest_jpeg(buf):
    """Return (jpeg_bytes, consumed_upto) of the LAST complete JPEG in buf."""
    end = buf.rfind(b'\xff\xd9')                 # EOI
    if end < 0:
        return None, 0
    start = buf.rfind(b'\xff\xd8', 0, end)       # SOI before that EOI
    if start < 0:
        return None, end + 2
    return bytes(buf[start:end + 2]), end + 2


def main():
    args = sys.argv[1:]
    host = args[0] if args else DEFAULT_HOST
    port = int(args[1]) if len(args) > 1 else DEFAULT_PORT
    W = int(args[2]) if len(args) > 2 else 1280   # frame size SENT by the
    H = int(args[3]) if len(args) > 3 else 720    # camera (must match)
    sock = socket.create_connection((host, port), timeout=10)
    sock.settimeout(None)
    print('connected to %s:%d' % (host, port))

    buf = bytearray()
    t0 = time.time()
    n = 0
    last_shown = time.time()
    while True:
        buf += sock.recv(RECV_CHUNK)
        jpeg, consumed = latest_jpeg(buf)
        if jpeg is None:
            continue
        del buf[:consumed]          # drop everything up to this frame
        frame = cv2.imdecode(np.frombuffer(jpeg, dtype='uint8'),
                             cv2.IMREAD_COLOR)
        if frame is None:
            continue
        n += 1
        if n == 1:
            print('FIRST FRAME after %.2fs' % (time.time() - t0))
        fps = n / max(time.time() - t0, 1)
        cv2.putText(frame, 'frame %d  %.1ffps  [s]=shot [q]=quit' % (n, fps),
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        cv2.imshow('stream_view', frame)
        k = cv2.waitKey(1) & 0xFF
        if k == ord('q'):
            break
        if k == ord('s'):
            name = 'results/stream_view_%s.png' % time.strftime('%H%M%S')
            cv2.imwrite(name, frame)
            print('saved', name)


if __name__ == '__main__':
    main()
