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

不需要硬件也不需要网口：收发都是假函数（`send_fn` 记账、`recv_iter` 按脚本给
`(t, status_dict)`）。`t` 是**距本次请求发出的相对秒数**，这个契约由
`StatusStream.recv_iter` 实现，并由 `test_stream_*` 几条钉住。
"""
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
    """共享谓词的比较对 NaN 恒假（NaN > x 永远不成立）——那道闸拦不住 NaN。

    所以本模块自己拒非有限值：NaN 一旦放过，`pack_nav` 把它写进线上，
    `speed >= threshold` 恒假，测出来是"超时 N 次"，看着像链路问题、其实是入参问题。
    这里只在自己家门口补闸，**不改共享模块**（那是最终审查后的收口项）。
    """
    for bad in (float('nan'), float('inf'), float('-inf')):
        with pytest.raises(ValueError):
            LP.measure_d2(lambda f: None, _no_frames, step_v=bad, repeats=1)
        with pytest.raises(ValueError):
            LP.measure_d2(lambda f: None, _no_frames, threshold=bad, repeats=1)
    assert not BL.nav_exceeds_bench_limit(float('nan'), float('nan'))   # 前提


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
    """线上来的 speed 是 NaN/None 时不进样本、进计数：这种帧证明不了任何东西。"""
    events = [(0.05, float('nan')), (0.10, None), (0.20, 0.06)]

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
                             'p95_ms': None, 'skipped': True}, _Rx(good=60)))]
    for exc in (lambda: LP.measure_d2(lambda f: None, _no_frames, threshold=0.01),
                lambda: LP.measure_d2(lambda f: None, _no_frames,
                                      step_v=float('nan')),
                lambda: LP.measure_d1(lambda f: None, _no_frames, profile_id=300)):
        with pytest.raises(ValueError) as info:
            exc()
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
