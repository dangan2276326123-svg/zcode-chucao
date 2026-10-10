#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E3 spec §7.2：延迟自测两条，都不改固件（D1 控制链路往返 / D2 指令到轮子真的转）。

作者 09-30 的原话是"测延迟换个简单方法，能不能自己测"。能，两条都用现有字段：

    D1 控制链路往返 = 交替发 `MODE(0x01)`（申请无人）/ `MODE(0x00)`（交回），
        量到 STATUS 里 `mode` 变成**这条请求所要的**那个值为止。
        ⚠️ **不能用 NAV 测**：A2 之后 NAV 不再改 `mode`（spec §3.3），发它看不到任何
        回显变化 —— 用 NAV 探 D1 会把"被测语义变了"读成"链路超时 30 次"。
        这条对应 B8 的一票否决判据（控制帧往返 p95）。分辨率受 STATUS 20 Hz 限制（±50 ms）。
    D2 指令到轮子真的转 = 每轮先把 NAV(0,0) **持停**到看见轮子确实停了，再发阶跃，
        量到 STATUS 的 `speed` 在那之后**首次**越过阈值。
        它含 D1 的全部 + 斜坡限幅 + PWM + 电机 + 传动 + 轮胎。
        ⚠️ `SLEW_ACC = 0.2 m/s^2`（`f0ecf73:firmware/retrofit.c:140`——10-10 批 1a Task 8 定身份：
        根副本已由 Task 6 删除，正身里同一条 `#define SLEW_ACC` 在 `:289`，**值未变**）⇒ 0 → 0.14 m/s 要约
        **0.7 秒**，它把百毫秒级的链路延迟完全掩盖，所以 **D1 与 D2 必须分开报**：
        论文口径是"链路延迟 = D1；机械响应 ≈ D2 − D1"，不写成一个数（spec §7.2 / R8）。

四条硬约束（都不是风格问题，都写着出处）：
  · **阈值下限 0.05 m/s 是硬的**：TIM3 是 16 位计时，脉冲间隔 > 65.536 ms 会取模
    （评审指出 0.005 m/s 会被算成约 0.01451 m/s）⇒ 低速段的 `speed` 不可信，
    `measure_d2()` 对更低的阈值直接拒。
  · **阶跃速度共用 `tools/bench_limits` 那一个数**（`NAV_BENCH_LIMIT_MPS = 0.20`，
    谓词 `nav_exceeds_bench_limit()`）。那条共享闸现在自己就 fail-closed（非有限值
    一律判为超限，C-1 收口）；本模块的 `_finite()` **照旧留着**，因为它给的是带参数名的
    `ValueError`，而谓词只回答是/否——一句能照着改的报错比一个布尔值有用（细节见那里）。
  · **续发 / 持停**：桥在最后一条 PC 帧 500 ms 后自注 ESTOP（`vehicle/bridge.py:24/30/206`），
    而锁存只能把板子断电清（台账 Fw-14、`retrofit_clear_estop()` 全工程无调用点）。
    阶跃到阈值本身要约 0.7 秒 > 500 ms，所以只发一条 NAV 的测法**必然**超时：
    `measure_d2()` 在等待期间按 `keepalive_s`（默认 0.2 s < 0.5 s）续发同一条阶跃。
    **同一条理由也管住了每轮开头**：`--settle` 那段不是"停一下再睡"，而是**边发 NAV(0,0)
    边看 STATUS 的持停段**——睡过去的 1 秒里 PC 一个字节都不发，桥就正好注一条 ESTOP，
    阶跃到板子时已经锁存（`retrofit.c:93` 直接 return），后面每一轮都只会超时，
    而板子还得断电。工具不许自己成为它正在诊断的那个症状。
    **`--keepalive 0`（= 把续发关掉）在命令行上直接拒**（10-08 第 2 轮复审 NEW-1）：0 一放开，
    两个阶段就退回"发一条、然后静默到窗口结束"，上面那条 bug 从参数的后门原样回来。
    API 层仍然允许 0（单测用它当"不建模续发"的简写，那条路一个字都不上线），但那里的
    静默是真的，所以 `estop_caution()` 与 `report()` 各自带 `keepalive_s == 0` 的分支，
    只许说"这一跑法不补发"，不许照着默认值说"持停到看见停住"。
    **续发一律重新 `pack_frame` 取新序号**，不是把同一个字节串冻结重传：现固件不读 NAV 的
    seq 所以今天无害，但批 2 要给指令带 seq 并让单片机回传"最后执行到的 seq"（spec §7.2），
    那时重传与原帧不可区分，而本文件自己承诺过"线上日志分得清是谁发的"。
  · **re-arm 门**：本轮**必须先看到一帧有限且 `speed < 阈值`**（轮子确实停了），之后的
    首次越阈才算样本。上一轮的余速（0.14 m/s 按 0.2 m/s^2 减到 < 0.05 要约 0.45–0.7 秒）
    会在新窗口的头几帧就满足判据，产出 50–200 ms 的"机械响应"——
    那是与本文件防 TIM3 混叠同一种东西：**自洽但不存在**的数（见 `MIN_THRESHOLD` 那条）。
    `--settle` 因此可以误调而不产坏数：停不下来的那些轮次一律不计样本，只把
    "没停住"这件事记进 `not_rearmed`（`timeouts` 仍记"这一轮没有样本"）。
    `not_rearmed` 混着两类轮次：**持停段没挣到证据所以一条阶跃都没发**的，与**发了阶跃
    但门始终没开**的。分开它们靠 `rounds_step_commanded`，`cross_read()` 的归属句按
    "这一跑到底发过阶跃没有"来分——一次阶跃都没发的 n=0 讲的是**本工具的 pacing**，
    发过阶跃却从没越阈才轮到执行面（Fw-21）说话（10-08 第 2 轮复审 NEW-3 同族项；
    把它们合并计数，等于把症状整条推给别人，那是"把症状推给别人"的镜像）。

D1 那条**做不到**同样地喂桥：它的语义就是"发一条 MODE，然后等回显"，中途补发同一条
MODE 会把一次往返改成两次请求，所以每轮的 `--timeout-d1`（默认 2.0 秒）就是一段真实的
PC 静默 > 500 ms。后果要写进台架规程而不是藏在注释里：在一块**不会回显**的板上
（批 1a 未烧：现固件的 switch 没有 TYPE_MODE 支，`retrofit.c:60-75`），D1 的每一轮都会
让桥注一条 ESTOP 并锁存，而 `!clear` 发的也是 TYPE_MODE——现固件同样不处理，
所以**只能断电清**（Fw-14）。这段由 `estop_caution()` 打印在开工那几行里，
不靠人翻源码。

`recv_iter` 的契约（两条测量函数都靠它，`StatusStream.recv_iter` 是它的真实现）：
    调用形式 `recv_iter(timeout_s)`，产出 `(t, status_dict)`，其中 **`t` 是"距本次请求
    发出"的秒数**（相对量，不是绝对时间戳）。所以 `samples_ms = t * 1000`。
    为什么是相对量：epoch 由被调方（`StatusStream`）在**被调用的那一刻**记下，而那一刻
    就是 `send_fn` 的下一行——测量函数因此不需要一个"和收发同一个钟"的假时钟，
    单测也就不必先造一个能同时骗过两套时钟的东西。真实实现里额外保证两件事：
    本调用开始之前就到了的帧一律丢掉并计数（`dropped_stale`，否则会算出偏小甚至为负
    的样本），窗口之外到的帧留给下一轮（吃掉它等于把一次真实回显判成超时）。

"发了"不等于"收到了"：UDP 没有送达反馈，所以样本**只**从真收到的 STATUS 帧算，
一条都收不齐就报 `n=0 + timeouts`；发送侧的 `frames_sent`/`sender.sent` 是另一套计数，
永远不进任何结论。STATUS 的解析复用 `pc.status_rx.StatusReceiver`（坏帧计数、乱序、
重启重同步与生产同一套判据），不另写一份近似的。

手机 60fps 同框拍屏幕与车轮（误差 1/60 s ≈ 17 ms）那条土办法**只作一次性交叉核对**
（spec §7.2 的第二个诚实限制），不进这个脚本。

用法（台架，**驱动轮必须离地**）：
    python -B tools/latency_probe.py --to 192.168.127.10:9000 --listen 9100 --repeats 30
    python -B tools/latency_probe.py --to 192.168.127.10:9000 --skip-d2   # 只量 D1

发送是 **opt-in**：不填 `--to` 时本脚本一个字节都不外发，并且**直接退出**而不是跑一遍
把所有轮次记成超时（那会把"没开发送"伪装成"链路有问题"）。目标地址的校验复用
`tools/bench_status.resolve_target`——广播/组播/网络号/正好打在监听端口上，四样都拒。
D1/D2 的**入参闸门在 `plan()` 里预跑一遍**（`_preflight_inputs`）：`--threshold 0.01`、
`--step nan`、`--keepalive 0.6`、`--keepalive 0`（关掉续发 = 桥的静默后门，见 NEW-1）、
`--settle -1`、`--repeats 0` 这些都在**建 socket、绑端口
之前**变成一行 ASCII 退出，而不是等 D1 发满 30 条之后抛 traceback——与 `--to` 同一条纪律。
`measure_d2()` 里那道闸**不撤**：直接调用 API 的人（单测、别的脚本）也要撞上它；
`keepalive_s == 0` 只有命令行拒、API 不拒（理由见 `_cli_keepalive`）。
`--listen` 与记录器一样独占 9100：`pc/main.py --live` 或 `tools/bench_status.py` 开着的时候
先关掉一个（同一时刻只能有一个收帧的人），本脚本退出时会把这一点说明白。

档案号（MODE 载荷里的 profile）**只从 `config/vehicle_profile.yaml` 取**，不在命令行上给
（spec §6 / Task 7、Task 8 已定的口径：档案号 = 哪台车的权限）。brief 草图里那个
`--profile` 参数因此**没有**做进来，`tests/test_latency_probe.py` 把这条偏离钉成断言。

控制台是 cp936：本文件所有**打印**出来的字符串都是 ASCII（判据、报告、告警都不含中文），
中文只留在注释与文档串里。
"""
import argparse
import collections
import math
import os
import socket
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:                                   # Windows cp936：编码问题不许把测量进程打死
    sys.stdout.reconfigure(errors='replace')
except AttributeError:                 # pragma: no cover - py<3.7
    pass

from common import protocol as P                        # noqa: E402
from pc.status_rx import StatusReceiver, STATUS_UDP_PORT  # noqa: E402
# 台架 NAV 限速的唯一出处（与 tools/link_probe.py、tools/bench_status.py 同一个数、
# 同一个谓词）。0.14 的阶跃走它，不在这里再写第二个限速数。
from tools.bench_limits import (NAV_BENCH_LIMIT_MPS,    # noqa: E402
                                nav_exceeds_bench_limit)
# 发送目标的校验与档案号读取都复用记录器那一份，不抄第二遍（AGENTS 清单第 6 条）。
from tools.bench_status import load_profile_id, resolve_target    # noqa: E402

SLEW_ACC = 0.2                  # m/s^2，与 retrofit.c:140 一致；用于文案与斜坡估算
MIN_THRESHOLD = 0.05            # m/s，低于它 TIM3 进入混叠区，speed 不可信（硬下限）
DEFAULT_STEP_MPS = 0.14         # 阶跃目标速度：0.14 < 0.20 的台架限速
BRIDGE_ESTOP_AFTER_S = 0.5      # vehicle/bridge.py:24 LINK_TIMEOUT_MS=500
DEFAULT_KEEPALIVE_S = 0.2       # 续发间隔，必须 < BRIDGE_ESTOP_AFTER_S
DEFAULT_STATUS_PORT = STATUS_UDP_PORT   # 就一个出处：pc.status_rx（别再抄第二个 9100）
MODE_NAME = {0: 'MANUAL', 1: 'AUTO', 2: 'ESTOP', 3: 'TELEOP'}   # 只用于打印诊断


# ------------------------------------------------------------------ 统计


def percentile(sorted_values, p):
    """p 分位数：绘图位置 k = (n+1)*p/100（1-based），夹到 [1, n]，相邻两点线性插值。

    空样本给 None（"没有数"与"数是 0"必须区分开，否则 n=0 会被印成一个像样的延迟）。
    输入不要求已排序（名字沿 brief 的 `sorted_values`，但这里自己 sort 一次，
    免得上游改了顺序就静默给出错的分位数）。

    为什么不是草图里那条 `(n-1)*p/100` 线性插值：它对 [1,2,3,4] 给 p95 = 3.85，
    而 brief 的测试要的是 4。两条 (n+1) 都满足（p50 = 2.5、p95 = 4）。第二层理由是
    口径：B8 是**一票否决**的门，尾部统计量往偏大取（保守）比往偏小取安全——偏小会把
    一个该否决的链路报成合格。
    """
    if not sorted_values:
        return None
    vals = sorted(sorted_values)
    n = len(vals)
    k = min(max((n + 1) * (p / 100.0), 1.0), float(n))
    lo = int(k)                                  # 1-based 下界
    hi = min(lo + 1, n)
    frac = k - lo
    return vals[lo - 1] + (vals[hi - 1] - vals[lo - 1]) * frac


def _summary(samples, timeouts, sent, extra=None):
    """两条测量共用的输出形状。`p50_ms`/`p95_ms` 在 n=0 时是 None，不是 0。"""
    out = {'samples_ms': list(samples), 'n': len(samples),
           'timeouts': timeouts, 'frames_sent': sent,
           'p50_ms': percentile(samples, 50),
           'p95_ms': percentile(samples, 95)}
    out.update(extra or {})
    return out


def _positive_int(name, value):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError('%s must be a positive int, got %r' % (name, value))
    return value


def _seq_no(name, value):
    """发送序号必须是 0..0xFFFF 的**整数**：`pack_frame` 对它做 `& 0xFFFF`，
    浮点会在那里 TypeError，而这类错该在入参门上说清楚，不该从组帧里逃出来。"""
    if (isinstance(value, bool) or not isinstance(value, int)
            or not 0 <= value <= 0xFFFF):
        raise ValueError('%s must be an int in 0..65535, got %r' % (name, value))
    return value


def _window(name, value):
    """非负、有限的秒数（等待窗口）。

    0 是合法值（"不等待"），NaN/inf/负数没有意义：负的等待窗口会让 `recv_iter`
    立刻收口，看起来像"链路超时"，其实是入参写错——把那伪装成链路问题正是本模块
    一路在防的事。
    """
    v = _finite(name, value)
    if v < 0:
        raise ValueError('%s must be >= 0, got %r' % (name, value))
    return v


def _finite(name, value):
    """把入参收成**有限**的 float。

    共享闸（`bench_limits.nav_exceeds_bench_limit()`）现在自己就 fail-closed 了
    （C-1 收口：非有限值一律判为超限），这道闸**仍然留着**，理由是分工不是重复：
    谓词只回答"能不能发"（bool），这里给的是**带参数名的 ValueError**——
    `step_v must be finite, got nan` 一句就能照着改，`True` 不会告诉你哪个参数坏了。
    顺序也因此要紧：`_check_d2_inputs()` 里 `_finite('step_v', ...)` 排在共享闸
    **之前**，所以非有限值拿到的是这句可执行的报错，而不是"beyond bench limit"那种
    会把入参问题说成限速问题的文案（顺序一改，文案就说假话——别把这两道闸调换）。
    放过去会怎样（这条闸存在的原意，仍然成立）：`pack_nav` 能把 NaN 写成线上的 f32，
    而 `speed >= threshold` 对 NaN 恒假 ⇒ 测出一串"超时"，把入参问题伪装成链路问题；
    inf 同理（超出 f32 值域还会 `struct.error`）。
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValueError('%s must be a finite number, got %r' % (name, value))
    if not math.isfinite(v):
        raise ValueError('%s must be finite, got %r (bench_limits.'
                         'nav_exceeds_bench_limit() now also refuses non-finite '
                         'speeds, but it only answers yes/no - this one names '
                         'the parameter)' % (name, value))
    return v


# ------------------------------------------------------------------ D1


def measure_d1(send_fn, recv_iter, repeats=30, timeout_s=2.0, profile_id=0,
               baseline_fn=None, seq_start=0):
    """D1 控制链路往返：交替发 MODE(0x01)/MODE(0x00)，量到 mode 变成期望值为止。

    ⚠️ 只能发 **TYPE_MODE**。A2 之后 NAV 不再改 `mode`，用 NAV 探这条会一个回显都
    等不到（`tests/test_latency_probe.py::test_d1_sends_mode_frames_and_never_nav`
    逐帧验字节，就是钉这条的）。

    `baseline_fn`：返回"发这条请求之前最后一帧 STATUS"的 dict（还没有就返回 None）。
    给了就挡住 Task 7 在 `link_probe.judge()` 上栽过的那个反例——**发送前就已经是期望态
    时，那帧回显不能算作本次请求引起的**。这类轮次连请求都不发，单独计
    `skipped_already_in_mode`：既不进样本也不进超时，它什么都没证明。
    交替（0x01/0x00）让它自愈：下一轮要的是相反态，基线必然不等于它。
    基线取不到（一帧 STATUS 都还没收到）计 `no_baseline`，样本照常收但归属低一档，
    报告里会说清楚。

    `seq_start`：发送序号的起点。结果里回 `next_seq`，调用方（`main()`）把它接着传给
    下一条测量 —— **整个进程一条发送序号线**（与 `bench_status.TxSender` 同口径）。
    各测各的从 0 开始，两次测量的帧会撞上同一个号，事后翻线上日志就分不出是谁发的。

    判据只用 `mode`，不用 `authority`/`reject`：那两个字段是诊断信息（现场拨档、遥控器
    夺权同样会动 `authority`），把它们当回显会把"别人动了车"算成本次请求的功劳。

    ⚠️ **这条测量本身会静默**：每轮发一帧 MODE 之后要等 `timeout_s`（默认 2.0 s），
    中途补发同一条请求会把"一次往返"改成"两次请求"，所以这里不能像 D2 那样喂桥。
    超过桥的 500 ms 窗口就由桥注 ESTOP（`bridge.py:24/30/206`），而现固件不认
    TYPE_MODE（`retrofit.c:60-75`）⇒ 锁存只能断电清（Fw-14）。这个后果由
    `estop_caution()` 印在开工行里，结果里带回 `wait_s` 供 `cross_read()` 引用。
    """
    reps = _positive_int('repeats', repeats)
    try:
        pid = int(profile_id)
    except (TypeError, ValueError):
        raise ValueError('profile_id must be an integer, got %r' % (profile_id,))
    # 2.5 会被 int() 悄悄截成 2 = PROFILE_REAL，而档案号是"哪台车的权限"（spec §6），
    # 所以非整数一律拒，不给它一个"看起来差不多"的号上线。
    if pid != profile_id or not 0 <= pid <= 0xFF:
        raise ValueError('profile_id must be an integer fitting u8 (0..255), got %r'
                         % (profile_id,))
    _window('timeout_s', timeout_s)
    seq = _seq_no('seq_start', seq_start)

    samples = []
    timeouts = sent = skipped = no_baseline = 0
    for i in range(reps):
        req = P.MODE_REQ_AUTO if i % 2 == 0 else P.MODE_REQ_MANUAL
        want = 1 if req == P.MODE_REQ_AUTO else 0
        if baseline_fn is not None:
            prev = baseline_fn()
            if prev is None:
                no_baseline += 1
            elif prev.get('mode') == want:
                skipped += 1
                continue
        send_fn(P.pack_frame(P.TYPE_MODE, P.pack_mode(req, pid), seq))
        seq = (seq + 1) & 0xFFFF
        sent += 1
        got = False
        for t, st in recv_iter(timeout_s):
            if st.get('mode') == want:
                samples.append(t * 1000.0)
                got = True
                break
        if not got:
            timeouts += 1
    out = _summary(samples, timeouts, sent,
                   {'skipped_already_in_mode': skipped,
                    'no_baseline': no_baseline,
                    'wait_s': timeout_s,
                    'repeats': reps})
    out['next_seq'] = seq
    return out


# ------------------------------------------------------------------ D2


def _check_d2_inputs(step_v, threshold, keepalive_s):
    """把 D2 的三个入参闸门排成一个函数：顺序即优先级，错误信息各自说得清。"""
    thr = _finite('threshold', threshold)
    if thr < MIN_THRESHOLD:
        # 硬下限：混叠区里量出来的数自洽但不存在（0.005 m/s -> 约 0.01451 m/s）。
        raise ValueError('threshold %.4f m/s is below %.2f m/s: TIM3 is a 16-bit '
                         'counter, so pulse gaps over 65.536 ms wrap around and '
                         'the low-speed range reports a plausible but wrong speed'
                         % (thr, MIN_THRESHOLD))
    step = _finite('step_v', step_v)
    if step <= thr:
        raise ValueError('step %.4f m/s cannot ever reach threshold %.4f m/s '
                         '(the slew ramp tops out at the commanded speed)'
                         % (step, thr))
    # 阶跃与 link_probe / bench_status 用**同一个**谓词、同一个数（不写第二个限速值）。
    if nav_exceeds_bench_limit(step, step):
        raise ValueError('step %.4f m/s exceeds the bench limit %.2f m/s '
                         '(tools/bench_limits.NAV_BENCH_LIMIT_MPS)'
                         % (step, NAV_BENCH_LIMIT_MPS))
    ka = _finite('keepalive_s', keepalive_s)
    if ka < 0:
        raise ValueError('keepalive_s must be >= 0 (0 disables re-sending; the command '
                         'line refuses that one, see --keepalive and _cli_keepalive), '
                         'got %r' % (keepalive_s,))
    if ka >= BRIDGE_ESTOP_AFTER_S:
        raise ValueError('keepalive_s %.3f s >= the bridge ESTOP window %.1f s '
                         '(vehicle/bridge.py:24): the board would be latched in '
                         'ESTOP before the wheels ever reach the threshold, and '
                         'that latch is cleared only by powering the board down '
                         '(Fw-14)' % (ka, BRIDGE_ESTOP_AFTER_S))
    return step, thr, ka


def _cli_keepalive(value):
    """命令行层的额外一道闸：`--keepalive 0` 拒（10-08 第 2 轮复审 NEW-1）。

    为什么只在 CLI 层拒、API 层继续允许 0：
      · 命令行是唯一会把帧送到大板的路。0 = 关掉续发，于是持停段从 `NAV(0,0)` 到阶跃
        之间**一个字都不发**（最长静默整个 `--settle` 窗口，默认 1.0 s），阶跃段同理
        静默到窗口结束——都超过桥的 500 ms 窗口 ⇒ 桥注 ESTOP 并锁存，只能断电清
        （Fw-14）。上一轮刚修掉的"工具自己造静默"正是从这个参数后门回来的：只改打印
        而不堵静默本身，等于把假话换成真话但症状照旧。
      · 单测与别的 API 调用不碰板子，`keepalive_s=0` 是它们"不建模续发"的简写，
        挡了只会逼人绕过 CLI 去写测试。那条路上的静默是**真的**，所以 `estop_caution()`
        与 `report()` 各自带 `keepalive_s == 0` 的分支，不许再说"re-sent often enough"。
    """
    ka = _finite('keepalive_s', value)
    if ka == 0:
        raise ValueError(
            'keepalive_s 0 turns re-sending off, and the re-send is what keeps BOTH D2 '
            'phases fed: the hold would send one NAV(0,0) and then say nothing until '
            'its --settle window ends, which is longer than the bridge ESTOP window of '
            '%.1f s (vehicle/bridge.py:24/30/206), so the bridge injects an ESTOP that '
            'only a power cycle clears (Fw-14) before the wheels ever move. Pass a '
            'cadence under %.1f s (default %.2f s), or drive measure_d2() from the API '
            'if you really mean "no re-sending" (that path never reaches the board).'
            % (BRIDGE_ESTOP_AFTER_S, BRIDGE_ESTOP_AFTER_S, DEFAULT_KEEPALIVE_S))
    return ka


def _speed_or_none(st):
    """STATUS 里的 speed，**不可信就给 None**（缺字段 / None / NaN / inf / 非数值）。

    调用方一律计数、不拿它做判据：这种帧既不能当"越过了阈值"，也不能当"确实停住了"
    ——持停段靠的就是"`speed < 阈值` 且是有限值"这一条证据，含糊的帧必须两头都不算。
    """
    v = st.get('speed_mps')
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def measure_d2(send_fn, recv_iter, step_v=DEFAULT_STEP_MPS, threshold=MIN_THRESHOLD,
               timeout_s=5.0, repeats=10, keepalive_s=DEFAULT_KEEPALIVE_S,
               settle_s=0.0, seq_start=0):
    """D2 指令到轮子真的转：每轮**持停**到看见轮子确实停了，再发阶跃，量其后的首次越阈。

    这个数**不是链路延迟**：它含 D1 的全部 + 斜坡限幅 + PWM + 电机 + 传动 + 轮胎，
    其中 `SLEW_ACC=0.2 m/s^2` 单独就贡献约 0.7 秒（0→0.14 m/s）。分开报，见 `report()`。

    一轮分两段，两段的节奏都是"**续发 + 消费 STATUS**"，没有一段是干等：

      1. **持停段**（`settle_s` 秒的窗口）：发 NAV(0,0)，然后按 `keepalive_s` 的节奏
         **续发 NAV(0,0)** 并逐帧读 STATUS，直到看见一帧**有限且 `speed < 阈值`**
         （= 上一轮真的停了）。这一段既喂着桥（桥 500 ms 静默就自注 ESTOP，
         bridge.py:24/30/206，锁存只能断电清 = Fw-14），也给第 2 段提供"从静止起算"的证据。
         窗口用完还没停住 ⇒ 这一轮**不发阶跃**：没有静止证据的越阈分不清是指令引起的
         还是余速。这一轮计 `timeouts`（期间见过可信帧的话，另计 `not_rearmed` 说明
         超时不是链路的事而是没停住）。
      2. **阶跃段**（`timeout_s` 秒的窗口）：发阶跃，按 `keepalive_s` 续发**同一条阶跃**
         （斜坡本身要 0.7 秒 > 500 ms，只发一条的测法在轮子转起来之前就被锁存了），
         到第一帧 `speed >= 阈值` 算样本并**先算样本再决定是否补发**。
         `settle_s == 0` 时（单测和"我不想等"的跑法）re-arm 门挪到这一段里：
         窗口内**必须先出现一帧有限且低于阈值**，之后的越阈才算样本；在那之前的越阈帧
         一律计 `pre_arm_above_frames` 并忽略——上一轮的 0.14 m/s 余速按 0.2 m/s^2 减到
         阈值以下要约 0.45–0.7 秒，正好落在新窗口的头几帧上，若照收就产出 50–200 ms 的
         "机械响应"，那是与本模块防 TIM3 混叠同类的**自洽但不存在**的数。

    续发的每一帧都**重新组帧、取新的发送序号**（M-1）：冻结重传在现固件下无害（它不读
    NAV 的 seq），但批 2 要让指令带 seq、单片机回传最后执行到的 seq（spec §7.2），
    那时"重传"与"原帧"就分不开了，而本文件承诺过线上日志分得清是谁发的。

    `keepalive_s == 0` 在这里仍然合法（单测用它当"不建模续发"的简写），但那是**真的静默**：
    两段各发一条就不出声了，桥 500 ms 就注 ESTOP。命令行那条路被 `_cli_keepalive()` 挡死，
    所以只有直接调 API 的人会遇到它——`estop_caution()` 与 `report()` 对它各有专门的分支。

    ⚠️ 续发节奏是**由到达的 STATUS 驱动**的：STATUS 停下（比 `keepalive_s` 还慢或干脆断流）
    时，节奏跟着停，PC 就又静默了。这一条**本体未修**（审查发现 M-3），登记处 =
    `docs/参数差异台账.md` 的 **Pc-9** 行（10-09 由文档收口批落成本行；在那之前它只活在
    task-9 报告 §F9 里，`docs/` 全目录 grep `M-3` 当时零命中）。它不是已解决的口子：
    落点两处见 Pc-9（本函数文档串 + `estop_caution()` 的输出行，`--keepalive` 的 help
    **没有**写它）；`_diagnostics()` 里的 `reader_error`/`rx` 计数就是给这个场景看的。

    计数 `rounds_step_commanded` = **真的发过阶跃**的轮次数。`not_rearmed` 混着两类轮次
    （持停段没挣到静止证据、一条阶跃都没发 / 发了阶跃但门始终没开），归因要靠上面那个数
    把它们分开：一次都没发的 n=0 讲的是本工具的 pacing，发过阶跃却从没越阈才轮到执行面
    （Fw-21）说话——见 `cross_read()`。

    `seq_start`/`next_seq` 与 `measure_d1` 同义：发送序号整进程一条线（spec 无关，
    但线上日志分得清是谁发的，是取证的基本要求）。
    """
    reps = _positive_int('repeats', repeats)
    window = _window('timeout_s', timeout_s)
    step, thr, ka = _check_d2_inputs(step_v, threshold, keepalive_s)
    settle = _window('settle_s', settle_s)
    seq = _seq_no('seq_start', seq_start)

    samples = []
    timeouts = sent = keepalive = bad_speed = 0
    not_rearmed = pre_arm_above = step_rounds = 0

    def nav(v):
        """发一条 NAV：每次调用都重新组帧并**占一个新序号**（见上面 M-1 那段）。"""
        nonlocal seq, sent
        send_fn(P.pack_frame(P.TYPE_NAV, P.pack_nav(v, v), seq))
        seq = (seq + 1) & 0xFFFF
        sent += 1

    for _i in range(reps):
        armed = False          # 本轮是否见过"确实停住"的证据（有限且 speed < 阈值）
        finite_seen = 0        # 本轮见过的可信帧数：区分"没停住"与"一帧都没来"
        next_due = ka
        # ---- 第 1 段：持停。"先停"不是发一条就算停，得亲眼看见停了才叫从静止起算。
        nav(0.0)
        if settle > 0:
            for t, st in recv_iter(settle):
                v = _speed_or_none(st)
                if v is None:
                    bad_speed += 1
                    continue
                finite_seen += 1
                if v < thr:
                    armed = True
                    break      # 停住了：下一条就是阶跃，本身也是发送，不用在此补停
                while ka > 0 and t >= next_due:
                    nav(0.0)
                    keepalive += 1
                    next_due += ka
            if not armed:
                # 没有静止证据就把轮子叫起来，量到的越阈可能是上一轮的余速：
                # 这一轮什么都不证明，所以只计超时不产样本。
                # `not_rearmed` 的**第 1 类**：这一轮连阶跃都没发（step_rounds 不加），
                # 所以"没样本"讲的是本工具的 pacing，与板子的执行面无关。
                timeouts += 1
                if finite_seen:
                    not_rearmed += 1
                continue
        # ---- 第 2 段：阶跃。
        nav(step)
        step_rounds += 1     # 这一轮真的叫过轮子：归属句按这条分（见 cross_read）
        next_due = ka
        got = False
        for t, st in recv_iter(window):
            v = _speed_or_none(st)
            if v is None:
                # 这种帧证明不了任何事：不进样本，进计数（线上真发过 NaN 就该被看见）。
                bad_speed += 1
                continue
            finite_seen += 1
            if v < thr:
                armed = True
            elif not armed:
                # 还没见过静止：这一帧是余速，不是"这条指令让轮子转起来"的证据。
                pre_arm_above += 1
            else:
                samples.append(t * 1000.0)
                got = True
                break
            while ka > 0 and t >= next_due:
                nav(step)
                keepalive += 1
                next_due += ka
        if not got:
            timeouts += 1
            # `not_rearmed` 的**第 2 类**：阶跃**已经发过**（step_rounds 计了这一轮），
            # 窗口里却没见过一帧低于阈值——这类轮次仍然是执行面的嫌疑人，别让
            # `cross_read()` 把它一起说成"pacing 的产物"。
            if finite_seen and not armed:
                not_rearmed += 1
    out = _summary(samples, timeouts, sent,
                   {'keepalive_sends': keepalive, 'bad_speed_frames': bad_speed,
                    'not_rearmed': not_rearmed,
                    'rounds_step_commanded': step_rounds,
                    'pre_arm_above_frames': pre_arm_above,
                    'wait_s': window, 'settle_s': settle, 'keepalive_s': ka,
                    'repeats': reps})
    out['next_seq'] = seq
    out['threshold_mps'] = thr
    out['step_mps'] = step
    return out


# ------------------------------------------------------------------ 报告


def _count_bits(d):
    """计数行里的**诊断后缀**（ASCII）：一个都没有就不印，绝不印成 `=0` 凑数。

    这些键在 `n=0` 时比在 `n>0` 时更要紧——"整轮被 re-arm 门拒掉"和"链路不通"在
    `n=0, 10 timeouts` 这一行里长得一模一样，分开它们靠的就是这几个数。
    """
    bits = []
    if d.get('frames_sent') is not None:
        bits.append('frames_sent=%d' % d['frames_sent'])
    if d.get('skipped_already_in_mode'):
        bits.append('rounds_skipped_already_in_that_mode=%d'
                    % d['skipped_already_in_mode'])
    if d.get('no_baseline'):
        bits.append('rounds_without_baseline=%d' % d['no_baseline'])
    if d.get('keepalive_sends'):
        bits.append('keepalive_re_sends=%d' % d['keepalive_sends'])
    if d.get('bad_speed_frames'):
        bits.append('non_finite_speed_frames=%d' % d['bad_speed_frames'])
    if d.get('not_rearmed'):
        # re-arm 门：这些轮次从未看见轮子停下来，所以一次样本都不产（见 measure_d2）。
        bits.append('rounds_never_rearmed=%d' % d['not_rearmed'])
    if d.get('rounds_step_commanded'):
        # 归属用的分母：这些轮次真的叫过轮子，所以"没样本"不能整条推给 pacing。
        bits.append('rounds_step_commanded=%d' % d['rounds_step_commanded'])
    if d.get('pre_arm_above_frames'):
        bits.append('above_threshold_before_standing_still=%d'
                    % d['pre_arm_above_frames'])
    return bits


def _fmt_counts(d):
    """一条测量的计数行（ASCII：控制台是 cp936）。"""
    if d.get('skipped'):
        # 没跑过与"跑了但一个样本都没有"是两件事，不许都印成 n=0 + 超时。
        return 'skipped by request (--skip-d2): nothing was commanded'
    bits = _count_bits(d)
    if not d.get('n'):
        head = 'n=0, %d timeouts -- no usable sample' % d.get('timeouts', 0)
        return '  '.join([head] + bits)
    return '  '.join(['n=%d p50=%.1f ms p95=%.1f ms timeouts=%d'
                      % (d['n'], d['p50_ms'], d['p95_ms'], d.get('timeouts', 0))]
                     + bits)


def _d2_phase_lines(d2):
    """D2 那几句**节奏**文案：跟着**这一跑的实参**走，不跟着默认值走（NEW-2）。

    为什么这是"说真话"而不是排版问题：`--settle 0` 的跑法根本没有持停段（re-arm 门挪进
    阶跃窗口里），`--keepalive 0` 更是把续发整个关掉；把默认参数的行为印成无条件事实，
    现场读到的就是一句关于**没发生过的事**的陈述——而它恰好掩盖了"这一跑会静默到锁存"。
    `measure_d2()` 的返回值本来就带 `settle_s`/`keepalive_s`/`pre_arm_above_frames`，
    所以这里没有理由不读它们。结果字典里**没有**这些键时（手写 dict、或 D2 被跳过），
    一句关于本跑节奏的话都不说。
    """
    thr = d2.get('threshold_mps', MIN_THRESHOLD)
    settle = d2.get('settle_s')
    ka = d2.get('keepalive_s')
    pre_arm = d2.get('pre_arm_above_frames') or 0
    out = ['   D2 = D1 plus the slew limiter, PWM, motor, drivetrain and tyre.']
    if d2.get('skipped'):
        out.append('   D2 never ran in this session (--skip-d2): there was no hold and '
                   'no step, so nothing below claims how the two phases were paced.')
        return out
    if settle is None or ka is None:
        out.append('   this result carries no settle_s/keepalive_s, so this report '
                   'makes no claim about how its rounds were paced (--help and '
                   'measure_d2 describe the two phases).')
        return out
    if settle > 0 and ka > 0:
        out.append('   this run: each round holds NAV(0,0) for up to %.2f s, re-sent '
                   'every %.2f s (on arriving STATUS) so the bridge never sees %.1f s '
                   'of PC silence (vehicle/bridge.py:24, Fw-14),'
                   % (settle, ka, BRIDGE_ESTOP_AFTER_S))
        out.append('   until STATUS shows a finite speed under %.2f m/s, THEN command '
                   'the step; t=0 is that step frame.' % thr)
    elif settle > 0:                      # ka == 0：持停段一个字都不补发
        out.append('   this run RE-SENDS NOTHING (--keepalive 0): the hold sends one '
                   'NAV(0,0) and then the PC goes silent until its %.2f s window ends, '
                   'which is longer than the bridge ESTOP window of %.1f s '
                   '(vehicle/bridge.py:24/30/206) - the bridge injects an ESTOP that '
                   'only a power cycle clears (Fw-14), and retrofit.c:93 then drops '
                   'the step. A round still waits for a finite speed under %.2f m/s '
                   'before commanding it; t=0 is that step frame.'
                   % (settle, BRIDGE_ESTOP_AFTER_S, thr))
    elif ka > 0:                          # settle == 0：没有持停段
        out.append('   this run has NO hold phase (--settle 0): the step is commanded '
                   'at once and the re-arm gate sits inside the step window - a finite '
                   'frame under %.2f m/s must appear there before any crossing counts. '
                   'Re-sends run every %.2f s, so the bridge still never sees %.1f s '
                   'of PC silence (Fw-14); t=0 is that step frame.'
                   % (thr, ka, BRIDGE_ESTOP_AFTER_S))
    else:                                 # settle == 0 且 ka == 0
        out.append('   this run RE-SENDS NOTHING and has no hold phase (--settle 0 '
                   '--keepalive 0): each window sends one frame then falls silent, so '
                   'the bridge injects an ESTOP after %.1f s (vehicle/bridge.py:24, '
                   'Fw-14, power cycle only). t=0 is the step frame and a sample still '
                   'needs a finite frame under %.2f m/s first.'
                   % (BRIDGE_ESTOP_AFTER_S, thr))
    if pre_arm:
        out.append('   a crossing seen before the wheels were seen standing still is '
                   'residual speed from the previous round, not a sample - it is '
                   'counted above as above_threshold_before_standing_still=%d.'
                   % pre_arm)
    else:
        out.append('   no crossing was ignored as residual speed this run, so '
                   'above_threshold_before_standing_still is not printed above (zero '
                   'counts are not printed).')
    return out


def report(d1, d2):
    """把两条结果写成**两段**，中间不出现"一个总延迟"这种东西。

    文案的三条硬话（spec §7.2）：
      · 链路延迟 = D1；机械响应 ≈ D2 − D1（后者标着 derived，不是第三个测得的数）；
      · D2 里斜坡限幅（SLEW_ACC=0.2 m/s^2，0→0.14 m/s 约 0.7 s）把百毫秒级掩盖掉了；
      · 分辨率 ±50 ms（STATUS 20 Hz 量化），低速段（< MIN_THRESHOLD）不可信。

    D2 那几句"这一轮是怎么喂着跑的"（持停/续发/t=0/被忽略的余速）**全部由 `_d2_phase_lines`
    按结果字典里的实参生成**，不印默认值（NEW-2）：`--settle 0` 没有持停段、
    `--keepalive 0` 干脆不补发，把默认参数的行为写成无条件事实就是对现场说假话。
    """
    thr = d2.get('threshold_mps', MIN_THRESHOLD)
    step = d2.get('step_mps', DEFAULT_STEP_MPS)
    lines = [
        'D1 control-path round trip (MODE 0x01/0x00 -> STATUS.mode): %s'
        % _fmt_counts(d1),
        '   resolution is +/-50 ms: STATUS arrives at 20 Hz, so this is the coarsest '
        'honest number.',
        '   this is what the B8 veto criterion asks for: control-frame round trip p95.',
        '   raw samples (ms): %s' % _raw(d1),
        'D2 command-to-wheel (step NAV %.2f m/s -> STATUS.speed >= %.2f m/s): %s'
        % (step, thr, _fmt_counts(d2)),
    ]
    if d1.get('n') and d2.get('n'):
        # 派生量，不是第三个测出来的数：标签写死"derived (not measured)"。
        lines.append('   derived (not measured): mechanical response ~= D2 - D1 = '
                     '%.1f ms' % (d2['p50_ms'] - d1['p50_ms']))
    lines.extend(_d2_phase_lines(d2))
    lines.extend([
        '   SLEW_ACC=%.1f m/s^2 (retrofit.c:140) -> 0 to %.2f m/s alone takes about '
        '%.1f s,' % (SLEW_ACC, step, step / SLEW_ACC),
        '   which buries a hundred-millisecond link delay: D2 is NOT the link delay.',
        '   thesis wording: link delay = D1; mechanical response ~= D2 - D1.',
        '   the two numbers are reported separately and never merged into one latency.',
        '   raw samples (ms): %s' % _raw(d2),
        'Low speed is unusable: below %.2f m/s the TIM3 16-bit pulse counter wraps'
        % MIN_THRESHOLD,
        '   (a gap over 65.536 ms is read modulo, 0.005 m/s comes back as about '
        '0.01451 m/s),',
        '   which is why measure_d2() refuses any threshold below %.2f m/s.'
        % MIN_THRESHOLD,
        'Cross-check only, not part of this script: a 60 fps phone video of the screen '
        'and',
        '   the wheel together (1/60 s ~= 17 ms) verifies D2 has no systematic offset.',
    ])
    return '\n'.join(lines)


def _raw(d):
    if not d.get('samples_ms'):
        return '(none)'
    return ', '.join('%.1f' % s for s in d['samples_ms'])


def cross_read(d1, d2, rx):
    """把**两个数放在一起**才说得出的那几句话（返回 ASCII 行列表）。

    这几条不是装饰，是台账里的既有事实决定的读法：
      · **Fw-21**：STATUS 是在 TIM6 中断里组的（`retrofit.c:311` 的 `retrofit_poll_1ms`
        → `:334` `if ((tick_ms % 50) == 0) status_report();`），四轮 PWM 只在**主循环**里
        写（`main.c:567-576`）。所以"D1 有样本、D2 全超时"读作**执行面**的问题
        （主循环停在 `main.c:305` 那个等待里 = Fw-18），不是链路问题——把这两种情况混成
        "链路不通"是本工具最贵的一种误读。
      · **Hw-26**：台架上出现过约 2.95 秒一轮的整机复位；复位会把 mode 打回 MANUAL 并把
        `tx_seq` 归零，`StatusReceiver.resynced` 就是它的签名。跨复位的样本不作数。
      · **批 1a 还没烧**：现固件的 switch 没有 TYPE_MODE 这一支（`retrofit.c:60-75`），
        三条 MODE 请求整条被丢 ⇒ 在这块板上 D1 超时是**预期**，不是故障。
      · **Fw-14**：ESTOP 锁存没有清除调用点，只能断电清；锁存期间 NAV 被 `:93` 直接 return
        ⇒ D2 全超时而 STATUS 照常 20 Hz。**但这句不许被读成"板子的锅"**：D1 每轮发一帧
        之后要等 `--timeout-d1`（默认 2.0 s）而中途不发声，它本身就是 > 500 ms 的 PC
        静默——所以"锁存"这个症状的嫌疑人里必须先列上**这次运行自己**。D2 一侧已经改成
        持停段续发，不再制造这种静默（`measure_d2`；`--keepalive 0` 那条后门 10-08 起
        在命令行上就被拒，见 `_cli_keepalive`）。
      · **re-arm 门**：本轮没见过"有限且低于阈值"的 speed 就不许把越阈帧当样本，
        否则上一轮的余速会被读成 50–200 ms 的机械响应。被拒的轮次计 `not_rearmed`，
        这里把它单独说出来，不让它伪装成链路超时。**但归属要按 `rounds_step_commanded`
        分两半**（NEW-3 同族项）：一次阶跃都没发的 n=0 才是本工具 pacing 的产物；
        发过阶跃却始终没越阈的那些轮次**仍然把执行面留在嫌疑人名单上**——把它们和前者
        合并成一句"这不是链路故障"，是"把症状推给别人"的镜像。
    """
    lines = []
    d2_skipped = bool(d2.get('skipped'))
    # 这一跑**到底叫过轮子没有**：None = 结果里没有这个计数（手写 dict / 老形状），
    # 这时退回旧的保守读法（只看 not_rearmed），不假装知道。
    step_rounds = d2.get('rounds_step_commanded')
    if step_rounds is None:
        wheels_never_asked = bool(d2.get('not_rearmed'))
    else:
        wheels_never_asked = (step_rounds == 0)
    if d1.get('n') and d2_skipped:
        # --skip-d2 时**不许**说"执行面有问题"：这条 NAV 根本没发过，没有东西可判。
        lines.append('D2 was skipped by request, so there is no mechanical-response '
                     'figure to compare against: read D1 alone as the link number and '
                     'run without --skip-d2 (wheels off the ground) before saying '
                     'anything about the execution side')
    if (d1.get('n') and not d2.get('n') and not d2_skipped
            and not wheels_never_asked):
        lines.append('D1 has samples but D2 has none: the request got through and '
                     'the echo came back, so the LINK is not the suspect. STATUS is '
                     'built in the TIM6 interrupt (retrofit.c:311/334) while the wheel '
                     'PWM is only written in the main loop (main.c:567-576) - this is '
                     'the Fw-21 shape (execution side parked, telemetry still '
                     'flowing), see also Fw-18 and the ESTOP latch Fw-14. Check the '
                     'wheels really are off the ground and the Hall/encoder feed before '
                     'touching the wiring.')
    if not d1.get('n') and not d2.get('n') and not d2_skipped:
        if getattr(rx, 'good', 0) == 0:
            lines.append('neither measurement produced a sample and no STATUS arrived '
                         'at all: this says nothing about the send direction - fix the '
                         'receive path first (bridge running? this host is the pc_ip? '
                         'firewall?)')
        else:
            msg = ('STATUS flows (%d good frames) but neither echo appeared: on '
                   'the flashed pre-E3 firmware this is expected for D1 (no '
                   'TYPE_MODE branch, retrofit.c:60-75) and for D2 while an '
                   'ESTOP is latched (retrofit.c:93 returns early; Fw-14 - power '
                   'cycle only)' % rx.good)
            wait = d1.get('wait_s')
            if wait and wait > BRIDGE_ESTOP_AFTER_S:
                # 归因要往自己身上查一遍：这个锁存很可能是**本次运行**造成的，
                # 不是板子的旧账。把症状推给被测对象是本工具最贵的误读之一。
                msg += ('. Before this latch is blamed on the board, note that this '
                        'very run is a suspect: each D1 round waits %.1f s with the PC '
                        'sending nothing, which is longer than the bridge window of '
                        '%.1f s (vehicle/bridge.py:24/30/206), so on a board that never '
                        'echoes every D1 round lets the bridge inject the ESTOP that '
                        'then swallows every NAV afterwards. Power the board down to '
                        'clear it (Fw-14) and write the bench procedure around that '
                        'power cycle, not around !clear - !clear sends TYPE_MODE, which '
                        'the flashed firmware drops exactly like the MODE requests '
                        'above' % (wait, BRIDGE_ESTOP_AFTER_S))
            lines.append(msg)
    if d2.get('not_rearmed') or d2.get('pre_arm_above_frames'):
        if step_rounds:
            # 混合轮次：有些轮**真的叫过轮子**却仍没越阈，那半句话不许被 pacing 抹掉。
            lines.append('D2 refused %d rounds that never showed the wheels standing '
                         'still before a crossing and ignored %d above-threshold frames '
                         'as residual speed from the previous round - but it DID command '
                         'the step in %d rounds, and those rounds asked the wheels to '
                         'turn and still never showed a crossing after standing still: '
                         'that part is the execution side (Fw-21 shape), not pacing, so '
                         'do not read these counts as explaining the whole n=0. The '
                         'ignored frames would have produced a 50-200 ms mechanical '
                         'response that never happened; raise --settle so every round '
                         're-arms, then quote what is left'
                         % (d2.get('not_rearmed', 0),
                            d2.get('pre_arm_above_frames', 0), step_rounds))
        else:
            msg = ('D2 refused %d rounds that never showed the wheels standing still '
                   'before a crossing and ignored %d above-threshold frames as '
                   'residual speed from the previous round: those counts are an '
                   'artefact of how this run was paced, not a latency figure and '
                   'not a link fault - the 50-200 ms those frames would have '
                   'produced describes a mechanical response that never happened. '
                   'Let each round re-arm (raise --settle) before quoting any D2 '
                   'number'
                   % (d2.get('not_rearmed', 0), d2.get('pre_arm_above_frames', 0)))
            if step_rounds is not None:
                # 这条只有在这一跑的计数**确实读到**时才说：一次阶跃都没发过，
                # 所以本跑对执行面一个字都不许说（这才是"pacing 的产物"那种情况）。
                msg += (' (rounds_step_commanded=%d: no round ever sent a step, so this '
                        'run never asked the wheels to turn and it says nothing about '
                        'the execution side)' % step_rounds)
            lines.append(msg)
    if getattr(rx, 'resynced', 0):
        lines.append('the receiver saw %d reboot re-syncs (Hw-26 signature, about one '
                     'every 2.95 s on the 09-28 bench): mode resets to MANUAL and '
                     'tx_seq restarts, so any sample whose round spans a reset is '
                     'VOID - do not quote these numbers until Hw-26 is closed'
                     % rx.resynced)
    if getattr(rx, 'bad', 0) or getattr(rx, 'out_of_order', 0):
        lines.append('bad frames=%d, rejected stale sequence numbers=%d: a nonzero '
                     'count means the frame stream itself was not clean, so the '
                     'p50/p95 above are not a link-quality statement'
                     % (getattr(rx, 'bad', 0), getattr(rx, 'out_of_order', 0)))
    if d1.get('skipped_already_in_mode') or d1.get('no_baseline'):
        lines.append('D1 skipped %d rounds whose mode already matched the request and '
                     'took %d rounds without a baseline: those are not evidence of a '
                     'round trip, and a low n here is an attribution problem, not a '
                     'speed problem' % (d1.get('skipped_already_in_mode', 0),
                                        d1.get('no_baseline', 0)))
    if d1.get('n') and d2.get('n'):
        lines.append('both numbers have samples: quote the link delay as D1 and the '
                     'mechanical response as D2 - D1; do not average, sum or replace '
                     'them with one latency figure')
    return lines or ['nothing to add: each number stands on its own samples']


# ------------------------------------------------------------------ 收发管线


class StatusStream:
    """STATUS 时间线：`ingest` 进，`recv_iter(deadline_s)` 出相对秒数。

    解析复用 `pc.status_rx.StatusReceiver`：坏帧计数、序号回退、重启重同步都和生产
    同一套判据，**不静默**（spec §3.5 / AGENTS 清单第 5 条）。
    """

    def __init__(self, rx=None, clock=time.monotonic):
        self.rx = rx if rx is not None else StatusReceiver()
        self.clock = clock
        self._items = collections.deque()
        self._cv = threading.Condition()
        self._stop = threading.Event()
        self.frames = 0          # 进时间线的好帧数（= rx.good 的另一面）
        self.datagrams = 0       # 从 socket 读到的报文数（含被拒收的）
        self.dropped_stale = 0   # 调用之前就到了、被丢掉的帧数
        self.reader_error = ''

    def close(self):
        self._stop.set()
        with self._cv:
            self._cv.notify_all()

    def ingest(self, data, t=None):
        """一个 UDP 报文 → 时间线。返回 True 只在**真的解出一帧 STATUS**时。"""
        t = self.clock() if t is None else t
        st = self.rx.handle(data, now=t)
        if st is None:
            return False                 # 计数已经在 rx.bad / out_of_order 里
        self.frames += 1
        with self._cv:
            self._items.append((t, st))
            self._cv.notify()
        return True

    def recv_iter(self, deadline_s):
        """产出 `(t - 本调用开始, status_dict)`，直到 `deadline_s` 到点或 `close()`。

        两条守卫（理由见模块文档串）：早于本调用的帧丢掉并计数；晚于窗口的帧
        **塞回队首**留给下一轮。
        """
        floor = self.clock()
        end = floor + deadline_s
        while not self._stop.is_set():
            with self._cv:
                item = self._items.popleft() if self._items else None
            if item is not None:
                t, st = item
                if t < floor:
                    self.dropped_stale += 1
                    continue
                if t > end:
                    with self._cv:
                        self._items.appendleft(item)
                    return
                yield (t - floor, st)
                continue
            remaining = end - self.clock()
            if remaining <= 0:
                return
            with self._cv:
                self._cv.wait(min(remaining, 0.05))


def pump_socket(sock, stream, stop):
    """把 socket 上的报文搬进时间线，直到 `stop` 置位或 socket 出错；返回报文数。

    `socket.timeout` 不是错误（对端暂时没发），但它也**不是证据**——只有进时间线的帧
    才可能变成样本。线程退出一定把原因留在 `stream.reader_error`：一条无声死掉的读线程
    会让后面所有轮次都变成"超时"，而屏幕上一个字都不说（Task 8 在 stdin 线程上补过）。
    """
    n = 0
    while not stop.is_set():
        try:
            data, _addr = sock.recvfrom(2048)
        except socket.timeout:
            continue
        except OSError as exc:
            stream.reader_error = '%s: %s' % (type(exc).__name__, exc)
            return n
        n += 1
        stream.datagrams = n
        stream.ingest(data)
    return n


class UdpSender:
    """发送侧：**不 bind** 的独立 socket。`sent` 只是"写进了 socket"。

    UDP 没有送达反馈，所以 `sent` 永远不等于"板子收到了"——它不进任何判据，
    只在小结里与 `errors` 一起作旁证（与 `bench_status.TxSender` 同口径）。
    """

    def __init__(self, host, port, sock=None):
        self.host = host
        self.port = port
        self.sock = sock if sock is not None else \
            socket.socket(socket.AF_INET, socket.SOCK_DGRAM)      # **不 bind**
        self.sent = 0
        self.errors = 0
        self.last_error = ''

    def send(self, frame):
        try:
            self.sock.sendto(frame, (self.host, self.port))
        except OSError as exc:
            self.errors += 1
            self.last_error = '%s: %s' % (type(exc).__name__, exc)
            return False
        self.sent += 1
        return True

    def close(self):
        try:
            self.sock.close()
        except OSError:                 # 关不掉也没什么：进程马上就走了
            pass


def make_sender(to, avoid_port=None, sock=None):
    """`--to` → `UdpSender`；**None → None = 发送彻底禁用**（opt-in）。

    地址/端口的校验整体复用 `bench_status.resolve_target`：广播、组播、未指定、
    定向广播 x.x.x.255、网络号 x.x.x.0、以及"端口正好是本机在收 STATUS 的那个"
    ——同一份规则不许有两个版本。
    """
    target = resolve_target(to, avoid_port=avoid_port)
    return None if target is None else UdpSender(target[0], target[1], sock=sock)


def bind_listener(port):
    """收 STATUS 的 socket：独占绑定（与记录器同一个理由，09-22 实测）。

    不用 SO_REUSEADDR：Windows 上第二个进程带这个选项 bind **照样成功**而包只发给
    先绑上的那个，于是"上一个没关干净"会伪装成"接线不通、一帧都收不到"。
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        sock.bind(('0.0.0.0', port))
    except OSError as exc:
        sock.close()
        raise SystemExit('port %d is already taken (%s). Only one process can read '
                         'STATUS: close the other `tools/bench_status.py` or '
                         '`pc/main.py --live`, or pass a different --listen.'
                         % (port, exc))
    sock.settimeout(0.5)
    return sock


# ------------------------------------------------------------------ CLI


def build_argparser():
    ap = argparse.ArgumentParser(
        description='D1/D2 latency self-test (E3 spec 7.2); two numbers, reported '
                    'separately. Bench only - drive wheels OFF the ground.')
    ap.add_argument('--to', default=None, metavar='HOST:PORT',
                    help='**opt-in**: send to the bridge (e.g. 192.168.127.10:9000, '
                         'the bridge RECV port - not the 9100 you listen on). '
                         'Without it nothing is sent and this script exits instead '
                         'of measuring an empty run. NAV is capped at %.2f m/s by '
                         'tools/bench_limits, same gate as link_probe/bench_status.'
                         % NAV_BENCH_LIMIT_MPS)
    ap.add_argument('--listen', type=int, default=DEFAULT_STATUS_PORT,
                    help='local UDP port receiving STATUS (default %d)'
                         % DEFAULT_STATUS_PORT)
    ap.add_argument('--repeats', type=int, default=30,
                    help='D1 rounds: MODE(0x01)/MODE(0x00) alternating '
                         '(spec 7.2: >= 30 for a p50/p95)')
    ap.add_argument('--d2-repeats', dest='d2_repeats', type=int, default=10,
                    help='D2 rounds (each one drives the wheels up to %.2f m/s)'
                         % DEFAULT_STEP_MPS)
    ap.add_argument('--step', type=float, default=DEFAULT_STEP_MPS,
                    help='D2 step speed m/s (must stay <= the %.2f m/s bench limit)'
                         % NAV_BENCH_LIMIT_MPS)
    ap.add_argument('--threshold', type=float, default=MIN_THRESHOLD,
                    help='D2 crossing threshold m/s (hard floor %.2f: below it the '
                         'TIM3 16-bit counter wraps and speed is not trustworthy)'
                         % MIN_THRESHOLD)
    ap.add_argument('--timeout-d1', dest='timeout_d1', type=float, default=2.0,
                    help='per-round wait for the MODE echo (STATUS is 20 Hz). NOTE: '
                         'D1 cannot re-send while it waits (a second MODE request '
                         'would no longer be one round trip), so this is real PC '
                         'silence and it is longer than the bridge ESTOP window of '
                         '%.1f s - see the caution lines this script prints at start'
                         % BRIDGE_ESTOP_AFTER_S)
    ap.add_argument('--timeout-d2', dest='timeout_d2', type=float, default=5.0,
                    help='per-round wait for the speed crossing (the slew ramp alone '
                         'needs ~%.1f s at %.2f m/s)'
                         % (DEFAULT_STEP_MPS / SLEW_ACC, DEFAULT_STEP_MPS))
    ap.add_argument('--keepalive', type=float, default=DEFAULT_KEEPALIVE_S,
                    help='re-send cadence for BOTH D2 phases (NAV(0,0) during the '
                         'hold, the step NAV while waiting); must stay under the '
                         'bridge ESTOP window of %.1f s '
                         '(vehicle/bridge.py:24/30/206, latch cleared only by a '
                         'power cycle - Fw-14). 0 turns re-sending off, which puts '
                         'both phases back to "one frame then silence until the '
                         'window ends", so it is refused here even though the '
                         'measure_d2() API still accepts it for tests.'
                         % BRIDGE_ESTOP_AFTER_S)
    ap.add_argument('--settle', type=float, default=1.0,
                    help='max seconds per D2 round spent HOLDING NAV(0,0) - re-sent '
                         'every --keepalive, not slept through - while watching '
                         'STATUS for a finite speed below --threshold. The step is '
                         'only commanded after that evidence appears; a round that '
                         'never re-arms yields no sample (counted as '
                         'rounds_never_rearmed), so setting this too small costs '
                         'samples rather than producing a false 50-200 ms reading.')
    ap.add_argument('--warmup', type=float, default=2.0,
                    help='seconds to listen before the first request, to get a '
                         'baseline mode and see which STATUS shape the board uses')
    ap.add_argument('--skip-d2', dest='skip_d2', action='store_true',
                    help='measure D1 only (the B8 gate number); D2 is the one that '
                         'turns the wheels')
    return ap


def estop_caution(timeout_d1_s, keepalive_s=DEFAULT_KEEPALIVE_S, settle_s=0.0):
    """开工要打印的那几行（ASCII）：**这个跑法自己**会不会把板子锁进 ESTOP。

    为什么放在打印面而不是只写在注释里：台架上没人翻源码，而后果是"板子要断电"这种
    现场动作。两条各自说清是谁的静默：
      · D1 —— 每轮发一帧 MODE 然后**安静地**等 `timeout_d1` 秒，中途不能补发（补发就不是
        一次往返了），所以这段静默 > 500 ms 是这条测法固有的代价，改不掉，只能说明白；
      · D2 —— 已经改成持停段续发，不再制造静默；但续发节奏由**到达的 STATUS** 驱动，
        STATUS 断了节奏也跟着停（本轮未收的遗留项，审查发现 M-3）。

    `keepalive_s` 的两个非默认值各说各的话，不许照着默认值念（10-08 第 2 轮复审 NEW-1）：
      · `0`（API 层合法、命令行被 `_cli_keepalive` 拒）——续发关掉 ⇒ 两段都静默到窗口结束，
        这句**必须**明说会触发桥的 ESTOP 注入，而不是印一句"每 0.00 秒续发"的假话；
      · `None`（`--skip-d2`）——D2 一条都不发，所以对它的节奏一个字都不说。
    """
    lines = []
    if timeout_d1_s is not None and timeout_d1_s > BRIDGE_ESTOP_AFTER_S:
        lines.append(
            'D1 will be SILENT for up to %.1f s per round (one MODE frame, then it '
            'waits for the echo - re-sending would no longer be one round trip). That '
            'exceeds the bridge ESTOP window of %.1f s (vehicle/bridge.py:24/30/206), '
            'so on a board that never echoes (batch 1a not flashed: the switch has no '
            'TYPE_MODE branch, retrofit.c:60-75) EVERY D1 round lets the bridge latch '
            'an ESTOP, and every NAV afterwards is dropped by retrofit.c:93. That '
            'latch is cleared only by powering the board down (Fw-14) - !clear sends '
            'TYPE_MODE too, so it does not work on the flashed firmware either. '
            'Bench procedure: power-cycle the board after this run, before any other '
            'bench action.' % (timeout_d1_s, BRIDGE_ESTOP_AFTER_S))
    if keepalive_s == 0:
        where = ('the hold sends ONE NAV(0,0) and then says nothing until its %.2f s '
                 'window ends, and the step window is fed the same way' % settle_s
                 if settle_s > 0 else
                 'there is no hold phase (--settle 0) and the step window gets a '
                 'single frame too: each window runs silent after its one frame')
        lines.append(
            'D2 re-sending is OFF in this run (keepalive 0): %s, so the bridge injects '
            'an ESTOP after %.1f s of silence (vehicle/bridge.py:24/30/206) and the '
            'step is then dropped by retrofit.c:93 - that latch is cleared only by '
            'powering the board down (Fw-14). The command line refuses this value '
            '(_cli_keepalive); reaching it means D2 was driven straight from the API, '
            'and the silence is real either way.' % (where, BRIDGE_ESTOP_AFTER_S))
    elif settle_s > 0 and keepalive_s:
        lines.append(
            'D2 does NOT sleep through its %.2f s settle: it re-sends NAV(0,0) every '
            '%.2f s and reads STATUS until the wheels are seen below the threshold, '
            'then commands the step and re-sends the step at the same cadence. Every '
            're-send is re-packed under a fresh sequence number (a frozen retransmit '
            'would be indistinguishable from the original once batch 2 puts seq on '
            'the wire, spec 7.2). Caveat: that cadence is driven by arriving STATUS, '
            'so a stalled STATUS stream stalls the feed too and the bridge latches '
            'again - known open hole, review finding M-3, not fixed in this round.'
            % (settle_s, keepalive_s))
    return lines


def _preflight_inputs(a):
    """`plan()` 的第一件事：把测量层会拒的入参**在碰任何资源之前**拒掉。

    为什么必须提前：`measure_d1/measure_d2` 里的闸门一个都没撤，但它们跑在
    `bind_listener` 之后——`--threshold 0.01`、`--step nan`、`--keepalive 0.6`、
    `--keepalive 0`、`--settle -1`、`--repeats 0` 在旧顺序下要等 socket 建好、端口绑上、
    D1 发满 30 条之后才炸出一个 traceback，那等于"先把 30 条指令发上线、再告诉你参数写错了"，
    而这次发送换来的只是超时。`--to` 早就有这条纪律（两条拒绝都不建 socket），
    入参没理由享受更低的标准（AGENTS 清单第 6 条：同一份规则不许有两个版本——
    这里复用的正是 `measure_*` 用的那几个谓词，不是第二份校验）。
    `--keepalive 0` 是这条纪律里**唯一 CLI 有、API 无**的一道：理由见 `_cli_keepalive`
    （只有命令行会把帧送到大板，而 0 一上线就是"持停段与阶跃段都不出声"）。
    """
    checks = [lambda: _positive_int('repeats', a.repeats),
              lambda: _window('timeout-d1', a.timeout_d1),
              lambda: _window('warmup', a.warmup)]
    if not a.skip_d2:
        # --skip-d2 时这些值一个都不上线，拒它们只会挡住"我只想看 D1"这条正当用法；
        # 但 d2-repeats/timeout-d2/settle/step/threshold/keepalive 真要跑 D2 时全在这里挡。
        checks += [lambda: _positive_int('d2-repeats', a.d2_repeats),
                   lambda: _check_d2_inputs(a.step, a.threshold, a.keepalive),
                   lambda: _cli_keepalive(a.keepalive),
                   lambda: _window('timeout-d2', a.timeout_d2),
                   lambda: _window('settle', a.settle)]
    for check in checks:
        try:
            check()
        except ValueError as exc:
            raise SystemExit('refusing to start: %s -- nothing was sent and no port '
                             'was bound yet, this is a command-line fix (see --help).'
                             % exc)


def plan(a):
    """main 的纯逻辑前段：**先**预检 D1/D2 入参，再解析 `--to` + 取档案号。

    没有目标就 **SystemExit**。为什么不是"照跑但全超时"：那会把"没开发送"伪装成
    "链路有问题"，一屏 n=0 比一句退出难读得多，而且本脚本的一切结论都建立在
    "确实发出去过一条请求"上。两条拒绝（入参、目标）都发生在建 socket、绑端口、
    读档案之前——见 `_preflight_inputs`。
    """
    _preflight_inputs(a)
    try:
        sender = make_sender(a.to, avoid_port=a.listen)
    except ValueError as exc:
        # 规则本身在 `bench_status.resolve_target` 里（共享的那一份，不抄第二份），
        # 但它的文案是中文的——那是记录器既有的输出面，重定向进管道/日志会变乱码。
        # 这里**不改共享模块**，只把同一套规则用 ASCII 重说一遍，并把原文带上（不丢信息）。
        raise SystemExit('--to %r was refused by the shared target check. It rejects: '
                         'a missing :PORT; a port outside 1..65535; broadcast / '
                         'multicast / unspecified (including x.x.x.255 and x.x.x.0 on '
                         'the /24 bench segment, because one command would then reach '
                         'every board that can hear it); and a port equal to the local '
                         'STATUS listen port (%d) - that echoes back into this very '
                         'receiver. The bridge recv port is 9000. Original message: %s'
                         % (a.to, a.listen, exc))
    if sender is None:
        raise SystemExit('no --to target, so this run would send no bytes and every '
                         'round would be counted as a timeout. Re-run with '
                         '--to <bridge-ip>:9000 (the bridge recv port, not the '
                         '%d you listen on). See --help.'
                         % DEFAULT_STATUS_PORT)
    # 档案号只从车辆档案取（spec §6）：命令行给档案号 = 允许拿另一台车的权限申请无人。
    return sender, load_profile_id()


def _diagnostics(rx, sender, stream):
    """收尾的旁证行（ASCII）：把"为什么可能一个样本都没有"按方向分开说。"""
    lines = ['rx: good=%d bad=%d out_of_order=%d resynced=%d '
             'datagrams=%d stale_dropped=%d (rx counters are evidence, '
             'tx counters are not)'
             % (rx.good, rx.bad, rx.out_of_order, rx.resynced,
                stream.datagrams, stream.dropped_stale)]
    lines.append('tx: sent=%d sendto_errors=%d %s'
                 % (sender.sent, sender.errors,
                    ('last: ' + sender.last_error) if sender.last_error else ''))
    if stream.reader_error:
        lines.append('reader: the STATUS thread STOPPED (%s) - every round after '
                     'that is a timeout of the reader, not of the board'
                     % stream.reader_error)
    if rx.last is None:
        lines.append('no STATUS was ever received: the SEND direction is untested by '
                     'this run - check the bridge on the X5 '
                     '(`pgrep -af bridge`), this machine\'s pc_ip in '
                     'vehicle/config.yaml, then the cable')
    else:
        if rx.status_version == 1:
            lines.append('STATUS payload is v1 (14 B) -> the board runs pre-E3 '
                         'firmware: it has no TYPE_MODE branch (retrofit.c:60-75) '
                         'so D1 cannot be measured until batch 1a is flashed. '
                         'Expect n=0 with timeouts, not a link fault')
        rej = rx.last.get('reject')
        lines.append('last STATUS: mode=%s authority=%s reject=%s '
                     '(Chinese reason text lives in common/protocol.REJECT_TEXT; '
                     'not printed here because this console is cp936)'
                     % (MODE_NAME.get(rx.last.get('mode'), rx.last.get('mode')),
                        rx.last.get('authority'),
                        'n/a' if rej is None else '0x%02X' % rej))
    return lines


def main(argv=None):
    a = build_argparser().parse_args(argv)
    sender, profile_id = plan(a)

    sock = bind_listener(a.listen)
    stream = StatusStream()
    stop = threading.Event()
    reader = threading.Thread(target=pump_socket, args=(sock, stream, stop),
                              daemon=True)
    reader.start()

    print('listening for STATUS on 0.0.0.0:%d, sending to %s:%d (profile %d from the '
          'vehicle profile)' % (a.listen, sender.host, sender.port, profile_id))
    print('bench only - drive wheels OFF the ground. D2 commands a NAV step of '
          '%.2f m/s; the bridge injects its own ESTOP %.1f s after the last frame '
          'and that latch is cleared only by a power cycle (Fw-14).'
          % (a.step, BRIDGE_ESTOP_AFTER_S))
    # 09-30 复审 Important-1：谁制造的静默谁说清楚。D2 已经不睡空窗了，D1 的等待
    # 改不掉（补发就不是往返），所以把它固有可能锁存板子这件事印在开工行里——
    # 连 --skip-d2 也要印，那一半静默正是 D1 自己的。
    # 10-08 第 2 轮 NEW-1：--skip-d2 时 D2 的 keepalive 传 **None**（不是 a.keepalive），
    # 因为那一跑 D2 一个字都不发，打印面不许对它作任何"会不会静默"的陈述。
    for line in estop_caution(a.timeout_d1,
                              keepalive_s=None if a.skip_d2 else a.keepalive,
                              settle_s=0.0 if a.skip_d2 else a.settle):
        print('caution: %s' % line)

    baseline = None
    for _t, st in stream.recv_iter(a.warmup):
        baseline = st
        break
    if baseline is None:
        print('warm-up: no STATUS within %.1f s - the measurements below will be '
              'n=0 with timeouts. That is the RECEIVE direction failing, which says '
              'nothing about the SEND direction.' % a.warmup)
    else:
        print('warm-up: first STATUS mode=%s (STATUS %s B payload)'
              % (MODE_NAME.get(baseline.get('mode'), baseline.get('mode')),
                 'v2 19' if baseline.get('v') == 2 else 'v1 14'))

    print('D1: %d rounds of MODE(0x01)/MODE(0x00), waiting for STATUS.mode ...'
          % a.repeats)
    tx_seq = 0                       # 整个进程一条发送序号线（与 TxSender 同口径）
    d1 = measure_d1(sender.send, stream.recv_iter, repeats=a.repeats,
                    timeout_s=a.timeout_d1, profile_id=profile_id,
                    baseline_fn=lambda: stream.rx.last, seq_start=tx_seq)
    tx_seq = d1['next_seq']
    # 交回人工：D1 的最后一次成功申请可能把车留在 AUTO，收尾必须把它还回去。
    # 这一条**不算任何样本**：它是清理动作，不是被测请求。
    sender.send(P.pack_frame(P.TYPE_MODE, P.pack_mode(P.MODE_REQ_MANUAL, profile_id),
                             tx_seq))
    tx_seq = (tx_seq + 1) & 0xFFFF
    if a.skip_d2:
        d2 = {'samples_ms': [], 'n': 0, 'timeouts': 0, 'p50_ms': None,
              'p95_ms': None, 'frames_sent': 0, 'threshold_mps': a.threshold,
              'step_mps': a.step, 'skipped': True}
    else:
        print('D2: %d step rounds to %.2f m/s, crossing measured at >= %.2f m/s ...'
              % (a.d2_repeats, a.step, a.threshold))
        d2 = measure_d2(sender.send, stream.recv_iter, step_v=a.step,
                        threshold=a.threshold, timeout_s=a.timeout_d2,
                        repeats=a.d2_repeats, keepalive_s=a.keepalive,
                        settle_s=a.settle, seq_start=tx_seq)
        tx_seq = d2['next_seq']
        # 收尾把命令速度回零：轮子该停在"最后一条指令 = 0"，而不是停在阶跃上。
        sender.send(P.pack_frame(P.TYPE_NAV, P.pack_nav(0.0, 0.0), tx_seq))

    stream.close()
    stop.set()
    reader.join(timeout=1.0)
    sock.close()

    print('')
    if a.skip_d2:
        print('D2 was skipped (--skip-d2): no NAV was sent, the wheels were never '
              'commanded.')
    print(report(d1, d2))
    print('')
    for line in cross_read(d1, d2, stream.rx):
        print('read: %s' % line)
    print('')
    for line in _diagnostics(stream.rx, sender, stream):
        print(line)
    print('next: put these two numbers (D1 p95 and D2 p95) plus the n/timeouts counts '
          'into the B8 row of the gap ledger under docs/ - as measured values with '
          'this script\'s command line, not as "done".')
    sender.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
