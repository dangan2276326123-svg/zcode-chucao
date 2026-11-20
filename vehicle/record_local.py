# -*- coding: utf-8 -*-
"""X5 本地录像：车一动起来，画面唯一能保证留下来的路（台账 Pc-20）。

为什么要有这个文件（作者 11-05 更正，原话"人不开车下田怎么拍视频拍照，车肯定要下田，
而且这次是实车"）：秋采的主路 11-03 已定成"录段 + 抽帧"（`tools/extract_frames.py`），
但录段那一路当时给的是 `tools/capture_field.py` 按 `v`——**它要先从 X5 拉 MJPEG 流**，
而这条流今天只有一支撑得起：网线直连 X5（`vehicle/stream_pi.py` → 笔记本 192.168.127.10）。
车一下田、一走就是十几米，网线跟着车走不成立；剩下的两条路里，
CPE 无线桥在田间距离上**没测过**（执行清单 §6 的 B8 拉距那格【回填】还是空的，是一票否决项），
所以本文件把另一条装上：**相机直接录在 X5 自己的盘上**，回来再拷、再抽帧。

分工照作者那句"能走抽帧的走抽帧，剩下的拍照"落：

    行进中的段（车在动、人在田头开遥控）→ 本文件，X5 本地录像，不需要笔记本
    停车下的特写（四类干扰、标定素材）  → 车停稳后网线 + `tools/capture_field.py` 拍照

用法（X5，仓库根目录 `~/qoder` 下）：

    python3 vehicle/record_local.py --check                 # 到田里第一步，先看这一屏
    python3 vehicle/record_local.py --check --probe         # 再试录 10 秒：实测 MB/s + 可读性
    python3 vehicle/record_local.py --batch t01 --segments 3 --segment-s 150
    python3 vehicle/record_local.py --batch t01 --dry-run   # 只看将落哪几段与命令

    # 画线漏沙采集（2026-11-20）：人在遥控上、够不着键盘，给总时长让它到点自停
    python3 vehicle/record_local.py --batch t20 --segment-s 120 --session-min 20 \
            --out data/paint_data/video
    sh vehicle/collect_demo.sh t20 20                       # 一键：检查 + 后台开录（断 SSH 也不停）

落盘名 = `data/autumn_data/video/t{NN}_{MMDD}_v{NN}.avi`，段号规则与笔记本那一路**同源**
（`common/capture_naming.py`，11-05 从 `tools/capture_field.py` 搬过来；板子上只 scp
`vehicle/` 与 `common/`，契约留在 tools 里就等于要抄一份）。所以 `tools/extract_frames.py`
在笔记本上不改一行就能抽这些文件。

四条现场规矩（前两条写死在代码里，别绕）：

1. **同一块相机不能两路同占**：`/dev/video0` 被 `stream_pi.py` 占着时本工具直接停手。
   注意这是**设计假设**——V4L2 的独占行为在这块板上没实测过，所以判据写成"发现占用者就停"，
   不是"假定能共享"。要拍照先 `pkill -f stream_pi.py`，反过来也一样。
2. **停录用 Ctrl-C，不许 kill -9、不许直接拔电**：AVI 的索引在收尾（EOS）时才写，
   没索引的文件 `cv2` 打不开——那一段就白走了。所以每段录完本工具自己开一遍文件报帧数。
3. **空间按实测算，不按估计算**：`MB_PER_S_AT_1080P30 = 12.0` 是**估的**（1080p30 MJPG 的
   量级；本仓没有这块相机的实测码率，也不许拿它当事实引用）。`--check --probe` 给实测值，
   一天的量（8 段 ×150 s ≈ 14 GB 按估值）要用实测值重核一遍才敢带。
4. **段号只增不减**：同一批次同一天已有 `_v03` 就从 `_v04` 接着排（Pc-16 那条：同名开文件
   是写语义，不报错也不留备份，而田里只走这一趟）。
5. **车一动 SSH 就断**：前台跑的录像会跟着 SIGHUP 死在第 N 段。要么用 `--session-min`
   让会话到点自停（人在遥控上够不着键盘），要么用 `vehicle/collect_demo.sh`——它先检查、
   再 `nohup` 后台起录，断线不影响；提前停只能 `kill -INT`（不是 -9）。

⚠️ 四态（AGENTS 审查清单第 5 条）：本文件 = **已编码 + 已本机单测**，
**没有在 X5 上跑过一秒**（11-05 登记时板子不通电，192.168.127.10 都 ping 不通）。
第一次上板盯三处：`--check` 里 `avimux` 在不在、`--probe` 那一段能不能读出帧数、
实测 MB/s 是多少。`--check` 不通就退回笔记本那一路（停车拍照 + 事后补录），别在田里改代码。
"""
import argparse
import csv
import datetime
import os
import shutil
import signal
import subprocess  # nosec B404 — 这里就是要起 gst-launch-1.0，参数走 argv 列表、不经 shell
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from common.capture_naming import (BATCH_RE, VIDEO_PATH,  # noqa: E402
                                   video_next_index, video_path)

DEVICE = '/dev/video0'
WIDTH, HEIGHT, FPS = 1920, 1080, 30   # 相机原生 MJPG 1080p30（清单第 1 节要求 >=1080p）
SEGMENT_S = 150.0                     # 一段 = 一个条件；0.8 m/s 走速下 ≈120 m
MIN_LAST_S = 10.0                     # 会话最后一段短于这个就并进上一段（免得收尾一个碎段）
MIN_FREE_FACTOR = 1.5                 # 剩余空间要 >= 计划量 ×1.5 才开录
MB_PER_S_AT_1080P30 = 12.0            # 🔴 估的，不是实测：见文件头第 3 条
X5 = 'sunrise@192.168.127.10'

LOG_HEADER = ['started', 'batch', 'day', 'file', 'planned_s', 'actual_s', 'exit_code',
              'bytes', 'mb_per_s', 'frames_read', 'device', 'size_fps', 'backend']


def now_day():
    """文件名里的 `MMDD`，与 `capture_field` 那一路同格式。"""
    return datetime.datetime.now().strftime('%m%d')


def estimate_mb(w, h, fps, seconds):
    """计划录这些秒大约占多少 MB——**按估的码率线性缩放，不是实测**。

    缩放以 1080p30 为基准：MJPG 每帧大小近似随像素数走、秒率随 fps 走。
    真正的数要 `--check --probe` 量；本函数的用途只是在开录前把"会不会撑爆盘"
    提前一天问出来。
    """
    per_s = MB_PER_S_AT_1080P30 * (w * h / (1920.0 * 1080.0)) * (fps / 30.0)
    return per_s * seconds


def space_verdict(free_mb, need_mb, factor=MIN_FREE_FACTOR):
    """(ok, 一句人话)。判据是"剩余 >= 计划 ×1.5"而不是"剩余 > 计划"——

    田里没有第二块盘，估错一次就是一整段没了；多留那 50% 是给"码率是估的"留的。
    """
    need_with_margin = need_mb * factor
    ok = free_mb >= need_with_margin
    msg = (u'计划 %.1f MB（估的码率），留 %.0f%% 余量后需要 %.1f MB，'
           u'盘上还剩 %.1f MB' % (need_mb, (factor - 1.0) * 100.0,
                                  need_with_margin, free_mb))
    if not ok:
        msg += (u' ⇒ 停手：减段数或减每段秒数，或换大盘。'
                u'要用当场量到的实测码率硬录，加 --force')
    return ok, msg


def stream_running(ps_output):
    """从 `ps -eo args` 的输出判"流占用者还在不在"。

    为什么不用 `pgrep -f` 的 stdout：那玩艺只印 **PID**，命令行根本不在里面，
    `'stream_pi' in out` 恒为假 ⇒ 这道闸会永远放行（写的时候差点就是这么错的，
    是测试把它抓出来的）。`ps -eo args` 印整条命令行，纯函数、能在笔记本上测。
    空串算没在跑；出现 `stream_pi.py` 且这一行不是本工具自己就算在跑。
    """
    for line in (ps_output or '').splitlines():
        if 'stream_pi.py' in line and 'record_local' not in line:
            return True
    return False


def is_posix():
    """平台判据单独包一层，别在调用点写 `os.name != 'posix'`。

    理由不是美观：11-05 变异验证时测试用 `monkeypatch.setattr(os, 'name', 'posix')` 改这个判据，
    结果 **pytest 自己崩了**——`pathlib` 在 Windows 上按 `os.name` 选实现，patch 期间任何
    `Path()` 实例化都抛 `NotImplementedError: cannot instantiate 'PosixPath'`，
    而那正是 pytest 格式化失败回溯要做的事 ⇒ 整个会话 INTERNALERROR、别的失败被吞掉。
    判据要能被替换，但不能是被全局替换。
    """
    return os.name == 'posix'


def ps_args():
    """本机的 `ps -eo args` 输出；非 POSIX 上直接给空串（不炸）。"""
    if not is_posix():
        return ''
    return subprocess.run(['ps', '-eo', 'args'],  # nosec B603
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                          text=True).stdout


def pipeline_argv(path, device=DEVICE, w=WIDTH, h=HEIGHT, fps=FPS):
    """gst 命令按 argv 列表给，不经 shell ⇒ `!` 和逗号不需要任何转义技巧。

    `image/jpeg` 直进 `avimux` = 不解码不重编，ARM 板子跑 1080p30 才扛得住；
    产物 fourcc = MJPG，与 `capture_field` 那一路、与 `extract_frames` 读的是同一种壳。
    """
    return ['gst-launch-1.0', '-e', 'v4l2src', 'device=%s' % device, '!',
            'image/jpeg,width=%d,height=%d,framerate=%d/1' % (w, h, fps), '!',
            'avimux', '!', 'filesink', 'location=%s' % path]


def build_pipeline(path, device=DEVICE, w=WIDTH, h=HEIGHT, fps=FPS):
    """给人看的那一行（跟 `stream_pi.build_pipeline` 同一个习惯：先打印再跑）。"""
    return ' '.join(pipeline_argv(path, device, w, h, fps))


def plan(out_folder, batch, day, count):
    """本次要落的段路径，段号从"目录里已有最大号 + 1"往上接着排。

    为什么自己推进而不逐段调 `video_next_index()`：那也行（每段录完目录里确实多了一个），
    但 `--dry-run` 要在**一段都没录之前**就把整串名字打出来给人核，所以这里一次算完。
    兜底还是 `video_next_index()`（Pc-16）。
    """
    idx = video_next_index(out_folder, batch, day)
    return [video_path(batch, day, idx + i, folder=out_folder) for i in range(count)]


def segment_durations(segment_s, session_s=0.0, count=None, min_last_s=MIN_LAST_S):
    """本次要录的各段秒数（与 `plan()` 的段一一对应）。

    - `session_s <= 0`：按段数切，`count` 段 × `segment_s`（原行为）。
    - `session_s > 0`：按**总时长**切、最后一段是余数；余数短于 `min_last_s` 就并进
      上一段（免得落一个几秒钟的碎段）。`count` 若给，只当上限——**总时长仍是硬上限**。

    为什么要按总时长：车一动，网线就拔，人在遥控上够不着键盘；到点自停是唯一
    不需要现场操作的收尾方式（`vehicle/collect_demo.sh` 用的就是这条）。
    """
    if segment_s <= 0:
        raise ValueError(u'每段秒数要正数')
    if session_s > 0:
        durs = []
        left = float(session_s)
        while left > 1e-6:
            d = min(float(segment_s), left)
            durs.append(d)
            left -= d
        if len(durs) > 1 and durs[-1] < min_last_s:
            durs[-2] += durs[-1]
            durs.pop()
        if count is not None:
            durs = durs[:int(count)]
        return durs
    if count is None or int(count) < 1:
        raise ValueError(u'段数要 >=1')
    return [float(segment_s)] * int(count)


def log_row(started, batch, day, path, planned_s, actual_s, rc, size, mb_per_s,
            frames, device, size_fps, backend):
    """`record_log_<MMDD>.csv` 的一行。

    路径一律写**正斜杠**——`capture_log` 那侧 10-21 栽过一次：`--out` 给 `/`、
    `os.path.join` 又拼进 `\\`，事后按前缀过滤的脚本静默漏匹配。
    `frames_read` 是录完当场用 cv2 开文件读到的帧数；读不出（0）或板子上没 cv2（空）
    都单独占一列，不许和"录到了多少帧"混成一格。
    """
    return [started, batch, day, path.replace('\\', '/'), '%.1f' % planned_s,
            '%.1f' % actual_s, str(rc), str(size), '%.2f' % mb_per_s,
            ('' if frames is None else str(frames)), device, size_fps, backend]


def append_log_row(lp, row):
    """日志**每段落一行**，不是收工才写：中途断电/崩了，前面几段的账还在。

    表头只在文件头一次；同一批次同一天的第二次会话往后追加（`started` 列是
    **该段**开始时刻，不是整场开始——事后拿它把段号对到现场的条件上）。
    """
    new = not os.path.exists(lp)
    with open(lp, 'a', encoding='utf-8', newline='') as f:
        wcsv = csv.writer(f)
        if new:
            wcsv.writerow(LOG_HEADER)
        wcsv.writerow(row)


def verify_file(path, verbose=True):
    """用 cv2 开一下刚录的文件，返回 (帧数, 自报 fps)；没 cv2 返回 None。

    这是本文件唯一能证明"这一段回来抽得出来"的凭据：AVI 索引没写成的文件在屏上
    看着一切正常，回来才发现在 `cv2.VideoCapture` 里是 0 帧——田里只走这一趟。
    X5 上有没有 python 版 cv2 **未确认**（gst 那路本身不依赖它），所以 import 失败
    只打提示、不算录失败，并在日志里留空格。
    """
    try:
        import cv2
    except ImportError:
        if verbose:
            print(u'    [i] 这台机器上没有 cv2，文件没当场验证 ⇒ '
                  u'回笔记本第一时间用 tools/extract_frames.py --dry-run 抽第一段核')
        return None
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        cap.release()
        return (0, 0.0)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    cap.release()
    return (n, fps)


def _run_gst(path, device, w, h, fps, seconds):
    """录一段（默认后端）。返回 (exit_code, actual_s, stderr 尾巴)。

    到点用 SIGINT 而不是 kill：gst-launch 收到 INT 会发 EOS，`avimux` 在这一步才写索引。
    """
    argv = pipeline_argv(path, device, w, h, fps)
    t0 = time.time()
    proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL,  # nosec B603
                            stderr=subprocess.PIPE, text=True)
    try:
        _, err = proc.communicate(timeout=seconds)
    except subprocess.TimeoutExpired:
        proc.send_signal(signal.SIGINT)
        try:
            _, err = proc.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()                     # 连 EOS 都等不到，只能终止（这段多半没索引）
            _, err = proc.communicate()
    return proc.returncode, time.time() - t0, (err or '')[-600:]


def _run_cv2(path, device, w, h, fps, seconds):
    """录一段（`--backend cv2`）：gst 那路起不来时的退路。

    与 `capture_field.record_video()` 同形（同样写 MJPG、同样"分辨率中途变了就丢这一帧"），
    差别只有两点：图像源是本机 `/dev/video0` 而不是网络流，和田里没窗可看（不开 imshow）。
    """
    import cv2
    cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
    cap.set(cv2.CAP_PROP_FPS, fps)
    if not cap.isOpened():
        return 1, 0.0, u'打不开 %s（被 stream_pi 占着？权限？换 --device？）' % device
    vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*'MJPG'), fps, (w, h))
    t_end = time.time() + seconds
    n = 0
    while time.time() < t_end:
        ok, frame = cap.read()
        if not ok or frame is None:
            time.sleep(0.005)
            continue
        if frame.shape[0] != h or frame.shape[1] != w:
            continue                        # 别让 Writer 悄悄截断
        vw.write(frame)
        n += 1
    vw.release()
    cap.release()
    return 0, seconds, u'frames=%d' % n


def free_mb(folder):
    """盘上剩余 MB。目录还不存在时向上找到第一个存在的祖先，按那个文件系统算。"""
    probe = folder
    while probe and not os.path.isdir(probe):
        parent = os.path.dirname(probe.rstrip(os.sep))
        probe = parent if parent and parent != probe else '.'
    return shutil.disk_usage(probe).free / 1048576.0


def check(out_folder, device, w, h, fps, backend, probe_s=None):
    """`--check`：把"这块板子今天能不能自己录"一屏打完；`--probe` 再真录几秒。

    逐项只报**当场测到**的东西，测不到就写"测不到"，不猜（AGENTS 事实铁律）。
    返回 0 表示"这一屏打完了"，不代表通过——通不通过是人看 🔴 与"缺"字的判断，
    故意不把综合结果压成一个退出码：田里要的是知道哪一项不满足。
    """
    print(u'== record_local 上板检查（X5 本地录像，台账 Pc-20）==')
    print(u'[1] 相机节点 %s：%s' % (device, u'在' if os.path.exists(device) else u'🔴 不在'))
    if backend == 'gst':
        has_mux = subprocess.call(['gst-inspect-1.0', 'avimux'],  # nosec B607 B603
                                  stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL) == 0
        has_gst = subprocess.call(['which', 'gst-launch-1.0'],  # nosec B607 B603
                                  stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL) == 0
        print(u'[2] gst-launch-1.0：%s' % (u'在' if has_gst else u'🔴 不在（换 --backend cv2）'))
        print(u'[3] 插件 avimux：%s' % (u'在' if has_mux else u'🔴 缺（换 --backend cv2）'))
    else:
        try:
            import cv2
            print(u'[2] cv2 后端：可用 %s（本路径不查 gst）' %
                  getattr(cv2, '__version__', '?'))
        except ImportError:
            print(u'[2] cv2 后端：🔴 import 不了 ⇒ 退回 --backend gst')
    busy = stream_running(ps_args())
    print(u'[4] 流占用者 stream_pi：%s'
          % (u'🔴 在跑 ⇒ 录像前先 `pkill -f stream_pi.py`（同一块相机不能两路同占，'
             u'且这是未实测的独占假设）' if busy else u'没在跑'))
    print(u'[5] 盘：%s 剩余 %.1f GB；一段 %.0f s @ %dx%d@%d 估 %.0f MB'
          u'（码率 12 MB/s 是估的，没在这块相机上量过）'
          % (out_folder, free_mb(out_folder) / 1024.0, SEGMENT_S, w, h, fps,
             estimate_mb(w, h, fps, SEGMENT_S)))
    if probe_s:
        os.makedirs(out_folder, exist_ok=True)
        p = os.path.join(out_folder, '_probe.avi')
        if backend == 'gst':
            rc, actual, tail = _run_gst(p, device, w, h, fps, probe_s)
        else:
            rc, actual, tail = _run_cv2(p, device, w, h, fps, probe_s)
        size = os.path.getsize(p) if os.path.exists(p) else 0
        mbps = size / 1048576.0 / max(actual, 0.001)
        print(u'[6] 试录 %.0f s：exit=%s，%.1f MB / %.1f s = **实测 %.2f MB/s**%s'
              % (probe_s, rc, size / 1048576.0, actual, mbps,
                 (u'' if rc == 0 else u'；stderr 尾：%s' % tail.strip())))
        got = verify_file(p)
        if got is None:
            print(u'[7] 可读性没验（板子上没 cv2）⇒ 回笔记本抽第一段时补这一眼')
        elif got[0] == 0:
            print(u'[7] 🔴 试录文件 0 帧 / 打不开 ⇒ 这个壳子不能用：换 --backend，'
                  u'或退回笔记本那一路（停车拍照），别带着它下田')
        else:
            print(u'[7] 试录文件可读：%d 帧、自报 %.2f fps ⇒ 与 extract_frames 对得上'
                  % (got[0], got[1]))
        if os.path.exists(p):
            os.remove(p)
            print(u'[8] 试录文件已删（_probe.avi 不是素材）')
    print(u'== 检查完：上面有 🔴 / 缺 就先在板子上解决，别到田里改代码 ==')
    return 0


def record(out_folder, paths, batch, day, device, w, h, fps, backend, durations):
    """按段顺序录；Ctrl-C 收尾当前段就停。返回日志路径（一段都没落返回 None）。

    `durations` 与 `paths` 一一对应（`segment_durations()` 给出的每段秒数）：
    会话总时长到点就停，人在遥控上够不着键盘时也能自己收尾。
    日志**每段落一行**（不是收工才写）：中途断电/崩了，前面几段的账还在。
    """
    if len(paths) != len(durations):
        raise ValueError(u'段数与时长对不上：%d vs %d' % (len(paths), len(durations)))
    os.makedirs(out_folder, exist_ok=True)
    lp = os.path.join(out_folder, 'record_log_%s.csv' % day)
    done = 0
    stop = {'flag': False}

    def _on_sigint(signum, frame):
        stop['flag'] = True
        print(u'\n[i] Ctrl-C：录完当前段就停（不许 kill -9，AVI 索引要收尾才写）')

    old = signal.signal(signal.SIGINT, _on_sigint)
    try:
        for i, (path, seg_s) in enumerate(zip(paths, durations)):
            if stop['flag']:
                break
            free = free_mb(out_folder)
            need = estimate_mb(w, h, fps, seg_s) * MIN_FREE_FACTOR
            if free < need:
                print(u'🔴 盘只剩 %.1f MB，本段按估的码率要 %.1f MB（已留 %.0f%% 余量）'
                      u' ⇒ 停在这里；已录的段都带索引，日志里有账'
                      % (free, need, (MIN_FREE_FACTOR - 1.0) * 100.0))
                break
            seg_start = datetime.datetime.now().strftime('%H:%M:%S')
            print(u'[%d/%d] %s 开始 %s，计划 %.0f s ｜ %s'
                  % (i + 1, len(paths), os.path.basename(path), seg_start, seg_s,
                     build_pipeline(path, device, w, h, fps)))
            if backend == 'gst':
                rc, actual, tail = _run_gst(path, device, w, h, fps, seg_s)
            else:
                rc, actual, tail = _run_cv2(path, device, w, h, fps, seg_s)
            size = os.path.getsize(path) if os.path.exists(path) else 0
            mbps = size / 1048576.0 / max(actual, 0.001)
            got = verify_file(path, verbose=(i == 0))
            frames = None if got is None else got[0]
            note = u'' if rc == 0 else u' 🔴 exit=%s' % rc
            if got is not None and got[0] == 0:
                note += u' 🔴 文件读不出帧，这一段多半废了'
            print(u'    -> %.1f s、%.1f MB、实测 %.2f MB/s、盘上还剩 %.1f GB%s'
                  u'｜ %s' % (actual, size / 1048576.0, mbps,
                              free_mb(out_folder) / 1024.0, note, tail.strip()))
            append_log_row(lp, log_row(seg_start, batch, day, path, seg_s, actual,
                                       rc, size, mbps, frames, device,
                                       '%dx%d@%d' % (w, h, fps), backend))
            done += 1
            if rc != 0:
                print(u'🔴 这一段的 gst/cv2 没干净退出（exit=%s）⇒ 停手：'
                      u'第一段就这样，后面几段只会是同一份失败。'
                      u'先跑 --check --probe 看是哪一项，再回来录' % rc)
                break
    finally:
        signal.signal(signal.SIGINT, old)
    if done:
        print(u'日志：%s（%d 段）' % (lp.replace('\\', '/'), done))
        print(u'回来拷：scp -r %s:~/qoder/%s ./%s'
              % (X5, out_folder.replace('\\', '/'), os.path.basename(out_folder)))
        return lp
    print(u'日志：一段都没落，没写文件')
    return None


def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        description=u'X5 本地录像（秋采行进段，台账 Pc-20）')
    ap.add_argument('--batch', default='t01', help='批次 t{NN}：一段视频=一个条件=一个批次')
    ap.add_argument('--segments', type=int, default=None,
                    help='本次录几段（不给时：有 --session-min 就按总时长自动切，否则 1）')
    ap.add_argument('--session-min', dest='session_min', type=float, default=0.0,
                    help='会话总时长上限（分钟），到点自动收尾；0=不限（默认）。'
                         '人在遥控上够不着键盘时用这个，别用段数硬数')
    ap.add_argument('--segment-s', dest='segment_s', type=float, default=SEGMENT_S,
                    help='每段秒数（默认 %.0f s）' % SEGMENT_S)
    ap.add_argument('--day', default=None, help='文件名里的日期段，默认今天 MMDD')
    ap.add_argument('--out', default=VIDEO_PATH, help='录像目录，默认 %s' % VIDEO_PATH)
    ap.add_argument('--device', default=DEVICE, help='相机节点，默认 %s' % DEVICE)
    ap.add_argument('--width', type=int, default=WIDTH)
    ap.add_argument('--height', type=int, default=HEIGHT)
    ap.add_argument('--fps', type=int, default=FPS,
                    help='帧率，默认 30（相机原生；extract_frames 认 25 与 30 两种）')
    ap.add_argument('--backend', choices=['gst', 'cv2'], default='gst',
                    help='gst=不解码直写 AVI（默认）；cv2=退路，需板子上有 cv2')
    ap.add_argument('--check', action='store_true', help='只做上板检查，不录')
    ap.add_argument('--probe', nargs='?', type=float, const=10.0, default=None,
                    metavar='S', help='试录 S 秒（默认 10）并报实测 MB/s 与可读性')
    ap.add_argument('--dry-run', dest='dry_run', action='store_true',
                    help='只打印将要落的段名与命令，不碰相机')
    ap.add_argument('--force', action='store_true',
                    help='只越「空间」这一道闸（码率是估的，当场量到过才许用）；'
                         u'相机占用与失败退出码不给越——那是物理与事实，不是余量')
    a = ap.parse_args(argv)
    if not BATCH_RE.match(a.batch):
        ap.error(u'批次名要 t{NN}（t01…t99），现在是 %r' % a.batch)
    if a.segments is not None and a.segments < 1:
        ap.error(u'--segments 至少 1（不给就按 --session-min 自动切）')
    if a.session_min < 0:
        ap.error(u'--session-min 不能为负；0 表示不限')
    if a.segment_s <= 0:
        ap.error(u'--segment-s 要正数（想停就 Ctrl-C，别设 0 绕过收尾）')
    if a.probe is not None and a.probe <= 0:
        ap.error(u'--probe 秒数要正数')
    return a


def main(argv=None):
    a = parse_args(argv)
    day = a.day or now_day()
    if a.session_min > 0:
        durations = segment_durations(a.segment_s, a.session_min * 60.0, a.segments)
    else:
        durations = segment_durations(a.segment_s, 0.0,
                                      a.segments if a.segments is not None else 1)
    paths = plan(a.out, a.batch, day, len(durations))
    total_s = sum(durations)

    if a.dry_run:
        for p in paths:
            print(build_pipeline(p, a.device, a.width, a.height, a.fps))
        print(u'共 %d 段、合计 %.0f s，估占 %.0f MB（码率是估的——用 --check --probe 量实测）'
              % (len(paths), total_s, estimate_mb(a.width, a.height, a.fps, total_s)))
        if a.session_min > 0:
            print(u'[i] 会话上限 %.1f 分钟（%.0f s），到点自动收尾'
                  % (a.session_min, a.session_min * 60.0))
        return 0

    if a.check or a.probe is not None:
        return check(a.out, a.device, a.width, a.height, a.fps, a.backend,
                     probe_s=a.probe)

    if not is_posix():
        print(u'🔴 停手：本地录像只能在 X5（Linux）上跑，现在是 %s。'
              u'笔记本这一侧要用的是 tools/capture_field.py（网线直连那一路）。'
              u'要先把这两个文件放上板子：scp vehicle/record_local.py %s:~/qoder/vehicle/ '
              u'与 scp common/capture_naming.py %s:~/qoder/common/'
              % (sys.platform, X5, X5))
        return 2

    need = estimate_mb(a.width, a.height, a.fps, total_s)
    ok, msg = space_verdict(free_mb(a.out), need)
    print(u'[i] %s' % msg)
    if not ok and not a.force:
        return 2
    if stream_running(ps_args()):
        print(u'🔴 停手：stream_pi.py 还在跑，同一块相机不能两路同占'
              u'（这条独占还没在板上实测）。先 `pkill -f stream_pi.py` 再录；'
              u'拍照那一路用完记得把它起回来。这道闸不给 --force 越。')
        return 2

    record(a.out, paths, a.batch, day, a.device, a.width, a.height, a.fps,
           a.backend, durations)
    return 0


if __name__ == '__main__':
    sys.exit(main())
