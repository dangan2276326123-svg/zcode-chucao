# -*- coding: utf-8 -*-
"""PC-side main loop: perception -> state machine -> control -> UDP.

Two modes:
  replay  — frames from a video file / image dir; full chain without hardware
  live    — frames from the GStreamer UDP stream; control frames sent via UDP

Usage:
  python pc/main.py --source field_video1.avi                # replay
  python pc/main.py --live --pc-ip 192.168.1.2               # live (PC is AP)
"""
import argparse
import csv
import os
import socket
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from pc.control import (MiddleToolPID, LatencyCompensator, DifferentialDrive,
                        LatErrorRate)
from pc.state_machine import StateMachine
from pc.perception import px_to_meters
from pc.replay import draw_overlay

PI_IP = '192.168.1.1'
PI_PORT = 9000
ESTOP_LAT_LIMIT = 0.05      # m, |lateral| beyond -> estop (v0.4 §7.2)
VISION_LOSS_S = 2.0         # s of unusable frames -> vision_loss event


class FrameSource:
    """Unified frame iterator over a video/dir (replay) or RTP stream (live)."""

    def __init__(self, source=None, live=False, step=1):
        self.live = live
        self.step = step
        if not live:
            if os.path.isdir(source):
                files = sorted(os.path.join(source, f) for f in os.listdir(source)
                               if f.lower().endswith(('.jpg', '.jpeg', '.png')))
                self._gen = self._from_dir(files)
            else:
                self._gen = self._from_video(source)

    @staticmethod
    def _from_video(path):
        import cv2
        cap = cv2.VideoCapture(path)
        while True:
            ok, f = cap.read()
            if not ok:
                return
            yield f

    @staticmethod
    def _from_dir(files):
        import cv2
        for f in files:
            img = cv2.imread(f)
            if img is not None:
                yield img

    def _from_stream(self):
        import cv2
        cap = cv2.VideoCapture('udp://@:' + str(5000), cv2.CAP_FFMPEG)
        while True:
            ok, f = cap.read()
            if not ok:
                continue
            yield f

    def frames(self):
        if self.live:
            yield from self._from_stream()
        else:
            for i, f in enumerate(self._gen):
                if i % self.step == 0:
                    yield f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', default=None, help='video/dir for replay mode')
    ap.add_argument('--live', action='store_true')
    ap.add_argument('--step', type=int, default=1)
    ap.add_argument('--pi-ip', default=PI_IP)
    ap.add_argument('--out', default='results/run')
    ap.add_argument('--no-gui', action='store_true')
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)

    from pc.perception import Perception
    per = Perception()
    sm = StateMachine()
    pid = MiddleToolPID()
    drive = DifferentialDrive()
    comp = LatencyCompensator()
    rate = LatErrorRate()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    pi = (args.pi_ip, PI_PORT)
    seq = 0

    def send(ftype, payload):
        nonlocal seq
        from common import protocol as P
        sock.sendto(P.pack_frame(ftype, payload, seq & 0xFFFF), pi)
        seq += 1

    from common import protocol as P

    csv_path = os.path.join(args.out, 'run_log.csv')
    last_good = None
    t_prev = time.time()
    t0_first = t_prev
    n = 0

    with open(csv_path, 'w', newline='', encoding='utf-8') as fcsv:
        wr = csv.writer(fcsv)
        wr.writerow(['t', 'frame_id', 'state', 'status', 'lat_m', 'lat_comp_m',
                     'vL', 'vR', 'tool_mm', 'conf', 'latency_ms'])
        for fid, frame in enumerate(FrameSource(args.source, args.live, args.step).frames()):
            t0 = time.time()
            dt = max(t0 - t_prev, 1e-3)
            t_prev = t0

            res = per.process(frame)
            latency = (time.time() - t0) * 1000.0
            comp.report(latency / 1000.0)

            usable = res['status'] in ('dual', 'left_only', 'right_only') \
                and res['confidence'] > 0.01
            if usable:
                last_good = time.time()
            elif last_good is not None and time.time() - last_good > VISION_LOSS_S:
                sm.vision_loss()

            lat_px = res['lateral_px']
            lat_m = px_to_meters(lat_px) if lat_px is not None else None
            if lat_m is None:
                lat_m = 0.0
                usable = False

            # ---- state machine events ----
            if abs(lat_m) > ESTOP_LAT_LIMIT:
                sm.estop('lat_exceeded')

            # ---- control by state ----
            vl = vr = 0.0
            tool_mm = 0.0
            if sm.state == 'AUTO' and usable:
                lat_c = comp.compensate(lat_m, rate.update(lat_m, dt))
                vl, vr = drive.wheel_speeds(lat_c)
                tool_mm = pid.update(res['tool_offset_px'] *
                                     px_to_meters(1.0) * 1000.0, dt)
                send(P.TYPE_NAV, P.pack_nav(vl, vr))
                send(P.TYPE_TOOL, P.pack_tool(tool_mm, 0))
            else:
                pid.reset()
                send(P.TYPE_HEARTBEAT, b'')

            t_rel = t0 - t0_first
            if not args.no_gui:
                import cv2
                vis = draw_overlay(res)
                cv2.putText(vis, 'STATE:%s  [A]uto [M]anual [E]stop [R]eset [Q]uit' % sm.state,
                            (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
                cv2.imshow('weeder', vis)
                k = cv2.waitKey(1) & 0xFF
                if k == ord('q'):
                    break
                elif k == ord('a'):
                    sm.go_auto(confidence_ok=res['confidence'] > 0.05)
                elif k == ord('m'):
                    sm.go_manual()
                elif k == ord('e'):
                    sm.estop('key')
                elif k == ord('r'):
                    sm.clear_estop()   # TEST ONLY; real reset is physical

            wr.writerow(['%.3f' % t_rel, fid, sm.state,
                         res['status'],
                         '%.4f' % lat_m if usable else '',
                         '%.4f' % (comp.compensate(lat_m, rate.rate)) if usable else '',
                         '%.3f' % vl, '%.3f' % vr,
                         '%.1f' % tool_mm, '%.3f' % res['confidence'],
                         '%.1f' % latency])
            n += 1
            if n % 20 == 0:
                print('[%d] %s lat=%.3fm vL=%.2f vR=%.2f tool=%.1fmm %.0fms' % (
                    fid, sm.state, lat_m, vl, vr, tool_mm, latency))
    print('done: %d frames -> %s' % (n, csv_path))


if __name__ == '__main__':
    main()
