# -*- coding: utf-8 -*-
"""RDK X5 camera stream: TCP multipart MJPEG (R3, 2026-09-14).

X5 is the TCP SERVER; the PC connects OUT — pc/main.py --live reads this via
common.mjpeg.StreamFeed.  This replaced H.264/MPEG-TS-over-UDP because
OpenCV's FFMPEG backend cannot open a mid-stream UDP TS on this host and MJPEG
frames exceed the UDP datagram limit (X5 验机 2026-09-10, see
docs/X5验机与接入执行清单.md).

Camera: USB3.0 UVC (MJPG) on X5 -> /dev/video0.

Usage (on X5):
  python3 vehicle/stream_pi.py                 # 1280x720@30 on 0.0.0.0:5000
  python3 vehicle/stream_pi.py 6000            # custom port (positional, kept)
  python3 vehicle/stream_pi.py --width 1920 --height 1080
        ^ 秋季采集要用这一条：docs/秋季图像采集清单.md 第 1 节要求分辨率
          >=1920x1080（与标定/训练域一致），而默认那路是 720p —— 拿 720p 素材
          去微调夏季 1080p 训出来的模型，域就不一致了。相机支持 MJPG 1080p30。
"""
import argparse
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


def parse_args(argv=None):
    """第一个位置参数仍是端口（老用法照抄不炸），宽高/帧率走旗标。"""
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('port', nargs='?', type=int, default=PORT)
    ap.add_argument('--port', dest='port_flag', type=int, default=None)
    ap.add_argument('--width', type=int, default=WIDTH)
    ap.add_argument('--height', type=int, default=HEIGHT)
    ap.add_argument('--fps', type=int, default=FPS)
    a = ap.parse_args(argv)
    if a.port_flag is not None:
        if a.port != PORT:
            ap.error('端口给了两次：位置参数和 --port 只能选一个')
        return a.port_flag, a.width, a.height, a.fps
    return a.port, a.width, a.height, a.fps


def main():
    port, w, h, fps = parse_args()
    cmd = build_pipeline(port, w, h, fps)
    print('run:', cmd)
    os.system(cmd)


if __name__ == '__main__':
    sys.exit(main())
