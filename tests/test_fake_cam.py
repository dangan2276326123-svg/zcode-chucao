# -*- coding: utf-8 -*-
"""tools/fake_cam.py — 合成相机推流。

这些测试要回答的不是"函数返回值对不对"，而是一个原始症状：
**"把数据集照片当相机喂，PC 侧那条真实读者链路认不认它。"**
所以最要紧的一条 `test_streamfeed_round_trip` 拿的是 `common/mjpeg.py` 里
**生产代码在用的同一个 `StreamFeed`** 走真 socket，而不是自己写一个假解析器——
自己再写一遍就等于把被判据保护的东西复制了一份（AGENTS 审查清单第 2 条）。

时钟与 sleep 一律注入（`VirtualTime`），只有那条集成测试允许真等待。
"""
import os
import socket
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.mjpeg import StreamFeed, latest_jpeg    # noqa: E402
from tools import fake_cam                          # noqa: E402


def fake_jpeg(tag=b'A', n=4):
    """结构上完整的最小 JPEG 容器（SOI..payload..EOI），够解析器用。"""
    return b'\xff\xd8' + tag * n + b'\xff\xd9'


class VirtualTime:
    """虚拟时间：`clock()` 只读，`sleep(s)` 把时间往前拨。

    这样"客户端慢"这件事就有了明确的落点——是 `sendall` 里拨表，不是真等。
    """

    def __init__(self, now=0.0):
        self.now = now
        self.sleeps = []

    def clock(self):
        return self.now

    def sleep(self, s):
        self.sleeps.append(s)
        self.now += s


class RecordingConn:
    """只记录 sendall 的假连接。`slow_s` 模拟"发一帧要这么久"（拨虚拟表）。"""

    def __init__(self, vt=None, slow_s=0.0, fail_after=None):
        self.sent = []
        self.fail_after = fail_after
        self.closed = False
        self.vt = vt
        self.slow_s = slow_s

    def sendall(self, blob):
        if self.fail_after is not None and len(self.sent) >= self.fail_after:
            raise OSError('peer reset')
        self.sent.append(blob)
        if self.vt is not None and self.slow_s:
            self.vt.now += self.slow_s

    def close(self):
        self.closed = True


# ---------- 分帧字节：能被本仓真实读者解开 ----------
def test_multipart_part_decodes_with_the_real_parser():
    jpeg = fake_jpeg(b'Q', 6)
    blob = fake_cam.encode_multipart(jpeg)
    got, consumed = latest_jpeg(blob)
    assert got == jpeg                              # 一帧不漏、一字节不改
    header_len = blob.index(jpeg)
    assert consumed == header_len + len(jpeg)       # 消费到 EOI 为止


def test_two_parts_in_one_buffer_yield_the_newest():
    f1, f2 = fake_jpeg(b'1'), fake_jpeg(b'2', 8)
    buf = fake_cam.encode_multipart(f1) + fake_cam.encode_multipart(f2)
    got, consumed = latest_jpeg(buf)
    assert got == f2
    assert consumed == len(buf) - 2                 # 末尾那对 CRLF 属于下一段的分隔
    assert buf[consumed:] == b'\r\n'


def test_part_headers_carry_the_real_content_length():
    jpeg = fake_jpeg(b'Z', 11)
    blob = fake_cam.encode_multipart(jpeg)
    assert b'Content-Type: image/jpeg' in blob
    assert ('Content-Length: %d' % len(jpeg)).encode() in blob
    assert blob.startswith(b'--') and blob.endswith(b'\r\n')


# ---------- 帧索引：latest-wins 的算式本身 ----------
def test_frame_index_at_walks_the_slots_in_order():
    n, fps = 3, 10.0
    got = [fake_cam.frame_index_at(t, n, fps) for t in
           (0.0, 0.1, 0.19, 0.2, 0.3, 0.4, 0.5, 0.6)]
    assert got == [0, 1, 1, 2, 0, 1, 2, 0]


def test_frame_index_at_goes_silent_once_when_not_looping():
    assert fake_cam.frame_index_at(0.05, 2, 10.0, loop=False) == 0
    assert fake_cam.frame_index_at(0.15, 2, 10.0, loop=False) == 1
    assert fake_cam.frame_index_at(0.25, 2, 10.0, loop=False) is None


@pytest.mark.parametrize('elapsed,n,fps', [(-0.1, 3, 10.0), (0.1, 0, 10.0),
                                           (0.1, 3, 0.0)])
def test_frame_index_at_refuses_degenerate_inputs(elapsed, n, fps):
    assert fake_cam.frame_index_at(elapsed, n, fps) is None


# ---------- serve_client ----------
def test_slow_client_gets_the_newest_frame_not_a_backlog():
    """发一帧要 0.5 秒的慢客户端：拿到的是 0、5、10 三帧，不是 0、1、2。

    这条钉的是 `serve_client` 里**没有队列**这件事。攒队列的实现会连发 idx 1、2、3，
    `StreamFeed` 自己也只留最新一帧，看起来"能用"，实际上 PC 读到的 `age` 一路涨到
    超过 `FRAME_MAX_AGE_S`，台架上就会被读成"链路卡了"——那是推流端自己造的假故障。
    """
    vt = VirtualTime()
    parts = [fake_jpeg(bytes([65 + i])) for i in range(12)]      # 12 帧 @10fps
    conn = RecordingConn(vt=vt, slow_s=0.5)
    log = []
    sent, total = fake_cam.serve_client(conn, parts, fps=10.0, loop=True,
                                        clock=vt.clock, sleep=vt.sleep,
                                        max_seconds=1.2, send_log=log)
    assert log == [0, 5, 10]
    assert sent == 3
    assert total == sum(len(p) for p in conn.sent)


def test_once_holds_the_connection_open_and_goes_silent():
    """播完不关链路：'活着但静默'与'断了'是两个不同的桶（见 common/mjpeg.py 文件头）。

    那条区别正是 C2/C13 这类"失视觉"格要的现场——`recv_timeouts` 在涨而
    `link_drops` 不涨。关连接会把这两件事糊成一个。
    """
    vt = VirtualTime()
    parts = [fake_jpeg(b'A'), fake_jpeg(b'B')]
    conn = RecordingConn(vt=vt)
    log = []
    sent, _ = fake_cam.serve_client(conn, parts, fps=10.0, loop=False,
                                    clock=vt.clock, sleep=vt.sleep,
                                    max_seconds=0.3, send_log=log)
    assert log == [0, 1] and sent == 2
    assert conn.closed is False                     # serve_client 自己不许关连接
    silent = [s for s in vt.sleeps if abs(s - 0.05) < 1e-9]
    assert silent, '静默期应该在轮询而不是空转：' + str(vt.sleeps)


def test_client_disconnect_ends_the_session_without_raising():
    vt = VirtualTime()
    parts = [fake_jpeg(bytes([65 + i])) for i in range(5)]
    conn = RecordingConn(vt=vt, fail_after=2)
    sent, _ = fake_cam.serve_client(conn, parts, fps=10.0, loop=True,
                                    clock=vt.clock, sleep=vt.sleep)
    assert sent == 2 and len(conn.sent) == 2


def test_stop_event_ends_the_session():
    vt = VirtualTime()
    parts = [fake_jpeg(b'A')]
    conn = RecordingConn(vt=vt)
    stop = threading.Event()

    def sleep(s):
        vt.sleep(s)
        if len(conn.sent) >= 1:
            stop.set()

    sent, _ = fake_cam.serve_client(conn, parts, fps=10.0, loop=True,
                                    clock=vt.clock, sleep=sleep, stop=stop)
    assert sent == 1


# ---------- 读图与失败面 ----------
def test_list_images_accepts_a_single_file(tmp_path):
    p = tmp_path / 'one.jpg'
    p.write_bytes(b'whatever')
    assert fake_cam.list_images(str(p)) == [str(p)]


def test_list_images_sorts_by_name_and_filters_extensions(tmp_path):
    for name in ('b.jpg', 'a.jpg', 'notes.txt', 'c.png'):
        (tmp_path / name).write_bytes(b'x')
    got = [os.path.basename(f) for f in fake_cam.list_images(str(tmp_path))]
    assert got == ['a.jpg', 'b.jpg', 'c.png']


def test_list_images_rejects_an_empty_dir(tmp_path):
    with pytest.raises(SystemExit) as e:
        fake_cam.list_images(str(tmp_path))
    assert '一张可读图片都没有' in str(e.value)


def test_list_images_rejects_a_missing_path(tmp_path):
    with pytest.raises(SystemExit) as e:
        fake_cam.list_images(str(tmp_path / 'nope'))
    assert '路径不存在' in str(e.value)


def test_encode_frames_skips_broken_files_and_errors_when_none_survive(tmp_path):
    cv2 = pytest.importorskip('cv2')
    import numpy as np
    ok = tmp_path / 'ok.jpg'
    cv2.imwrite(str(ok), np.zeros((8, 8, 3), 'uint8'))
    bad = tmp_path / 'bad.jpg'
    bad.write_bytes(b'not a jpeg at all')
    parts = fake_cam.encode_frames([str(ok), str(bad)])
    assert len(parts) == 1 and parts[0][:2] == b'\xff\xd8'
    with pytest.raises(SystemExit):                 # 全军覆没不许静默推一条空流
        fake_cam.encode_frames([str(bad)])


def test_encode_frames_limit_caps_the_plan(tmp_path):
    cv2 = pytest.importorskip('cv2')
    import numpy as np
    files = []
    for i in range(5):
        p = tmp_path / ('img_%06d.jpg' % i)
        cv2.imwrite(str(p), np.full((8, 8, 3), i * 10, 'uint8'))
        files.append(str(p))
    assert len(fake_cam.encode_frames(files, limit=3)) == 3


# ---------- CLI ----------
def test_dry_run_opens_no_port(capsys, tmp_path):
    cv2 = pytest.importorskip('cv2')
    import numpy as np
    p = tmp_path / 'one.jpg'
    cv2.imwrite(str(p), np.zeros((8, 8, 3), 'uint8'))
    port = 5599
    assert fake_cam.main(['--source', str(p), '--dry-run', '--port', str(port)]) == 0
    out = capsys.readouterr().out
    assert 'dry-run' in out and 'NOT a camera' in out
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)   # 口没被占 = 真没开
    try:
        srv.bind(('127.0.0.1', port))
    finally:
        srv.close()


def test_cli_rejects_a_nonpositive_fps(tmp_path):
    p = tmp_path / 'one.jpg'
    p.write_bytes(b'x')
    with pytest.raises(SystemExit):
        fake_cam.parse_args(['--source', str(p), '--fps', '0'])


def test_cli_rejects_out_of_range_quality(tmp_path):
    p = tmp_path / 'one.jpg'
    p.write_bytes(b'x')
    with pytest.raises(SystemExit):
        fake_cam.parse_args(['--source', str(p), '--quality', '0'])


def test_once_flag_flips_loop_off(tmp_path):
    p = tmp_path / 'one.jpg'
    p.write_bytes(b'x')
    assert fake_cam.parse_args(['--source', str(p)]).loop is True
    assert fake_cam.parse_args(['--source', str(p), '--once']).loop is False


# ---------- 集成：真实 StreamFeed 走真 socket 收得到帧 ----------
def test_streamfeed_round_trip():
    """这一条是本工具存在的理由：**生产读者**能在真 TCP 上解出我们的帧。

    允许真等待，上限 5 秒。三个判据各管一件事：
      · 收够 3 帧且形状对 —— 分帧字节没错；
      · `decode_fail == 0` —— 帧不是残缺的；
      · `link_drops == 0` —— 症状判据。字节错了 `StreamFeed` 会一路重连，
        这个计数立刻把它露出来，而不是静默给一张旧图。
    """
    cv2 = pytest.importorskip('cv2')
    import numpy as np
    parts = []
    for i in (11, 22, 33):
        ok, buf = cv2.imencode('.jpg', np.full((8, 10, 3), i, 'uint8'))
        assert ok
        parts.append(buf.tobytes())

    srv = fake_cam.make_listener('127.0.0.1', 0)
    port = srv.getsockname()[1]
    stop = threading.Event()
    events = []
    th = threading.Thread(target=fake_cam.serve_forever,
                          args=(srv, parts, 20.0, True),
                          kwargs={'stop': stop, 'on_event': events.append},
                          daemon=True)
    th.start()
    feed = StreamFeed('127.0.0.1', port, recv_timeout=0.1, reconnect_s=0.2)
    frames = []
    snap = None
    deadline = time.time() + 5.0
    try:
        # 判据是 `seq`——StreamFeed 每**发布一帧**才 +1。数"get() 拿到非 None"是假判据：
        # 同一帧在下一帧到之前会被反复返回，第一次跑就是这么把"只到了一帧"读成"到了三帧"的。
        while time.time() < deadline:
            _s, seq, _a = feed.snapshot()
            if seq >= 3:
                break
            time.sleep(0.02)
        frame, _age = feed.get(max_age_s=0.5)
        if frame is not None:
            frames.append(frame)
        snap = feed.snapshot()          # **收够帧那一刻**的计数，取证要在拆之前
    finally:
        stats = feed.close()
        stop.set()
        srv.close()
        th.join(timeout=3.0)

    _sstats, _seq, _age = snap
    assert frames, 'StreamFeed 一帧都没收到: %s / events=%s' % (_sstats, events)
    assert _seq >= 3, '只发布了 %d 帧: %s' % (_seq, _sstats)
    assert frames[0].shape[:2] == (8, 10)
    assert _sstats['decode_fail'] == 0
    # link_drops 只在**运行中**是症状：拆链路时那一次 drop 是 teardown 的正常噪音，
    # 所以这条读的是 snap（收够三帧那一刻），不是 close() 之后的最终计数。
    assert _sstats['link_drops'] == 0, _sstats
    assert _sstats['frames'] >= 3
    assert _seq >= 3
