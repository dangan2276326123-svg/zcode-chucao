# -*- coding: utf-8 -*-
"""边开边看 + 边录：笔记本从 X5 拉 MJPEG 流，窗口里看画面，同时分段录视频（2026-11-20）。

为什么不在车上录：作者要**边开边看**。相机同一时刻只给一路——要么车上本地录
（看不见画面），要么 X5 推流给笔记本（能看，录像也就在笔记本上）。这条走后者：

    X5（网桥上，仍是 192.168.127.10）:
        python3 vehicle/stream_pi.py --width 1920 --height 1080
    笔记本（网桥上，192.168.127.100）:
        python -B tools/watch_record.py --batch t20 --session-min 20

窗口里显示画面 + 录制状态（REC / 段号 / 剩余时间 / 链路 age / 丢线次数）；
到点自停，`q` 或 Ctrl-C 收尾。**录进文件的是干净帧**——状态字只画在窗口那份拷贝上，
往帧上写字等于换模型输入域（`fake_cam.py` 里同一条规矩）。

四条现场规矩：

1. **相机独占**：这条开着时不要同时在 X5 上跑 `record_local.py`（同一块 `/dev/video0`，
   两路同占没在这块板上实测过）。要本地录就先把笔记本这条停掉，反之亦然。
2. **断链就切段**：超过 `--gap-s` 没有新帧，当前段收尾、恢复后另起一段。AVI 没有时间戳，
   把一段的缺口留在文件中间会让回放时间轴悄悄压短；切成两段 + 日志里记一笔，缺口就是明的。
3. **每帧只写一次**：按 `StreamFeed` 的 `seq` 判新帧。同一个 `get()` 在没有新帧时会把
   上一张反复返回，照着写就是重复帧（`split_dataset` 那类近重复检查会骂人的）。
4. **落盘名与车上那一路同源**：`t{NN}_{MMDD}_v{NN}.avi`，走 `common/capture_naming.py`，
   `tools/extract_frames.py` 不改一行就能抽。日期用**笔记本的钟**（X5 的钟可能差几小时）。

⚠️ 四态：本工具**已编码 + 已本机单测 + 合成流往返**；真网桥、真相机、田间距离都没跑过。
第一次上田按 `docs/画线漏沙采集_20261120.md` 的"开录前"走，链路那一格（B8 拉距）
到今天仍是空的——本工具的 `link_drops`/`recv_timeouts` 就是给这一趟用的现场读数。
"""
import argparse
import csv
import datetime
import os
import shutil
import signal
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from common.capture_naming import BATCH_RE, video_next_index, video_path  # noqa: E402
from common.mjpeg import StreamFeed  # noqa: E402
from vehicle.record_local import estimate_mb, segment_durations  # noqa: E402

DEFAULT_HOST, DEFAULT_PORT = '192.168.127.10', 5000
VIDEO_FPS = 30.0                 # 与 stream_pi 的默认帧率一致（AVI 自报的帧率）
SEGMENT_S = 120.0                # 一段 = 一个条件
SESSION_MIN = 20.0               # 到点自停
GAP_S = 1.5                      # 超过这么久没新帧 = 断链：当前段收尾
MIN_FREE_MB = 1024.0             # 每次开段前至少留这么多，只防写满
OUT_DIR = os.path.join('data', 'paint_data', 'video')
WINDOW = 'watch_record'

LOG_HEADER = ['started', 'batch', 'day', 'file', 'planned_s', 'actual_s',
              'stream_frames', 'written', 'link_drops', 'recv_timeouts',
              'connect_fails', 'age_max_s', 'bytes', 'note']


def now_day():
    return datetime.datetime.now().strftime('%m%d')


def free_mb(folder):
    probe = folder
    while probe and not os.path.isdir(probe):
        parent = os.path.dirname(probe.rstrip(os.sep))
        probe = parent if parent and parent != probe else '.'
    return shutil.disk_usage(probe).free / 1048576.0


def hud_text(recording, tag, seg_elapsed, seg_budget, left_s, link_age,
             written, link_drops, recv_timeouts, gap_s=GAP_S):
    """窗口上那两行字（纯函数，测试直接读）。录进文件的帧不经过它。"""
    def mmss(s):
        s = max(0, int(s))
        return '%02d:%02d' % (s // 60, s % 60)

    if link_age is None:
        link = 'NO LINK (no frame yet)'
    elif link_age > gap_s:
        link = 'NO LINK %.1fs' % link_age
    else:
        link = 'link ok  age %.2fs' % link_age
    head = ('%s %s  seg %s/%s  left %s  |  %s'
            % ('REC ' if recording else 'WAIT', tag, mmss(seg_elapsed),
               mmss(seg_budget), mmss(left_s), link))
    tail = ('written %d  drops %d  timeouts %d'
            % (written, link_drops, recv_timeouts))
    return head, tail


def log_row(started, batch, day, path, planned_s, actual_s, stream_frames,
            written, link_drops, recv_timeouts, connect_fails, age_max_s,
            size, note):
    return [started, batch, day, path.replace('\\', '/'), '%.1f' % planned_s,
            '%.1f' % actual_s, str(stream_frames), str(written),
            str(link_drops), str(recv_timeouts), str(connect_fails),
            '%.2f' % age_max_s, str(size), note]


def append_log_row(lp, row):
    new = not os.path.exists(lp)
    with open(lp, 'a', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        if new:
            w.writerow(LOG_HEADER)
        w.writerow(row)


def cv2_writer(path, fps, size):
    import cv2
    vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*'MJPG'), fps, size)
    if not vw.isOpened():
        raise RuntimeError('打不开 VideoWriter：%s（路径/编码器？）' % path)
    return vw


class Recorder(object):
    """把一条 MJPEG 流录成分段 AVI。窗口只画在拷贝上，写入的是原帧。

    依赖（feed/时钟/写盘/显示）全部可注入：本机单测不碰 socket、不碰窗口，
    真机那一层由 `common.mjpeg.StreamFeed` 自己保证。
    """

    def __init__(self, feed, out_folder, batch, day, segment_s, session_s,
                 fps=VIDEO_FPS, gap_s=GAP_S, display=True,
                 writer_factory=None, clock=None, sleep=None, wall=None,
                 free_mb_fn=None, connect_timeout_s=10.0):
        self.feed = feed
        self.out = out_folder
        self.batch, self.day = batch, day
        self.segment_s, self.session_s = segment_s, session_s
        self.fps, self.gap_s = fps, gap_s
        self.display = display
        self.writer_factory = writer_factory or cv2_writer
        self.clock = clock or time.monotonic
        self.sleep = sleep or time.sleep
        self.wall = wall or (lambda: datetime.datetime.now().strftime('%H:%M:%S'))
        self.free_mb_fn = free_mb_fn or free_mb
        self.connect_timeout_s = connect_timeout_s
        self.log_path = os.path.join(out_folder,
                                     'watch_log_%s_%s.csv' % (batch, day))
        self._writer = None
        self._seg = None
        self._size = None            # 当前帧的 (w, h)
        self._writer_size = None     # 打开写盘时定的 (w, h)
        self._frame = None
        self._last_seq = None
        self._last_frame_t = None
        self._last_stats = {}
        self._stop = {'flag': False}
        self.rows = 0

    # ---- 段 -------------------------------------------------------------
    def _open_segment(self):
        free = self.free_mb_fn(self.out)
        if free < MIN_FREE_MB:
            print(u'🔴 盘只剩 %.0f MB ⇒ 停手（开段前至少留 %.0f MB）'
                  % (free, MIN_FREE_MB))
            self._stop['flag'] = True
            return False
        path = video_path(self.batch, self.day,
                          video_next_index(self.out, self.batch, self.day),
                          folder=self.out)
        self._writer = self.writer_factory(path, self.fps, self._size)
        self._writer_size = self._size
        self._seg = {'path': path, 't0': self.clock(), 'started': self.wall(),
                     'written': 0, 'age_max': 0.0,
                     'base': dict(self._last_stats)}
        print(u'[段] %s 开始 %s' % (os.path.basename(path),
                                    self._seg['started']))
        return True

    def _close_segment(self, note):
        if self._writer is None:
            return
        try:
            self._writer.release()
        finally:
            seg = self._seg
            actual = self.clock() - seg['t0']
            size = os.path.getsize(seg['path']) if os.path.exists(seg['path']) else 0
            now_stats = self._last_stats
            base = seg['base']
            row = log_row(
                seg['started'], self.batch, self.day, seg['path'],
                self.segment_s, actual,
                now_stats.get('frames', 0) - base.get('frames', 0),
                seg['written'],
                now_stats.get('link_drops', 0) - base.get('link_drops', 0),
                now_stats.get('recv_timeouts', 0) - base.get('recv_timeouts', 0),
                now_stats.get('connect_fails', 0) - base.get('connect_fails', 0),
                seg['age_max'], size, note)
            append_log_row(self.log_path, row)
            self.rows += 1
            print(u'[段] %s 收 %s：%.1f s、写 %d 帧、%.1f MB%s'
                  % (os.path.basename(seg['path']), note, actual,
                     seg['written'], size / 1048576.0,
                     u'' if note in ('segment', 'session-end', 'quit') else
                     u'（这段有缺口）'))
            self._writer = None
            self._seg = None

    # ---- 显示 -----------------------------------------------------------
    def _draw(self, frame, age, seg_elapsed, left_s, stats):
        import cv2
        vis = frame.copy()
        rec = self._writer is not None
        tag = (os.path.basename(self._seg['path']) if rec
               else '%s_%s' % (self.batch, self.day))
        head, tail = hud_text(rec, tag, seg_elapsed,
                              self.segment_s if rec else 0.0, left_s, age,
                              self._seg['written'] if rec else 0,
                              (stats or {}).get('link_drops', 0),
                              (stats or {}).get('recv_timeouts', 0),
                              self.gap_s)
        cv2.putText(vis, head, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (0, 255, 0) if rec else (0, 200, 255), 2)
        cv2.putText(vis, tail, (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (0, 255, 0), 1)
        cv2.imshow(WINDOW, vis)
        return cv2.waitKey(1) & 0xFF

    # ---- 主循环 ---------------------------------------------------------
    def _on_sigint(self, signum, frame):
        self._stop['flag'] = True
        print(u'\n[i] Ctrl-C：收尾当前段就停')

    def run(self):
        old = signal.signal(signal.SIGINT, self._on_sigint)
        note = 'stop'
        try:
            os.makedirs(self.out, exist_ok=True)
            t0 = self.clock()
            # 等第一帧：这里只报"流没来"，不猜是网桥还是相机
            deadline = t0 + self.connect_timeout_s
            while self.clock() < deadline and not self._stop['flag']:
                stats, seq, age = self.feed.snapshot()
                if seq:
                    frame, age2 = self.feed.get()
                    if frame is not None:
                        self._frame = frame
                        self._last_seq = seq
                        self._size = (frame.shape[1], frame.shape[0])
                        break
                if self.display:
                    self._draw_waiting()
                else:
                    self.sleep(0.05)
            if self._frame is None:
                raise RuntimeError(u'10 秒内没有帧：先在 X5 上确认 stream_pi 在跑、'
                                   u'网桥 ping 得通、port 对')
            if self.display:
                import cv2
                cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
                cv2.resizeWindow(WINDOW, 960, 540)

            while not self._stop['flag']:
                elapsed = self.clock() - t0
                left = max(0.0, self.session_s - elapsed) if self.session_s else 0.0
                if self.session_s and elapsed >= self.session_s:
                    note = 'session-end'
                    break

                stats, seq, age = self.feed.snapshot()
                self._last_stats = dict(stats or {})
                fresh = seq is not None and seq != self._last_seq
                frame = None
                if fresh:
                    frame, age2 = self.feed.get()
                    if frame is not None:
                        self._frame = frame
                        self._last_seq = seq
                        self._size = (frame.shape[1], frame.shape[0])
                        age = age2

                # 断链：超过 gap_s 没写新帧 ⇒ 当前段收尾（缺口别留在段中间）
                if (self._writer is not None and self._last_frame_t is not None
                        and self.clock() - self._last_frame_t > self.gap_s):
                    self._close_segment('link-gap')

                if frame is not None:
                    if self._writer is None and age is not None and age <= self.gap_s:
                        if not self._open_segment():
                            note = 'disk-low'
                            break
                    if self._writer is not None:
                        if (frame.shape[1], frame.shape[0]) != self._writer_size:
                            self._close_segment('size-change')
                            if not self._open_segment():
                                note = 'disk-low'
                                break
                        self._writer.write(frame)     # 原帧：干净
                        self._seg['written'] += 1
                        self._seg['age_max'] = max(self._seg['age_max'],
                                                   age or 0.0)
                        self._last_frame_t = self.clock()

                if (self._writer is not None
                        and self.clock() - self._seg['t0'] >= self.segment_s):
                    self._close_segment('segment')

                if self.display:
                    key = self._draw(self._frame, age,
                                     (self.clock() - self._seg['t0'])
                                     if self._seg else 0.0, left, stats)
                    if key == ord('q'):
                        note = 'quit'
                        break
                else:
                    self.sleep(0.002)
        finally:
            self._close_segment(note)
            signal.signal(signal.SIGINT, old)
        return self.rows

    def _draw_waiting(self):
        import cv2
        import numpy as np
        vis = np.zeros((240, 640, 3), dtype='uint8')
        cv2.putText(vis, 'waiting for %s:%s ...' %
                    (getattr(self.feed, 'host', '?'), getattr(self.feed, 'port', '?')),
                    (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 255), 2)
        cv2.imshow(WINDOW, vis)
        cv2.waitKey(1)


def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        description=u'笔记本侧：边看 X5 画面、边分段录视频（画线漏沙采集）')
    ap.add_argument('--host', default=DEFAULT_HOST)
    ap.add_argument('--port', type=int, default=DEFAULT_PORT)
    ap.add_argument('--batch', default='t20', help='批次 t{NN}')
    ap.add_argument('--day', default=None, help='文件名日期段，默认笔记本今天 MMDD')
    ap.add_argument('--out', default=OUT_DIR, help='录像目录，默认 %s' % OUT_DIR)
    ap.add_argument('--segment-s', dest='segment_s', type=float, default=SEGMENT_S,
                    help='每段秒数（默认 %.0f）' % SEGMENT_S)
    ap.add_argument('--session-min', dest='session_min', type=float,
                    default=SESSION_MIN,
                    help='会话总时长（分钟），到点自停（默认 %.0f）；0=不限'
                         % SESSION_MIN)
    ap.add_argument('--fps', type=float, default=VIDEO_FPS,
                    help='写进 AVI 的帧率，默认 %.0f（与 stream_pi 一致）' % VIDEO_FPS)
    ap.add_argument('--gap-s', dest='gap_s', type=float, default=GAP_S,
                    help='超过这么久没有新帧就当断链、切段（默认 %.1f s）' % GAP_S)
    ap.add_argument('--display', choices=['on', 'off'], default='on',
                    help='on=开窗口看图（默认）；off=无窗口（测试/无桌面）')
    ap.add_argument('--connect-timeout', dest='connect_timeout', type=float,
                    default=10.0, help='等第一帧的秒数，默认 10')
    ap.add_argument('--force', action='store_true',
                    help='只越「空间」这一道；链路/相机的事不给越')
    a = ap.parse_args(argv)
    if not BATCH_RE.match(a.batch):
        ap.error(u'批次名要 t{NN}（t01…t99），现在是 %r' % a.batch)
    if a.segment_s <= 0:
        ap.error(u'--segment-s 要正数')
    if a.session_min < 0:
        ap.error(u'--session-min 不能为负；0 表示不限')
    if a.fps <= 0:
        ap.error(u'--fps 要正数')
    if a.gap_s <= 0:
        ap.error(u'--gap-s 要正数')
    return a


def main(argv=None):
    a = parse_args(argv)
    day = a.day or now_day()
    os.makedirs(a.out, exist_ok=True)

    if a.session_min > 0 and not a.force:
        need = estimate_mb(1920, 1080, 30, a.session_min * 60.0) * 1.5
        free = free_mb(a.out)
        print(u'[i] 盘剩 %.1f GB；%.1f 分钟按 1080p30 估 %.1f GB（12 MB/s 是估的，'
              u'留 50%% 余量）' % (free / 1024.0, a.session_min, need / 1024.0))
        if free < need:
            print(u'🔴 盘不够：减 --session-min，或换盘。要硬录加 --force')
            return 2

    print(u'[i] X5 侧先起流：python3 vehicle/stream_pi.py --width 1920 --height 1080')
    print(u'[i] 相机同一时刻只给一路：别同时跑 record_local（车上本地录）')
    feed = StreamFeed(a.host, a.port, recv_timeout=0.5, reconnect_s=1.0)
    rec = Recorder(feed, a.out, a.batch, day, a.segment_s,
                   (a.session_min * 60.0) if a.session_min > 0 else 0.0,
                   fps=a.fps, gap_s=a.gap_s, display=(a.display == 'on'),
                   connect_timeout_s=a.connect_timeout)
    try:
        rows = rec.run()
    finally:
        stats = feed.close()
    print(u'[完] %d 段；流帧 %d、丢线 %d、接收超时 %d、连接失败 %d'
          % (rows, stats.get('frames', 0), stats.get('link_drops', 0),
             stats.get('recv_timeouts', 0), stats.get('connect_fails', 0)))
    print(u'日志：%s' % rec.log_path.replace('\\', '/'))
    print(u'录像：%s' % a.out.replace('\\', '/'))
    return 0


if __name__ == '__main__':
    sys.exit(main())