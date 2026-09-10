# -*- coding: utf-8 -*-
"""Low-latency UDP viewer for X5 streaming tests (B7/B8 latency checks).

pc/main.py live mode will use OpenCV FFMPEG, but OpenCV 5.0.0's FFMPEG
wrapper cannot open a mid-stream UDP TS (isOpened() False after 30 s
timeout — verified 2026-09-10), so this viewer shells out to the
imageio-ffmpeg binary and reads raw BGR frames over a pipe instead.
Same visual result, no VLC-style 1 s buffering.

Sender (X5):
  gst-launch-1.0 v4l2src device=/dev/video0 ! \
    image/jpeg,width=1280,height=720,framerate=30/1 ! jpegdec ! \
    videoconvert ! x264enc tune=zerolatency bitrate=2000 key-int-max=30 ! \
    mpegtsmux ! udpsink host=<PC_IP> port=5000 sync=false

Usage:
  python tools/udp_view.py            # default udp://@:5000 1280x720
  python tools/udp_view.py @:5000 1280 720

Keys: q quit, s save a timestamped screenshot (for stopwatch latency
photos: the on-screen clock vs wall clock delta IS the latency).
"""
import subprocess
import sys
import time

import cv2
import imageio_ffmpeg

W, H = 1280, 720


def main():
    args = sys.argv[1:]
    addr = args[0] if args else 'udp://@:5000'
    if addr.startswith('@'):
        addr = 'udp://' + addr
    if len(args) >= 3:
        global W, H
        W, H = int(args[1]), int(args[2])

    ff = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [ff, '-fflags', 'nobuffer', '-flags', 'low_delay',
           '-i', addr, '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-']
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL)
    print('ffmpeg reading %s ...' % addr)
    t0 = time.time()
    n = 0
    while True:
        buf = proc.stdout.read(W * H * 3)
        if not buf or len(buf) < W * H * 3:
            print('stream ended')
            break
        n += 1
        frame = None
        frame = cv2.imdecode  # noqa: keep linters calm about cv2 usage below
        import numpy as np
        frame = np.frombuffer(buf, dtype='uint8').reshape((H, W, 3))
        if n == 1:
            print('FIRST FRAME after %.2fs' % (time.time() - t0))
        hud = 'frame %d  %.1ffps  [s]=shot [q]=quit' % (
            n, n / max(time.time() - t0, 1))
        cv2.putText(frame, hud, (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        cv2.imshow('udp_view', frame)
        k = cv2.waitKey(1) & 0xFF
        if k == ord('q'):
            break
        if k == ord('s'):
            name = 'results/udp_view_%s.png' % time.strftime('%H%M%S')
            cv2.imwrite(name, frame)
            print('saved', name)
    proc.kill()


if __name__ == '__main__':
    main()
