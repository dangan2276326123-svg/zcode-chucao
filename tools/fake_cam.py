# -*- coding: utf-8 -*-
"""合成相机：把数据集照片推成一条 TCP multipart MJPEG 流（**不是相机，不是准入证据**）。

为什么要这个工具：相机已经从样机上拆下来了，而 `pc/main.py --live` 那一整条链
（推流 → `StreamFeed` 有界读 → 去畸变 → 分割 → IPM → 双墙 → 导航线拟合 → 状态机
→ wire 发帧 → X5 桥 → UART → 固件 → STATUS 回读）里，只有"相机"这一段断着。
拿已有的田间照片当"眼睛"，这段就能补上，于是整条链可以在**没相机、没下田**的情况下跑通。

用法（笔记本两个窗口）：

    # 窗口 1：推流。单张照片循环播 / 一个目录按文件名顺序播
    python -B tools/fake_cam.py --source "D:/JetBrains/chucao_prj/model_data/val/images" --fps 10
    python -B tools/fake_cam.py --source some.jpg --once          # 播完一遍就静默（链路保持）
    python -B tools/fake_cam.py --source some.jpg --dry-run       # 只报参数，不开端口

    # 窗口 2：正常跑 live（控制帧照常上线，台架纪律一条不松）
    python -B pc/main.py --live --stream-host 127.0.0.1 --stream-port 5000 --out results/syn_01

为什么走"推流"而不是给 `pc/main.py` 加一个 `--live --source` 组合：后者要改控制循环
本身（P0-8 那条"回放永远不许开车"的闸门就在 `send()` 里），而这条**一行都不碰 main**——
PC 侧读的是同一个 `common/mjpeg.py` 的 `StreamFeed`，同一个端口，同一种分帧字节，
所以传输层、有界读、`FRAME_MAX_AGE_S` 判旧、HUD 的 `age:`/`silent:` 计数**一并被跑到**，
少测的层数是零。代价是它只到"图像源是假的"这一层，而这一层恰恰是本意。

**这张流能证明什么、不能证明什么**（AGENTS 审查清单第 5 条，写在这里防止被读成后者）：

- 能证明：一帧图像进得去、一条导航线出得来、`tx_frames` 那列真上了线、固件真回了 STATUS。
  也就是**通路**。
- **不能**证明跟踪精度、伤苗率、时延（B8 四个口径）、或任何准入格。三条理由：
  1. 图像不会随这台车的动作变——照片是**被重放**的，不是被这台车拍到的。单张循环播时
     横向误差恒定，AUTO 会朝一边一直打差速而**永不收敛**；那正是开环该有的样子，
     不是 bug，但也别把它读成"沿线走通了"。
  2. 帧率与节拍跟真相机不同（默认 10 fps vs 相机 30 fps），任何 `latency_ms`/`age`
     读数都不属于 B8 那四个口径。
  3. 照片是数据集里的 960x720，`pc/perception.py` 的去畸变那一步会把它放大到
     1920x1080 再按 `data/calib_params.npz` 重映射——那套内参是不是拍这批照片的
     那支相机（**未确认**），所以米制横向数在这一路上本来就不可引用（Pc-1 的外参
     仍是占位）。
- 想看出"收敛"的样子：播**连续编号**的那批照片（`img_000000.jpg`、`img_000012.jpg`…
  同一段田间视频抽的帧），视角本身在变，`lat_m` 序列跟着变，L1/ESTOP/CONF-LOW
  那些分支也就都能被自然走到。这仍然是开环重放，只是比一张图走得像。

不改一个像素：推出去的就是照片文件本身的 JPEG 编码（只做一次 `imencode`，之后按字节重发），
所以模型看到的输入域与数据集一致。往帧上写字看起来好用，但那等于换了模型输入域。
"""
import argparse
import os
import socket
import sys
import threading
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

BOUNDARY = b'fake-cam'
IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.bmp')
DEFAULT_PORT = 5000
DEFAULT_FPS = 10.0
DEFAULT_QUALITY = 90


def encode_multipart(jpeg, boundary=BOUNDARY):
    """一个 JPEG -> multipart MJPEG 的一段（头 + 图 + CRLF）。

    判据不是"看着像 gstreamer"，而是**能被本仓真实的读者解开**：
    `common/mjpeg.py` 的 `latest_jpeg()` 只扫 SOI/EOI，所以头部怎么写都行，
    但图必须是一整帧、边界必须完整——单测就是拿 `latest_jpeg` 解这一段来钉住的。
    """
    header = (b'--' + boundary + b'\r\nContent-Type: image/jpeg\r\n'
              b'Content-Length: %d\r\n\r\n' % len(jpeg))
    return header + jpeg + b'\r\n'


def frame_index_at(elapsed_s, n_frames, fps, loop=True):
    """按**时间**算这一拍该发第几帧，而不是排队。

    latest-wins 是这么来的：客户端慢、网络堵、笔记本打了个盹，下一拍发的就是
    "按时间该到的那一帧"，积压的那几帧直接不发了。这与 `StreamFeed` 的语义对齐
    （它自己也只留最新一帧），而且不会让 PC 读到一串越来越旧的图——那些旧图
    会被 `FRAME_MAX_AGE_S` 判掉，看起来像"链路卡了"，其实是推流端在攒队列。

    `loop=False` 且已经播完 -> None（= 这一拍没东西可发，客户端随后走 NO FRAME 分支，
    这条正是 C2/C13 那类"失视觉"格想要的现场）。
    """
    if n_frames <= 0 or fps <= 0 or elapsed_s < 0:
        return None
    idx = int(elapsed_s * fps)
    if idx < 0:
        return 0
    if idx >= n_frames:
        return idx % n_frames if loop else None
    return idx


def list_images(source):
    """单张照片或一个目录 -> 有序文件列表（排序按文件名，与 `pre_annotate.py` 同口径）。"""
    if os.path.isdir(source):
        files = [os.path.join(source, f) for f in sorted(os.listdir(source))
                 if f.lower().endswith(IMAGE_EXTS)]
        if not files:
            raise SystemExit(
                '目录里一张可读图片都没有：%s\n'
                '  支持的扩展名：%s\n'
                '  注意 split_dataset 产物是 images/{.jpg,.json} 两层，指到 .jpg 那一层'
                % (source, ' '.join(IMAGE_EXTS)))
        return files
    if os.path.isfile(source):
        return [source]
    raise SystemExit('路径不存在：%s' % source)


def encode_frames(files, quality=DEFAULT_QUALITY, limit=None):
    """图片文件 -> JPEG 字节列表（**只编一次**，之后每帧重发同一串字节）。

    编码失败的文件跳过但计数打印出来：静默少几帧会让人以为"流就是这么多帧"，
    而 `--once` 那一路的静默时刻会跟着错。
    `limit` 是给几十张以上的目录用的（内存账：一张 1080p JPEG 约 0.3 MB）。
    """
    import cv2
    out, skipped = [], []
    for path in files:
        if limit is not None and len(out) >= limit:
            break
        img = cv2.imread(path)
        if img is None:
            skipped.append(os.path.basename(path))
            continue
        ok, buf = cv2.imencode('.jpg', img,
                               [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
        if not ok:
            skipped.append(os.path.basename(path))
            continue
        out.append(buf.tobytes())
    if skipped:
        print('skipped %d unreadable file(s): %s' % (len(skipped), ', '.join(skipped[:5])))
    if not out:
        raise SystemExit('全部图片都编不出 JPEG（0 帧可推）；检查文件是否损坏')
    return out


def serve_client(conn, parts, fps, loop, clock=time.monotonic, sleep=time.sleep,
                 stop=None, max_seconds=None, header_boundary=BOUNDARY,
                 send_log=None):
    """把一个客户端从连接到断开这段的帧发完；返回 (发出帧数, 发出字节数)。

    不 bind、不 accept、不开线程——那三件事留在 `main()`，所以这一层可以被单测
    直接拿一个真实连接喂。

    `--once` 播完之后**保持连接静默**而不是关掉它。理由是 `common/mjpeg.py` 文件头
    那条区分：**"链路活着但没有帧"和"链路断了"是两个不同的桶**，前者才是 C2/C13
    那类"失视觉"格要复现的现场（PC 该走 `NO_FRAME_RESULT` 那一支，`recv_timeouts`
    在涨而 `link_drops` 不涨）。关连接会把这两件事糊成一个。
    """
    t0 = clock()
    sent = total = 0
    while True:
        if stop is not None and stop.is_set():
            break
        elapsed = clock() - t0
        if max_seconds is not None and elapsed > max_seconds:
            break
        slot = int(elapsed * fps)                    # 按时间算该发第几拍，不排队
        idx = frame_index_at(elapsed, len(parts), fps, loop)
        if idx is None:
            sleep(min(1.0 / fps, 0.05))              # 播完了：静默而不关链路
            continue
        blob = encode_multipart(parts[idx], header_boundary)
        try:
            conn.sendall(blob)
        except OSError:
            break                                   # 客户端走了：正常结束，不是故障
        sent += 1
        total += len(blob)
        if send_log is not None:
            send_log.append(idx)
        delay = t0 + (slot + 1) / fps - clock()
        if delay > 0:
            sleep(delay)
    return sent, total


def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        description='把数据集照片推成合成 MJPEG 流（非相机、非准入证据）')
    ap.add_argument('--source', required=True, help='一张照片或一个图片目录')
    ap.add_argument('--host', default='127.0.0.1',
                    help='默认只监听本机；要给 X5 或另一台笔记本连再填 0.0.0.0')
    ap.add_argument('--port', type=int, default=DEFAULT_PORT)
    ap.add_argument('--fps', type=float, default=DEFAULT_FPS,
                    help='默认 10（真相机是 30；两者不可混着报时延）')
    ap.add_argument('--quality', type=int, default=DEFAULT_QUALITY)
    ap.add_argument('--limit', type=int, default=None,
                    help='最多推前 N 张（目录很大时控内存）')
    ap.add_argument('--duration', type=float, default=None,
                    help='每个客户端最多服务多少秒（默认一直服务）')
    loop = ap.add_mutually_exclusive_group()
    loop.add_argument('--loop', dest='loop', action='store_true', default=True,
                      help='播完一遍从头再来（默认）')
    loop.add_argument('--once', dest='loop', action='store_false',
                      help='播完一遍就静默，让 PC 走到 NO FRAME 那一支')
    ap.add_argument('--dry-run', action='store_true',
                    help='只读图并打印参数，不开端口')
    if argv is not None:
        args = ap.parse_args(argv)
    else:
        args = ap.parse_args()
    if args.fps <= 0:
        ap.error('--fps 必须 > 0')
    if not 1 <= args.quality <= 100:
        ap.error('--quality 必须在 1..100')
    return args


def make_listener(host='127.0.0.1', port=DEFAULT_PORT):
    """绑好一个 TCP 监听口（`port=0` 让系统发一个空闲口，单测用这一条）。

    accept 带 1 秒超时：`stop` 事件要能在没有客户端的情况下被看见。Windows 上
    "关了监听口去叫醒阻塞的 accept"不可靠，所以这里不指望它，靠超时轮询。
    """
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(4)
    srv.settimeout(1.0)
    return srv


def serve_forever(srv, parts, fps, loop, stop=None, max_seconds=None,
                  on_event=None):
    """accept 循环：每个客户端一条守护线程。返回服务过的客户端数。

    `on_event(str)` 是唯一的通知出口（main 拿它 print，单测拿它记事件）——
    这一层不直接往 stdout 写，否则每条集成测试都会往控制台灌一屏。
    """
    def emit(msg):
        if on_event is not None:
            on_event(msg)

    n_clients = 0
    while stop is None or not stop.is_set():
        try:
            conn, addr = srv.accept()
        except socket.timeout:
            continue
        except OSError:
            return n_clients                       # 监听口被关了：正常收工
        n_clients += 1
        emit('client %s:%s connected' % addr[:2])

        def _run(c=conn, a=addr):
            try:
                sent, total = serve_client(c, parts, fps, loop, stop=stop,
                                           max_seconds=max_seconds)
                emit('client %s:%s done: %d frame(s), %.0f KB sent'
                     % (a[0], a[1], sent, total / 1024.0))
            finally:
                try:
                    c.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                c.close()
        threading.Thread(target=_run, name='fake-cam-client', daemon=True).start()
    return n_clients


def _echo(msg):
    """打印并**立刻刷**。

    不是洁癖：本工具几乎一定在后台窗口或管道里跑（作者一边推流一边开 `pc/main.py`）。
    实测第一次就是这样——stdout 全缓冲，`client ... done: N frame(s)` 那条要等进程退出
    才出来，于是"有没有客户端连上"这件事在现场看起来像"服务没动"。
    """
    print(msg, flush=True)


def main(argv=None):
    args = parse_args(argv)
    files = list_images(args.source)
    parts = encode_frames(files, args.quality, args.limit)
    period_ms = 1000.0 / args.fps
    nbytes = sum(len(p) for p in parts)
    _echo('SYNTHETIC stream: %d frame(s), %.0f KB, %.1f fps (%.0f ms/帧), '
          'loop=%s, source=%s' % (len(parts), nbytes / 1024.0, args.fps,
                                  period_ms, args.loop, args.source))
    _echo('NOT a camera. 不得用于时延（B8）、跟踪精度、伤苗率或任何准入判定；'
          '图像不随这台车的动作变化。')
    if args.dry_run:
        _echo('dry-run: 未开端口，未推一帧')
        return 0

    srv = make_listener(args.host, args.port)
    _echo('listening on %s:%d  (PC 侧: pc/main.py --live --stream-host %s --stream-port %d)'
          % (args.host, args.port, args.host, args.port))
    stop = threading.Event()
    try:
        serve_forever(srv, parts, args.fps, args.loop, stop=stop,
                      max_seconds=args.duration, on_event=_echo)
    except KeyboardInterrupt:
        _echo('interrupted')
    finally:
        stop.set()
        srv.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
