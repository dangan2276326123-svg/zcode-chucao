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
    python -B tools/bench_status.py                 # 默认 0.0.0.0:9100
    python -B tools/bench_status.py --out results/bench/S1_0922
X5 侧配套一条命令：`sh ~/qoder/vehicle/start_bridge.sh`（清掉抢串口的 cat + sudo 起桥）。

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

# 固件 retrofit.h:11-13 只有这三个值（pl[13]=mode，没有第四态）。
# 这里不列的编号会原样打印数字——宁可看见"3"，也不要工具替它编一个名字。
MODE_NAME = {0: 'MANUAL', 1: 'AUTO', 2: 'ESTOP'}
# 限位位定义来自固件 read_limits()：PD15 原点 / PD10 左 / PD11 右，低有效。
LIMIT_NAME = [(0x01, 'origin'), (0x02, 'left'), (0x04, 'right')]
GAP_NOTICE_S = 1.0            # 静默超过这个数就记一条 gap（与 STALE_S 同量级）


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


def verdict(good, bad, out_of_order, resynced, rows, seconds, active=None):
    """把小结那几个计数器直接换成判据。

    纯函数 + 单测，理由是现场教训：09-28 那份小结里 `重启重同步 6` 已经写得很明白，
    但人要先把"6"翻译成"板子在复位"才知道不能往下做——今天差点就在复位循环上继续测
    场景了。判据该由工具给，不该留给车边上的人心算。
    """
    if rows == 0:
        return ['判定：一行都没收到。**这不是"接线不通"的证据**，按顺序查发送端：'
                'X5 上 bridge 在不在跑（`sh ~/qoder/vehicle/start_bridge.sh` 一条命令带过'
                '清 cat + sudo）→ 本机有没有 config.yaml 里那个 pc_ip → 防火墙。']
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


def classify(prev_mode, mode):
    """这一行该记成什么类型。抽成纯函数以便单测——瞬时行为取证最怕'当时没注意'。"""
    if prev_mode is None:
        return 'first'
    if prev_mode != mode:
        return 'mode_change'
    return 'frame'


class BenchLog:
    """时间轴：帧 / 模式跳变 / 静默段 / 人工场景标记，全落一个 CSV。"""

    def __init__(self, path, t0=None):
        self.path = path        # 小结与调用方都要能拿到证据文件名
        self.t0 = t0 if t0 is not None else time.time()
        self.f = open(path, 'w', newline='', encoding='utf-8')
        self.w = csv.writer(self.f)
        self.w.writerow(['t_rel', 'iso', 'kind', 'seq', 'mode', 'speed',
                         'current_a', 'batt_v', 'limits', 'note', 'peer'])
        self.prev_mode = None
        self.last_rx = None
        self.first_rx = None      # 第一帧到达时刻：帧率只该按"帧流覆盖的那段"算
        self.gap_open_at = None
        self.rows = 0

    def _row(self, kind, st=None, note='', peer=''):
        now = time.time()
        st = st or {}
        self.w.writerow([
            '%.3f' % (now - self.t0),
            time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now))
            + '.%03d' % int((now % 1) * 1000),
            kind,
            st.get('seq', ''), st.get('mode', ''),
            '%.3f' % st['speed_mps'] if 'speed_mps' in st else '',
            '%.2f' % st['current_a'] if 'current_a' in st else '',
            '%.2f' % st['battery_v'] if 'battery_v' in st else '',
            st.get('limits', ''), note, peer])
        self.f.flush()
        self.rows += 1
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
        if self.first_rx is None:
            self.first_rx = now
        return kind

    def note(self, text):
        return self._row('note', note=text)

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


def _note_listener(log, stop):
    """键盘输入 = 场景标记。按 Ctrl-C 前不阻塞主循环（daemon 线程）。"""
    try:
        while not stop.is_set():
            line = sys.stdin.readline()
            if not line:
                return
            line = line.strip()
            if line:
                t = log.note(line)
                print('  [标记 @%.3f] %s' % (t - log.t0, line))
    except (EOFError, OSError):
        pass


def _during_note(ctr):
    """静默行上那句旁证：把"线上真的没人发"和"有人在发但全被拒收"分开写。"""
    if not ctr['rejected']:
        return ''
    return ('，这期间到达的 %d 个报文全被拒收（序号回退或坏帧）'
            '⇒ 链路并没有真的静默，是发送端在重启或协议错位' % ctr['rejected'])


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
        else:
            ctr['rejected'] = 0
            kind = log.frame(st, peer=addr[0])
            st_out = st
    log.check_gap(now=now, during=_during_note(ctr))
    return kind, st_out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=9100)
    ap.add_argument('--out', default=None, help='输出目录，默认 results/bench_<日期>')
    a = ap.parse_args()

    out_dir = a.out or os.path.join('results', 'bench_' + time.strftime('%Y%m%d_%H%M'))

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
    csv_path = os.path.join(out_dir, 'bench_log.csv')
    log = BenchLog(csv_path)
    rx = StatusReceiver()

    stop = threading.Event()
    threading.Thread(target=_note_listener, args=(log, stop), daemon=True).start()

    print('STATUS 记录中 → %s' % csv_path)
    print('每一行字 + 回车 = 打一条场景标记；Ctrl-C 结束并打印小结。')
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
            if rx.alarm():
                log.note('ALARM 坏帧告警（疑似 PC/固件协议错位）')
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        log.close()
        print('\n=== 小结 ===')
        print('  行数 %d  好帧 %d  坏帧 %d  乱序 %d  重启重同步 %d'
              % (log.rows, rx.good, rx.bad, rx.out_of_order, rx.resynced))
        _active = (log.last_rx - log.first_rx) if log.first_rx else None
        for line in verdict(rx.good, rx.bad, rx.out_of_order, rx.resynced,
                            log.rows, time.time() - log.t0, active=_active):
            print(line)
        print('  证据文件：%s' % csv_path)
        print('  下一步：把这份 CSV 的路径写进缺口清单 ② 板对应行的"证据"栏，'
              '别只写"已做"。')


if __name__ == '__main__':
    main()
