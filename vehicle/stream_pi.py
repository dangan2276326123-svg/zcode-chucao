# -*- coding: utf-8 -*-
"""Raspberry Pi camera stream: H.264 over RTP to the PC (GStreamer).

Latency-first pipeline (720p25): v4l2 -> hardware H.264 -> RTP.
PC side (see pc/view_stream.sh): gst-launch-1.0 udpsrc ... decodebin.
"""
import os
import subprocess
import sys

PC_IP = '192.168.1.2'
PORT = 5000
WIDTH, HEIGHT, FPS = 1280, 720, 25
BITRATE = 2500  # kbps


def build_pipeline(pc_ip=PC_IP, port=PORT, w=WIDTH, h=HEIGHT, fps=FPS,
                   bitrate=BITRATE):
    return (
        'gst-launch-1.0 -e v4l2src device=/dev/video0 io-mode=4 ! '
        f'video/x-h264,width={w},height={h},framerate={fps}/1 ! '
        f'h264parse config-interval=1 ! mpegtsmux ! '
        f'udpsink host={pc_ip} port={port}'
    )   # MPEG-TS over UDP: decodable by OpenCV/ffmpeg udp:// without SDP


def build_pipeline_soft(pc_ip=PC_IP, port=PORT, w=WIDTH, h=HEIGHT, fps=FPS,
                        bitrate=BITRATE):
    """If the camera does not output H.264 natively, encode in software
    (or use v4l2h264enc on Pi with hardware encoder):"""
    return (
        'gst-launch-1.0 -e v4l2src device=/dev/video0 ! '
        f'video/x-raw,width={w},height={h},framerate={fps}/1 ! '
        'videoconvert ! '
        f'x264enc tune=zerolatency bitrate={bitrate} key-int-max={fps} ! '
        f'h264parse config-interval=1 ! mpegtsmux ! '
        f'udpsink host={pc_ip} port={port}'
    )   # MPEG-TS over UDP: decodable by OpenCV/ffmpeg udp:// without SDP


def main():
    pc_ip = sys.argv[1] if len(sys.argv) > 1 else PC_IP
    cmd = build_pipeline(pc_ip)
    print('run:', cmd)
    os.system(cmd)


if __name__ == '__main__':
    main()
