# -*- coding: utf-8 -*-
"""tools/latency_probe.py 的测试（E3 批 1b Task 9，spec §7.2）。

这个脚本量的是**两个不同的数**，测试就把"两个数不许合成一个"当作主线来钉：

1. **D1 只能用 MODE 帧**。A2 之后 NAV 不再改 `mode`（spec §3.3），拿 NAV 探 D1 的话
   回显永远不会变，30 遍跑完得到的是"超时 30 次"，而链路其实好好的。所以有一条测试
   逐帧检查 `send_fn` 收到的字节：类型必须是 `TYPE_MODE`，载荷的 request 必须在
   0x01/0x00 之间交替——这是本文件里最容易被"顺手改回去"的一条契约。
2. **归属**。Task 7 在 `link_probe.judge()` 上栽过的同一个坑：发送前就已经是期望态时，
   那帧回显不能算作本次请求引起的。D1 用 `baseline_fn` 把这一类轮次单独计数
   （`skipped_already_in_mode`），它既不是样本也不是超时——它什么都没证明。
3. **"发了"不等于"收到了"**。UDP 没有送达反馈，样本只从真收到的 STATUS 帧算；
   一条都收不到时输出 `n=0 + timeouts`，而不是因为 `send_fn` 被调了 30 次就报个 p95。
4. **入参闸门**。阈值下限 0.05 m/s 是硬的（TIM3 16 位计时在低速段取模）；阶跃速度走的
   是 `tools/bench_limits.nav_exceeds_bench_limit` 这**同一个**谓词，不是第二个限速数；
   而这个谓词对 NaN 比较恒假，所以非有限值必须在**本模块**的校验里拒掉
   （不改共享模块——那是最终审查后的收口项）。

5. **D2 不许把自己锁进 ESTOP**（fix round 1，Important-1）。桥在最后一条 PC 帧 500 ms 后
   自注 ESTOP，而锁存只能断电清（Fw-14）——所以"发一条停帧然后干等 `--settle` 秒"这种写法
   会让工具**自己**成为它正在诊断的那个症状。测试用一把**收发共用的虚拟钟**（`_Feed`）把
   整轮的发送时刻记下来，断言相邻两次发送的间隔从不越过那个窗口，并把发送序列**回放给
   桥自己的判据** `vehicle/bridge.decide_forward`（不在测试里重抄一遍 500 ms 规则）。
6. **re-arm 门**（fix round 1，Important-2）。本轮必须先见到一帧**有限且低于阈值**的 speed，
   之后的首次越阈才算样本；在那之前的越阈帧是上一轮的余速，计 `pre_arm_above_frames` 并忽略。
   没有这道门时，`--settle` 被调小就会产出 50–200 ms 的"机械响应"——本模块对 TIM3 混叠
   明令防范的那种"自洽但不存在"的数。
7. **续发是重新组帧的新帧**（fix round 1，M-1）：每次续发占一个新发送序号。
8. **入参早拒**（fix round 1，M-2）：`--threshold 0.01` 这类在建 socket、绑端口之前就该退出，
   而不是等 D1 把 30 条 MODE 发满之后抛 traceback。
9. **打印面与归属句不许照着默认值说**（fix round 2，NEW-1/NEW-2/NEW-3 + 一条计数器）：
   `--keepalive 0` 在命令行上拒（0 = 关掉续发 ⇒ 两段静默到窗口结束，Important-1 的后门），
   `estop_caution()`/`report()` 在 `settle 0` / `keepalive 0` 下各说各的话而不是念默认参数，
   "台账上已经有这一条"那类没有落盘对应的措辞做成静态断言（读源码文本，命中即红），
   而 `cross_read()` 的归属按 `rounds_step_commanded`（这一跑到底发过阶跃没有）分——
   发过阶跃却没越阈的轮次仍然把执行面留在嫌疑人名单上，不许整条推给 pacing。

不需要硬件也不需要网口：收发都是假函数（`send_fn` 记账、`recv_iter` 按脚本给
`(t, status_dict)`）。`t` 是**距本次请求发出的相对秒数**，这个契约由
`StatusStream.recv_iter` 实现，并由 `test_stream_*` 几条钉住。
"""
import io
import os
import threading

import pytest

from common import protocol as P
from tools import bench_limits as BL
from tools import latency_probe as LP

# ---------------------------------------------------------------- 小工具


def _status_frame(seq, mode=0, speed=0.0, authority=None, reject=0, profile=2):
    """STATUS 帧：给 authority 就是 v2（19 B），否则 v1（14 B）。

    D1 的样本判据是 `mode`；`authority`/`reject` 只作诊断用（见模块文档串）。
    """
    if authority is None:
        payload = P.pack_status(speed, 1.0, 48.0, 0, mode)
    else:
        payload = P.pack_status_v2(speed, 1.0, 48.0, 0, mode, profile, authority,
                                  7, 1, reject)
    return P.pack_frame(P.TYPE_STATUS, payload, seq)


def _no_frames(deadline):
    return iter([])


class _Ticks:
    """按需推进的假时钟；用完最后一个值就停在那里。

    停在那里而不是抛 StopIteration，是因为 `recv_iter` 每轮调用几次 `clock()` 属于实现
    细节——测试钉的是"窗口到点自己收口"，不是它问了几次钟。
    """

    def __init__(self, *values):
        self.values = list(values)
        self.i = 0

    def __call__(self):
        v = self.values[min(self.i, len(self.values) - 1)]
        self.i += 1
        return v


# --------------------------------------------------- 假世界：一条绝对时间轴 + 记账的发送

STATUS_HZ = 20.0          # retrofit.c:334 (tick_ms % 50) == 0 -> status_report()


def _frames(spec, interval=None):
    """把 [(from_s, to_s, speed)] 摊成 `interval` 网格上的**到达时刻**序列。

    网格从每段的 lo+interval 开始，这样段边界不会两处各产一条（重复到达=假帧）。
    """
    step = interval or (1.0 / STATUS_HZ)
    out = []
    for lo, hi, v in spec:
        n = int(round((hi - lo) / step))
        out.extend((round(lo + (i + 1) * step, 6), v) for i in range(n))
    return sorted(out)


class _Feed:
    """假世界：STATUS 按**绝对时间轴**到达，`send_fn` 的时刻记在同一把虚拟钟上。

    为什么需要一把共用钟：Important-1 说的是"PC 静默了多久"，这句话只有在一个能
    **同时看见发送与接收时刻**的钟上才是可断言的。真实时钟帮不上忙（单测不该真等几秒），
    而 `measure_d2` 的续发节奏是**由到达的帧驱动**的，所以收发必须一起建模。

    `recv_iter(window)` 严格按 `StatusStream.recv_iter` 的契约演：
      · epoch = 被调用那一刻的虚拟钟 ⇒ 产出相对秒数（`t` 从 0 起算）；
      · 早于 epoch 的帧丢掉（真实现里是 `dropped_stale`）；
      · 窗口里没有帧可给了，钟**走到窗口结束**才收口（真实现里就是 socket 超时到点）——
        这一条是关键：它让"这段窗口 PC 一个字都没发"在钟上留下痕迹，而不是被跳过；
      · 调用方提前 break（读到样本）时，钟停在那一帧的时刻，剩下的帧留给下一轮。
    """

    def __init__(self, frames):
        self.arrivals = list(frames)
        self.now = 0.0
        self.sends = []              # [(绝对秒数, 原始帧字节)]
        self.stale = 0

    def send(self, frame):
        self.sends.append((self.now, frame))

    def recv_iter(self, window):
        epoch = self.now
        end = epoch + window
        while self.arrivals and self.arrivals[0][0] <= end:
            at, v = self.arrivals.pop(0)
            if at < epoch:
                self.stale += 1
                continue
            self.now = at
            yield at - epoch, {'speed_mps': v}
        self.now = max(self.now, end)

    def decoded(self):
        """[(绝对秒数, 指令速度, 发送序号)]：把记账的字节真解一遍（不信任实现写的注释）。"""
        out = []
        for ts, frame in self.sends:
            ftype, seq, payload = P.unpack_frame(frame)
            assert ftype == P.TYPE_NAV, 'D2 must only ever send NAV'
            v_left, v_right, _flags = P.unpack_nav(payload)
            assert v_left == v_right
            out.append((ts, v_left, seq))
        return out


def _bridge_injection_ms(sends, poll_ms=2):
    """把发送时刻**回放给桥自己的判据** `vehicle.bridge.decide_forward`。

    为什么不在这儿重写一条 ">500 ms" 的规则：那条规则的权威版本在 `bridge.py`
    （`LINK_TIMEOUT_MS=500`、`SEEN_WINDOW_MS=60000`、`auto_on=True` 硬编码在 :206），
    测试里再抄一遍就成了第二个事实源（AGENTS 清单第 6 条）。回放还能顺手证明
    "这个假世界真的会注入"——见 `test_the_d2_run_never_leaves_the_bridge…` 里那条前提断言。

    返回第一次注入的毫秒时刻（相对第一条发送），没有注入给 None。
    """
    from vehicle import bridge as B
    base = min(ts for ts, _frame in sends)
    times = sorted(1000 + int(round((ts - base) * 1000.0)) for ts, _frame in sends)
    if not times:
        return None
    # 1000 ms 的偏移不是装饰：`last_pc_ms == 0` 在桥里表示"这台 PC 从没露过面"
    # （bridge.py:53-54 的 `last_pc_ms > 0` 条件，P0-5），从 0 开始回放会让假世界
    # 永远处于"纯 RC 运行"那一支，注入判据根本不会被执行。
    last_pc = last_inject = 0
    i = 0
    now = times[0]
    end = times[-1]                      # 只看**这次运行之内**（收尾是台架规程的事）
    while now <= end:
        raw = b'x' if (i < len(times) and times[i] == now) else None
        if raw is not None:
            i += 1
        _fwd, inject, last_pc, last_inject = B.decide_forward(
            raw, now, last_pc, True, last_inject_ms=last_inject)
        if inject:
            return now - 1000
        now += poll_ms
    return None



# ---------------------------------------------------------------- brief 给的 5 条


def test_percentile():
    assert LP.percentile([1, 2, 3, 4], 50) == 2.5
    assert LP.percentile([1, 2, 3, 4], 95) == 4


def test_d1_measures_request_to_mode_echo():
    """D1 = 发 MODE(0x01) 到看见 mode/authority 变化。用假收发，不碰硬件。"""
    calls = []

    def send_fn(frame):
        calls.append(frame)

    # 第 3 帧才带来 mode 变化；时间戳由假 recv 提供
    events = [(0.010, {'mode': 0, 'authority': 0, 'speed_mps': 0.0}),
              (0.060, {'mode': 0, 'authority': 0, 'speed_mps': 0.0}),
              (0.110, {'mode': 1, 'authority': 1, 'speed_mps': 0.0})]

    def recv_iter(deadline):
        for t, st in events:
            if t > deadline:
                break
            yield t, st

    out = LP.measure_d1(send_fn, recv_iter, repeats=1, timeout_s=1.0)
    assert out['n'] == 1 and out['timeouts'] == 0
    assert abs(out['samples_ms'][0] - 110.0) < 1e-6


def test_d1_counts_timeout_when_no_change():
    out = LP.measure_d1(lambda f: None, lambda deadline: iter([]),
                        repeats=2, timeout_s=0.01)
    assert out['n'] == 0 and out['timeouts'] == 2
    assert out['p50_ms'] is None


def test_d2_waits_for_speed_to_cross_threshold():
    events = [(0.010, {'speed_mps': 0.0}),
              (0.400, {'speed_mps': 0.02}),      # 低于阈值，不算
              (0.900, {'speed_mps': 0.06})]      # 越过 0.05

    def recv_iter(deadline):
        for t, st in events:
            if t > deadline:
                break
            yield t, st

    out = LP.measure_d2(lambda f: None, recv_iter, step_v=0.14,
                        threshold=0.05, timeout_s=2.0, repeats=1)
    assert out['n'] == 1
    assert abs(out['samples_ms'][0] - 900.0) < 1e-6


def test_report_keeps_d1_and_d2_separate():
    """斜坡限幅会把链路延迟掩盖掉，两个数不许合成一个。"""
    d1 = {'samples_ms': [100.0], 'p50_ms': 100.0, 'p95_ms': 100.0,
          'n': 1, 'timeouts': 0}
    d2 = {'samples_ms': [900.0], 'p50_ms': 900.0, 'p95_ms': 900.0,
          'n': 1, 'timeouts': 0, 'threshold_mps': 0.05}
    text = LP.report(d1, d2)
    assert 'D1' in text and 'D2' in text
    assert '100.0' in text and '900.0' in text
    assert '0.2' in text            # SLEW_ACC 的说明必须在场


# ---------------------------------------------------------------- 数学校准


def test_percentile_is_the_plotting_position_not_the_sketch_formula():
    """分位数定义要钉住：空样本给 None、单样本就是它自己、p95 不超过最大值。

    用 (n+1)*p/100 的绘图位置（Weibull/Hazen），**不是** brief 草图里那条 (n-1) 线性
    插值——后者对 [1,2,3,4] 给 p95=3.85，与上面那条测试要求的 4 不符（草图与测试打架，
    这里以测试为准）。选它还有第二层理由：B8 是一票否决的门，尾数取偏（偏大）比偏松安全。
    """
    assert LP.percentile([], 50) is None
    assert LP.percentile([123.0], 95) == 123.0
    assert LP.percentile([4, 1, 3, 2], 50) == LP.percentile([1, 2, 3, 4], 50)
    assert LP.percentile([1, 2, 3, 4], 50) <= LP.percentile([1, 2, 3, 4], 95)
    assert LP.percentile([1, 2, 3, 4], 95) <= 4
    assert LP.percentile([1, 2, 3, 4], 100) == 4
    assert LP.percentile([1, 2, 3, 4], 0) == 1


# ---------------------------------------------------------------- D1：帧型契约


def test_d1_sends_mode_frames_and_never_nav():
    """**D1 用的是 MODE 帧不是 NAV**——逐帧验字节。

    A2 之后 NAV 不改 `mode`（spec §3.3），用 NAV 探 D1 只会得到"超时 30 次"这种
    看着像链路坏了、其实是被测语义变了的结论。这条把"发出去的是什么型、什么 request"
    钉死，顺带钉住"request 必须交替"（一直只发 0x01，第二轮起 mode 已经在 1，
    归属问题就以另一种形式回来了）。
    """
    sent = []
    out = LP.measure_d1(sent.append, _no_frames, repeats=4, timeout_s=0.01,
                        profile_id=2)
    assert len(sent) == 4
    types = [P.unpack_frame(f)[0] for f in sent]
    assert types == [P.TYPE_MODE] * 4
    assert P.TYPE_NAV not in types
    requests = [P.unpack_mode(P.unpack_frame(f)[2])[0] for f in sent]
    assert requests == [P.MODE_REQ_AUTO, P.MODE_REQ_MANUAL,
                        P.MODE_REQ_AUTO, P.MODE_REQ_MANUAL]
    profiles = [P.unpack_mode(P.unpack_frame(f)[2])[1] for f in sent]
    assert profiles == [2] * 4                      # 档案号确实带上线了
    # 一条 STATUS 都没收到：发了 4 条不是 4 个样本
    assert out['n'] == 0 and out['timeouts'] == 4


def test_d1_wants_the_state_its_own_request_asks_for():
    """期望态跟着 request 走：0x01 要看到 mode==1，0x00 要看到 mode==0。

    反向验证：把 `want` 写死成 1（就是 Task 7 废掉的"只看有没有出现过 AUTO"），
    第 2、4 轮（请求交回人工、回显 mode==0）会各判一次超时，这条立刻红。
    """
    sent = []

    def recv_iter(deadline):
        req = P.unpack_mode(P.unpack_frame(sent[-1])[2])[0]
        echo = 1 if req == P.MODE_REQ_AUTO else 0
        yield 0.050, {'mode': echo, 'speed_mps': 0.0}

    out = LP.measure_d1(sent.append, recv_iter, repeats=4, timeout_s=0.5)
    assert out['n'] == 4 and out['timeouts'] == 0
    assert out['samples_ms'] == [50.0, 50.0, 50.0, 50.0]


def test_d1_skips_a_round_whose_mode_is_already_the_requested_one():
    """Task 7 那个反例在 D1 上的等价形：发送前就已经是期望态 -> 不能算本次引起的。

    这类轮次**连请求都不发**（发了也产生不了"变化"），单独记
    `skipped_already_in_mode`，既不进样本也不进超时。交替本身让它自愈：下一轮要的是
    相反态，基线必然不等于它。
    """
    sent = []
    out = LP.measure_d1(sent.append, _no_frames, repeats=1, timeout_s=0.01,
                        baseline_fn=lambda: {'mode': 1})
    assert out['n'] == 0 and out['timeouts'] == 0
    assert out['skipped_already_in_mode'] == 1
    assert sent == []

    # 基线是相反态时照常发、照常测（这一轮收不到回显 -> 超时）
    out2 = LP.measure_d1(sent.append, _no_frames, repeats=1, timeout_s=0.01,
                         baseline_fn=lambda: {'mode': 0})
    assert len(sent) == 1 and out2['timeouts'] == 1
    assert out2['skipped_already_in_mode'] == 0


def test_d1_a_missing_baseline_is_counted_not_treated_as_proof():
    """还没有任何 STATUS 可当基线时：`baseline_fn()` 给 None -> 照常测，但归属低一档，
    并且把这一档留进计数给报告用（`no_baseline`）。"""
    def recv_iter(deadline):
        yield 0.020, {'mode': 1, 'speed_mps': 0.0}

    out = LP.measure_d1(lambda f: None, recv_iter, repeats=1, timeout_s=0.5,
                        baseline_fn=lambda: None)
    assert out['n'] == 1
    assert out['no_baseline'] == 1


def test_d1_rejects_an_out_of_range_profile():
    """profile 是 u8：越界要在组帧之前拒掉，不能让 struct.error 从发送循环里逃出去。"""
    for bad in (256, -1):
        with pytest.raises(ValueError):
            LP.measure_d1(lambda f: None, _no_frames, repeats=1, profile_id=bad)


def test_d1_rejects_a_fractional_profile_instead_of_truncating_it():
    """`int(2.5)` 会悄悄截成 2 = PROFILE_REAL——档案号是"哪台车的权限"（spec §6），
    截出来的那个号看着合法，测的却是另一台车的拒绝逻辑。"""
    with pytest.raises(ValueError):
        LP.measure_d1(lambda f: None, _no_frames, repeats=1, profile_id=2.5)
    with pytest.raises(ValueError):
        LP.measure_d1(lambda f: None, _no_frames, repeats=1, profile_id='x')


# ---------------------------------------------------------------- D2：入参闸门


def test_d2_refuses_a_threshold_below_the_aliasing_floor():
    """TIM3 是 16 位计时：脉冲间隔 > 65.536 ms 会取模，低速段的 speed 不可信。

    0.005 m/s 会被算成约 0.01451 m/s —— 阈值放进混叠区，量出来的是一个自洽但不存在的数。
    所以低于 0.05 m/s 直接拒，不给"我就试一下"的机会；正好等于下限放行。
    """
    assert LP.MIN_THRESHOLD == 0.05
    for bad in (0.049, 0.005, 0.0):
        with pytest.raises(ValueError) as exc:
            LP.measure_d2(lambda f: None, _no_frames, threshold=bad, repeats=1)
        assert 'TIM3' in str(exc.value)
    LP.measure_d2(lambda f: None, _no_frames, threshold=0.05, repeats=1,
                  timeout_s=0.01)


def test_d2_refuses_a_step_above_the_shared_bench_limit():
    """阶跃速度走 `bench_limits.nav_exceeds_bench_limit` 这同一个谓词，不写第二个数。

    边界与共享谓词一致：正好等于限值放行（谓词给 f32 留了余量），超一点就拒。
    自己写 0.5 或 1.0 的话，`--to` 那条硬闸就跟 link_probe / bench_status 分家了。
    """
    assert LP.NAV_BENCH_LIMIT_MPS is BL.NAV_BENCH_LIMIT_MPS
    with pytest.raises(ValueError):
        LP.measure_d2(lambda f: None, _no_frames,
                      step_v=BL.NAV_BENCH_LIMIT_MPS + 0.01, repeats=1)
    LP.measure_d2(lambda f: None, _no_frames,
                  step_v=BL.NAV_BENCH_LIMIT_MPS, repeats=1, timeout_s=0.01)


def test_d2_refuses_non_finite_inputs_because_the_shared_gate_is_nan_blind():
    """共享闸现在 fail-closed（C-1 收口）：非有限值一律判为超限，这道闸拦得住 NaN 了。

    本模块的 `_finite()` 仍然保留，理由不是"共享闸拦不住"而是它给的是**带参数名的
    ValueError**——一句能照着改的报错比一个布尔值有用；NaN 一旦放过，`pack_nav` 把它
    写进线上，`speed >= threshold` 恒假，测出来是"超时 N 次"，看着像链路问题、其实是
    入参问题。`_check_d2_inputs()` 的先后（`:307` 的 `_finite` 在 `:313` 的共享闸之前）
    保证非有限值拿到的是 "must be finite" 那条，不是误导人的 "beyond bench limit"。
    """
    for bad in (float('nan'), float('inf'), float('-inf')):
        with pytest.raises(ValueError):
            LP.measure_d2(lambda f: None, _no_frames, step_v=bad, repeats=1)
        with pytest.raises(ValueError):
            LP.measure_d2(lambda f: None, _no_frames, threshold=bad, repeats=1)
    assert BL.nav_exceeds_bench_limit(float('nan'), float('nan'))   # 共享闸 fail-closed


def test_d2_refuses_a_step_that_cannot_reach_its_own_threshold():
    """cmd <= 阈值时斜坡永远到不了阈值，只会得到一串超时：直接拒。"""
    with pytest.raises(ValueError):
        LP.measure_d2(lambda f: None, _no_frames, step_v=0.05, threshold=0.05,
                      repeats=1)
    with pytest.raises(ValueError):
        LP.measure_d2(lambda f: None, _no_frames, step_v=0.0, repeats=1)


def test_d2_refuses_a_keepalive_wider_than_the_bridge_estop_window():
    """桥在最后一条 PC 帧 500 ms 后自注 ESTOP（bridge.py:24/30/206），锁存只能断电清
    （Fw-14）。阶跃到 0.05 m/s 本身要约 0.7 秒 —— 续发间隔必须小于那个窗口。"""
    with pytest.raises(ValueError):
        LP.measure_d2(lambda f: None, _no_frames, keepalive_s=0.5, repeats=1)
    with pytest.raises(ValueError):
        LP.measure_d2(lambda f: None, _no_frames, keepalive_s=-1, repeats=1)
    LP.measure_d2(lambda f: None, _no_frames, keepalive_s=0.2, repeats=1,
                  timeout_s=0.01)


def test_measure_functions_reject_a_non_positive_repeat_count():
    """repeats=0 会给出 n=0/p50=None 的"空报告"，看着像测过了。当场拒。"""
    with pytest.raises(ValueError):
        LP.measure_d2(lambda f: None, _no_frames, repeats=0)
    with pytest.raises(ValueError):
        LP.measure_d1(lambda f: None, _no_frames, repeats=0)


# ---------------------------------------------------------------- D2：发帧形状


def test_d2_sends_a_stop_then_a_step_nav():
    """每轮先 NAV(0,0) 把车停住，再 NAV(step, step)。

    "从静止起算"才有 spec §7.2 那句 0→0.14 m/s 约 0.7 秒的意义；上一条的先停也顺手
    把轮子留在零速，不是一轮测完车还在转。
    """
    sent = []
    out = LP.measure_d2(sent.append, _no_frames, step_v=0.14, threshold=0.05,
                        timeout_s=0.01, repeats=1, keepalive_s=0)
    frames = [P.unpack_frame(f) for f in sent]
    assert [f[0] for f in frames] == [P.TYPE_NAV, P.TYPE_NAV]
    assert P.unpack_nav(frames[0][2])[:2] == (0.0, 0.0)
    vl, vr, flags = P.unpack_nav(frames[1][2])
    assert abs(vl - 0.14) < 1e-6 and abs(vr - 0.14) < 1e-6
    assert flags == 0
    assert frames[0][1] != frames[1][1]          # 两条帧各占一个发送序号
    assert out['n'] == 0 and out['timeouts'] == 1
    assert out['threshold_mps'] == 0.05 and abs(out['step_mps'] - 0.14) < 1e-6


def test_d2_re_sends_the_step_while_waiting():
    """等待期间必须续发同一条阶跃，否则桥的 500 ms 注入先把板子锁在 ESTOP 里。

    续发是**由到达的帧驱动**的（STATUS 20 Hz 时约每 0.2 s 一条）；判到越过阈值的那一帧
    先算样本、不再补发。
    """
    sent = []
    events = [(0.05, 0.0), (0.10, 0.0), (0.25, 0.0), (0.45, 0.0), (0.75, 0.06)]

    def recv_iter(deadline):
        for t, v in events:
            if t > deadline:
                break
            yield t, {'speed_mps': v}

    out = LP.measure_d2(sent.append, recv_iter, step_v=0.14, threshold=0.05,
                        timeout_s=2.0, repeats=1, keepalive_s=0.2)
    navs = [P.unpack_nav(P.unpack_frame(f)[2]) for f in sent]
    steps = [nv for nv in navs if nv[0] > 0.0]
    assert out['keepalive_sends'] == 2                    # t=0.25 与 t=0.45 各一条
    assert len(steps) == 3                                  # 首条 + 2 条续发
    assert all(abs(a - 0.14) < 1e-6 and abs(b - 0.14) < 1e-6
               for a, b, _flags in steps)
    assert navs[0][:2] == (0.0, 0.0)              # 每轮开头那条是"停"
    assert out['n'] == 1
    assert abs(out['samples_ms'][0] - 750.0) < 1e-6
    assert out['frames_sent'] == len(sent)


def test_d2_does_not_sample_a_non_finite_speed():
    """线上来的 speed 是 NaN/None 时不进样本、进计数：这种帧证明不了任何东西。

    本轮开头那帧 0.02 是**给 re-arm 门的证据**（见 `test_d2_requires_a_sub_threshold_frame…`）：
    没有它，这一轮本来就不该产样本，测试会把"被 re-arm 门拒掉"误报成"非有限值处理错了"。
    """
    events = [(0.02, 0.0), (0.05, float('nan')), (0.10, None), (0.20, 0.06)]

    def recv_iter(deadline):
        for t, v in events:
            yield t, {'speed_mps': v}

    out = LP.measure_d2(lambda f: None, recv_iter, step_v=0.14, threshold=0.05,
                        timeout_s=1.0, repeats=1, keepalive_s=0)
    assert out['bad_speed_frames'] == 2
    assert out['n'] == 1
    assert abs(out['samples_ms'][0] - 200.0) < 1e-6


def test_d2_send_is_never_a_sample():
    """一条 STATUS 都收不到时：发了 20 条 = timeouts=10，不是"延迟已知"。"""
    sent = []
    out = LP.measure_d2(sent.append, _no_frames, step_v=0.14, threshold=0.05,
                        timeout_s=0.01, repeats=10, keepalive_s=0)
    assert out['n'] == 0
    assert out['timeouts'] == 10
    assert out['p95_ms'] is None
    assert len(sent) == 20                                   # 10 轮 x (停 + 阶跃)


# -------------------------------------------------- D2：不许自己造出桥的静默窗口（Important-1）


def _two_round_world():
    """一条 20 Hz 的假时间轴，专门用来暴露"持停段是不是真的在发东西"：

        0.00–0.80 s  speed 0.08  —— 上一轮的**余速**（高于阈值），本轮不许就此发阶跃
        0.80–1.40 s  speed 0.00  —— 停住了：第 1 轮的 re-arm 证据
        1.40 s 之后   speed 0.06  —— 阶跃引起的越阈；也是第 2 轮的余速（永不 re-arm）

    取 `repeats=2`：第 2 轮整个持停段都没有停下来的证据，用来验"不发阶跃"这件事。
    """
    world = _Feed(_frames([(0.0, 0.8, 0.08), (0.8, 1.4, 0.0), (1.4, 3.2, 0.06)]))
    out = LP.measure_d2(world.send, world.recv_iter, step_v=0.14, threshold=0.05,
                        timeout_s=1.0, repeats=2, keepalive_s=0.2, settle_s=1.0)
    return world, out


def test_d2_keeps_the_pc_sending_through_the_settle():
    """**默认参数下 D2 不再把自己锁进 ESTOP**：settle 那段是"边发 NAV(0,0) 边看 STATUS"，
    不是"停一下再睡 1 秒"。睡的那 1 秒里 PC 一个字节都不发，而桥 500 ms 就注 ESTOP
    （bridge.py:24/30/206），Fw-14 之后只能断电清——工具会把**自己**变成它正在诊断的症状。

    旧实现下这条必红：`send stop; sleep(1.0); send step` 之间一条发送都没有，
    于是"从第一次停到阶跃的跨度"是 0（假世界的钟被 sleep 跳过＝什么都没发生），
    而"跨度 ≥ 一个桥窗口"和"这期间至少有 N 条续发"两条都过不了。
    """
    world, out = _two_round_world()
    times = [ts for ts, _f in world.sends]
    gaps = [b - a for a, b in zip(times, times[1:])]
    assert gaps, 'D2 sent nothing at all'
    # 1) 整个 D2 过程里，相邻两次 PC 发送的间隔不许超过桥的静默窗口
    assert max(gaps) <= LP.BRIDGE_ESTOP_AFTER_S, 'max gap %.3f s' % max(gaps)
    # 2) 第 1 轮的持停跨度真的跨过了一个桥窗口（不然上面的 1) 是空跑出来的）
    decoded = world.decoded()
    first_step = min(i for i, (_t, v, _s) in enumerate(decoded) if v > 0.0)
    span = decoded[first_step][0] - decoded[0][0]
    assert span >= LP.BRIDGE_ESTOP_AFTER_S
    # 3) 这段跨度里每一拍都发了东西：停帧续发次数 >= 跨度/节奏 - 1（留 1 拍的边角余量）
    re_sent = sum(1 for i in range(first_step) if decoded[i][1] == 0.0) - 1
    assert re_sent >= int(span / 0.2) - 1
    # 顺带钉住测量本身没被这次改动改坏：样本是**阶跃之后**第一次越阈那一帧
    # （持停在 0.85 s 挣到证据 -> 阶跃 0.85 s -> 越阈 1.45 s -> 600 ms，不是 50 ms）
    assert out['n'] == 1 and abs(out['samples_ms'][0] - 600.0) < 1e-6


def test_the_bridge_never_injects_an_estop_during_a_d2_run():
    """把 D2 的发送时刻**回放给桥自己的判据** `vehicle/bridge.py:decide_forward`：
    整个运行期间它一次都不该决定注入 ESTOP（`auto_on=True` 是 :206 硬编码的）。

    为什么在测试里回放而不是重写一条 ">500 ms"：那条规则的权威版本在桥里，抄一遍就
    是第二个事实源（AGENTS 清单第 6 条）。

    两条**前提**必须先立住，否则"没注入"是一文不值的绿：
      · 回放本身抓得住违规——把"发一条停帧、干等 1 秒、再发阶跃"这个旧形状喂给它，
        必须报出注入；
      · 这个假世界**真的**跑出了一段比桥窗口还长的持停，并且那段持停是按节奏喂着的
        （`keepalive_sends` 说计数）。这一条正是旧实现红的地方：旧代码在窗口之外
        `time.sleep(settle)`，那 1 秒不进这把建模的钟，于是它的"发送序列"在桥上看着
        毫无破绽——**没有这两条前提，回放会把"工具睡了一觉"读成"工具一秒都没停过"**。
    """
    world, out = _two_round_world()
    stop = P.pack_frame(P.TYPE_NAV, P.pack_nav(0.0, 0.0), 0)
    step = P.pack_frame(P.TYPE_NAV, P.pack_nav(0.14, 0.14), 1)
    assert _bridge_injection_ms([(0.0, stop), (1.0, step)]) is not None
    decoded = world.decoded()
    first_step = min(i for i, d in enumerate(decoded) if d[1] > 0.0)
    assert decoded[first_step][0] - decoded[0][0] >= LP.BRIDGE_ESTOP_AFTER_S
    assert out['keepalive_sends'] >= 8          # 3 轮段的续发：持停 4 + 窗口 2 + 持停 5
    assert _bridge_injection_ms(world.sends) is None


def test_d2_does_not_command_the_step_until_the_hold_proved_standing_still():
    """持停段的证据门槛：没有"有限且低于阈值"的一帧，就**不发**那条阶跃。

    第 2 轮整个持停段都是 0.06 m/s 的余速 ⇒ 一轮里只该看到停帧（NAV(0,0)），
    一条阶跃都不该上线。旧实现每轮无条件发阶跃 ⇒ 红。
    """
    world, out = _two_round_world()
    kinds = ['step' if v > 0.0 else 'stop' for _t, v, _s in world.decoded()]
    pairs = zip(['stop'] + kinds, kinds)
    bursts = sum(1 for a, b in pairs if b == 'step' and a == 'stop')
    assert bursts == 1                    # 两轮里只有一轮挣到了发阶跃的资格
    assert out['repeats'] == 2 and out['n'] == 1
    assert out['timeouts'] == 1 and out['not_rearmed'] == 1
    assert kinds[-6:] == ['stop'] * 6     # 最后一整轮全是停帧：一直喂着，没叫轮子转
    assert out['keepalive_sends'] >= 3    # 第 2 轮的持停一直是喂着的


# -------------------------------------------------- D2：re-arm 门（Important-2）


def test_d2_requires_a_sub_threshold_frame_before_it_samples_a_crossing():
    """上一轮的余速不许冒充"首次越阈"：判据必须是**先见到停、再见到越阈**。

    0.14 m/s 的余速按 0.2 m/s^2 减到 0.05 以下要约 0.45–0.7 秒，正好落在新窗口的头几帧
    上；照收就得到 50–200 ms 的"机械响应"——与本模块防 TIM3 混叠同一种**自洽但不存在**
    的数（`--settle` 被操作员调小时，这道门是唯一还剩的东西）。旧实现把 0.05 秒那帧
    直接当样本 ⇒ 红。
    """
    events = [(0.05, 0.10), (0.20, 0.0), (0.90, 0.06)]

    def recv_iter(deadline):
        for t, v in events:
            yield t, {'speed_mps': v}

    out = LP.measure_d2(lambda f: None, recv_iter, step_v=0.14, threshold=0.05,
                        timeout_s=2.0, repeats=1, keepalive_s=0)
    assert out['n'] == 1
    assert abs(out['samples_ms'][0] - 900.0) < 1e-6
    assert out['pre_arm_above_frames'] == 1     # 被拒的那一帧要看得见，不许静默丢弃


def test_d2_treats_a_round_of_pure_residual_speed_as_no_sample():
    """整轮都停不下来（一帧都高于阈值）：不产样本，并且说清是**哪一类**没产。

    `timeouts` 记"这一轮没有样本"，`not_rearmed` 记"因为没有静止证据"——少了后面这个数，
    一屏 n=0 会被读成链路不通。旧实现下这条红（它会把第一帧当 50 ms 的样本）。
    """
    def recv_iter(deadline):
        for k in range(20):
            yield 0.05 * (k + 1), {'speed_mps': 0.08}

    out = LP.measure_d2(lambda f: None, recv_iter, step_v=0.14, threshold=0.05,
                        timeout_s=1.0, repeats=1, keepalive_s=0)
    assert out['n'] == 0 and out['timeouts'] == 1
    assert out['not_rearmed'] == 1
    assert out['pre_arm_above_frames'] == 20


def test_d2_a_non_finite_speed_is_not_evidence_of_standing_still():
    """NaN/None 既不能当"越过了阈值"，**也不能当"确实停住了"**：两头都不算。

    这道门要的是证据，不是"这一帧没写字段所以算它低于阈值"。旧实现只在这一条上
    把 0.06 那帧当样本（因为根本没有门）⇒ 红。
    """
    events = [(0.05, None), (0.10, float('nan')), (0.15, 0.06)]

    def recv_iter(deadline):
        for t, v in events:
            yield t, {'speed_mps': v}

    out = LP.measure_d2(lambda f: None, recv_iter, step_v=0.14, threshold=0.05,
                        timeout_s=1.0, repeats=1, keepalive_s=0)
    assert out['bad_speed_frames'] == 2
    assert out['n'] == 0 and out['timeouts'] == 1
    assert out['pre_arm_above_frames'] == 1      # 0.06 那一帧是余速，不是样本
    assert out['not_rearmed'] == 1               # 有可信帧却从未停住：诊断名叫 re-arm
    # 另一头：一帧可信的都没有时不许冒领 `not_rearmed`——那是"没收到/没解出"，
    # 与"收到了但从没停下"是两种不同的故障，混在一起就等于把收帧问题说成 pacing 问题。
    out2 = LP.measure_d2(lambda f: None,
                         lambda dl: iter([(0.05, {'speed_mps': None}),
                                          (0.10, {'speed_mps': float('nan')})]),
                         step_v=0.14, threshold=0.05, timeout_s=1.0, repeats=1,
                         keepalive_s=0)
    assert out2['bad_speed_frames'] == 2 and out2['n'] == 0
    assert out2['not_rearmed'] == 0 and out2['timeouts'] == 1


# -------------------------------------------------- D2：到底发过阶跃没有（fix round 2 的计数器）


def test_d2_counts_the_rounds_that_actually_commanded_a_step():
    """`rounds_step_commanded`：把"没挣到资格所以没发阶跃"与"发了阶跃但门没开"分开（NEW-3 同族）。

    `not_rearmed` 一个键混着这两类，而它们的归属完全不同：前者是本工具的 pacing，
    后者是**问过了轮子、轮子没答**。合并计数会让混合轮次（3 轮没发 + 7 轮发了从不越阈）
    把执行面整条抹掉——那是"把症状推给别人"的镜像。旧实现没有这个键 ⇒ KeyError 红。
    """
    # 两轮世界：第 1 轮持停挣到证据并发了阶跃，第 2 轮全程余速、一条阶跃都没发。
    _world, out = _two_round_world()
    assert out['not_rearmed'] == 1 and out['timeouts'] == 1
    assert out['rounds_step_commanded'] == 1
    # `settle_s == 0`：门挪进阶跃窗口内，每一轮都真的叫过轮子（分母 = repeats）。
    def all_residual(deadline):
        for k in range(20):
            yield 0.05 * (k + 1), {'speed_mps': 0.08}

    out2 = LP.measure_d2(lambda f: None, all_residual, step_v=0.14, threshold=0.05,
                         timeout_s=1.0, repeats=3, keepalive_s=0)
    assert out2['n'] == 0 and out2['not_rearmed'] == 3
    assert out2['rounds_step_commanded'] == 3
    # 计数行：非零才印（与 `_count_bits` 的"不印 =0 凑数"同一条纪律）。
    line = LP._fmt_counts(out)
    assert 'rounds_step_commanded=1' in line, line
    assert 'rounds_step_commanded' not in LP._fmt_counts(
        {'n': 0, 'timeouts': 1, 'frames_sent': 2, 'rounds_step_commanded': 0})


# -------------------------------------------------- D2：续发的序号不许冻结（Minor M-1）


def test_d2_re_sends_are_repacked_with_a_fresh_sequence_number():
    """续发的每一帧都是**重新组帧的新帧**，不是同一个字节串的冻结重传。

    现固件不读 NAV 的 seq，所以今天看着无害；但批 2 要让指令带 seq、单片机回传"最后
    执行到的 seq"（spec §7.2），那时重传与原帧不可区分，而本文件自己承诺过
    "线上日志分得清是谁发的"。旧实现把 `step_frame` 变量反复 `send_fn` ⇒ 红。
    """
    world, _out = _two_round_world()
    decoded = world.decoded()
    assert len(decoded) >= 10, 'this world should have produced a lot of feeding'
    seqs = [s for _t, _v, s in decoded]
    assert len(set(seqs)) == len(seqs), 'two sends share one sequence number: %r' % seqs
    assert len({f for _t, f in world.sends}) == len(world.sends)
    # 同一条阶跃的续发：载荷一模一样，只有序号在走（证明差别确实在 seq 那一层）
    steps = [d for d in decoded if d[1] > 0.0]
    assert len({s for _t, _v, s in steps}) == len(steps)
    assert steps[0][1] == steps[-1][1] == pytest.approx(0.14)
    # 而且整进程一条序号线仍然是连续的（与 measure_d1 的 seq_start 契约不打架）
    assert seqs == list(range(seqs[0], seqs[0] + len(seqs)))



# ---------------------------------------------------------------- StatusStream


def test_stream_accepts_status_and_counts_the_rest():
    """坏帧必须计数、不许静默：解不开的报文和非 STATUS 型都不进时间线。"""
    s = LP.StatusStream()
    assert s.ingest(_status_frame(1, mode=0)) is True
    assert s.ingest(b'\xa5\x5Anot-a-frame') is False
    assert s.ingest(P.pack_frame(P.TYPE_NAV, P.pack_nav(0.0, 0.0), 9)) is False
    assert s.ingest(_status_frame(2, mode=1)) is True
    assert s.frames == 2
    assert s.rx.good == 2
    assert s.rx.bad == 2                       # 账在 StatusReceiver 里：一套判据


def test_stream_rejects_a_15_byte_status_instead_of_guessing_fields():
    """载荷长度只认 14/19（A8）。字段错位必须计成坏帧，不能被读成"速度很小"。"""
    s = LP.StatusStream()
    assert s.ingest(P.pack_frame(P.TYPE_STATUS, b'\x00' * 15, 1)) is False
    assert s.rx.bad == 1 and s.frames == 0


def test_stream_drops_frames_that_arrived_before_the_request():
    """上一轮之后到达的帧不能算这一轮的回显——否则得到偏小甚至为负的样本。"""
    s = LP.StatusStream()
    s.clock = _Ticks(0.0, 10.0)
    s.ingest(_status_frame(1, mode=1), t=-1.0)
    assert list(s.recv_iter(0.01)) == []
    assert s.dropped_stale == 1


def test_stream_yields_seconds_since_the_request_was_sent():
    """recv_iter 的产出是相对秒数（契约见模块文档串），样本 = t*1000 就是这么来的。

    floor 故意不是 0（真实时钟当然也不是）：只有基线非零，"忘了减 floor"这种写法
    才会被抓住——它 otherwise 与正确实现给出一样的数，测试也就白写了。
    """
    s = LP.StatusStream()
    s.clock = _Ticks(2.0, 10.0)
    s.ingest(_status_frame(1, mode=1), t=2.25)
    items = list(s.recv_iter(1.0))
    assert len(items) == 1
    t, st = items[0]
    assert t == 0.25          # 2.25 - 2.0 在二进制里是精确的，所以能写 ==
    assert st['mode'] == 1


def test_stream_hands_a_frame_beyond_the_window_to_the_next_round():
    """窗口外到的帧留给下一轮，不吃掉：吃掉就等于把一次真实回显判成超时。"""
    s = LP.StatusStream()                      # 默认时钟 = time.monotonic
    s.ingest(_status_frame(1, mode=1), t=s.clock() + 5.0)
    assert list(s.recv_iter(0.5)) == []
    got = list(s.recv_iter(6.0))
    assert len(got) == 1
    assert got[0][0] > 0.0
    assert s.dropped_stale == 0


def test_stream_recv_iter_stops_at_the_deadline():
    """窗口到点自己收口（真实现里靠 socket 超时，这里靠时钟推进）。"""
    s = LP.StatusStream()
    s.clock = _Ticks(0.0, 10.0)
    assert list(s.recv_iter(0.5)) == []
    assert s.dropped_stale == 0


# ---------------------------------------------------------------- 读线程 / 发送侧


class _Sock:
    """假 socket：按脚本给报文，给完就 OSError（模拟 socket 被关掉）。"""

    def __init__(self, packets):
        self.packets = list(packets)

    def recvfrom(self, n):
        if self.packets:
            return self.packets.pop(0), ('192.168.127.10', 9000)
        raise OSError('socket closed')


class _TimeoutSock(_Sock):
    """先超时一次（对端暂时没发），再给一帧，然后报错。"""

    def __init__(self, packets):
        _Sock.__init__(self, packets)
        self.timeouts = 0

    def recvfrom(self, n):
        if self.timeouts == 0:
            self.timeouts += 1
            raise LP.socket.timeout('nothing yet')
        return _Sock.recvfrom(self, n)


def test_pump_socket_moves_datagrams_and_leaves_a_trace_when_it_ends():
    """读线程退出要留下痕迹，不能无声停住（Task 8 在 stdin 线程上补过同一课）。"""
    s = LP.StatusStream()
    sock = _Sock([_status_frame(1, mode=0), b'garbage', _status_frame(2, mode=1)])
    n = LP.pump_socket(sock, s, threading.Event())
    assert n == 3 and s.datagrams == 3
    assert s.frames == 2 and s.rx.bad == 1
    assert s.reader_error                        # 说得出为什么停的


def test_pump_socket_keeps_going_through_socket_timeouts():
    s = LP.StatusStream()
    sock = _TimeoutSock([_status_frame(1, mode=0)])
    LP.pump_socket(sock, s, threading.Event())
    assert s.frames == 1
    assert s.rx.last_good_time is not None


class _FailSock:
    def sendto(self, frame, addr):
        raise OSError('10065 unreachable')


class _OkSock:
    def __init__(self):
        self.sent = []

    def sendto(self, frame, addr):
        self.sent.append((frame, addr))


def test_sender_counts_errors_and_never_claims_delivery():
    ok = LP.UdpSender('h', 1, sock=_OkSock())
    assert ok.send(b'x') is True and ok.sent == 1 and ok.errors == 0
    bad = LP.UdpSender('h', 1, sock=_FailSock())
    assert bad.send(b'x') is False
    assert bad.sent == 0 and bad.errors == 1 and bad.last_error


def test_sender_is_opt_in_and_reuses_the_recorder_target_rules():
    """不给 `--to` 就一个字节都不发；给了也不许打到广播地址或自己正在听的端口。

    校验用的是 `bench_status.resolve_target` 这**同一份**规则，不在这里再抄一遍
    （AGENTS 清单第 6 条：单一事实源不许漂移）。
    """
    assert LP.make_sender(None, avoid_port=9100) is None
    with pytest.raises(ValueError):
        LP.make_sender('192.168.127.255:9000', avoid_port=9100)   # 定向广播
    with pytest.raises(ValueError):
        LP.make_sender('255.255.255.255:9000', avoid_port=9100)   # 全网广播
    with pytest.raises(ValueError):
        LP.make_sender('192.168.127.10:9100', avoid_port=9100)    # 打回自己
    with pytest.raises(ValueError):
        LP.make_sender('192.168.127.10', avoid_port=9100)         # 少了端口


# ---------------------------------------------------------------- 报告 / CLI


def test_report_lines_do_not_merge_the_two_numbers():
    """两行各自只带自己的数：合并成"一个延迟"就是 spec §7.2 明令禁的写法。"""
    d1 = {'samples_ms': [100.0], 'n': 1, 'timeouts': 0, 'p50_ms': 100.0,
          'p95_ms': 100.0, 'frames_sent': 1}
    d2 = {'samples_ms': [900.0], 'n': 1, 'timeouts': 0, 'p50_ms': 900.0,
          'p95_ms': 900.0, 'frames_sent': 3, 'threshold_mps': 0.05,
          'step_mps': 0.14}
    lines = LP.report(d1, d2).split('\n')
    l1 = [ln for ln in lines if ln.startswith('D1')]
    l2 = [ln for ln in lines if ln.startswith('D2')]
    assert l1 and l2
    assert any('100.0' in ln and '900.0' not in ln for ln in l1)
    assert any('900.0' in ln and '100.0' not in ln for ln in l2)
    text = '\n'.join(lines)
    assert 'link delay = D1' in text            # 论文口径的原文
    assert 'D2 - D1' in text                    # 机械响应是**派生量**，不是新的第三个数
    assert 'SLEW_ACC=0.2' in text
    low = text.lower()
    assert 'total latency' not in low and 'overall latency' not in low


def test_report_handles_zero_samples_without_inventing_a_number():
    d = {'samples_ms': [], 'n': 0, 'timeouts': 3, 'p50_ms': None, 'p95_ms': None}
    text = LP.report(dict(d), dict(d, threshold_mps=0.05, timeouts=10))
    assert 'n=0' in text
    assert '3 timeouts' in text and '10 timeouts' in text
    assert 'None' not in text                    # p50=None 不许印成 "None ms"
    assert 'nan' not in text.lower()


class _Rx:
    """假 StatusReceiver：cross_read 只读那几个计数器。"""

    def __init__(self, good=0, bad=0, out_of_order=0, resynced=0):
        self.good = good
        self.bad = bad
        self.out_of_order = out_of_order
        self.resynced = resynced


def _d(n=0, timeouts=0, **kw):
    out = {'samples_ms': [100.0] * n, 'n': n, 'timeouts': timeouts,
           'p50_ms': 100.0 if n else None, 'p95_ms': 100.0 if n else None,
           'frames_sent': 0, 'skipped_already_in_mode': 0, 'no_baseline': 0}
    out.update(kw)
    return out


def test_cross_read_says_the_d1_yes_d2_no_case_is_not_a_link_fault():
    """D1 有样本、D2 全超时 -> 台账 Fw-21 的形状：STATUS 在中断里组，轮子 PWM 在主循环里写。

    这条是"两个数放在一起才读得出来"的那半句话。没有它，操作员会把执行面的问题
    （Fw-18 那个 `main.c:305` 的等待、Fw-14 的 ESTOP 锁存）当成链路坏了去拆线。
    """
    lines = '\n'.join(LP.cross_read(_d(n=5), _d(n=0, timeouts=10), _Rx(good=200)))
    assert 'Fw-21' in lines
    assert 'link' in lines.lower() and 'not the suspect' in lines.lower()
    assert 'retrofit.c:311/334' in lines and 'main.c:567-576' in lines


def test_cross_read_voids_every_sample_when_the_board_rebooted():
    """Hw-26（约 2.95 秒一轮复位）期间出的数不作数：resynced 是它的签名。"""
    lines = '\n'.join(LP.cross_read(_d(n=5), _d(n=5), _Rx(good=200, resynced=3)))
    assert 'Hw-26' in lines
    assert 'VOID' in lines


def test_cross_read_keeps_no_status_and_no_echo_apart():
    """一帧 STATUS 都没收到（收的方向）与"STATUS 在流但两种回显都没出现"（发的方向 /
    现固件丢 MODE 帧 / ESTOP 锁存）是两种完全不同的故障，文案不许混。"""
    silent = '\n'.join(LP.cross_read(_d(n=0, timeouts=3), _d(n=0, timeouts=10),
                                     _Rx(good=0)))
    flowing = '\n'.join(LP.cross_read(_d(n=0, timeouts=3), _d(n=0, timeouts=10),
                                      _Rx(good=120)))
    assert 'receive path' in silent
    assert 'receive path' not in flowing
    assert 'retrofit.c:60-75' in flowing and 'Fw-14' in flowing

    # 但"锁存"这个嫌疑人里必须列上**这次运行自己**：D1 每轮发一帧之后要等 `--timeout-d1`
    # 秒而中途不能补发，那段静默本身就超桥的窗口。把症状全推给板子=把工具自己的 sleep
    # 洗成被测机制的故障，这正是本轮 Important-1 要求反查的那一类归因错误。
    ours = '\n'.join(LP.cross_read(_d(n=0, timeouts=3, wait_s=2.0),
                                   _d(n=0, timeouts=10, wait_s=5.0), _Rx(good=120)))
    assert 'this very run is a suspect' in ours
    assert 'vehicle/bridge.py:24/30/206' in ours and 'Power the board down' in ours
    # 等待短于桥窗口时，这句自我怀疑不该出现（不许把没发生的风险写成结论）
    assert 'this very run is a suspect' not in '\n'.join(
        LP.cross_read(_d(n=0, timeouts=3, wait_s=0.4), _d(n=0, timeouts=10),
                      _Rx(good=120)))


def test_cross_read_keeps_the_execution_side_suspect_when_some_rounds_stepped():
    """**混合轮次**（3 轮没发阶跃 + 7 轮发了却从不越阈）不许把执行面整条抹掉（NEW-3 同族）。

    旧实现只按 `not_rearmed` 挡 Fw-21 那句，并把全部 n=0 说成"pacing 的产物、不是链路
    故障"——那等于把"我问过轮子、轮子没答"洗成"我没问"。旧实现下这条红（它连
    `rounds_step_commanded` 这个键都没有，Fw-21 也被合并计数挡掉了）。
    """
    mixed = _d(n=0, timeouts=10, not_rearmed=3, pre_arm_above_frames=12,
               rounds_step_commanded=7, wait_s=5.0, settle_s=1.0, keepalive_s=0.2)
    text = '\n'.join(LP.cross_read(_d(n=5), mixed, _Rx(good=300)))
    assert 'Fw-21' in text, 'the rounds that did command a step must stay a suspect'
    assert 'DID command the step in 7 rounds' in text
    assert 'artefact of how this run was paced' not in text
    # 计数行里这一跑的分母看得见（操作员不用读源码也知道 7 轮叫过轮子）
    assert 'rounds_step_commanded=7' in LP.report(_d(n=5), mixed)

    # 反面：一次阶跃都没发 ⇒ 这才是"本跑的 pacing"，执行面一个字都不许说。
    never = _d(n=0, timeouts=10, not_rearmed=10, rounds_step_commanded=0, wait_s=5.0)
    text2 = '\n'.join(LP.cross_read(_d(n=5), never, _Rx(good=300)))
    assert 'Fw-21' not in text2
    assert 'artefact of how this run was paced' in text2
    assert 'rounds_step_commanded=0: no round ever sent a step' in text2

    # 老形状（结果里没有这个键）不许被新分支误伤：仍按 `not_rearmed` 的旧读法走。
    legacy = _d(n=0, timeouts=10, not_rearmed=2)
    assert 'Fw-21' not in '\n'.join(LP.cross_read(_d(n=5), legacy, _Rx(good=300)))
    assert text.isascii() and text2.isascii()


def test_cross_read_refuses_to_call_a_dirty_stream_a_link_quality():
    lines = '\n'.join(LP.cross_read(_d(n=5), _d(n=5), _Rx(good=100, bad=7,
                                                          out_of_order=4)))
    assert 'not a link-quality statement' in lines


def test_cross_read_labels_d2_minus_d1_as_the_only_derived_number():
    lines = '\n'.join(LP.cross_read(_d(n=5), _d(n=5), _Rx(good=200)))
    assert 'D2 - D1' in lines
    assert 'do not average, sum or replace' in lines


def test_cross_read_does_not_accuse_the_execution_side_when_d2_was_skipped():
    """`--skip-d2` 的那一条 NAV 根本没发过：没有东西可判，就不许说"执行面有问题"。

    这条是自检时发现的**自己造的假结论**：`d1 有样本 + d2 没样本` 那个分支原本只看
    `d2['n']`，而"被跳过"与"发了但没越过阈值"在计数上长得一模一样。
    """
    skipped = {'samples_ms': [], 'n': 0, 'timeouts': 0, 'p50_ms': None,
               'p95_ms': None, 'frames_sent': 0, 'skipped': True}
    lines = '\n'.join(LP.cross_read(_d(n=5), skipped, _Rx(good=200)))
    assert 'Fw-21' not in lines
    assert 'skipped by request' in lines
    text = LP.report(_d(n=5), skipped)
    assert 'skipped by request (--skip-d2)' in text
    assert 'n=0, 0 timeouts' not in text        # 没跑过 != 跑了且全超时


def test_next_seq_threads_so_no_two_sent_frames_share_one_number():
    """`seq_start`/`next_seq` 让 D1 与 D2 共用**一条**发送序号线（`main()` 这么串）。

    各自从 0 开始的话，两轮里会出现同样的号，事后翻线上日志分不出是谁发的——
    取证工具不该给自己造这种歧义（与 `bench_status.TxSender` 的独立计数器同口径）。
    """
    sent = []
    d1 = LP.measure_d1(sent.append, _no_frames, repeats=3, timeout_s=0.01,
                       seq_start=0)
    d2 = LP.measure_d2(sent.append, _no_frames, timeout_s=0.01, repeats=2,
                       keepalive_s=0, seq_start=d1['next_seq'])
    seqs = [P.unpack_frame(f)[1] for f in sent]
    assert len(seqs) == 7 and len(set(seqs)) == 7
    assert d1['next_seq'] == 3 and d2['next_seq'] == 7


def test_measure_functions_refuse_a_negative_window_or_seq():
    """负的等待窗口会让 `recv_iter` 立刻收口 -> 看着像"链路超时"，其实是入参写错。"""
    for bad in (-1, -0.5):
        with pytest.raises(ValueError):
            LP.measure_d1(lambda f: None, _no_frames, timeout_s=bad, repeats=1)
        with pytest.raises(ValueError):
            LP.measure_d2(lambda f: None, _no_frames, timeout_s=bad, repeats=1)
    with pytest.raises(ValueError):
        LP.measure_d1(lambda f: None, _no_frames, seq_start=-1, repeats=1)
    with pytest.raises(ValueError):
        LP.measure_d2(lambda f: None, _no_frames, seq_start=1.5, repeats=1)
    with pytest.raises(ValueError):
        LP.measure_d2(lambda f: None, _no_frames, settle_s=-0.1, repeats=1)


def test_everything_this_script_prints_is_ascii():
    """控制台是 cp936：判据、报告、诊断、参数帮助里都不许有中文字符。

    中文留在注释和文档串里（源文件 UTF-8，不进控制台）。这条把纪律钉成断言，
    否则下一次"顺手加一句中文提示"就会在真机上变成 UnicodeEncodeError 或乱码。
    扫所有公开可调用面，不给"只测一半"的机会。
    """
    targets = [LP.report({'samples_ms': [100.0], 'n': 1, 'timeouts': 0,
                          'p50_ms': 100.0, 'p95_ms': 100.0, 'frames_sent': 4},
                         {'samples_ms': [900.0], 'n': 1, 'timeouts': 0,
                          'p50_ms': 900.0, 'p95_ms': 900.0, 'frames_sent': 3,
                          'threshold_mps': 0.05, 'step_mps': 0.14}),
               LP.report({'samples_ms': [], 'n': 0, 'timeouts': 3, 'p50_ms': None,
                          'p95_ms': None},
                         {'samples_ms': [], 'n': 0, 'timeouts': 10, 'p50_ms': None,
                          'p95_ms': None, 'threshold_mps': 0.05}),
               LP._diagnostics(LP.StatusStream().rx,
                               LP.UdpSender('h', 1, sock=_OkSock()),
                               LP.StatusStream()),
               '\n'.join(LP.cross_read(_d(n=3), _d(n=0, timeouts=9), _Rx(good=60))),
               '\n'.join(LP.cross_read(_d(n=3), _d(n=3), _Rx(good=60))),
               '\n'.join(LP.cross_read(
                   _d(n=3), {'samples_ms': [], 'n': 0, 'timeouts': 0, 'p50_ms': None,
                             'p95_ms': None, 'skipped': True}, _Rx(good=60))),
               # 本轮新增的两处打印面：告警行 + 带 re-arm 计数的计数行
               '\n'.join(LP.estop_caution(2.0, keepalive_s=0.2, settle_s=1.0)),
               '\n'.join(LP.estop_caution(0.4)),
               LP.report(_d(n=3), _d(n=0, timeouts=2, not_rearmed=1,
                                    pre_arm_above_frames=7, keepalive_sends=11,
                                    wait_s=2.0, settle_s=1.0, keepalive_s=0.2)),
               '\n'.join(LP.cross_read(_d(n=3), _d(n=0, timeouts=2, not_rearmed=2,
                                                   pre_arm_above_frames=9, wait_s=2.0),
                                        _Rx(good=60))),
               # 第 2 轮新增的打印面：keepalive 关掉时的两句 + 四种节奏 + 混合轮次归属
               '\n'.join(LP.estop_caution(2.0, keepalive_s=0, settle_s=1.0)),
               '\n'.join(LP.estop_caution(2.0, keepalive_s=0, settle_s=0.0)),
               '\n'.join(LP.estop_caution(2.0, keepalive_s=None, settle_s=0.0)),
               LP.report(_d(n=3), _d(n=0, settle_s=0.0, keepalive_s=0.2)),
               LP.report(_d(n=3), _d(n=0, settle_s=1.0, keepalive_s=0.0)),
               LP.report(_d(n=3), _d(n=0, settle_s=0.0, keepalive_s=0.0)),
               LP.report(_d(n=3), _d(n=0, timeouts=1, rounds_step_commanded=0,
                                    settle_s=1.0, keepalive_s=0.2)),
               '\n'.join(LP.cross_read(_d(n=3), _d(n=0, timeouts=10, not_rearmed=3,
                                                   pre_arm_above_frames=12,
                                                   rounds_step_commanded=7),
                                        _Rx(good=60))),
               '\n'.join(LP.cross_read(_d(n=3), _d(n=0, timeouts=10, not_rearmed=10,
                                                   rounds_step_commanded=0),
                                        _Rx(good=60)))]
    for exc in (lambda: LP.measure_d2(lambda f: None, _no_frames, threshold=0.01),
                lambda: LP.measure_d2(lambda f: None, _no_frames,
                                      step_v=float('nan')),
                lambda: LP.measure_d1(lambda f: None, _no_frames, profile_id=300)):
        with pytest.raises(ValueError) as info:
            exc()
        targets.append(str(info.value))
    # 早拒时打印的那一行也是打印面
    for extra in (['--threshold', '0.01'], ['--step', 'nan'], ['--keepalive', '0.9'],
                  ['--keepalive', '0']):
        with pytest.raises(SystemExit) as info:
            LP._preflight_inputs(LP.build_argparser().parse_args(extra))
        targets.append(str(info.value))
    for text in targets:
        for chunk in text if isinstance(text, list) else [text]:
            assert chunk.isascii(), repr(chunk)
    # --help 也是打印面：所有 help 字符串一起扫
    parser = LP.build_argparser()
    assert parser.format_help().isascii()
    assert parser.format_usage().isascii()


def test_argparser_defaults_are_part_of_the_contract():
    """默认值也钉一下：D1 >=30 遍、阶跃 0.14、阈值 0.05、续发 < 桥的失联窗口。

    `--profile` **不在**参数里（brief 草图收了它，但 spec §6 与 Task 7/8 的既有口径是
    "档案号只从 config/vehicle_profile.yaml 取"——命令行给档案号 = 允许拿另一台车的
    权限申请无人。这里把偏离钉成断言，别让下一次"顺手补个参数"把它带回来）。
    """
    a = LP.build_argparser().parse_args([])
    assert a.to is None                       # 默认不发
    assert a.listen == 9100
    assert a.repeats >= 30                    # spec §7.2：一次跑 >=30 遍出 p50/p95
    assert abs(a.step - 0.14) < 1e-9
    assert abs(a.threshold - 0.05) < 1e-9
    assert 0 < a.keepalive < LP.BRIDGE_ESTOP_AFTER_S
    assert not hasattr(a, 'profile')


def test_plan_turns_a_refused_target_into_an_ascii_explanation():
    """规则在 `bench_status.resolve_target` 里（共享那一份），文案是中文的。

    中文提示重定向进管道/日志会变乱码，而这是操作员**唯一会读的一行**。plan() 不改共享
    模块，只把同一套规则用 ASCII 重说一遍，并把原文带上（信息一条不丢）。
    """
    a = LP.build_argparser().parse_args(['--to', '192.168.127.255:9000'])
    with pytest.raises(SystemExit) as exc:
        LP.plan(a)
    text = str(exc.value)
    head = text.split('Original message:')[0]
    assert head.isascii(), repr(head[:60])
    assert 'broadcast' in head and '9000' in head
    assert 'Original message' in text


def test_run_needs_a_target_and_refuses_to_send_without_one():
    """`plan()` 是 main 的纯逻辑部分：没有 --to 就不该有任何发送计划。"""
    a = LP.build_argparser().parse_args([])
    with pytest.raises(SystemExit) as exc:
        LP.plan(a)
    assert 'send' in str(exc.value).lower()


# ------------------------------------------- CLI 层早拒（Minor M-2）与开工打印的告警行


def test_bad_inputs_are_refused_before_any_socket_or_packet(monkeypatch):
    """`--threshold 0.01` / `--step nan` / `--keepalive 0.6` 要在**建 socket 之前**就退出。

    闸门本身在 `measure_d1/measure_d2` 里（那两条一道没撤），但它们跑在 `bind_listener`
    之后——旧顺序下这些入参要等端口绑上、D1 把 30 条 MODE 发满之后才炸出 traceback：
    那等于"先把指令发上线、再告诉你参数写错了"，换来的只是一堆超时，而这一次发送
    本身可能已经把板子锁进 ESTOP。`--to` 一直是早拒的（"两条拒绝都发生在碰任何资源
    之前"），入参没理由享受更低的标准。
    """
    created = []

    def _no_sockets(*args, **kwargs):
        created.append((args, kwargs))
        raise AssertionError('a socket was created before the command line was checked')

    monkeypatch.setattr(LP.socket, 'socket', _no_sockets)
    bad = (['--threshold', '0.01'], ['--threshold', 'nan'], ['--step', 'nan'],
           ['--step', '0.3'], ['--keepalive', '0.6'], ['--keepalive', '-1'],
           ['--settle', '-1'], ['--repeats', '0'], ['--d2-repeats', '0'],
           ['--timeout-d1', '-0.5'], ['--timeout-d2', '1e999'],
           ['--warmup', '-0.1'])
    for extra in bad:
        argv = ['--to', '192.168.127.10:9000'] + extra
        with pytest.raises(SystemExit) as info:
            LP.main(argv)
        assert created == [], 'socket created for %r' % extra
        text = str(info.value)
        assert text.isascii() and 'nothing was sent' in text
    # --skip-d2 时这些值一条都不上线，拒它们只会挡住"这次只想量 D1"这条正当用法。
    # （用 _preflight_inputs 直接验，不走 main：那条路要建 socket。）
    LP._preflight_inputs(LP.build_argparser().parse_args(
        ['--skip-d2', '--threshold', '0.01', '--keepalive', '0.9']))
    # 而**正确**的参数必须放行，否则这条早拒就成了新的误伤。
    LP._preflight_inputs(LP.build_argparser().parse_args(
        ['--to', '192.168.127.10:9000']))


def test_estop_caution_says_which_phase_is_silent_and_what_the_bench_must_do():
    """D1 那条静默**改不掉**（中途补发 MODE 就不再是一次往返了），所以只能说明白：
    在没有回显的板上，本跑法会注入并锁存 ESTOP，台架规程要写明跑后断电。

    `!clear` 也救不了：它发的同样是 TYPE_MODE，现固件的 switch 里没有这一支
    （`retrofit.c:60-75`）——这句必须一起说，否则操作员会以为有软件捷径。
    """
    lines = LP.estop_caution(2.0, keepalive_s=0.2, settle_s=1.0)
    text = '\n'.join(lines)
    assert 'D1' in text and 'SILENT' in text
    assert 'Fw-14' in text and 'power' in text.lower() and '!clear' in text
    assert 'retrofit.c:60-75' in text and 'vehicle/bridge.py:24/30/206' in text
    # D2 那半边：说清持停段是"发着等"，并且不许假装遗留项已修
    assert 'M-3' in text and 'STATUS' in text
    # 等待短于桥窗口时，D1 那句不该出现（不许把没发生的风险写成告警）
    assert LP.estop_caution(0.4) == []
    # --skip-d2 时没有持停段，D2 那句也不该出现
    assert len(LP.estop_caution(2.0, settle_s=0.0)) == 1


def test_estop_caution_with_re_sending_off_says_the_run_goes_silent():
    """`keepalive_s == 0` 时那句告警不许念默认参数（NEW-1 的"不许只改打印"那一半）。

    旧实现无条件下印 `it re-sends NAV(0,0) every 0.00 s`——而 0 就是"不续发"，那句话对
    现场是一句假话，且掩盖了"持停与等待两段都会静默到窗口结束 ⇒ 桥注 ESTOP"这个真事实。
    命令行现在根本到不了这个值（`test_keepalive_zero_is_refused_…`），但 API 那条路还在，
    所以打印面自己也得说真话。旧实现下前两条断言就红。
    """
    text = '\n'.join(LP.estop_caution(2.0, keepalive_s=0, settle_s=1.0))
    assert 'every 0.00 s' not in text
    assert 'does NOT sleep' not in text
    assert 'D2 re-sending is OFF' in text
    assert '1.00 s window' in text and 'injects an ESTOP' in text
    assert 'Fw-14' in text and 'power' in text.lower()
    # settle 也关掉时，不许凭空描述一个不存在的持停段
    t2 = '\n'.join(LP.estop_caution(2.0, keepalive_s=0, settle_s=0.0))
    assert 'no hold phase' in t2 and 'every 0.00 s' not in t2
    # keepalive_s=None（main 在 --skip-d2 时传的就是它）：D2 一个字都不发，
    # 于是关于它的节奏一句都不许说——只有 D1 那句。
    lines = LP.estop_caution(2.0, keepalive_s=None, settle_s=0.0)
    assert len(lines) == 1 and 'D2' not in lines[0]
    # 正常跑法（0 < keepalive < 桥窗口）仍说"不睡空窗"，并带上 M-3 那句未修的话
    t3 = '\n'.join(LP.estop_caution(2.0, keepalive_s=0.2, settle_s=1.0))
    assert 'does NOT sleep' in t3 and 'every 0.20 s' in t3 and 'M-3' in t3
    # 这句也跟着**实参**走（同一处把默认值印成事实也是假话）
    t4 = '\n'.join(LP.estop_caution(2.0, keepalive_s=0.1, settle_s=0.35))
    assert '0.35 s settle' in t4 and 'every 0.10 s' in t4
    for t in (text, t2, t3, t4):
        assert t.isascii()


def test_main_does_not_describe_d2_pacing_when_d2_was_skipped(monkeypatch, capsys):
    """`--skip-d2 --keepalive 0`：D2 从未上线，开工行与报告都不许描述它的节奏。

    这是 NEW-1 修法①的**反向保险**：挡 0 之后，`--skip-d2` 仍走豁免（那一跑 D2 一条都不发），
    于是 `main()` 传给 `estop_caution()` 的必须是 `None` 而不是 `a.keepalive`——否则
    "0 = 会静默"那句会被印在一个**什么都没发**的跑法上，同一类假话换了个方向。
    """
    sender = _FakeSender()
    monkeypatch.setattr(LP, 'plan', lambda a: (sender, 2))
    monkeypatch.setattr(LP, 'bind_listener', lambda port: _BoomSock())
    monkeypatch.setattr(LP, 'measure_d1',
                        lambda *a, **k: {'samples_ms': [], 'n': 0, 'timeouts': 1,
                                         'p50_ms': None, 'p95_ms': None,
                                         'frames_sent': 1, 'next_seq': 1,
                                         'wait_s': 2.0})
    assert LP.main(['--to', '192.168.127.10:9000', '--warmup', '0',
                    '--skip-d2', '--keepalive', '0']) == 0
    out = capsys.readouterr().out
    assert 'caution: D1 will be SILENT' in out          # D1 那句照印
    assert 're-sending is OFF' not in out               # D2 一句都不许说
    assert 'every 0.00 s' not in out
    assert 'never ran in this session' in out           # 报告里也不作节奏声明
    assert 're-sent often enough' not in out
    assert out.isascii()


def test_keepalive_zero_is_refused_on_the_command_line_before_any_socket(monkeypatch):
    """`--keepalive 0` 在 CLI 层拒（NEW-1 选的修法①）——静默事实本身被堵住，不只是改口。

    0 = 关掉续发，于是持停段从 `NAV(0,0)` 到阶跃**一个字都不发**（默认 `--settle 1.0`），
    阶跃段也一样静默到窗口结束：都 > 桥的 500 ms ⇒ 桥注 ESTOP 并锁存，只能断电清（Fw-14）。
    那正是上一轮 Important-1 的症状从参数后门回来。API 层继续允许 0（单测用它当"不建模
    续发"的简写，那条路不碰板子），`--skip-d2` 也照旧豁免（D2 一条都不上线）。
    旧实现下这条红：0 过闸 → `make_sender` 建 socket → AssertionError，而且不是 SystemExit。
    """
    created = []

    def _no_sockets(*args, **kwargs):
        created.append((args, kwargs))
        raise AssertionError('a socket was created for --keepalive 0')

    monkeypatch.setattr(LP.socket, 'socket', _no_sockets)
    with pytest.raises(SystemExit) as info:
        LP.main(['--to', '192.168.127.10:9000', '--keepalive', '0'])
    assert created == [], 'a socket was built before --keepalive 0 was refused'
    text = str(info.value)
    assert text.isascii() and 'nothing was sent' in text
    assert 'keepalive_s 0' in text and 'ESTOP' in text and 'Fw-14' in text
    assert 'vehicle/bridge.py:24/30/206' in text
    # API 层不拒：挡了它等于把 40 多条单测一起打死，而那条路一个字都不上线。
    out = LP.measure_d2(lambda f: None, _no_frames, keepalive_s=0, repeats=1,
                        timeout_s=0.01)
    assert out['n'] == 0 and out['rounds_step_commanded'] == 1
    # --skip-d2 的豁免照旧（那些值一条都不上线），正常参数照常放行。
    LP._preflight_inputs(LP.build_argparser().parse_args(
        ['--skip-d2', '--keepalive', '0']))
    LP._preflight_inputs(LP.build_argparser().parse_args(
        ['--to', '192.168.127.10:9000', '--keepalive', '0.2']))


class _BoomSock:
    """假监听 socket：一读就报错，让读线程立刻带着 `reader_error` 退出来。"""

    def recvfrom(self, n):
        raise OSError('nothing on the bench yet')

    def close(self):
        pass


class _FakeSender:
    """假发送侧：只记账，不碰网络（`main()` 的收发段本来就只在这条路上测到这里）。"""

    host = '192.168.127.10'
    port = 9000

    def __init__(self):
        self.frames = []
        self.sent = 0
        self.errors = 0
        self.last_error = ''

    def send(self, frame):
        self.frames.append(frame)
        self.sent += 1
        return True

    def close(self):
        pass


def test_main_prints_the_estop_caution_in_the_startup_lines(monkeypatch, capsys):
    """告警必须**印在开工那几行**里，不是只躺在文档串里：台架上没人翻源码。

    这条是 Important-1 "至少补一行打印"的闭环核对——定义了 `estop_caution()` 而
    `main()` 不印它，操作员看到的东西和以前一模一样。旧实现没有这一段 ⇒ 红。
    """
    sender = _FakeSender()
    monkeypatch.setattr(LP, 'plan', lambda a: (sender, 2))
    monkeypatch.setattr(LP, 'bind_listener', lambda port: _BoomSock())
    monkeypatch.setattr(LP, 'measure_d1',
                        lambda *a, **k: {'samples_ms': [], 'n': 0, 'timeouts': 1,
                                         'p50_ms': None, 'p95_ms': None,
                                         'frames_sent': 1, 'next_seq': 1,
                                         'wait_s': 2.0})
    monkeypatch.setattr(LP, 'measure_d2',
                        lambda *a, **k: {'samples_ms': [], 'n': 0, 'timeouts': 1,
                                         'p50_ms': None, 'p95_ms': None,
                                         'frames_sent': 1, 'next_seq': 2,
                                         'threshold_mps': 0.05, 'step_mps': 0.14})
    assert LP.main(['--to', '192.168.127.10:9000', '--warmup', '0']) == 0
    out = capsys.readouterr().out
    assert 'caution: D1 will be SILENT' in out
    assert 'vehicle/bridge.py:24/30/206' in out and 'power-cycle' in out
    assert 'Fw-14' in out and '!clear' in out
    # D2 那一半也说清楚：持停是"发着等"，而 STATUS 断流这个口子本轮没修
    assert 'does NOT sleep through its' in out and 'M-3' in out
    assert out.isascii(), 'the whole console output must stay cp936-safe'


def test_report_shows_why_a_run_produced_no_sample():
    """n=0 那一行必须带上"为什么"：被 re-arm 门拒掉的轮次与链路不通不是一件事。"""
    d1 = {'samples_ms': [100.0], 'n': 1, 'timeouts': 0, 'p50_ms': 100.0,
          'p95_ms': 100.0, 'frames_sent': 1}
    # 键按 `measure_d2()` 的真实输出形状给（它每一跑都带 settle_s/keepalive_s/
    # rounds_step_commanded）：报告里那几句节奏话现在**读这些实参**，不读默认值（NEW-2），
    # 手写 dict 少了它们就只能得到"不作任何声明"那一句。
    d2 = {'samples_ms': [], 'n': 0, 'timeouts': 2, 'p50_ms': None, 'p95_ms': None,
          'frames_sent': 14, 'threshold_mps': 0.05, 'step_mps': 0.14,
          'not_rearmed': 1, 'pre_arm_above_frames': 19, 'keepalive_sends': 11,
          'rounds_step_commanded': 0, 'settle_s': 1.0, 'keepalive_s': 0.2}
    text = LP.report(d1, d2)
    assert 'rounds_never_rearmed=1' in text
    assert 'above_threshold_before_standing_still=19' in text
    assert 'keepalive_re_sends=11' in text
    assert 'rounds_step_commanded' not in text      # 0 不印（不印 =0 凑数）
    # 报告自己要把"两轮段"的口径说清：读者不看源码也知道 t=0 是**挣到资格之后**那条阶跃
    assert 'THEN command the step' in text and 'residual speed' in text
    read = '\n'.join(LP.cross_read(d1, d2, _Rx(good=300)))
    assert 're-arm' in read
    # **不许**在这样的轮次上说"执行面停了（Fw-21）"：D2 一条样本都没产是因为它自己
    # 就没挣到发阶跃的资格，与板子的主循环无关——这条归属守卫是审查清单第 2 条的形状。
    assert 'Fw-21' not in read
    assert text.isascii()


def test_report_pacing_lines_follow_the_actual_settle_and_keepalive():
    """节奏那几句跟着**实参**走，不跟着默认值走（NEW-2）。

    `--settle 0` 的跑法没有持停段，`--keepalive 0` 更是关掉续发；旧实现把默认参数的
    行为印成无条件事实（"re-sent often enough that the bridge never sees 0.5 s of PC
    silence"），现场读到的是关于**没发生过的事**的陈述，而它正好掩盖了"这一跑会静默到
    锁存"。⇒ 旧实现下这条在几处同时红。
    """
    d1 = {'samples_ms': [100.0], 'n': 1, 'timeouts': 0, 'p50_ms': 100.0,
          'p95_ms': 100.0, 'frames_sent': 1}

    def d2(**kw):
        out = {'samples_ms': [], 'n': 0, 'timeouts': 0, 'p50_ms': None,
               'p95_ms': None, 'frames_sent': 4, 'threshold_mps': 0.05,
               'step_mps': 0.14}
        out.update(kw)
        return out

    # 1) 非默认的实参必须被印出来（这就是"跟着默认值走"的反证）
    t1 = LP.report(d1, d2(settle_s=0.35, keepalive_s=0.1))
    assert '0.35 s' in t1 and 'every 0.10 s' in t1
    assert 're-sent often enough' not in t1
    # 2) --settle 0：没有持停段，不许说"holds NAV(0,0) ... until ..."
    t2 = LP.report(d1, d2(settle_s=0.0, keepalive_s=0.2))
    assert 'NO hold phase' in t2 and 're-sent often enough' not in t2
    assert 'holds NAV(0,0) for up to' not in t2
    # 3) --keepalive 0：句子必须是"会静默到锁存"，不是"re-sent often enough"
    t3 = LP.report(d1, d2(settle_s=1.0, keepalive_s=0.0))
    assert 'RE-SENDS NOTHING' in t3 and '1.00 s window' in t3
    assert 'power cycle clears (Fw-14)' in t3
    assert 're-sent often enough' not in t3 and 'holds NAV(0,0) for up to' not in t3
    # 4) 两个都关掉
    t4 = LP.report(d1, d2(settle_s=0.0, keepalive_s=0.0))
    assert 'RE-SENDS NOTHING' in t4 and 'no hold phase' in t4
    # 5) 被忽略的余速为 0 时，不许把读者指向一行**不存在**的东西（_count_bits 不印 0）
    assert 'above_threshold_before_standing_still=' not in t3
    assert 'is not printed above' in t3
    t5 = LP.report(d1, d2(settle_s=1.0, keepalive_s=0.2, pre_arm_above_frames=6))
    assert 'above_threshold_before_standing_still=6' in t5
    # 6) D2 被跳过 / 结果里没有这两个键 ⇒ 关于本跑节奏一个字都不说
    t6 = LP.report(d1, d2(skipped=True, settle_s=1.0, keepalive_s=0.2))
    assert 'never ran in this session' in t6 and 're-sent' not in t6
    t7 = LP.report(d1, d2())
    assert 'carries no settle_s/keepalive_s' in t7
    assert 're-sent often enough' not in t7
    for text in (t1, t2, t3, t4, t5, t6, t7):
        assert text.isascii()





# ------------------------------------ 口径：不许说"台账上已经有这一条"（NEW-3，静态断言）

# 这些词**用码点拼**，不写成字面量：本测试要扫的面里就包括 `tests/test_latency_probe.py`
# 自己，把被禁的写法原样写在源码里，等于让这条检查永远命中自己（或者逼自己把它删掉）。
#   U+5DF2 yi3 = "already"（注意不是 U+5DF1 ji3）；U+53F0 U+8D26 = "the ledger"。
_YI = chr(0x5DF2)
_LEDGER = chr(0x53F0) + chr(0x8D26)
_LEDGER_CLAIMS = (
    [_YI + v + _LEDGER for v in (chr(0x8BB0),                          # ji4  "logged"
                                 chr(0x767B) + chr(0x8BB0),             # dengji
                                 chr(0x8BB0) + chr(0x5165),             # jiru
                                 chr(0x5199) + chr(0x5165),             # xieru
                                 chr(0x8FDB),                           # jin4
                                 chr(0x5F55))]                           # lu4
    + [_LEDGER + _YI + v for v in (chr(0x767B) + chr(0x8BB0),
                                   chr(0x66F4) + chr(0x65B0),
                                   chr(0x8BB0))]
    + [_YI + chr(0x767B) + chr(0x8BB0)])          # bare "already registered"


def _ledger_claims_in(text):
    """返回文本里出现的"已经落盘到台账"类声明（命中列表为空才算干净）。"""
    return [c for c in _LEDGER_CLAIMS if c in text]


def test_the_probe_never_claims_a_ledger_entry_that_was_never_written():
    """源码/报告里不许写"这条已经进台账了"——除非台账里真有（NEW-3，AGENTS 第 1/第 5 条）。

    被审那一版在 `measure_d2()` 文档串里把 M-3 说成"台账上有这一条"，而 `docs/` 全目录 grep
    `M-3` **零命中**：那句话结构性为假，属"把没做的写成做了"。台账本轮不许动，所以
    唯一正确的改法是改口（"见 task-9 报告 F9，台账待登记"）。这条把它做成静态断言。

    非空性自检放在最后：**零命中要先怀疑自己写错了**，所以用同一批码点拼一个样本喂回去，
    断言扫描器确实抓得住——不然"扫了个空"会被读成"扫过了、很干净"。
    """
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    paths = [os.path.join(root, 'tools', 'latency_probe.py'),
             os.path.join(root, 'tests', 'test_latency_probe.py')]
    report = os.path.join(root, '.superpowers', 'sdd',
                          '2026-10-08-e3-batch-1b-pc-tools', 'task-9-report.md')
    if os.path.exists(report):
        paths.append(report)
    scanned = 0
    for path in paths:
        text = io.open(path, encoding='utf-8').read()
        assert len(text) > 500, 'empty read of %s is not a clean scan' % path
        hits = _ledger_claims_in(text)
        assert not hits, ('%s claims a ledger entry (%s) that has no landed '
                          'counterpart: say where it is recorded, or say "pending"'
                          % (os.path.basename(path),
                             ', '.join(h.encode('ascii', 'replace').decode()
                                       for h in hits)))
        scanned += 1
    assert scanned >= 2, scanned
    # 反向自检：扫描器不是空转——被禁的写法它必须抓到（每种构形各验一次）
    sample = (u'%s%s' % (_YI + chr(0x8BB0), _LEDGER),
              u'%s%s%s' % (_YI, chr(0x767B) + chr(0x8BB0), _LEDGER),
              u'%s%s%s' % (_LEDGER, _YI, chr(0x8BB0)))
    for s in sample:
        assert _ledger_claims_in(s), s.encode('unicode-escape').decode()
    assert _ledger_claims_in(u'nothing suspicious here') == []
