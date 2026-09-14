# -*- coding: utf-8 -*-
"""RDK X5 camera stream: TCP multipart MJPEG (R3, 2026-09-14).

X5 is the TCP SERVER; the PC connects OUT — pc/main.py --live reads this via
common.mjpeg.iter_frames.  This replaced H.264/MPEG-TS-over-UDP because
OpenCV's FFMPEG backend cannot open a mid-stream UDP TS on this host and MJPEG
frames exceed the UDP datagram limit (X5 验机 2026-09-10, see
docs/X5验机与接入执行清单.md).

Camera: USB3.0 UVC (MJPG) on X5 -> /dev/video0.

Usage (on X5):
  python3 vehicle/stream_pi.py            # listen 0.0.0.0:5000
  python3 vehicle/stream_pi.py 6000       # custom port
"""
import os
import sys

PORT = 5000
WIDTH, HEIGHT, FPS = 1280, 720, 30


def build_pipeline(port=PORT, w=WIDTH, h=HEIGHT, fps=FPS, host='0.0.0.0'):
    return (
        'gst-launch-1.0 -e v4l2src device=/dev/video0 ! '
        f'image/jpeg,width={w},height={h},framerate={fps}/1 ! '
        f'jpegparse ! multipartmux ! '
        f'tcpserversink host={host} port={port}'
    )   # TCP multipart MJPEG: PC connects out, cv2.imdecode per whole frame


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    cmd = build_pipeline(port)
    print('run:', cmd)
    os.system(cmd)


if __name__ == '__main__':
    main()
