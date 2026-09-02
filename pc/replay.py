# -*- coding: utf-8 -*-
"""Offline replay: run the perception chain on recorded field videos.

No hardware needed — validates the algorithm loop end-to-end and produces
the CSV log format used for thesis data.

Usage:
  python pc/replay.py field_video1.avi --step 15 --out results/replay1
  python pc/replay.py avi_frames --step 1 --out results/replay_frames1  (dir of jpgs)
"""
import argparse
import csv
import os
import sys
import time

import cv2
import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from pc.perception import Perception, px_to_meters  # noqa: E402


def frames_from_video(path, step):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise IOError('cannot open video: %s' % path)
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % step == 0:
            yield idx, frame
        idx += 1
    cap.release()


def frames_from_dir(path, step):
    files = sorted(f for f in os.listdir(path)
                   if f.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp')))
    for i, f in enumerate(files):
        if i % step:
            continue
        img = cv2.imread(os.path.join(path, f))
        if img is not None:
            yield i, img


def draw_overlay(result):
    vis = result['undistorted'].copy()
    vis[result['mask'] == 1] = (vis[result['mask'] == 1] * 0.6 +
                                np.array([100, 255, 255]) * 0.4).astype('uint8')
    ipm = cv2.cvtColor(result['ipm_mask'] * 255, cv2.COLOR_GRAY2BGR)
    for nav, y, color in ((result['nav_far'], 180, (0, 255, 0)),
                          (result['nav_near'], 620, (0, 0, 255))):
        cx = nav.get('center_x')
        if cx is not None:
            cv2.line(ipm, (int(cx), y - 40), (int(cx), y + 40), color, 3)
            cv2.circle(ipm, (int(cx), y), 6, color, -1)
    h = 360
    ipm_small = cv2.resize(ipm, (int(ipm.shape[1] * h / ipm.shape[0]), h))
    vis[-h:, :ipm_small.shape[0] if False else ipm_small.shape[1]] = ipm_small
    cv2.putText(vis, 'status:%s lat:%s tool:%s conf:%.2f' % (
        result['status'],
        ('%.0fpx' % result['lateral_px']) if result['lateral_px'] is not None else 'n/a',
        ('%.0fpx' % result['tool_offset_px']) if result['tool_offset_px'] is not None else 'n/a',
        result['confidence']), (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    return vis


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('source', help='video file or image directory')
    ap.add_argument('--step', type=int, default=15,
                    help='process every Nth frame')
    ap.add_argument('--out', default='results/replay')
    ap.add_argument('--save-every', type=int, default=20,
                    help='save overlay image every Nth processed frame')
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    per = Perception()

    if os.path.isdir(args.source):
        gen = frames_from_dir(args.source, args.step)
    else:
        gen = frames_from_video(args.source, args.step)

    csv_path = os.path.join(args.out, 'replay_log.csv')
    n = 0
    t0 = time.time()
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        wr = csv.writer(f)
        wr.writerow(['frame_id', 'latency_ms', 'status', 'lateral_px',
                     'lateral_m', 'tool_offset_px', 'tool_offset_m',
                     'confidence'])
        for fid, frame in gen:
            t1 = time.time()
            res = per.process(frame)
            dt_ms = (time.time() - t1) * 1000.0
            lat_px = res['lateral_px']
            tool_px = res['tool_offset_px']
            wr.writerow([fid, '%.1f' % dt_ms, res['status'],
                         '' if lat_px is None else '%.1f' % lat_px,
                         '' if lat_px is None else '%.4f' % px_to_meters(lat_px),
                         '' if tool_px is None else '%.1f' % tool_px,
                         '' if tool_px is None else '%.4f' % px_to_meters(tool_px),
                         '%.3f' % res['confidence']])
            if n % args.save_every == 0:
                cv2.imwrite(os.path.join(args.out, 'overlay_%06d.jpg' % fid),
                            draw_overlay(res))
            n += 1
            if n % 10 == 0:
                print('frame %d: %s lat=%s %.0fms' % (
                    fid, res['status'],
                    'n/a' if lat_px is None else '%.0fpx' % lat_px, dt_ms))
    print('done: %d frames -> %s (%.1f s total, %.0f ms/frame)' % (
        n, csv_path, time.time() - t0, (time.time() - t0) * 1000 / max(n, 1)))


if __name__ == '__main__':
    main()
