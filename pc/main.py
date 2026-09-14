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
from pc.status_rx import StatusReceiver, STATUS_UDP_PORT

PI_IP = '192.168.127.10'        # RDK X5 (bridge) — control UDP target
PI_PORT = 9000
STREAM_HOST = '192.168.127.10'  # TCP multipart MJPEG server = X5 (R3)
STREAM_PORT = 5000
ESTOP_LAT_LIMIT = 0.05      # m, |lateral| beyond -> estop (v0.4 §7.2)
VISION_LOSS_S = 2.0         # s of unusable frames -> vision_loss event


class FrameSource:
    """Unified frame iterator over a video/dir (replay) or RTP stream (live)."""

    def __init__(self, source=None, live=False, step=1,
                 stream_host=STREAM_HOST, stream_port=STREAM_PORT):
        self.live = live
        self.step = step
        self.stream_host = stream_host
        self.stream_port = stream_port
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
        from common.mjpeg import iter_frames
        yield from iter_frames(self.stream_host, self.stream_port)

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
    ap.add_argument('--stream-host', default=STREAM_HOST)
    ap.add_argument('--stream-port', type=int, default=STREAM_PORT)
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

    # live only: replay must never be able to drive the vehicle (P0-8)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) if args.live else None
    pi = (args.pi_ip, PI_PORT)
    seq = 0

    # live only: receive MCU STATUS relayed by the bridge (D7).  Bad frames
    # are caught+counted inside StatusReceiver — never a bare unpack.
    rx = None
    status_sock = None
    if args.live:
        rx = StatusReceiver()
        status_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        status_sock.bind(('0.0.0.0', STATUS_UDP_PORT))
        status_sock.setblocking(False)

    def drain_status(now):
        if rx is None:
            return
        while True:
            try:
                raw, _ = status_sock.recvfrom(2048)
            except BlockingIOError:
                break
            rx.handle(raw, now=now)
        if rx.alarm(now):
            print('WARNING: %d bad status frames in the last 1 s — '
                  'check firmware/Python STATUS payload sync' % rx.bad)
        if rx.stale(now):
            age = rx.age_s(now)
            print('WARNING: no fresh MCU STATUS (link down / MCU hung) — '
                  'last-good %s' % ('never' if age is None else '%.1fs' % age))

    def send(ftype, payload):
        nonlocal seq
        if sock is None:      # replay mode: no radio, no commands leave the PC
            return
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
                     'vL', 'vR', 'tool_mm', 'conf', 'latency_ms',
                     'mcu_mode', 'batt_v', 'rx_good', 'rx_bad'])
        for fid, frame in enumerate(FrameSource(
                args.source, args.live, args.step,
                args.stream_host, args.stream_port).frames()):
            t0 = time.time()
            dt = max(t0 - t_prev, 1e-3)
            t_prev = t0
            prev_state = sm.state   # captured BEFORE any state event (P0-4)

            drain_status(t0)

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
            if sm.state != prev_state:
                # wire semantics (review round 3, item 6): entering ESTOP
                # latches the MCU (physical reset to clear); entering LIFT is
                # recoverable and is driven by the NAV-zero + TOOL-up frames
                # in the state branch below - never an ESTOP frame.
                if sm.state == 'ESTOP':
                    send(P.TYPE_ESTOP, b'')

            # ---- control by state ----
            vl = vr = 0.0
            tool_mm = 0.0
            if sm.state == 'AUTO' and usable:
                tool_px = res.get('tool_offset_px')
                if tool_px is None:      # far field ok, near field lost (P1-3)
                    tool_px = 0.0
                e_dot = rate.update(lat_m, dt)   # filtered lateral rate (ė)
                lat_c = comp.compensate(lat_m, e_dot)
                vl, vr = drive.wheel_speeds(lat_c, err_rate=e_dot)  # PD(e,ė), H4.6-A
                tool_mm = pid.update(tool_px * px_to_meters(1.0) * 1000.0, dt)
                send(P.TYPE_NAV, P.pack_nav(vl, vr))
                send(P.TYPE_TOOL, P.pack_tool(tool_mm, 0))
            elif sm.state == 'LIFT':
                # degraded vision: stay in AUTO on the wire with zero wheel
                # speeds and all knives raised - recoverable when vision
                # returns; if the PC dies entirely the MCU watchdog latches.
                send(P.TYPE_NAV, P.pack_nav(0.0, 0.0))
                send(P.TYPE_TOOL, P.pack_tool(0.0, 0x07))
            else:
                pid.reset()
                send(P.TYPE_HEARTBEAT, b'')   # MANUAL/ESTOP keep-alive; MCU
                # releases AUTO to MANUAL on HEARTBEAT (P0-2 fix, 09-05).
                # ESTOP frame is sent once on the transition (see above);
                # MCU latches and only a physical reset clears it.

            t_rel = t0 - t0_first
            if not args.no_gui:
                import cv2
                vis = draw_overlay(res)
                hud2 = 'STATE:%s  [A]uto [M]anual [E]stop [R]eset [Q]uit' % sm.state
                if rx is not None:
                    st = rx.last
                    if st is not None:
                        hud2 += '  MCU:m%d %.1fV %.1fA' % (st['mode'], st['battery_v'],
                                                           st['current_a'])
                    if rx.bad:
                        hud2 += '  bad:%d' % rx.bad
                    if rx.stale(t0):
                        hud2 += '  MCU:STALE'
                cv2.putText(vis, hud2,
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
                    prev = sm.state
                    sm.estop('key')
                    if sm.state != prev and sm.state in ('ESTOP', 'LIFT'):
                        send(P.TYPE_ESTOP, b'')   # keyboard path must wire too (P0-4)
                elif k == ord('r'):
                    sm.clear_estop()   # TEST ONLY; real reset is physical

            wr.writerow(['%.3f' % t_rel, fid, sm.state,
                         res['status'],
                         '%.4f' % lat_m if usable else '',
                         '%.4f' % (comp.compensate(lat_m, rate.rate)) if usable else '',
                         '%.3f' % vl, '%.3f' % vr,
                         '%.1f' % tool_mm, '%.3f' % res['confidence'],
                         '%.1f' % latency,
                         rx.last['mode'] if rx and rx.last else '',
                         '%.2f' % rx.last['battery_v'] if rx and rx.last else '',
                         rx.good if rx else '', rx.bad if rx else ''])
            n += 1
            if n % 20 == 0:
                print('[%d] %s lat=%.3fm vL=%.2f vR=%.2f tool=%.1fmm %.0fms' % (
                    fid, sm.state, lat_m, vl, vr, tool_mm, latency))
    print('done: %d frames -> %s' % (n, csv_path))


if __name__ == '__main__':
    main()
