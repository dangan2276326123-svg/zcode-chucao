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

# ---- E3 批 1b Task 6 fix round 1（审查 I-2 / I-6 / I-4）----
# I-2 裁定：**"进无人"和"继续跑"是两个风险等级，各一份判据，不许共用一个变量**。
#   usable           —— "这一拍还能继续跑"：状态名有效 + confidence > 0.01
#                       （循环里算的就是它，判据不变，还含"拿不到横向量就 False"）。
#   ENTER_MIN_CONF   —— "允许把车交给 PC"：在 usable 之上再加的一道，只在按 [A]
#                       申请无人那一拍用。base 的进无人判据本来就是 >0.05；Task 6
#                       接线时把它换成了 usable，等于把出车门槛降到 0.1% 的行像素
#                       支撑（confidence = min(1, support*10)，见 pc/perception.py
#                       :154,:163），而且单侧墙也算数。L2.5 闸门是一次性的、这道
#                       判据是闸门之后唯一剩下的东西——它必须自己站住。
ENTER_MIN_CONF = 0.05       # 进无人的置信度门槛（>），与 usable 的 0.01 各司其职
# I-6（spec §5.2 的 L1：仅单侧墙有效）。**系数是初始值，待台架整定**；接线与
# 降级事件计数不可延后（控制器裁定）——将来整定只改这个数，不改这段逻辑。
L1_SPEED_SCALE = 0.5        # x v_nominal，spec §5.2 L1（初始值，待台架整定）
# I-4：HUD 拆行 + 每行字符预算。预算的来路（本机 cv2 5.0.0 实测，与下面 putText
# 完全同参：FONT_HERSHEY_SIMPLEX、scale 0.7、thickness 2）：
#   可打印 ASCII 全集 95 个字符 = 1063 px => 平均 11.19 px/字符；
#   HUD 画在**最窄的那块画布**上——没有帧可画时兜底的是 np.zeros((720, 960))，
#   960 / 11.19 = 85.8 => 预算 85 字符。
#   真实 HUD 串小写偏多，实测 9.5~9.8 px/字符，85 字符约 835 px，加上 x=10 的
#   原点仍落在 960 px 之内（所以 85 是"按最坏字形的平均值算"的保守预算）。
#   旧实现是一整行、实测最坏 297 字符，被挤掉的正好是尾巴：prof/auth/loop/build、
#   !!LOOP-STALLED!!、MCU:STALE、reject——即"字段在代码里、不在屏幕上"。
#   测试侧另写一份同名预算（tests/test_control.py:_HUD_MAX_CHARS），两边不许漂，
#   由 test_hud_lines_are_short_and_ascii 钉住。
HUD_MAX_CHARS = 85
HUD_ORIGIN = (10, 40)       # 第一行的左下角
HUD_LINE_H = 30             # 行间距（px）
HUD_KEYS = '[A]uto [T]eleop [M]anual [E]stop [R]eset [C]onfirm [Q]uit'
# 手操档的方向键（W 直行 / S 左转 / D 右转）单列一行：它们不是「按一下切换」的状态键，
# 是每拍重读的「按住」键，混进上面那行会让人以为按一次就一直走（2026-10-13 手操 spec §4）。
HUD_TELEOP = 'HOLD [W]fwd [S]left [D]right  (release => stop; no reverse yet)'
AUTO_REFUSE_NOTICE_S = 3.0  # "AUTO REFUSED" 在 HUD 上停留多久（I-3：被拒必须看得见）


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


def _hud_wrap(tokens, max_chars=HUD_MAX_CHARS):
    """把一组 HUD 片段拼成若干行，每行不超过 max_chars 个字符（fix round 1 I-4）。

    只在片段边界上折行，两个空格相接。**单个片段本身就超长时照样独占一行**：
    宁可溢出也不截断——截断就是"这条告警其实没显示"，正是这条 finding 要治的病。
    空列表返回空列表（那一行干脆不画，不留一条空串占位）。
    """
    lines, cur = [], ''
    for tok in tokens:
        cand = tok if not cur else cur + '  ' + tok
        if len(cand) > max_chars and cur:
            lines.append(cur)
            cur = tok
        else:
            cur = cand
    if cur:
        lines.append(cur)
    return lines


def fresh_out_dir(out_dir, allow_overwrite=False):
    """`run_log.csv` 是以 `'w'` 打开的 —— 复用 `--out` 目录会把上一轮证据整份冲掉。

    10-14 台架实测：`results/tel_C23` 被同一个目录名连续覆盖三次，两份几百 KB 的读数
    当场没了（其中一份是唯一记录 `mcu_mode` 3→1 跳变的证据）。所以默认**拒绝启动**，
    要覆盖必须显式 `--overwrite`。返回 csv 路径，让调用处只有一个事实源。
    """
    path = os.path.join(out_dir, 'run_log.csv')
    if os.path.exists(path) and not allow_overwrite:
        raise SystemExit(
            'refusing to overwrite %s -- run_log.csv is opened with mode "w", '
            'so starting this run would destroy the previous evidence.\n'
            'Use a fresh --out directory, or pass --overwrite if you really mean it.'
            % path)
    os.makedirs(out_dir, exist_ok=True)
    return path


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
    ap.add_argument('--overwrite', action='store_true',
                    help='明知故犯地复用 --out 目录（默认拒绝：CSV 是覆盖写的）')
    args = ap.parse_args()

    csv_path = fresh_out_dir(args.out, args.overwrite)

    # ---- E3 spec §6：车辆档案必须在任何控制量之前读到 ----
    # 读不到 / 值非法就抛，**不许带错参数进无人**：档案里的 profile_id 决定
    # 米<->像素换算，permit 决定门 N 期间刀能不能落。loader 的契约是
    # "不存在与打不开都是 ValueError"，这里故意不 catch——让它把进程停下来。
    # 位置在加载感知权重之前：配置错了不该先花十秒钟再告诉操作者。
    cfg_profile = vehicle_profile.load()
    permit = cfg_profile['permit']
    profile_id = cfg_profile['profile_id']
    vehicle_tag = cfg_profile['log_tag']      # 台账 Pc-10：车型列，取消握手后的唯一凭据
    print('vehicle profile: id=%d permit=%d tag=%s file=%s' % (
        profile_id, permit, vehicle_tag, os.path.basename(cfg_profile['path'])))

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

    tx_this_beat = []   # T2：这一拍**真的写进 socket** 的帧型，run_log 的 tx_frames 列用它

    def send(ftype, payload):
        nonlocal seq
        if sock is None:      # replay mode: no radio, no commands leave the PC
            return
        from common import protocol as P
        sock.sendto(P.pack_frame(ftype, payload, seq & 0xFFFF), pi)
        tx_this_beat.append(ftype)   # 在 sendto 之后：抛了就不算发过（与 bench_status 同纪律）
        seq += 1

    from common import protocol as P

    last_good = None
    last_vis = None   # last drawn overlay (E2-4)
    t_prev = time.time()
    t0_first = t_prev
    n = 0
    # ---- fix round 1 的三件事的循环状态 ----
    handshake_sent = False   # I-5：MODE(MODE_REQ_PROFILE) 只在开机和"检测到 MCU 重启"时发
    resync_seen = 0          # 上一次据此判"MCU 重启"的 rx.resynced 值
    l1_prev = False          # I-6：上一拍是否在 L1（单侧墙）里 —— 计数按边缘
    l1_events = 0            # 累计 L1 降级事件数（进 run_log 的 l1_events 列 + HUD）
    auto_refusal = ''        # I-3：最近一次 [A] 被拒的原因，HUD 上要看得见
    t_refuse = 0.0
    # 手操档（2026-10-13 spec §4）只记两件事：最后一次方向键是哪个、什么时候按的。
    # 归零判据是超时而不是松开事件——cv2.waitKey 没有可靠的松开事件，拿它当存在性判据
    # 会让车多走一段，而那一段在田间是压苗。
    tele_key = None
    tele_key_t = 0.0
    # 手操转向档位（NAV 的 flags 字节）：`g` 循环 直行->左->右。默认直行 = 现状，
    # 所以本批之后不按键的行为与之前逐字相同。
    tele_gear = wire.GEAR_STRAIGHT

    with open(csv_path, 'w', newline='', encoding='utf-8') as fcsv:
        wr = csv.writer(fcsv)
        wr.writerow(wire.RUN_LOG_COLUMNS)     # 列定义与行构造都在 pc/wire.py（列数不在这里写，AGENTS 清单第 8 条）
        src = FrameSource(args.source, args.live, args.step,
                          args.stream_host, args.stream_port)
        for fid, frame in enumerate(src.frames()):
            t0 = time.time()
            # beat_gap_s 用**未钳位**的原始间隔：`dt` 被 max(...,1e-3) 保护过，
            # 是给 PID 用的；而我们要看的恰恰是「这一拍隔了多久没跑」，钳位会把它抹平。
            beat_gap = t0 - t_prev
            dt = max(beat_gap, 1e-3)
            t_prev = t0
            prev_state = sm.state   # captured BEFORE any state event (P0-4)
            del tx_this_beat[:]      # T2：这一列只描述这一拍；上一拍的帧型不许漂过来

            drain_status(t0)
            # ---- I-5：上电档案握手（MODE 0x20 + 档案号），必须早于任何控制帧 ----
            # 固件 enter_unmanned() 的**第一条件**就是 handshake_ok，而它是 RAM 位：
            # MCU 一重启就清零（spec §4.2/§6）。Python 侧此前零调用点 ⇒ 批 1a 烧上去
            # 后永远 reject=0x01，门 N 步 4 逻辑上不可能通过，而且会被 B2 那道
            # fail-closed 遮住，第一次排障会误判成"档案不匹配"。
            # 重启检测用 rx.resynced（StatusReceiver 由"序号回退后连续递增的被拒 run"
            # 得出，见 pc/status_rx.py 里 E1 第 (1) 项修复那段）——这是接收器自己
            # 承认的信号，不在这里另造一套判据。重新同步只恢复状态显示，
            # **不代为放行任何权限**。
            resync = rx.resynced if rx is not None else 0
            if not handshake_sent or resync != resync_seen:
                send(P.TYPE_MODE, P.pack_mode(P.MODE_REQ_PROFILE, profile_id))
                if sock is not None:      # 回放模式 send() 是空操作，别谎报发出去了
                    print('E3: profile handshake sent (id=%d, reason=%s)'
                          % (profile_id, 'boot' if not handshake_sent else 'mcu-reboot'))
                handshake_sent = True
                resync_seen = resync
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

            # ---- 感知分级 L1 的落点（spec §5.2 / fix round 1 I-6）----
            # 位置在状态机事件**之后**：这一拍究竟是不是"PC 正在按 L1 降速跑"，
            # 取决于跳变之后的状态。MANUAL/LIFT/ESTOP 下 PC 没在开车，把那些拍
            # 计进降级事件会把"操作员手动路过一段单侧墙"混进无人作业的计数里。
            # 计数按**事件**（进入 L1 的边缘）而不是按拍：一次 10 秒的单侧墙若按拍
            # 计，日志里会读成上百次降级，"记一次降级事件"的口径就废了。
            l1_now = (sm.state == 'AUTO' and usable
                      and res['status'] in ('left_only', 'right_only'))
            if l1_now and not l1_prev:
                l1_events += 1
            l1_prev = l1_now

            # ---- control by state（E3 §5.1：状态优先，持权期间永不发心跳）----
            # 原来这里是三分支（AUTO+usable / LIFT / else），"AUTO 但这一帧不可用
            # 且未满 2 秒"会掉进 else 发心跳，固件收心跳就把权限交回遥控，而 PC
            # 状态与 run_log 仍写 AUTO（codex 新发现一）。发帧内容整个交给 wire。
            vl = vr = 0.0
            tool_mm = 0.0
            if sm.state == 'TELEOP':          # 字面量，与本文件其余判据同一写法；单测把 StateMachine 换成工厂函数，引类属性会撞
                # 手操档：两侧速度就是「按住哪个键 + 按住多久」，视觉那条链整个不参与。
                # 钳位（0.1 上限、第一阶段负值钳 0）在 wire.frames_for_state 里再做一遍——
                # 两层都要，发帧那一道不依赖这里的自觉。
                vl, vr = wire.teleop_speeds(tele_key, time.time() - tele_key_t)
                pid.reset()          # 这一拍不驱动工具轴，积分不许跨过手操段
            elif sm.state == 'AUTO' and usable:
                tool_px = res.get('tool_offset_px')
                if tool_px is None:      # far field ok, near field lost (P1-3)
                    tool_px = 0.0
                e_dot = rate.update(lat_m, dt)   # filtered lateral rate (ė)
                lat_c = comp.compensate(lat_m, e_dot)
                # I-6：L1（仅单侧墙有效）降速。用的是 wheel_speeds 已有的 speed_mps
                # 形参（pc/control.py:100-102），语义不变——它就是"这一拍的名义前进
                # 速度"；不这么接就得改 control.py 的语义，那是本任务明令不许做的。
                v_target = drive.v_nominal * (L1_SPEED_SCALE if l1_now else 1.0)
                vl, vr = drive.wheel_speeds(lat_c, err_rate=e_dot,
                                            speed_mps=v_target)   # PD(e,ė), H4.6-A
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
                    sm.state, usable, vl, vr, tool_mm, permit, gear=tele_gear):
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
                # ---- HUD（fix round 1 I-4：拆多行、每行 <= HUD_MAX_CHARS、纯 ASCII）----
                # 四组：状态/权限、MCU 回显、告警、键位图例。哪组过预算就在片段边界
                # **折行**，不截断——截断等于把那条告警藏起来，而"字段在代码里、
                # 不在屏幕上"正是这条 finding 本身。
                state_bits = ['STATE:%s' % sm.state, 'permit:%d' % permit,
                              'cfg:%d' % profile_id,
                              'vL:%.2f vR:%.2f' % (vl, vr),
                              'tool:%.1fmm' % tool_mm]
                if l1_now:        # I-6：这一拍真的在按 L1 降速跑
                    state_bits.append('L1 x%g' % L1_SPEED_SCALE)
                state_bits.append('l1:%d' % l1_events)   # 累计降级事件数（I-6）
                mcu_bits, alerts = [], []
                if rx is None:
                    mcu_bits.append('MCU:no-link')       # 回放/无链路：不留白
                else:
                    st = rx.last
                    if st is not None:
                        mcu_bits.append('MCU:m%d %.1fV %.1fA'
                                        % (st['mode'], st['battery_v'],
                                           st['current_a']))
                        if st.get('v') == 2:
                            # spec §5.4：档案号 / 权限来源 / 主循环计数 / build 号
                            mcu_bits += ['prof:%d' % st['profile'],
                                         'auth:%d' % st['authority'],
                                         'loop:%d' % st['loop_alive'],
                                         'build:%02X' % st['build_id']]
                            if rx.loop_stalled():
                                alerts.append('!!LOOP-STALLED!!')
                        else:
                            mcu_bits.append('MCU:STATUS-v1')  # 旧固件没这四个字段
                        # reject 进 HUD 用 ASCII 短码：REJECT_TEXT 是中文人话，而
                        # cv2.putText 画不出 CJK，进 HUD 就是一排方框，比不显示还难
                        # 排障（报告 Concern 4）。短码表在 pc/wire.py:REJECT_SHORT，
                        # **仍然不是十六进制**（spec §5.4）。中文全文这条**还没有生产
                        # 调用点**：CSV 的 reject 列存的是数字码，stdout 这里也没打全文
                        # （`status_rx.reject_text()` 只被单测调用），spec §5.4 的"人话"
                        # 到批 1b 为止是「已编码 + 待联调」，不是"已经在屏幕上"。
                        _rj = wire.reject_short(st.get('reject'))
                        if _rj:
                            alerts.append('rej:%s' % _rj)
                    if rx.bad:
                        alerts.append('bad:%d' % rx.bad)
                    if rx.stale(t0):
                        alerts.append('MCU:STALE')
                if sm.needs_confirm:
                    # E3 §5.2 L2.5：闸门是一次性的，必须让操作者看得见"现在按 [C]
                    # 才算数"。文案跟着 I-1 的两个分支走（视觉仍坏着 / 已交回人工）。
                    alerts.append('L2.5 CONFIRM - press [C] while blind or in [M]anual')
                if auto_refusal and time.time() - t_refuse > AUTO_REFUSE_NOTICE_S:
                    auto_refusal = ''            # 过期就不许一直挂着（I-3 的 TTL）
                if auto_refusal:
                    alerts.append(auto_refusal)  # I-3：被拒不许只剩"按了没反应"
                hud_extra = []
                if sm.state == 'TELEOP':          # 字面量，与本文件其余判据同一写法；单测把 StateMachine 换成工厂函数，引类属性会撞
                    # 手操时人必须一眼看见两件事：现在是谁在说话、这一拍给出去多少。
                    # 松手归零要看得见——看不见就会有人以为「按了没反应」是坏了。
                    alerts.append('TELEOP v=%.2f/%.2f gear:%s [g]=switch'
                                % (vl, vr, wire.gear_text(tele_gear)))
                    hud_extra = [HUD_TELEOP]
                if frame is None:
                    alerts.append('*** NO FRAME - vision lost ***')
                if _age is not None:
                    alerts.append('age:%dms' % round(_age * 1000))
                if _st.get('recv_timeouts') or _st.get('link_drops'):
                    alerts.append('silent:%d drop:%d' % (
                        _st.get('recv_timeouts', 0), _st.get('link_drops', 0)))
                hud_lines = []
                for bits, color in ((state_bits, (255, 255, 0)),
                                    (mcu_bits, (255, 255, 0)),
                                    (alerts, (0, 0, 255)),
                                    ([HUD_KEYS] + hud_extra, (255, 255, 255))):
                    hud_lines += [(ln, color) for ln in _hud_wrap(bits)]
                for i, (ln, color) in enumerate(hud_lines):
                    # 每行自己的 y：都画在同一个 y 上等于叠在一起，仍然看不见。
                    cv2.putText(vis, ln,
                                (HUD_ORIGIN[0], HUD_ORIGIN[1] + i * HUD_LINE_H),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
                cv2.imshow('weeder', vis)
                k = cv2.waitKey(1) & 0xFF
                if k == ord('q'):
                    break
                elif k == ord('a'):
                    # E3 §3.1：申请无人 = 显式 MODE 帧，不再靠"开始发 NAV"隐含进 AUTO。
                    # fix round 1 I-3：**先问状态机，它点头了才把申请发到线上**。旧写法
                    # 是无条件、且在 go_auto() **之前**发——ESTOP 下 go_auto() 必返回
                    # False，于是 PC 停在 ESTOP 一帧不发，而 MCU 已经收到申请：批 1a
                    # 之后四条件一旦成立就授权，PC 静默 ⇒ 500 ms 链路看门狗把 MCU 闩死
                    # （`f0ecf73:firmware/retrofit.c:316-318`；10-10 批 1a Task 8 定身份：根下那份影子副本已由 Task 6 删除、裸路径不可解析，正身里同一条看门狗在 `:566-567`，批 1a 未改它）。🔴 10-10 作者改判（撤销"现场拨档"那条判据，
                    # 契约 §4.2 条件③ / A4）：原来下面那两句"今天不咬人只是因为
                    # FIELD_SW_CALIBRATED=0 也在挡，危害窗口在 B2 填表之后才打开"**已成假话**——
                    # 那个宏批 1a 根本不写入固件，危害窗口也不由填 B2 那张表打开。今天不咬人的
                    # 真正原因是现固件把 MODE 整条丢掉（retrofit.c:60-75 没有 TYPE_MODE 分支），
                    # 而批 1a 之后不咬人靠的就是上面这条"先问状态机、点头才发"的顺序。
                    # fix round 1 I-2：进无人的门槛是 ENTER_MIN_CONF，不跟着 usable
                    # 一起降到 0.01——"进无人"与"继续跑"各一份判据（控制器裁定）。
                    pre_state, pre_gate = sm.state, sm.needs_confirm
                    enter_ok = usable and res['confidence'] > ENTER_MIN_CONF
                    if sm.go_auto(confidence_ok=enter_ok):
                        send(P.TYPE_MODE, P.pack_mode(P.MODE_REQ_AUTO, profile_id))
                        auto_refusal = ''
                    else:
                        why = ('ESTOP' if pre_state == 'ESTOP' else
                               'L2.5' if pre_gate else 'CONF-LOW')
                        auto_refusal = 'AUTO REFUSED:%s' % why
                        t_refuse = time.time()
                        print('AUTO request refused: reason=%s state=%s '
                              'needs_confirm=%s usable=%s conf=%.2f'
                              ' (ENTER_MIN_CONF=%.2f)'
                              % (why, pre_state, pre_gate, usable,
                                 res['confidence'], ENTER_MIN_CONF))
                elif k == ord('t'):
                    # 手操档进档（spec §2）：门槛比无人少一道（不查视觉信心、不消费 L2.5
                    # 闸门），但顺序规矩一样不能少——先问状态机，它点头才把申请发上线。
                    # 反过来的话，急停锁存下 PC 一帧不发而 MCU 已收到申请（同 [A] 的 I-3）。
                    pre_state = sm.state
                    if sm.go_teleop():
                        send(P.TYPE_MODE, P.pack_mode(P.MODE_REQ_TELEOP, profile_id))
                        auto_refusal = ''
                    else:
                        auto_refusal = 'TELEOP REFUSED:ESTOP'
                        t_refuse = time.time()
                        print('TELEOP request refused: state=%s' % pre_state)
                elif k == ord('g'):
                    # 转向档位：直行 -> 左 -> 右 -> 直行。横移档不在循环里（几何常数未定，
                    # 见 pc/wire.py 的 GEAR_LATERAL 注释与台账 Hw-23）。
                    tele_gear = wire.cycle_gear(tele_gear)
                    print('TELEOP gear -> %s (%d)' % (wire.gear_text(tele_gear), tele_gear))
                elif k in (ord('w'), ord('s'), ord('d')):
                    # 方向键只在手操档里有意义。不在手操时也记时间戳，但发帧那条路不进
                    # TELEOP 分支，所以不会偷偷把速度塞给 AUTO。
                    tele_key = chr(k)
                    tele_key_t = time.time()
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
                    # 这条**保持无条件**（控制器裁定在 A3 授权范围内）：解除急停的
                    # 申请本来就该在 PC 不持权时也能发出去。
                    send(P.TYPE_MODE, P.pack_mode(P.MODE_REQ_CLEAR_ESTOP, profile_id))
                    sm.clear_estop()
                elif k == ord('c'):
                    # L2.5 人工确认。**闸门是一次性的**：confirm_continue() 清掉
                    # needs_confirm 之后，这条恢复链路上就只剩调用方传的 confidence_ok
                    # 独任（go_auto 的另一个条件），所以"什么时候允许消费闸门"要收口。
                    # fix round 1 I-1：旧收口是 `needs_confirm and not usable`，结果
                    # 视野一旦恢复就**永远清不掉**——C 被拒（usable 为真）、A 也被拒
                    # （闸门还在），闸门只能靠"视觉再坏一次"才清得掉，门 N 的进无人
                    # 就此锁死（审查者内存复现：200 拍内 AUTO 不可达；main 从不主动
                    # 调 vision_ok()，所以"停在 LIFT 而 usable 为真"是可达状态）。
                    # 现在两个分支都能消费：
                    #   not usable            —— L2.5 自己的现场：已停车、刀已提；
                    #   sm.state == 'MANUAL'  —— 视觉已恢复但车已交回人工：操作员就在
                    #                            驾驶位，这次的确认不可能是误按。
                    # ESTOP 两个分支都不给过，而且 confirm_continue() 自己也拒绝（双
                    # 保险，见 pc/state_machine.py 的 fail-closed 契约）。
                    # "一次性"这件事仍要落进台账（Task 10，报告 Concern 6）。
                    if (sm.needs_confirm
                            and (not usable or sm.state == 'MANUAL')
                            and sm.confirm_continue()):
                        print('L2.5 confirmed: gate cleared (state=%s usable=%s)'
                              % (sm.state, usable))
                    else:
                        # Minor 2：被拒的原因不止"视觉已恢复"那一种——ESTOP 下
                        # needs_confirm 也可以是真，同样被拒但原因完全不同。提示里
                        # 带上 state，否则现场会照着"等视觉坏掉再按"去排障。
                        print('L2.5 confirm ignored: needs_confirm=%s usable=%s'
                              ' state=%s (press [C] while vision is still lost,'
                              ' or in MANUAL once it has recovered)'
                              % (sm.needs_confirm, usable, sm.state))

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
                link_drops=_st.get('link_drops', ''),
                l1_events=l1_events,           # I-6：降级事件落到时间轴上
                tx_frames=wire.tx_frames_text(tx_this_beat),   # T2：这一拍线上真有什么
                nav_flags=(str(tele_gear) if sm.state == 'TELEOP' else ''),
                beat_gap_s='%.3f' % beat_gap,
                vehicle_tag=vehicle_tag))
            n += 1
            if n % 20 == 0:
                print('[%d] %s lat=%.3fm vL=%.2f vR=%.2f tool=%.1fmm %.0fms%s' % (
                    fid, sm.state, lat_m, vl, vr, tool_mm, latency,
                    '' if frame is not None else '  NO-FRAME(stream silent)'))
    print('done: %d frames -> %s' % (n, csv_path))


if __name__ == '__main__':
    main()
