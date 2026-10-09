# -*- coding: utf-8 -*-
"""B1/B2 台架验收记录器（v1.0 §4.1 里"用户执行，qoder 出验收脚本"那句的实体）。

为什么需要它：B2 的场景（失联停车、模式切换、旧命令残留、夺权后仍发 TOOL）都是
**几秒内发生的瞬时行为**。只靠人眼+记忆，回来就变成"我做了但没证据"——本项目
被这条绊过好几次。本工具做三件事：

  1. 收 MCU 的 STATUS 帧（UDP 9100），复用 `pc/status_rx.StatusReceiver`，
     所以新鲜度、乱序、重启重同步的判据**和生产环境同一套**，不是另写一份近似的；
  2. 把每一帧、每一次模式跳变、每一段静默（gap）带**绝对时间戳**写进 CSV；
  3. 让你**边做边记**：敲一行字回车 = 打一条场景标记（如"④ 拔SBUS (b)悬空"），
     标进同一个时间轴，回来对表不用猜哪段是哪个场景。

不测的事（现在测了也不算数）：横向偏差的**米制**数值——`perception.py` 仍是
占位几何（`IPM_SCALE_X=0.0015`）、`load_ipm_params` 无调用方，所以厘米级结论
要等 E2⑤ 接线 + 一次真标定。这台器只负责**链路、模式、动作**三类证据。

用法（PC 侧，接好 X5/网桥后）：
    python -B tools/bench_status.py                 # 默认 0.0.0.0:9100，**只收不发**
    python -B tools/bench_status.py --out results/bench/S1_0922
    python -B tools/bench_status.py --to 192.168.127.10:9000    # 显式开启发送
X5 侧配套一条命令：`sh ~/qoder/vehicle/start_bridge.sh`（清掉抢串口的 cat + sudo 起桥）。

发送是 **opt-in**（E3 spec §9 / A17，2026-10-08 加）：不填 `--to` 时本工具**一个字节都
不往外发**，`!nav` 之类的输入也只打一行"没启用"的提示。填了才**另开一个不 bind 的**
UDP socket 往 `<桥IP>:<桥端口>` 发（收帧那个 socket 独占 0.0.0.0:9100，不复用它），
stdin 上多一套命令：`!nav vL vR` / `!tool mm lift` / `!beat` / `!auto` / `!manual` /
`!clear`；档案号只从 `config/vehicle_profile.yaml` 取，不在命令行或输入行上给（spec §6，
换档案号 = 换一台车的权限）。**发出的每一帧同样落进那张 CSV**（`kind=tx_*`，带自己的
发送序号），否则"边发边记"的时间轴对不上；发送序号与 STATUS 的接收序号是**两套计数**——
`StatusReceiver` 靠接收序号判新鲜度/重同步（out_of_order、resynced、RESYNC_RUN），
共用就等于自己给自己的判据喂假数据。有了它，验收表里"PC 持续发 NAV/TOOL 的同时看
STATUS"那一类（②③⑧）才不用关掉记录器改用 `pc/main.py`——那条时间轴就是这么丢的。

**发 NAV 之前必须知道的三件事**（09-30 复审 I-1，都是代码事实，出处写着）：
  1. 现在烧在板上的固件，**一条 NAV 就是进 AUTO 的钥匙**：`firmware/retrofit.c:93`
     `if (len < 9 || estop_latched) return;` → `:98-101` 把 `cmd_vl`/`cmd_vr` 钳到
     **±1.0 m/s** → `:102` `mode = MODE_AUTO;`（批 1a 的 F1 修法就是拆掉这一支，但
     **尚未实施、尚未烧**，所以板上还是这个语义）；
  2. "钳到 ±1.0"**不等于安全**：行走斜率 `SLEW_ACC = 0.2 m/s²`（`retrofit.c:140`），
     一条 0.9 的命令约 **4.5 秒**后真的把车推到 0.9 m/s；
  3. 所以本工具对 NAV 有 **0.20 m/s 的硬闸**，与 `tools/link_probe.py` 读同一个数
     （两者共用 `tools/bench_limits.py`，那还是唯一的一份）。超限就 `[TX REFUSED]`：
     不发送、不消耗序号、不落 CSV，只加一个 `refused` 计数。
     **用法前提：驱动轮离地。** 要跑行车闭环请用 `pc/main.py`，这个工具不是行车工具。

**你敲的每一下都会让桥自己注一条 ESTOP**（09-30 复审 I-2，读 STATUS 前先知道）：
`vehicle/bridge.py:24` `LINK_TIMEOUT_MS=500`、`:30` `SEEN_WINDOW_MS=60000`、`:206`
`auto_on=True` 是硬编码 ⇒ 任何**一条**真帧（`!beat`/`!tool`/`!auto` 都算，不只是 NAV）
都会把 PC 标成"在用"，**500 ms 后桥自己往串口注一条 ESTOP**。而 `retrofit_clear_estop()`
全工程没有调用点（台账 **Fw-14**），`!clear` 发的 `TYPE_MODE` 在**现固件**的 switch 里
根本没有分支（`retrofit.c:60-75`）——所以这个锁存**只能把板子断电清**。
后果很具体：边发边记（场景 ②③⑧）时，你回头在 STATUS 里看到的 ESTOP，很可能是**你自己
敲键的节奏**造成的，不是被测机制的反应；把它当成机制结论就是假证据。要连续观察就得
**连续发**——本工具暂无 `--every`，需要周期发送时用
`python -B tools/link_probe.py nav 0 0 --every 0.2 --count 30 --host <X5>`。

开机不用你自查的两件事（09-28 加，都是当天在现场真踩过才写进工具的）：
  · 启动时自动核对"本机是否真的有 `vehicle/config.yaml` 里那个 pc_ip"——不是就直接说出
    该怎么改，不再让你拿 `ipconfig` 的输出自己猜；
  · Ctrl-C 后的小结直接给一句**判定**（0 行→先查发送端而不是拆线；出现重启重同步→板子在
    复位、这轮观察全部不作数；帧率不足→去看 gap 行；否则才说"可以做场景实验"）。

一次只能有一个收帧的人：`pc/main.py --live` 也绑 9100，两个同时开必然有一个
收不到（本工具会直接拒启并说明谁占着）。要做闭环回放就别开它，要取证就别开 main。
⚠️ X5 侧 `vehicle/config.yaml` 的 `pc_ip` 必须指向你这台 PC 的地址：
   网线直连与走 CPE 网桥**是同一个值**（透明网桥、同网段，PC 两端都是 192.168.127.100），
   换桥不用改。代码出厂默认 `192.168.1.2` 是历史遗留，config.yaml 没读到时才会用到它。
"""
import argparse
import csv
import os
import socket
import struct
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
try:                                   # Windows cp936 控制台：中文/符号不许把记录进程打死
    sys.stdout.reconfigure(errors='replace')
except AttributeError:                 # pragma: no cover - py<3.7
    pass

from pc.status_rx import StatusReceiver          # noqa: E402
from common import protocol as P                 # noqa: E402
# 台架 NAV 限速与判定逻辑都在这里（与 tools/link_probe.py 共用同一个出处，09-30 复审 I-1）。
from tools.bench_limits import NAV_BENCH_LIMIT_MPS, nav_exceeds_bench_limit   # noqa: E402

# 固件 retrofit.h:11-13 只有这三个值（pl[13]=mode，没有第四态）。
# 这里不列的编号会原样打印数字——宁可看见"3"，也不要工具替它编一个名字。
MODE_NAME = {0: 'MANUAL', 1: 'AUTO', 2: 'ESTOP'}
# 限位位定义来自固件 read_limits()：PD15 原点 / PD10 左 / PD11 右，低有效。
LIMIT_NAME = [(0x01, 'origin'), (0x02, 'left'), (0x04, 'right')]
GAP_NOTICE_S = 1.0            # 静默超过这个数就记一条 gap（与 STALE_S 同量级）
# 只有这三条 ! 命令的载荷里带 profile（TYPE_MODE，spec §3.1）⇒ 只有它们的 tx 行该填
# profile 列。NAV/TOOL 填了就是给"线上根本没带的字段"造一条看起来像证据的数。
TX_MODE_KINDS = ('tx_auto', 'tx_manual', 'tx_clear')


def local_has_ip(addr):
    """这台机器上到底有没有这个地址。

    用 bind 试探，不去解析 `ipconfig`：跨 Windows/Linux 都能用，而且不依赖外部命令的
    输出格式——格式一改，解析式检查会**静默失效**（变成"永远说没有"或"永远说有"）。
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.bind((addr, 0))
        return True
    except OSError:
        return False
    finally:
        probe.close()


def configured_pc_ip(root=None):
    """取 `vehicle/config.yaml` 里的 `pc_ip`。读不到（没装 pyyaml、文件不在）就返回
    None，让这项自检降级为"不做"，而不是拖着一个好端端的记录器报错退出。"""
    path = os.path.join(root or _ROOT, 'vehicle', 'config.yaml')
    try:
        import yaml
        with open(path, encoding='utf-8') as f:
            return (yaml.safe_load(f) or {}).get('pc_ip')
    except Exception:
        return None


def verdict(good, bad, out_of_order, resynced, seconds, *, rx_rows,
            active=None, tx_rows=0):
    """把小结那几个计数器直接换成判据。

    纯函数 + 单测，理由是现场教训：09-28 那份小结里 `重启重同步 6` 已经写得很明白，
    但人要先把"6"翻译成"板子在复位"才知道不能往下做——今天差点就在复位循环上继续测
    场景了。判据该由工具给，不该留给车边上的人心算。

    `rx_rows` 是**收到的帧行数**（`BenchLog.rx_rows`），不是 CSV 的总行数：Task 8 之后
    同一张表里还有 `tx_*`（发出去的）与 note/gap 行。它做成**只能按关键字传**的参数，
    不叫 `rows`（09-30 复审 M-6）：下一个调用方（Task 9 的 D1/D2）照字面传 `log.rows`
    就把"一帧都没收到"那一支救活了，而那正是本工具明令防的事——名字骗人时至少让写法
    当场 TypeError。

    `tx_rows` 只用来在"一帧都没收到"时多说一句"但你发了 N 条"，它**不进任何分支的条件**——
    发出去的不是收到的证据，拿它去把 `rx_rows == 0` 那一支救活，就等于"因为我发了 NAV
    所以链路算稳定"。
    """
    if rx_rows == 0:
        lines = ['判定：一行都没收到。**这不是"接线不通"的证据**，按顺序查发送端：'
                'X5 上 bridge 在不在跑（`sh ~/qoder/vehicle/start_bridge.sh` 一条命令带过'
                '清 cat + sudo）→ 本机有没有 config.yaml 里那个 pc_ip → 防火墙。']
        if tx_rows:
            lines.append('  注：本次**发出**了 %d 条命令（CSV 里的 tx_* 行）。发出去不等于'
                         '收到，它一条都不算收的证据：查发送端的清单里现在多一项——`--to` '
                         '指的那台机器、那个端口是不是桥（bridge 收帧端口是 9000，'
                         '**不是**你自己在听的 9100）。' % tx_rows)
        return lines
    # 分母必须是**帧流实际覆盖的那段**，不是"从启动到 Ctrl-C"。09-29 现场翻车实例：
    # 启动后 49 秒 bridge 还没起来，之后 135 秒是一条不漏的 20.00 帧/秒，按总时长算出来
    # 只有 14.6 帧/秒，于是本函数指着 CSV 说"去看 gap 行"——CSV 里根本没有 gap 行，
    # 自相矛盾，还把注意力从"链路其实是好的"引开。
    window = active if (active and active > 0) else seconds
    rate = good / window if window else 0.0
    lines = ['判定：帧流覆盖 %.0f 秒，好帧 %d（约 %.1f 帧/秒，固件设计是 20Hz），坏帧 %d，'
             '旧序号拒收 %d，重启重同步 %d。'
             % (window, good, rate, bad, out_of_order, resynced)]
    if active and seconds - active > 3.0:
        lines.append('  注：另有 %.0f 秒落在帧流之外（开机到首帧、或末帧到结束），已从帧率里'
                     '剔除。那段时间记录器根本没在读：bridge 还没起来、X5 没通，或者窗口被'
                     '鼠标选中冻住（快速编辑模式）。它不是链路质量证据。' % (seconds - active))
    # 09-30 复审（codex 新发现二）用两个反例打中本函数：①"10 秒 201 帧后断流 60 秒"
    # 仍被判"链路稳定"——因为我把窗口外的沉默**整段剔除**了却没单独检查它；②"201 好帧 +
    # 1000 坏帧 + 200 旧序号拒收"也判通过——因为 bad/out_of_order 只打印不参与结论。
    # 现在两者都进结论：剔除是为了不误报开机等待，不是为了放过结尾断流。
    if resynced:
        lines.append('  ✗ 出现过 %d 次"重启重同步" ⇒ **序号反复回退**（Hw-26 的形状是每轮约'
                     ' 2.95 秒）。机制尚未定（Hw-26 已撤回"排除看门狗"，Fw-18 的等待循环是当前'
                     '首要嫌疑）；但无论哪种，这段时间里任何模式/动作/方向的观察都不作数。'
                     '现场可判：把油门推住（ch[4]>=800）看还循不循环，见 Fw-18。' % resynced)
    elif bad or out_of_order:
        lines.append('  ✗ 坏帧 %d、旧序号拒收 %d ⇒ 计数不为零就不算干净链路，先查协议/接线，'
                     '不要在这上面做场景实验。' % (bad, out_of_order))
    elif rate < 18.0 or (seconds - window) > 3.0:
        lines.append('  ✗ 帧率低于 18/s 或存在 %.0f 秒的窗口外沉默 ⇒ 中间/结尾有断流，'
                     '去 CSV 看 gap_start/gap_end；gap 行的 note 会写明"这期间到达的 N 个'
                     '报文全被拒收"——那一句区分"线上真没人发"和"发的人在重启"。'
                     '**结尾断流尤其要紧：它意味着"现在"已经不连通。**' % (seconds - window))
    else:
        lines.append('  ✓ 链路稳定 ⇒ 可以做场景实验（④/④a/④b、模式跳变、反向探针）。')
    return lines


def unique_path(path):
    """已存在就往后加 _2/_3……返回一个**还不存在**的路径（配合 BenchLog 的 'x' 打开）。"""
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    n = 2
    while os.path.exists('%s_%d%s' % (stem, n, ext)):
        n += 1
    return '%s_%d%s' % (stem, n, ext)


def classify(prev_mode, mode):
    """这一行该记成什么类型。抽成纯函数以便单测——瞬时行为取证最怕'当时没注意'。"""
    if prev_mode is None:
        return 'first'
    if prev_mode != mode:
        return 'mode_change'
    return 'frame'


class BenchLog:
    """时间轴：帧 / 模式跳变 / 静默段 / 人工场景标记 / **发出的帧**，全落一个 CSV。"""

    def __init__(self, path, t0=None):
        self.path = path        # 小结与调用方都要能拿到证据文件名
        self.t0 = t0 if t0 is not None else time.time()
        # 'x' 而不是 'w'：09-30 复审指出，默认目录只到分钟，同一分钟重跑一次就会
        # 把上一份证据**静默清空**——而台账里可能已经引用过它。宁可报错也不覆盖。
        self.f = open(path, 'x', newline='', encoding='utf-8')
        self.w = csv.writer(self.f)
        # E3 那五列（spec §3.2）：v1 固件（14 B）时它们就是空 —— 空 = "这块板没报"，
        # 不是 0。别在这里替固件填默认值。
        self.w.writerow(['t_rel', 'iso', 'kind', 'seq', 'mode', 'speed',
                         'current_a', 'batt_v', 'limits', 'note', 'peer',
                         'profile', 'authority', 'reject', 'loop_alive',
                         'build_id'])
        # 帧行由主循环写、tx/note 行由 stdin 线程写：②③⑧ 这类场景就是**在 20 Hz 帧流
        # 里敲 !nav**，两个线程同时往一张表里写。撕裂的一行 = 丢掉的一条证据，所以
        # writerow+flush 必须整体在锁里（csv 一行可能分几次 write 落下去）。
        self._lock = threading.Lock()
        self.prev_mode = None
        self.last_rx = None
        self.first_rx = None      # 第一帧到达时刻：帧率只该按"帧流覆盖的那段"算
        self.gap_open_at = None
        self.rows = 0
        self.rx_rows = 0          # **收到的**帧行：verdict 的分母用它，不用 rows
        self.tx_rows = 0          # 发出去的行：只当旁证，永远不进收的判据

    def _row(self, kind, st=None, note='', peer=''):
        now = time.time()
        st = st or {}
        row = [
            '%.3f' % (now - self.t0),
            time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now))
            + '.%03d' % int((now % 1) * 1000),
            kind,
            st.get('seq', ''), st.get('mode', ''),
            '%.3f' % st['speed_mps'] if 'speed_mps' in st else '',
            '%.2f' % st['current_a'] if 'current_a' in st else '',
            '%.2f' % st['battery_v'] if 'battery_v' in st else '',
            st.get('limits', ''), note, peer,
            # v1 帧这五个键的值是 None（protocol.unpack_status_any），csv 写成空字段：
            # "这块板没报"与"报了 0"在表里从此是两种长相。
            st.get('profile', ''), st.get('authority', ''), st.get('reject', ''),
            st.get('loop_alive', ''), st.get('build_id', '')]
        with self._lock:
            self.w.writerow(row)
            self.f.flush()
            self.rows += 1
            if kind.startswith('tx_'):
                self.tx_rows += 1
        return now

    def frame(self, st, peer):
        kind = classify(self.prev_mode, st.get('mode'))
        self.prev_mode = st.get('mode')
        now = time.time()
        if self.gap_open_at is not None:
            # gap_end 先落账：静默是在"这一帧到达"时结束的，顺序反过来会让
            # 回来对表的人读成"先收到帧、gap 才结束"，误判恢复时刻。
            self._row('gap_end', note='静默 %.2f s' % (now - self.gap_open_at))
            self.gap_open_at = None
        self.last_rx = self._row(kind, st, peer=peer)
        self.rx_rows += 1          # 只有"收到并接受的帧"才算收的证据（verdict 的分母）
        if self.first_rx is None:
            self.first_rx = now
        return kind

    def note(self, text):
        return self._row('note', note=text)

    def tx(self, kind, note='', st=None):
        """发出的帧也落同一张 CSV —— 否则"边发边记"的时间轴对不上。

        `st` 只带发送侧真有的那几项（seq，MODE 帧再加 profile）；mode/speed/电流
        那些列留空——"我发了什么"与"板子回了什么"是两条独立证据，在这张表里不许互相对顶。
        """
        return self._row(kind, st=st, note=note)

    def check_gap(self, now=None, during=''):
        """静默检测： STATUS 停发 = 链路断或 MCU 挂，是 ④⑤⑦⑧ 场景的主证据。

        `during` 是调用方给的一句旁证（"这期间还有报文到达但全被拒收"），它把
        "线上真的没人发" 与 "发的人在重启" 这两种在 CSV 里长得一模一样的静默分开。
        """
        now = now if now is not None else time.time()
        if self.last_rx is None:
            return False
        if now - self.last_rx > GAP_NOTICE_S and self.gap_open_at is None:
            self.gap_open_at = self.last_rx
            self._row('gap_start',
                      note='STATUS 静默 >%.1f s%s' % (GAP_NOTICE_S, during))
            return True
        return False

    def close(self):
        if self.gap_open_at is not None:
            self._row('gap_end', note='结束时仍未收到新帧')
        self.f.close()


# --------------- 发送：opt-in（E3 spec §9 / A17；不填 --to 就是只收）---------------

def build_command(line, profile_id, seq):
    """把 stdin 的一行翻成一个待发帧，返回 (kind, frame_bytes)。

    解析不了就返回 **None**（不猜、不默认）：`!nav` 少了参数、`!tool x y` 里 x 不是
    数、`!nope` 不认识——三种都该什么都不发，而不是"发个 0 试试"。

    seq 由调用方给（发送侧那一套独立计数器，见 TxSender），这里只组帧不记号。
    """
    parts = line.strip().split()
    if not parts or not parts[0].startswith('!'):
        return None
    cmd, args = parts[0][1:], parts[1:]
    try:
        if cmd == 'nav' and len(args) == 2:
            payload = P.pack_nav(float(args[0]), float(args[1]))
            return 'tx_nav', P.pack_frame(P.TYPE_NAV, payload, seq)
        if cmd == 'tool' and len(args) == 2:
            # lift 用 int(x, 0)：台架上要写 `!tool 0 0x07` 一次提三把刀。注意 base 0
            # 不接受 `07` 这种前导零（那是 ValueError ⇒ 返回 None），不写 0x 就按十进制。
            payload = P.pack_tool(float(args[0]), int(args[1], 0))
            return 'tx_tool', P.pack_frame(P.TYPE_TOOL, payload, seq)
        if cmd == 'beat' and not args:
            return 'tx_beat', P.pack_frame(P.TYPE_HEARTBEAT, b'', seq)
        if cmd in ('auto', 'manual', 'clear') and not args:
            req = {'auto': P.MODE_REQ_AUTO, 'manual': P.MODE_REQ_MANUAL,
                   'clear': P.MODE_REQ_CLEAR_ESTOP}[cmd]
            return ('tx_' + cmd,
                    P.pack_frame(P.TYPE_MODE, P.pack_mode(req, profile_id), seq))
    except (ValueError, TypeError, OverflowError, struct.error):
        # 为什么接这四样而不只是前两样：`struct.error` 与 `OverflowError` **都不是**
        # ValueError 的子类，`!tool 0 256`（lift 越出 u8）或 `!nav 1e39 0`（f32 装不下）
        # 会从这里逃出去，把 stdin 那条线程整个打死 —— 之后场景标记与命令都不再进时间轴，
        # 而这正是本工具存在的理由。宁可一行都不发，也不能让记录器因为一个字打错而失忆。
        return None
    return None


def resolve_target(text, avoid_port=None):
    """把 --to 的 `HOST:PORT` 翻成 (host, port)；`text` 是 None 就是**不发送**。

    解析失败一律 ValueError，**不静默降级成"只收"**：填了 --to 就说明人准备发命令，
    端口写错却照常启动，他会以为自己正在发 NAV，而板上一个字节都没收到——
    ②③⑧ 那类"PC 持续发的同时看 STATUS"的证据就是这么凭空变成假的。

    两类目标直接拒：
      · 广播 / 组播 / 未指定（255.255.255.255、0.0.0.0、224–239.x.x），**以及定向广播**
        `x.x.x.255` 与网络号 `x.x.x.0`：一条命令对整个网段下指令，那不等于"发个测试帧"，
        是发给**所有**听得见的板子。台架网段固定是 /24（PC 192.168.127.100、
        X5 192.168.127.10），所以 192.168.127.255 就是本段的广播地址——它"看着像单播"
        但后果与 255.255.255.255 一模一样（09-30 复审 M-3，选"拒"而不是"写明不拦"）。
      · 端口 = 本机正在收 STATUS 的那个端口：发出去打回自己，`StatusReceiver` 会把
        它们当坏帧计进 bad/ALARM，自己污染自己的判据（bridge 收帧端口是 9000）。
    主机名不在这里做解析（不调 getaddrinfo），所以"某个域名指到广播地址"不在拦截
    范围内：台架是 IP 对 IP，这里就按 IP 写。
    """
    if text is None:
        return None
    host, sep, port_text = str(text).strip().rpartition(':')
    if not sep or not host or not port_text:
        raise ValueError('--to 要写成 HOST:PORT（例如 192.168.127.10:9000），收到 %r'
                         % text)
    try:
        port = int(port_text)
    except ValueError:
        raise ValueError('--to 的端口不是十进制整数：%r' % text)
    if not 1 <= port <= 65535:
        raise ValueError('--to 的端口超出 1..65535：%r' % text)
    octets = host.split('.')
    if len(octets) == 4 and all(o.isdigit() for o in octets):
        nums = [int(o) for o in octets]
        if any(n > 255 for n in nums):
            raise ValueError('--to 的地址不是合法 IPv4：%r' % text)
        if host in ('255.255.255.255', '0.0.0.0') or 224 <= nums[0] <= 239:
            raise ValueError('--to 拒绝广播/组播/未指定地址（%r）：那是对整个网段上所有'
                             '板子下命令' % text)
        if nums[3] == 255:
            raise ValueError('--to 拒绝定向广播（%r）：台架网段是 /24，x.x.x.255 是本段的'
                             '广播地址，一条命令会同时指挥所有听得见的板子——后果与 '
                             '255.255.255.255 一样，不因为它"看着像单播"就放行' % text)
        if nums[3] == 0:
            raise ValueError('--to 拒绝网络号（%r）：/24 的 x.x.x.0 是网段本身，'
                             '不是任何一台主机，发过去没有接收方' % text)
    if avoid_port is not None and port == avoid_port:
        raise ValueError('--to 的端口 %d 正是本机在收 STATUS 的端口：发出去会打回自己，'
                         '坏帧计数与 ALARM 就被自己污染了。桥收帧用的是 9000。' % port)
    return host, port


class TxSender:
    """发送侧：**独立的 socket + 独立的序号计数器**（两个"独立"都是契约不是风格）。

    不复用收帧那个 socket —— 它 bind 在 0.0.0.0:9100 还带 SO_EXCLUSIVEADDRUSE，
    拿它 sendto 等于把源端口也变成 9100，在同一张套接字上又收又发。
    不复用接收序号 —— `StatusReceiver` 靠 STATUS 的 seq 判新鲜度、乱序
    （out_of_order）与重启重同步（连续 RESYNC_RUN=50 个递增的被拒序号）。发送帧如果
    从同一个计数器取号，就是自己往那套判据里塞假数据；判据一坏，这台器就没有
    证据价值了（这正是"边发边记"最容易被忽略的地方）。

    sock 参数是给测试留的缝（假 socket 记 sendto 的字节，不需要网口也不需要板子）。
    """

    def __init__(self, host, port, sock=None):
        self.host, self.port = host, port
        self.sock = sock if sock is not None else \
            socket.socket(socket.AF_INET, socket.SOCK_DGRAM)      # **不 bind**
        self.seq = 0
        self.sent = 0
        self.errors = 0
        self.unparsed = 0
        self.refused = 0          # 过了语法、没过限速（I-1 的闸）

    def send_line(self, line, profile_id, log):
        """一行 stdin → 帧 → 限速闸 → sendto → 落一行 tx_*。成功返回 (kind, seq)，否则 None。

        只有**真的写出去了**才落 tx 行、才消耗序号：sendto 抛了还记一行 tx_nav，
        就是给"这帧上过线"造一条假证据；而序号不消耗，下一条接着用同一个号。

        三类"什么都没发生"各有自己的出口，也都各有计数，不混在一起：
          · 解析不了      -> `unparsed`（[TX SKIPPED]）
          · 超出台架限速  -> `refused` （[TX REFUSED]，I-1）
          · 发送失败      -> `errors`  （[TX FAILED]）
        """
        parsed = build_command(line, profile_id, self.seq)
        if parsed is None:
            self.unparsed += 1
            print('  [TX SKIPPED] cannot parse %r  (want: !nav vL vR | '
                  '!tool mm lift | !beat | !auto | !manual | !clear)' % line)
            return None
        kind, frame = parsed
        if kind == 'tx_nav':
            # 速度硬闸（09-30 复审 I-1）。判的是**要上线的那对字节**，不是输入行上的字面量：
            # 闸该拦的是帧，不是打字。现固件把一条 NAV 当进 AUTO 的钥匙并把速度钳到 ±1.0 m/s
            # （firmware/retrofit.c:93-102），而斜率是 0.2 m/s²（:140）——0.9 的命令 4.5 秒
            # 后真的会把车推到 0.9 m/s。同一个 bridge:9000 入口的两个 PC 侧发送器
            # （这里与 tools/link_probe.py）必须共用一个数，所以常量在 tools/bench_limits.py。
            vl, vr = P.unpack_nav(P.unpack_frame(frame)[2])[:2]
            if nav_exceeds_bench_limit(vl, vr):
                self.refused += 1
                print('  [TX REFUSED] nav beyond %.2f m/s bench limit '
                      '(nothing sent, nothing recorded)' % NAV_BENCH_LIMIT_MPS)
                return None
        try:
            self.sock.sendto(frame, (self.host, self.port))
        except OSError as exc:
            self.errors += 1
            print('  [TX FAILED] sendto %s:%d -> %s (nothing sent, nothing recorded)'
                  % (self.host, self.port, exc))
            return None
        seq = self.seq
        self.seq = (self.seq + 1) & 0xFFFF          # u16 回绕，与固件那边同一个宽度
        self.sent += 1
        st = {'seq': seq}
        if kind in TX_MODE_KINDS:                   # 只有 MODE 帧的载荷里真有档案号
            st['profile'] = profile_id
        log.tx(kind, note='%s -> %s:%d' % (line, self.host, self.port), st=st)
        print('  [TX @%.3fs] %-9s seq=%-5s %d B -> %s:%d'
              % (time.time() - log.t0, kind, seq, len(frame),
                 self.host, self.port))
        return kind, seq

    def close(self):
        try:
            self.sock.close()
        except OSError:                 # 关不掉也没什么：进程马上就走，别让小结变成 traceback
            pass


def sender_from_target(text, avoid_port=None):
    """--to 的取值 → TxSender；**缺省（None）→ None = 发送彻底禁用**。"""
    target = resolve_target(text, avoid_port=avoid_port)
    return None if target is None else TxSender(target[0], target[1])


def handle_command_line(line, log, sender, profile_id=P.PROFILE_NONE):
    """`!` 开头的输入行都走这里。

    sender 为 None（没给 --to）时**一个字节都不发**，也不写 tx 行——把没上线的帧
    记进 CSV，⑧ 那条"线上 PC 仍在发"的证据就是假的。但也不静默吞掉：打一行说明，
    否则人以为自己正在发 NAV。
    """
    if sender is None:
        print('  [TX DISABLED] %r not sent: this recorder is receive-only unless it '
              'was started with --to HOST:PORT' % line)
        return None
    return sender.send_line(line, profile_id, log)


def load_profile_id():
    """!auto/!manual/!clear 载荷里的档案号**只从车辆档案取**（spec §6；与
    `tools/link_probe.py` 同一个口径：档案号 = 哪台车的权限，不在命令行/输入行上给）。

    读不到就用 PROFILE_NONE=0 并打一行 ASCII 警告。0 一定被固件 reject=0x01 拒掉，
    CSV 的 reject 列会写着——宁可被板子拒绝并看得见原因，也不替车猜一个"看起来合法"
    的号：猜了就把"用错档案号申请无人"（验收表 ⑪）测成"档案握手一致"了。
    """
    try:
        from pc import vehicle_profile
        return int(vehicle_profile.load()['profile_id'])
    except (ValueError, OSError) as exc:      # load() 把 OSError 也收进 ValueError
        print('warning: vehicle profile unavailable (%s) -> sending profile=0; '
              'the board will reject MODE requests with reject=0x01' % exc)
        return P.PROFILE_NONE


def _note_listener(log, stop, sender=None, profile_id=P.PROFILE_NONE):
    """键盘输入 = 场景标记；`!` 开头的行 = 一条待发命令（见 handle_command_line）。

    sender 由 `main()` 给：没给 `--to` 时它就是 **None**，`!nav` 之类的输入一个字节
    都不会出去。解析不了的 `!` 行**不降级成场景标记**——那样时间轴上会多出一条
    长得像"我发了 NAV"的记录，而线上什么都没发生。
    """
    try:
        while not stop.is_set():
            line = sys.stdin.readline()
            if not line:
                return
            line = line.strip()
            if not line:
                continue
            if line.startswith('!'):
                handle_command_line(line, log, sender, profile_id)
                continue
            t = log.note(line)
            print('  [标记 @%.3f] %s' % (t - log.t0, line))
    except (EOFError, OSError) as exc:
        # 旧写法是 `pass`（09-30 复审 M-4）：磁盘满、CSV 被 Excel 占住、stdin 被别的
        # 进程关掉，都会让这条线程**无声退出**——之后的每一次模式跳变、每一条场景标记、
        # 每一条 !命令都不再进时间轴，而屏幕上什么都看不出来。本工具存在的理由就是
        # "当时没注意回来就没了"，被它自己无声没收一次是最坏的结果。
        # 正常的 stdin 结束走的是上面的 `if not line: return`，到不了这里。
        print('  [NOTE LISTENER DEAD] %s: %s -- notes and !commands are NO LONGER '
              'being recorded' % (type(exc).__name__, exc))


def _during_note(ctr):
    """静默行上那句旁证：把"线上真的没人发"和"有人在发但全被拒收"分开写。"""
    if not ctr['rejected']:
        return ''
    return ('，这期间到达的 %d 个报文全被拒收（序号回退或坏帧）'
            '⇒ 链路并没有真的静默，是发送端在重启或协议错位' % ctr['rejected'])


def _alarm_note(rx, log, ctr, cooldown_s=5.0):
    """坏帧洪水也要落一条 note。

    09-30 复审指出：原来 `rx.alarm()` 的检查放在**有效帧**路径之后，而主循环遇到
    坏帧就 `continue` —— 于是"坏帧持续到达"这个 alarm 设计要抓的唯一场景，恰恰永远
    走不到检查那一行，ALARM 形同虚设。现在由 pump_once 在拒收分支里调用。
    """
    if not rx.alarm():
        return
    nowt = time.time()
    if ctr.get('alarm_at') and nowt - ctr['alarm_at'] < cooldown_s:
        return                                  # 洪水期间每 5 秒最多一条，别淹掉时间轴
    ctr['alarm_at'] = nowt
    log.note('ALARM 坏帧告警（1 秒内 >=5 个坏帧，疑似 PC/固件协议错位）')


def pump_once(data, addr, rx, log, ctr, now=None):
    """处理一次 recvfrom 的结果，返回 (kind, status_dict)；没东西可打印时 (None, None)。

    **check_gap 每轮都要调，与这一帧有没有被接受无关。** 09-28 台架实测出这个静默
    缺陷：原来只在 `except socket.timeout` 分支里调它，于是"报文一直到达、但全部被
    StatusReceiver 拒收"这一路（MCU 重启后序号回退正好就是这个样子）永远进不了
    timeout 分支。证据就是当天那份 CSV：kind 只有 `first` 1 行 + `frame` 110 行，
    **gap_start / gap_end 一行都没有**，而屏幕时间戳明摆着有六段 2.95 秒空窗。
    ④⑤⑦⑧ 的场景证据本质就是"从断到停的那几秒"，这个盲点正对着它们，所以修在
    调用点上而不是只改注释：现在无论这一帧被接受、被拒收、还是根本没到达，
    静默判定都走一遍。
    """
    kind = st_out = None
    if data is not None:
        st = rx.handle(data)
        if st is None:
            ctr['rejected'] += 1
            _alarm_note(rx, log, ctr)
        else:
            ctr['rejected'] = 0
            kind = log.frame(st, peer=addr[0])
            st_out = st
    log.check_gap(now=now, during=_during_note(ctr))
    return kind, st_out


def build_argparser():
    """argparse 单独成函数：`--to` 的**默认值**就是"发送禁用"这件事的唯一载体，
    它得能被单测直接问一句，而不是藏在 main 的流程里问不到。"""
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=9100)
    ap.add_argument('--out', default=None, help='输出目录，默认 results/bench_<日期>')
    ap.add_argument('--to', default=None, metavar='HOST:PORT',
                    help='**opt-in**：往 X5 的 bridge 发送（例如 192.168.127.10:9000，'
                         '桥的收帧端口），stdin 上的 !nav/!tool/!beat/!auto/!manual/'
                         '!clear 才生效。**不填 = 彻底禁用发送**，一个字节都不外发。'
                         '填了但写错（缺端口、端口非数字、广播/组播/未指定地址、'
                         '定向广播 x.x.x.255 与网络号 x.x.x.0、端口正好是本机的收帧端口）'
                         '会报错退出，不会静默降级成"只收"。开启后驱动轮必须**离地**，'
                         'NAV 有 %.2f m/s 的硬闸（与 tools/link_probe.py 同源，超了拒发）；'
                         '另外桥会在单条命令 0.5 秒后自注 ESTOP，锁存只能断电清。'
                         % NAV_BENCH_LIMIT_MPS)
    return ap


def main():
    a = build_argparser().parse_args()

    out_dir = a.out or os.path.join('results', 'bench_' + time.strftime('%Y%m%d_%H%M'))

    # 发送目标在**绑端口之前**解析：--to 写错就在碰任何资源之前退出，既不在盘上留下
    # 半份 CSV，也不会让人开着记录器以为"我正在发 NAV"。
    try:
        sender = sender_from_target(a.to, avoid_port=a.port)
    except ValueError as exc:
        sys.exit(str(exc))
    # 档案号只在真的要发 MODE 请求时才去读（读不到会打一行警告并退回 0）。
    profile_id = load_profile_id() if sender is not None else P.PROFILE_NONE

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # 不用 SO_REUSEADDR：09-22 在 Windows 上实测，第二个进程带这个选项 bind
    # **照样成功**，包却只发给先绑上的那个 socket —— 于是"端口被上次没关干净的
    # 进程占着"这个最常见的现场故障，会伪装成"接线不通、一帧都收不到"。
    # 改成独占绑定（Windows 上 SO_EXCLUSIVEADDRUSE 连别人留下的可复用绑定也拦，
    # 实测第二个进程 rc=1 并报 WinError 10048），下面那句错才真的会说真话。
    if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        sock.bind(('0.0.0.0', a.port))
    except OSError as exc:
        # 09-22 台架预演真实踩过：上一次没关干净的记录进程还占着端口，
        # 这一句裸 traceback 会让人在车边上分不清是没接线还是没关干净。
        sock.close()
        sys.exit('端口 %d 已被另一个进程占用（%s）。同一个端口只能有一个收帧的人，'
                 '最常见的是还开着的 `python pc/main.py --live`（它也绑 9100，'
                 '见 pc/status_rx.py:19），或上一次没关干净的记录进程。'
                 '先关掉它，或换一个 --port。' % (a.port, exc))
    sock.settimeout(0.5)

    # 绑定成功之后才建日志：先建再绑的话，被拒的那一次会在盘上留下一个空 CSV，
    # 事后翻 results/ 会多出假证据文件。
    os.makedirs(out_dir, exist_ok=True)
    csv_path = unique_path(os.path.join(out_dir, 'bench_log.csv'))
    if csv_path.endswith('_2.csv') or '_3.csv' in csv_path or '_4.csv' in csv_path:
        print('注意：同一目录里已有别的记录文件，本次另存为 %s（旧文件不覆盖）'
              % os.path.basename(csv_path))
    log = BenchLog(csv_path)
    rx = StatusReceiver()

    stop = threading.Event()
    threading.Thread(target=_note_listener,
                     args=(log, stop, sender, profile_id), daemon=True).start()

    print('STATUS 记录中 → %s' % csv_path)
    print('每一行字 + 回车 = 打一条场景标记；Ctrl-C 结束并打印小结。')
    print('  commands: !nav vL vR | !tool mm lift | !beat | !auto | !manual | !clear')
    # 发送状态必须**开机就看得见**：它决定你正在做的场景是不是"边发边记"。
    if sender is None:
        print('send: DISABLED (receive-only) -- nothing is sent unless this run was '
              'started with --to HOST:PORT')
    else:
        print('send: ENABLED -> %s:%d  (own socket, own seq counter, profile=%d from '
              'the vehicle profile)' % (sender.host, sender.port, profile_id))
        # 下面两行是 09-30 复审点出来的两个风险面（I-1 / I-2）。放这里而不是只放
        # docstring：台架上没人翻文件，操作员只看开机这几行；而这两件事的后果
        # 分别是"车自己开走"和"把自己的敲键读成机制结论"。
        print('  bench only, drive wheels OFF the ground; nav is hard-capped at '
              '%.2f m/s -- the flashed firmware enters AUTO on ONE nav frame and '
              'clamps speed to +/-1.0 m/s (retrofit.c:93-102), slew 0.2 m/s^2 '
              '(retrofit.c:140), so 0.9 takes about 4.5 s to actually move the '
              'vehicle' % NAV_BENCH_LIMIT_MPS)
        print('  the bridge injects its OWN ESTOP 0.5 s after any single frame '
              '(bridge.py:24/30/206); that latch is cleared only by powering the '
              'board down -- retrofit_clear_estop has no caller (Fw-14) and !clear '
              'sends TYPE_MODE, which the flashed firmware does not handle. '
              'To observe continuously, keep sending (this tool has no --every yet)')
    # 原来这里只是一句"请先去确认 pc_ip"的提示，等于把判断推给人做。09-28 改成自己查：
    # X5 是按 config.yaml 里的 pc_ip **单向投递**的，本机不是那个地址就一帧都收不到，
    # 而这在 CSV 里和"接线不通"长得一模一样——今天已经为此白拆过一次线。
    _ip = configured_pc_ip()
    if _ip and not local_has_ip(_ip):
        print('注意：X5 会把 STATUS 投递到 %s，但这台机器上**没有**这个地址（bind 不上）。'
              '现在收不到帧不是接线的锅：要么把本机网卡设成 %s/24，要么改 X5 上 '
              'vehicle/config.yaml 的 pc_ip 后重启 bridge。' % (_ip, _ip))
    elif _ip:
        print('本机地址核对通过：%s 在这台机器上（与 X5 config.yaml 的 pc_ip 一致）。' % _ip)
    print('注意：I=电流、U=电压两列固件里是 adc_current_a() 与写死的 48.0f（retrofit.c:226），'
          '只能当占位，不是实测。')
    n = 0
    last_hint = 0.0
    ctr = {'rejected': 0}
    try:
        while True:
            try:
                data, addr = sock.recvfrom(2048)
            except socket.timeout:
                data, addr = None, None
            # 静默判定跟"这一帧有没有被接受"无关，统一放进 pump_once（为什么必须这样，
            # 那里的注释写着——这是 09-28 那份 CSV 里 gap 一行都没有的根因）。
            kind, st = pump_once(data, addr, rx, log, ctr)
            if st is None:
                # 09-28 在车边上连撞两次同一个歧义：0 帧时，"线没通"和"X5 上根本
                # 没人发"长得一模一样——bridge.py 是 UDP 的唯一发送方，它没跑、或者
                # 有人用 `sudo cat /dev/ttyS1` 跟它抢同一个串口（两个读者会把帧撕成
                # 半截，谁都解不出来），这边看到的都是同样的空 CSV。所以静默满 5 秒
                # 就点名最可能的那一个，而不是让人去怀疑接线。
                if data is None and n == 0 and time.time() - log.t0 >= 5 and \
                        time.time() - last_hint >= 10:
                    last_hint = time.time()
                    print('  [%.0fs] 还是 0 帧。先查发送端，别拆线：X5 上 '
                          '`pgrep -af bridge` 看 bridge.py 在不在跑，'
                          '`pgrep -af "cat /dev/ttyS"` 看有没有 cat 在抢串口'
                          '（两者不能同读一个 ttyS1）。' % (time.time() - log.t0))
                continue
            n += 1
            tag = {'first': '首帧', 'mode_change': '>>> 模式跳变', 'frame': ''}[kind]
            lim = ''.join('+' + name for bit, name in LIMIT_NAME if st['limits'] & bit)
            print('%.2fs seq=%-5s mode=%-6s v=%+.2f I=%5.2f U=%5.2f lim=0x%02x %-18s %s'
                  % (st.get('t', 0) or time.time() - log.t0, st['seq'],
                     MODE_NAME.get(st['mode'], st['mode']), st['speed_mps'],
                     st['current_a'], st['battery_v'], st['limits'], lim, tag))

    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        log.close()
        print('\n=== 小结 ===')
        print('  行数 %d  好帧 %d  坏帧 %d  乱序 %d  重启重同步 %d'
              % (log.rows, rx.good, rx.bad, rx.out_of_order, rx.resynced))
        if sender is not None:
            # 发出去多少、被限速闸拦了多少、失败多少、以及"这些都不算收到的证据"
            # （分开的两套计数）。refused 单列（I-1）：它既不是发送成功也不是解析失败，
            # 混进任何一边都会让"我发了几条"这个问题在事后答不准。
            print('  TX sent=%d  refused=%d  send_errors=%d  unparsed_lines=%d  '
                  'next_tx_seq=%d  (rx frame rows=%d / csv rows=%d)'
                  % (sender.sent, sender.refused, sender.errors, sender.unparsed,
                     sender.seq, log.rx_rows, log.rows))
            sender.close()
        _active = (log.last_rx - log.first_rx) if log.first_rx else None
        # 分母是 rx_rows（**收到的**帧行），不是 rows：加了 tx_*/note/gap 行之后的
        # 总行数会把"一行都没收到"那一支救活，那正是"因为我发了所以算稳定"。
        for line in verdict(rx.good, rx.bad, rx.out_of_order, rx.resynced,
                            time.time() - log.t0, rx_rows=log.rx_rows,
                            active=_active, tx_rows=log.tx_rows):
            print(line)
        print('  证据文件：%s' % csv_path)
        print('  下一步：把这份 CSV 的路径写进缺口清单 ② 板对应行的"证据"栏，'
              '别只写"已做"。')


if __name__ == '__main__':
    main()
