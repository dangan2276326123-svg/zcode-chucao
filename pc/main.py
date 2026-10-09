# -*- coding: utf-8 -*-
"""PC-side main loop: perception -> state machine -> control -> UDP.

Two modes:
  replay  — frames from a video file / image dir; full chain without hardware
  live    — frames from the GStreamer UDP stream; control frames sent via UDP

Usage:
  python pc/main.py --source field_video1.avi                # replay
  python pc/main.py --live --pi-ip 192.168.127.10            # live (X5 bridge)
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
# E3 批 1b：线上发什么帧由 wire 决定，执行许可位与档案号由 vehicle_profile 决定。
# 这两件事在 pc/wire.py 与 pc/vehicle_profile.py 里各自只有一份事实，这里只引用。
from pc import vehicle_profile
from pc import wire

PI_IP = '192.168.127.10'        # RDK X5 (bridge) — control UDP target
PI_PORT = 9000
STREAM_HOST = '192.168.127.10'  # TCP multipart MJPEG server = X5 (R3)
STREAM_PORT = 5000
ESTOP_LAT_LIMIT = 0.05      # m, |lateral| beyond -> estop (v0.4 §7.2)
VISION_LOSS_S = 2.0         # s of unusable frames -> vision_loss event
# E2-4 (review 2026-09-21): the live video read used to be a blocking
# generator, so an open-but-silent stream parked the whole control loop in
# recv() -- no STATUS polling, no GUI, and VISION_LOSS_S could never fire.
# The loop now polls a bounded feed.  FRAME_MAX_AGE_S counts from the LOCAL
# arrival of the last byte of a frame, not from anything the camera stamped
# (this stream carries no capture timestamps), so it is a LOWER BOUND on
# glass-to-PC latency -- keep it separate from the four B8 delay columns.
FRAME_MAX_AGE_S = 0.5       # s: older than this, do not steer by the frame
STREAM_POLL_S = 0.02        # s: how often the loop asks the feed for a beat


# What perception "returns" on a beat with no fresh frame.  Its status is
# intentionally NOT one of dual/left_only/right_only, so the existing
# `usable` test goes False with no special-casing and the vision-loss
# timer starts.  Re-running perception on the last buffered image would
# make a frozen wall look like a healthy line, which is the failure this
# branch exists to avoid.
NO_FRAME_RESULT = {'status': 'no_frame', 'lateral_px': None,
                   'confidence': 0.0, 'tool_offset_px': None,
                   'nav_far': {}, 'nav_near': {}}


class FrameSource:
    """Unified frame iterator over a video/dir (replay) or RTP stream (live)."""

    def __init__(self, source=None, live=False, step=1,
                 stream_host=STREAM_HOST, stream_port=STREAM_PORT):
        self.live = live
        self.step = step
        self.stream_host = stream_host
        self.stream_port = stream_port
        self.feed = None          # live only; set when _from_stream starts
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
        """One entry per control-loop beat; **None means no fresh frame**.

        E2-4: deliberately not a pass-through of the socket.  Reading lives on
        the StreamFeed thread, so a link that stays open but stops delivering
        bytes yields None beats instead of freezing us here, and a frame older
        than FRAME_MAX_AGE_S is dropped rather than steered by.  ``self.feed``
        stays reachable so the HUD/CSV can report age and the counters.
        """
        from common.mjpeg import StreamFeed
        self.feed = StreamFeed(self.stream_host, self.stream_port,
                               recv_timeout=STREAM_POLL_S)
        try:
            while True:
                frame, _age = self.feed.get(max_age_s=FRAME_MAX_AGE_S)
                yield frame
                time.sleep(STREAM_POLL_S)
        finally:
            self.feed.close()

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

    # ---- E3 spec §6：车辆档案必须在任何控制量之前读到 ----
    # 读不到 / 值非法就抛，**不许带错参数进无人**：档案里的 profile_id 决定
    # 米<->像素换算，permit 决定门 N 期间刀能不能落。loader 的契约是
    # "不存在与打不开都是 ValueError"，这里故意不 catch——让它把进程停下来。
    # 位置在加载感知权重之前：配置错了不该先花十秒钟再告诉操作者。
    cfg_profile = vehicle_profile.load()
    permit = cfg_profile['permit']
    profile_id = cfg_profile['profile_id']
    print('vehicle profile: id=%d permit=%d file=%s' % (
        profile_id, permit, os.path.basename(cfg_profile['path'])))

    from pc.perception import Perception
    per = Perception()
    sm = StateMachine(permit=permit)      # E3 §5.3：门 N 下 AUTO 也必须提刀
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
    last_vis = None   # last drawn overlay (E2-4)
    t_prev = time.time()
    t0_first = t_prev
    n = 0

    with open(csv_path, 'w', newline='', encoding='utf-8') as fcsv:
        wr = csv.writer(fcsv)
        wr.writerow(wire.RUN_LOG_COLUMNS)     # 24 列；E3 的六列在 pc/wire.py 里定义
        src = FrameSource(args.source, args.live, args.step,
                          args.stream_host, args.stream_port)
        for fid, frame in enumerate(src.frames()):
            t0 = time.time()
            dt = max(t0 - t_prev, 1e-3)
            t_prev = t0
            prev_state = sm.state   # captured BEFORE any state event (P0-4)

            drain_status(t0)
            # E2-4: the feed snapshot exists on every beat, frame or not.
            _st, _seq, _age = src.feed.snapshot() if src.feed else ({}, 0, None)

            res = NO_FRAME_RESULT if frame is None else per.process(frame)
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
                # ESTOP 帧**只在跳变这一拍发一次**（E3 §5.1）；稳态由下面的
                # wire.frames_for_state('ESTOP', ...) 返回 []，也就是 PC 在线上
                # 完全静默——旧代码在这里还会发 HEARTBEAT keep-alive，那是
                # 有意的行为变更，不是漏掉（交互见 task-6-report.md 的失联一节）。
                if sm.state == 'ESTOP':
                    send(P.TYPE_ESTOP, b'')

            # ---- control by state（E3 §5.1：状态优先，持权期间永不发心跳）----
            # 原来这里是三分支（AUTO+usable / LIFT / else），"AUTO 但这一帧不可用
            # 且未满 2 秒"会掉进 else 发心跳，固件收心跳就把权限交回遥控，而 PC
            # 状态与 run_log 仍写 AUTO（codex 新发现一）。发帧内容整个交给 wire。
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
            else:
                # 这一拍不驱动工具轴，清积分。两半边都要：
                #   LIFT / "AUTO 但这一拍瞎了"——仍持权，帧仍由 wire 给（速度锁零 + 提刀）；
                #   MANUAL / ESTOP——旧代码在这里也清；brief 的片段写成
                #   `elif sm.holds_authority: pid.reset()` 就把这一半省了，积分会跨过
                #   急停活着，恢复那一拍刀带着 windup 顶出去。那是旧不变量的回归，
                #   不是新行为（见 task-6-report.md §4 第 5 条）。
                pid.reset()

            for ftype, payload in wire.frames_for_state(
                    sm.state, usable, vl, vr, tool_mm, permit):
                send(ftype, payload)

            t_rel = t0 - t0_first
            if not args.no_gui:
                import cv2
                if frame is not None:
                    last_vis = draw_overlay(res)
                # E2-4: while the stream is silent we keep repainting the LAST
                # overlay with a NO-FRAME banner rather than freezing the UI --
                # the operator must still be able to press [M]/[E] on a beat
                # with no vision.  Displaying it is not steering by it: `res`
                # above is NO_FRAME_RESULT, so control never reads these pixels.
                if last_vis is None:
                    import numpy as np
                    last_vis = np.zeros((720, 960, 3), 'uint8')
                vis = last_vis.copy()
                hud2 = ('STATE:%s  permit:%d  cfg:%d  '
                        '[A]uto [M]anual [E]stop [R]eset [C]onfirm [Q]uit'
                        % (sm.state, permit, profile_id))
                if sm.needs_confirm:
                    # E3 §5.2 L2.5：闸门是一次性的，所以必须让操作者看得见
                    # "现在按 [C] 才算数"（视觉已恢复时按了不生效，见按键处）。
                    hud2 += '  L2.5 CONFIRM REQUIRED - press [C] while blind'
                if rx is not None:
                    st = rx.last
                    if st is not None:
                        hud2 += '  MCU:m%d %.1fV %.1fA' % (st['mode'], st['battery_v'],
                                                           st['current_a'])
                        if st.get('v') == 2:
                            # spec §5.4：档案号 / 权限来源 / 主循环计数 / build 号
                            hud2 += '  prof:%d auth:%d loop:%d build:%02X' % (
                                st['profile'], st['authority'],
                                st['loop_alive'], st['build_id'])
                            if rx.loop_stalled():
                                hud2 += '  !!LOOP-STALLED!!'
                        else:
                            hud2 += '  MCU:STATUS-v1'   # 旧固件没这四个字段，不留白
                    if rx.bad:
                        hud2 += '  bad:%d' % rx.bad
                    if rx.stale(t0):
                        hud2 += '  MCU:STALE'
                    _rj = rx.reject_text()          # 人话文案，不是十六进制
                    if _rj:
                        hud2 += '  reject:%s' % _rj
                if frame is None:
                    hud2 += '  *** NO FRAME - vision lost ***'
                if _age is not None:
                    hud2 += '  age:%dms' % round(_age * 1000)
                if _st.get('recv_timeouts') or _st.get('link_drops'):
                    hud2 += '  silent:%d drop:%d' % (
                        _st.get('recv_timeouts', 0), _st.get('link_drops', 0))
                cv2.putText(vis, hud2,
                            (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
                cv2.imshow('weeder', vis)
                k = cv2.waitKey(1) & 0xFF
                if k == ord('q'):
                    break
                elif k == ord('a'):
                    # E3 §3.1：申请无人 = 显式 MODE 帧，不再靠"开始发 NAV"隐含进 AUTO
                    send(P.TYPE_MODE, P.pack_mode(P.MODE_REQ_AUTO, profile_id))
                    sm.go_auto(confidence_ok=usable)
                elif k == ord('m'):
                    send(P.TYPE_MODE, P.pack_mode(P.MODE_REQ_MANUAL, profile_id))
                    sm.go_manual()
                elif k == ord('e'):
                    prev = sm.state
                    sm.estop('key')
                    if sm.state != prev and sm.state in ('ESTOP', 'LIFT'):
                        send(P.TYPE_ESTOP, b'')   # keyboard path must wire too (P0-4)
                elif k == ord('r'):
                    # A3 单确认解除急停；清锁 != 授权——固件按 §4.6 的三条件复查后
                    # 回到 MANUAL，不会因此直接进无人。真复位仍是物理复位。
                    send(P.TYPE_MODE, P.pack_mode(P.MODE_REQ_CLEAR_ESTOP, profile_id))
                    sm.clear_estop()
                elif k == ord('c'):
                    # L2.5 人工确认。**闸门是一次性的**：confirm_continue() 清掉
                    # needs_confirm 之后，这条恢复链路上就只剩调用方传的
                    # confidence_ok 独任（go_auto 的另一个条件）。所以这里做最小收口：
                    # 只在"确实需要确认、且视觉仍不可用"（= L2.5 自己的现场：已停车、
                    # 刀已提）时才生效；视觉已恢复时的误按不许消费这道闸门
                    # （Task 3 审查缺口 B）。"一次性"这件事要落进台账（Task 10）。
                    if sm.needs_confirm and not usable:
                        sm.confirm_continue()
                    else:
                        print('L2.5 confirm ignored: needs_confirm=%s usable=%s'
                              ' (press [C] only while vision is still lost)'
                              % (sm.needs_confirm, usable))

            # lat_comp_m 沿用原来的表达式（延迟补偿后的横向误差）。两个横向量都
            # 只在**可用**那一拍写值，不可用写空：日志里的 0.0000 读起来像
            # "实测正好压在行上"，把没测到当成测到了就是伪造证据（旧实现同样是空）。
            lat_comp_m = comp.compensate(lat_m, rate.rate) if usable else None
            wr.writerow(wire.run_log_row(
                t_rel, fid, sm.state, res,
                lat_m if usable else None, lat_comp_m, vl, vr, tool_mm, latency,
                rx.last if rx else None, (_st, _seq, _age), permit,
                rx_good=rx.good if rx else '', rx_bad=rx.bad if rx else '',
                recv_timeouts=_st.get('recv_timeouts', ''),
                link_drops=_st.get('link_drops', '')))
            n += 1
            if n % 20 == 0:
                print('[%d] %s lat=%.3fm vL=%.2f vR=%.2f tool=%.1fmm %.0fms%s' % (
                    fid, sm.state, lat_m, vl, vr, tool_mm, latency,
                    '' if frame is not None else '  NO-FRAME(stream silent)'))
    print('done: %d frames -> %s' % (n, csv_path))


if __name__ == '__main__':
    main()
