# -*- coding: utf-8 -*-
"""Low-latency UDP viewer for X5 streaming tests (B7/B8 latency checks).

Receives the MJPEG/TS stream from the vehicle board and shows it with a
1-frame receive buffer — this is the same receive path class as
pc/main.py live mode, unlike VLC whose ~1 s buffering hides the real
link latency.

Usage:
  python tools/udp_view.py            # default udp://@:5000
  python tools/udp_view.py @:6000

Keys: q quit, s save a timestamped screenshot (for stopwatch latency
photos: the on-screen clock vs wall clock delta IS the latency).
"""
import sys
import time

import cv2

DEFAULT_ADDR = 'udp://@:5000'


def main():
    addr = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ADDR
    if addr.startswith('@'):
        addr = 'udp://' + addr
    cap = cv2.VideoCapture(addr, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if not cap.isOpened():
        print('waiting for stream on %s ... (start gst-launch on the board)'
              % addr)
    t0 = time.time()
    n = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            if time.time() - t0 > 30:
                print('no frames for 30 s — is the sender running?')
                t0 = time.time()
            continue
        n += 1
        hud = '%s  frame %d  %.1ffps' % (addr, n, n / max(time.time() - t0, 1))
        cv2.putText(frame, hud, (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        cv2.imshow('udp_view (q quit, s screenshot)', frame)
        k = cv2.waitKey(1) & 0xFF
        if k == ord('q'):
            break
        if k == ord('s'):
            name = 'results/udp_view_%s.png' % time.strftime('%H%M%S')
            cv2.imwrite(name, frame)
            print('saved', name)


if __name__ == '__main__':
    main()
