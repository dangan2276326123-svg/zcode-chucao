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
    print('（若一直看不到帧：先确认 X5 config.yaml 的 pc_ip 指向本机，再查防火墙）')
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
        print('  证据文件：%s' % csv_path)
        print('  下一步：把这份 CSV 的路径写进缺口清单 ② 板对应行的"证据"栏，'
              '别只写"已做"。')


if __name__ == '__main__':
    main()
