# -*- coding: utf-8 -*-
"""tools/watch_record.py — 笔记本侧"边看边录"（画线漏沙采集，2026-11-20）。

钉的是四件现场会坏掉的事：

1. **录进文件的是干净帧**：HUD 只画在窗口那份拷贝上。往帧上写字等于换模型输入域
   （`fake_cam.py` 里同一条规矩），而这件事在屏幕上完全看不出来。
2. **每帧只写一次**：`StreamFeed` 在没有新帧时会把上一张反复返回，照着写就是重复帧。
3. **断链切段**：AVI 没有时间戳，把缺口留在段中间会把回放时间轴悄悄压短；
   切段 + 日志里的 note 让缺口变成明的。
4. **落盘名与车上那一路同源**：`t{NN}_{MMDD}_v{NN}.avi`，`extract_frames` 不改一行就能抽。

时钟与 feed 全部注入（`VClock`/`FakeFeed`），只有最后一条集成测试走真 socket + 真
`StreamFeed` + 真的 `fake_cam`——那条测的是"接线对不对"，不是逻辑。
"""
import csv
import os
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import capture_field as cf          # noqa: E402
from tools import fake_cam                      # noqa: E402
from tools import watch_record as wr            # noqa: E402
from vehicle import record_local as rl          # noqa: E402


class VClock(object):
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, s):
        self.now += s


def make_frame(seq, h=48, w=64):
    import numpy as np
    img = np.zeros((h, w, 3), dtype='uint8')
    img[:, :, 0] = seq % 251
    img[:, :, 1] = (seq * 7) % 251
    return img


class FakeFeed(object):
    """按拍子产帧：每次 `snapshot()` 把虚拟时间往前拨 dt，并（默认）发布一帧。

    `stop_at < t < resume_at` 这段不产新帧（断链）；只给 `stop_at` 不给 `resume_at`
    就是永久断。`stats` 的键与 `StreamFeed` 一致。
    """

    def __init__(self, clock, dt=1 / 60.0, stop_at=None, resume_at=None):
        self.clock = clock
        self.dt = dt
        self.stop_at, self.resume_at = stop_at, resume_at
        self.seq = 0
        self.last_t = 0.0
        self.host, self.port = 'fake', 0
        self.stats = {'frames': 0, 'link_drops': 0, 'recv_timeouts': 0,
                      'connect_fails': 0, 'decode_fail': 0, 'bytes': 0}

    def _silent(self):
        t = self.clock()
        return (self.stop_at is not None and self.resume_at is not None
                and self.stop_at <= t < self.resume_at)

    def snapshot(self):
        self.clock.advance(self.dt)
        if not self._silent():
            self.seq += 1
            self.stats['frames'] += 1
            self.last_t = self.clock()
        age = (self.clock() - self.last_t) if self.seq else None
        return dict(self.stats), self.seq, age

    def get(self):
        age = (self.clock() - self.last_t) if self.seq else None
        return make_frame(self.seq), age


class FakeWriter(object):
    """模拟编码器：`write()` 当场把帧拷走（真 cv2.VideoWriter 也是当场编码）。"""

    def __init__(self, path, fps, size):
        self.path = path
        self.fps = fps
        self.size = size
        self.frames = []
        self.released = False
        self._fh = open(path, 'wb')     # 与真写盘一样：文件立刻存在，段号才会推进

    def write(self, frame):
        self.frames.append(frame.copy())
        self._fh.write(b'x')

    def release(self):
        self._fh.close()
        self.released = True


def run_fake(tmp_path, **kw):
    clock = VClock()
    feed = FakeFeed(clock, **kw.pop('feed_kw', {}))
    writers = []
    day = kw.pop('day', '1120')
    rec = wr.Recorder(
        feed, str(tmp_path), kw.pop('batch', 't20'), day,
        kw.pop('segment_s', 0.5), kw.pop('session_s', 1.6),
        display=False, clock=clock, sleep=lambda s: None,
        wall=lambda: '10:00:00',
        free_mb_fn=lambda folder: 10_000.0,
        writer_factory=lambda p, f, s: (writers.append(FakeWriter(p, f, s)) or writers[-1]),
        **kw)
    rows = rec.run()
    return rec, writers, rows


def read_log(rec):
    with open(rec.log_path, encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


# ---------- 1) 命名与切段规则同源 ----------

def test_reuses_the_same_naming_and_durations_as_the_vehicle_route():
    """不是"写得一样"，是同一个函数对象——两条路落的名必须能互相抽。"""
    assert wr.video_path is cf.video_path
    assert wr.video_next_index is cf.video_next_index
    assert wr.segment_durations is rl.segment_durations


# ---------- 2) HUD 的状态字 ----------

def test_hud_text_reports_recording_and_link_state():
    head, tail = wr.hud_text(True, 't20_1120_v03', 45, 120, 1065, 0.08,
                             900, 0, 0)
    assert head.startswith('REC') and 'link ok' in head
    assert '02:00' in head and 'written 900' in tail

    head2, _ = wr.hud_text(False, 't20_1120', 0, 0, 0, 9.9, 0, 3, 1)
    assert head2.startswith('WAIT') and 'NO LINK' in head2


# ---------- 3) 分段、干净帧、日志 ----------

def test_segments_split_and_written_frames_stay_clean(tmp_path):
    rec, writers, rows = run_fake(tmp_path, segment_s=0.3, session_s=1.0)
    assert rows >= 3, rows
    assert len(writers) == rows, (len(writers), rows)
    assert all(w.released for w in writers)
    import numpy as np
    total = 0
    for w in writers:
        assert w.frames, '空段'
        total += len(w.frames)
        for f in w.frames:
            # HUD 一旦画进文件，纯色帧就会多出几种颜色——这就是"干净帧"的判据
            assert len(np.unique(f.reshape(-1, 3), axis=0)) == 1
    assert total > 30, total
    log = read_log(rec)
    assert len(log) == rows
    assert set(log[0]) == set(wr.LOG_HEADER)
    assert len({r['file'] for r in log}) == rows, '段名重复 = 后一段把前一段冲掉'
    for row in log:
        assert row['note'] in ('segment', 'session-end'), row
        assert '\\' not in row['file'] and row['file'].endswith('.avi')
        assert int(row['written']) > 0


def test_session_end_closes_the_open_segment(tmp_path):
    rec, writers, rows = run_fake(tmp_path, segment_s=5.0, session_s=0.8)
    assert rows == 1, rows
    row = read_log(rec)[0]
    assert row['note'] == 'session-end', row
    assert 0.7 < float(row['actual_s']) < 0.95, row
    assert int(row['written']) > 10


def test_no_duplicate_writes_while_the_feed_stalls(tmp_path):
    """断链期间 `get()` 会反复给上一张；按 seq 判新帧就不该写出重复帧。"""
    rec, writers, rows = run_fake(tmp_path, segment_s=5.0, session_s=1.2,
                                  gap_s=0.2,
                                  feed_kw={'stop_at': 0.4, 'resume_at': 99.0})
    assert rows == 1, rows
    frames = writers[0].frames
    assert len(frames) > 5
    for a, b in zip(frames, frames[1:]):
        assert not (a == b).all(), '写进了重复帧'
    row = read_log(rec)[0]
    # 开段那一刻的那一帧已经算进 base 的快照里（±1 的读账，不影响两列各记什么）
    assert int(row['written']) <= int(row['stream_frames']) + 1, row
    assert row['note'] == 'link-gap', row


def test_link_gap_closes_the_segment_and_marks_the_log(tmp_path):
    rec, writers, rows = run_fake(tmp_path, segment_s=5.0, session_s=1.5,
                                  gap_s=0.2,
                                  feed_kw={'stop_at': 0.3, 'resume_at': 0.8})
    notes = [r['note'] for r in read_log(rec)]
    assert 'link-gap' in notes, notes
    assert notes[-1] == 'session-end', notes
    assert rows >= 2 and len(writers) == rows


def test_low_disk_stops_before_opening_a_segment(tmp_path):
    clock = VClock()
    feed = FakeFeed(clock)
    writers = []
    rec = wr.Recorder(feed, str(tmp_path), 't20', '1120', 0.5, 1.6,
                      display=False, clock=clock, sleep=lambda s: None,
                      wall=lambda: '10:00:00',
                      free_mb_fn=lambda folder: 1.0,
                      writer_factory=lambda p, f, s: (writers.append(FakeWriter(p, f, s))
                                                      or writers[-1]))
    assert rec.run() == 0
    assert writers == []


# ---------- 4) 入口的硬闸 ----------

@pytest.mark.parametrize('bad', ['t1', 'abc', 't001', '01'])
def test_batch_name_is_checked_at_parse_time(bad):
    with pytest.raises(SystemExit):
        wr.parse_args(['--batch', bad])


def test_session_minutes_cannot_be_negative():
    with pytest.raises(SystemExit):
        wr.parse_args(['--session-min', '-1'])


def test_gap_and_segment_seconds_must_be_positive():
    with pytest.raises(SystemExit):
        wr.parse_args(['--segment-s', '0'])
    with pytest.raises(SystemExit):
        wr.parse_args(['--gap-s', '0'])


# ---------- 5) 接线：真 fake_cam + 真 StreamFeed + 真写盘 ----------

def test_end_to_end_with_fake_cam(tmp_path, capsys):
    cv2 = pytest.importorskip('cv2')
    import numpy as np
    parts = []
    for v in (40, 120, 200):
        ok, buf = cv2.imencode('.jpg', np.full((48, 64, 3), v, 'uint8'))
        assert ok
        parts.append(buf.tobytes())
    srv = fake_cam.make_listener('127.0.0.1', 0)
    port = srv.getsockname()[1]
    stop = threading.Event()
    th = threading.Thread(target=fake_cam.serve_forever,
                          args=(srv, parts, 20.0, True),
                          kwargs={'stop': stop}, daemon=True)
    th.start()
    try:
        rc = wr.main(['--host', '127.0.0.1', '--port', str(port),
                      '--batch', 't20', '--day', '1120',
                      '--out', str(tmp_path), '--display', 'off',
                      '--session-min', '0.03', '--segment-s', '0.5'])
        assert rc == 0, capsys.readouterr().out
        files = sorted(p for p in os.listdir(str(tmp_path)) if p.endswith('.avi'))
        assert files, os.listdir(str(tmp_path))
        cap = cv2.VideoCapture(os.path.join(str(tmp_path), files[0]))
        assert cap.isOpened()
        ok, frame = cap.read()
        cap.release()
        assert ok and frame is not None
        assert os.path.exists(os.path.join(str(tmp_path), 'watch_log_t20_1120.csv'))
    finally:
        stop.set()
        srv.close()