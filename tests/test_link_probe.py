# -*- coding: utf-8 -*-
"""tools/link_probe.py 的测试（`--serial` 那条路与判据，全都不需要硬件）。

钉的是三件事：
1. `_read_status` 能**跨读边界**把帧拼出来并认出 mode 变化（现场用的是 USB-TTL，
   一次 read 给半帧是常态）；
2. 它记的是"模式跳变序列"，不是"最后一帧"——B2 那些场景要的正是跳变的时刻与顺序；
3. Task 7 起，它还必须把**"发送前基线"与"发送后变化"**分开记（`pre_send` / `seen`），
   并把 v2 帧的 `reject` 与帧形态版本收下来——`judge()` 的两个反例全靠这条时间线。
"""
import threading
import time

import pytest

from common import protocol as P
from pc import wire
from tools import link_probe as lp


class _FakeSer:
    """按脚本给字节，喂完就返回空（模拟"对端暂时没发东西"）。"""

    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.i = 0

    def read(self, n):
        if self.i >= len(self.chunks):
            time.sleep(0.01)
            return b''
        c = self.chunks[self.i]
        self.i += 1
        return c


class _GatedSer(_FakeSer):
    """读到第 gap 块之前把 started 置位——把"第一条帧写出去"的时刻钉死。

    `_read_status` 要分得清发送前/发送后，测试就得能控制这条时间线，
    不能靠 sleep 的时长赌它落在哪两帧之间。
    """

    def __init__(self, chunks, started, gap):
        _FakeSer.__init__(self, chunks)
        self.started = started
        self.gap = gap

    def read(self, n):
        if self.i == self.gap:
            self.started.set()
        return _FakeSer.read(self, n)


def _status(seq, mode):
    return P.pack_frame(P.TYPE_STATUS, P.pack_status(0.0, 0.0, 48.0, 0, mode), seq)


def _status_v2(seq, mode, reject=0, profile=2, authority=0, loop_alive=1):
    """STATUS v2（19 B，E3 之后板子上发的形态）：带 profile/authority/loop_alive/reject。"""
    return P.pack_frame(
        P.TYPE_STATUS,
        P.pack_status_v2(0.0, 0.0, 48.0, 0, mode, profile, authority,
                         loop_alive, 0x5A, reject), seq)


def _run(chunks, wait=0.35, started=None):
    """chunks 可以是字节列表（自己包 _FakeSer），也可以是一个串口替身对象。"""
    ser = _FakeSer(chunks) if isinstance(chunks, list) else chunks
    out = {'good': 0, 'changes': [], 't0': time.time()}
    stop = threading.Event()
    th = threading.Thread(target=lp._read_status, args=(ser, stop, out, started),
                          daemon=True)
    th.start()
    time.sleep(wait)
    stop.set()
    th.join(timeout=2.0)
    return out


def test_read_status_sees_the_mode_sequence():
    out = _run([_status(1, 0), _status(2, 1), _status(3, 1), _status(4, 2)])
    assert out['good'] == 4
    assert [c[2] for c in out['changes']] == [0, 1, 2]      # MANUAL -> AUTO -> ESTOP
    assert out['changes'][0][1] is None                     # 第一条没有"上一个状态"
    assert out['changes'][1][1] == 0


def test_read_status_survives_a_frame_split_across_reads():
    """USB-TTL 一次 read 给半帧是常态：拼不上就不许算一帧，拼上了必须算。"""
    whole = _status(7, 1)
    out = _run([whole[:9], whole[9:]])
    assert out['good'] == 1
    assert [c[2] for c in out['changes']] == [1]


def test_stale_seq_is_not_counted_as_a_frame():
    """序号回退的帧（MCU 重启的旁证）不许当成新帧计进 good——判据与生产同一套。"""
    out = _run([_status(50, 0), _status(1, 0), _status(2, 0)])
    assert out['good'] == 1


# ---- Task 7：judge()——按命令定义预期响应（spec §9 / A17）----------------
# 外部评审给的两个真实反例，旧实现都会说错话：
#   发 ESTOP 看到 MANUAL->ESTOP（正确响应）被打印成"一直在 MANUAL，检查接线"；
#   第一帧本来就是 AUTO 被打印成"收得进，问题在 X5 一侧"。
# 旧实现里根本没有 judge()，所以下面每一条在动手前都是红的（AttributeError）。


def test_judge_uses_baseline_not_ever_seen():
    """评审反例一：发送前就已经是 AUTO，不能算这次发送的功劳。"""
    v, _ = lp.judge('mode_auto', baseline_mode=1, seen_modes=[1], reject_codes=[])
    assert v == 'INCONCLUSIVE'


def test_judge_pass_on_real_transition():
    v, _ = lp.judge('mode_auto', baseline_mode=0, seen_modes=[0, 1], reject_codes=[])
    assert v == 'PASS'


def test_judge_estop_transition_is_pass_not_wiring_error():
    """评审反例二：发 estop 看到 MANUAL->ESTOP 过去被报成"一直在 MANUAL，检查接线"。"""
    v, _ = lp.judge('estop', baseline_mode=0, seen_modes=[0, 2], reject_codes=[])
    assert v == 'PASS'


def test_judge_reject_code_is_reported_as_rejected_not_failed():
    """E3：申请被拒是**正常响应**，要说清是哪一条，不是"链路不通"。"""
    v, detail = lp.judge('mode_auto', baseline_mode=0, seen_modes=[0],
                         reject_codes=[3])
    assert v == 'FAIL'
    assert '现场拨档' in detail


def test_judge_inconclusive_when_no_frame_at_all():
    v, _ = lp.judge('mode_auto', baseline_mode=None, seen_modes=[], reject_codes=[])
    assert v == 'INCONCLUSIVE'


def test_judge_nav_no_longer_expects_mode_change():
    """A2 之后 NAV 不改 mode：nav 命令的判据是"收到 STATUS 且 mode 未变"。"""
    v, _ = lp.judge('nav', baseline_mode=0, seen_modes=[0], reject_codes=[])
    assert v == 'PASS'
    v2, _ = lp.judge('nav', baseline_mode=0, seen_modes=[0, 1], reject_codes=[])
    assert v2 == 'FAIL'


# ---- 上面那六条之外的、同样会当场说错话的情形（都做过"旧实现必红"反查）----


def test_judge_reject_zero_is_not_reported_as_a_rejection():
    """reject=0 是"无拒绝"。把它当拒绝码 = 给一次正常的没响应编一个不存在的原因。"""
    v, detail = lp.judge('mode_auto', baseline_mode=0, seen_modes=[0], reject_codes=[0])
    assert v == 'FAIL'
    assert '拒绝' not in detail


def test_judge_clear_rejected_while_latched_names_the_reason():
    """clear 被"急停仍锁存"拒掉：链路是通的，要说的是这一条，不是查接线。"""
    v, detail = lp.judge('clear', baseline_mode=2, seen_modes=[2], reject_codes=[4])
    assert v == 'FAIL'
    assert '急停仍锁存' in detail


def test_judge_never_claims_a_frame_when_none_arrived():
    """发送后一帧都没收到时，不许报 PASS 并写"收到 STATUS"——那是假话。"""
    v, _ = lp.judge('tool', baseline_mode=0, seen_modes=[], reject_codes=[])
    assert v == 'INCONCLUSIVE'


def test_judge_unknown_kind_is_not_a_silent_pass():
    """判据表里没有的命令：不给结论，免得一个拼错的名字印出一个 PASS。"""
    v, _ = lp.judge('no_such_command', baseline_mode=0, seen_modes=[0], reject_codes=[])
    assert v == 'INCONCLUSIVE'


def test_judge_nav_reject_is_told_but_is_not_a_link_failure():
    """nav 期间看到 reject：链路是通的（否则收不到 STATUS），但原因必须说出来。"""
    v, detail = lp.judge('nav', baseline_mode=0, seen_modes=[0], reject_codes=[7])
    assert v == 'PASS'
    assert '夺权' in detail


def test_judge_tool_and_beat_are_not_judged_by_mode_change():
    """tool/beat 的判据不是 mode 变化：心跳把 AUTO 放回 MANUAL 本来就是预期（:73）。"""
    assert lp.judge('tool', baseline_mode=0, seen_modes=[0, 2],
                    reject_codes=[])[0] == 'PASS'
    assert lp.judge('beat', baseline_mode=1, seen_modes=[0],
                    reject_codes=[])[0] == 'PASS'


# ---- 审查遗留四条（口径与契约收口；每条都做过"旧写法下必红"反查）----


@pytest.mark.parametrize('kind, reject_codes', [
    ('tool', []), ('beat', []), ('tool', [3]), ('beat', [7]),
])
def test_judge_tool_and_beat_pass_text_claims_only_what_was_checked(kind, reject_codes):
    """Important：tool/beat 根本没检查 mode 变化，PASS 文案就不许写"没有意外的权限变化"。

    verdict=PASS 本身是 brief 契约（EXPECTED 里 tool/beat = None），错的是那句**越过证据**
    的话（AGENTS 清单第 5 条：不得声称没检验的事）。reject 后缀是观察到的码，可以提，
    但只能说"板子对某条请求的答复"，不许被读成"本次检查过权限、没查出问题"。
    """
    v, detail = lp.judge(kind, baseline_mode=0, seen_modes=[0, 2],
                         reject_codes=reject_codes)
    assert v == 'PASS'
    assert '权限' not in detail
    assert '收到 STATUS' in detail


@pytest.mark.parametrize('kind, want', [
    ('mode_auto', 1), ('mode_manual', 0), ('estop', 2), ('clear', 0),
])
def test_judge_never_credits_a_transition_without_a_baseline(kind, want):
    """Minor-1：没有发送前基线时，"看到了期望态"不能算 PASS——初始态说明不了因果。

    从 `_run_serial` 当前走不到这里（暖机期内它会先打一行警告），这条收的是 `judge()`
    作为公开纯函数的契约：调用方漏传基线时不许印出一个 PASS。
    """
    v, detail = lp.judge(kind, baseline_mode=None, seen_modes=[want], reject_codes=[])
    assert v == 'INCONCLUSIVE'
    assert '基线' in detail


@pytest.mark.parametrize('seen_modes', [[0], [0, 1]])
def test_judge_nav_without_baseline_is_inconclusive(seen_modes):
    """Minor-3：nav 的"mode 有没有变"必须有基线才能判——没基线给 INCONCLUSIVE。

    旧写法把 `m != None` 恒真当成"变了"，印出一个 FAIL，把"没采到基线"说成"固件有问题"。
    """
    v, detail = lp.judge('nav', baseline_mode=None, seen_modes=seen_modes,
                         reject_codes=[])
    assert v == 'INCONCLUSIVE'
    assert '基线' in detail


def test_judge_nav_fail_names_a_human_at_the_tx_as_a_cause():
    """Minor-2：台架最常见的跳变是有人在旁边动遥控器/按急停，那是合法跳变不是故障。"""
    v, detail = lp.judge('nav', baseline_mode=0, seen_modes=[0, 2], reject_codes=[])
    assert v == 'FAIL'
    assert '遥控器' in detail
    assert '旧固件' in detail      # 归因列全，但旧固件那条不许被换掉


def test_mode_name_and_expected_tables_match_the_e3_contract():
    """两张表是 brief 定下的契约：MODE 含 TELEOP，nav 的预期不再是 mode=1。

    10-12（T1）把 `mode_profile` / `mode_teleop` 也写进这张表——**两条都是 None**：
    它们都不走这张通用转移表（握手的产物是 handshake_ok 那一位，不在 STATUS 里；
    TELEOP 有两种成功形状，一张表装不下，判据在 `_judge_new_mode` 里自己写）。
    10-13 手操档落地后这条等式**仍然成立**，因为留 None 的含义是"别落到通用分支"，
    不是"TELEOP 不会改 mode"——后者恰好现在会（成功时 mode 跳 3）。
    """
    assert lp.MODE_NAME == {0: 'MANUAL', 1: 'AUTO', 2: 'ESTOP', 3: 'TELEOP'}
    assert lp.EXPECTED == {'nav': None, 'mode_auto': 1, 'mode_manual': 0,
                           'estop': 2, 'clear': 0, 'tool': None, 'beat': None,
                           'mode_profile': None, 'mode_teleop': None}


# ---- 采集侧：发送前基线 / 发送后变化 / reject / 帧形态版本 ----


def test_read_status_separates_baseline_from_post_send():
    """started 之前读到的态进 pre_send，之后的才进 seen——judge 全靠这条时间线。"""
    started = threading.Event()
    ser = _GatedSer([_status(1, 0), _status(2, 2), _status(3, 2)], started, gap=1)
    out = _run(ser, started=started)
    assert out['baseline'] == 0                 # 第一帧：还没开始发
    assert out['pre_send'] == 0                 # 发送开始那一刻的态
    assert out['seen'] == [2]                   # 连续同态只记一次，别把细节糊成一串
    assert [c[2] for c in out['changes']] == [0, 2]


def test_read_status_counts_pre_started_frames_as_post_when_no_gate():
    """不传 started（老调用方式）：没有"发送"这回事，所有帧都算观察到的。"""
    out = _run([_status(1, 0)])
    assert out['seen'] == [0]
    assert 'pre_send' not in out


def test_read_status_collects_nonzero_reject_and_records_frame_version():
    out = _run([_status_v2(1, 0, reject=0), _status_v2(2, 0, reject=3),
                _status_v2(3, 0, reject=4)])
    assert out['rejects'] == [3, 4]      # reject=0 不进账：它是"没有拒绝"
    assert out['versions'] == {2}


def test_read_status_marks_v1_frames_as_pre_e3_firmware():
    """v1（14 B）帧没有 reject 字段：不猜一个 0，也不留 None 进账。"""
    out = _run([_status(9, 0)])
    assert out['versions'] == {1}
    assert out.get('rejects', []) == []


# ---- build()：三条 MODE 命令是新的探针，帧型/请求码/档案号都得对上 ----


@pytest.mark.parametrize('kind, want', [
    ('mode_auto', P.MODE_REQ_AUTO),
    ('mode_manual', P.MODE_REQ_MANUAL),
    ('clear', P.MODE_REQ_CLEAR_ESTOP),
    ('mode_profile', P.MODE_REQ_PROFILE),
    ('mode_teleop', P.MODE_REQ_TELEOP),
])
def test_build_mode_frames_carry_the_request_and_profile(kind, want):
    frame = lp.build(kind, [], 7, profile=2)
    ftype, seq, payload = P.unpack_frame(frame)
    assert (ftype, seq) == (P.TYPE_MODE, 7)
    assert P.unpack_mode(payload) == (want, 2)


def test_build_mode_frame_defaults_to_profile_none():
    """档案读不到时探针仍要发得出去，但 profile 必须是 0（固件按 0x01 拒）。

    不许悄悄顶一个"看起来合法"的档案号——那会把"用错档案号申请无人"那条场景测成"档案握手一致"。
    """
    _ftype, _seq, payload = P.unpack_frame(lp.build('mode_auto', [], 0))
    assert P.unpack_mode(payload) == (P.MODE_REQ_AUTO, P.PROFILE_NONE)


@pytest.mark.parametrize('bad', ['no_such_kind', '', 'navv'])
def test_build_rejects_unknown_kind(bad):
    with pytest.raises(ValueError):
        lp.build(bad, [], 0)


def test_build_still_makes_nav_tool_beat_estop_frames():
    """旧四条一条不许被这次改动带偏：帧型与载荷逐条钉住。"""
    ftype, seq, payload = P.unpack_frame(lp.build('nav', ['0.05', '-0.02'], 3))
    assert (ftype, seq) == (P.TYPE_NAV, 3)
    vl, vr, flags = P.unpack_nav(payload)      # f32 存不下 0.05，按近似值钉
    assert (vl, vr, flags) == (pytest.approx(0.05, abs=1e-6),
                               pytest.approx(-0.02, abs=1e-6), 0)

    ftype, _seq, payload = P.unpack_frame(lp.build('tool', ['12.5', '7'], 4))
    assert ftype == P.TYPE_TOOL
    assert P.unpack_tool(payload) == (pytest.approx(12.5, abs=1e-6), 7)

    assert P.unpack_frame(lp.build('beat', [], 5))[0] == P.TYPE_HEARTBEAT
    assert P.unpack_frame(lp.build('estop', [], 6))[0] == P.TYPE_ESTOP


# ---- 打印层面：评审那两个反例的**原始症状就是这句话**，所以整条时间线要跑一遍 ----
# 写一帧 -> 假板子换态 -> 读线程读出跳变 -> judge() 出结论 -> 打印。
# 只测 judge() 的返回值不够：现场读的是那行"判定："。


class _FakeBoard:
    """一块约 50 Hz 回 STATUS 的假板子，收到帧就按**指定那一代固件**的语义换态。"""

    def __init__(self, mode=0, status_v=2, refuse_auto=None, nav_forces_auto=False):
        self.mode = mode
        self.status_v = status_v
        self.refuse_auto = refuse_auto      # 非 None = 申请被拒，STATUS 挂这个码
        self.nav_forces_auto = nav_forces_auto   # True = E3 之前那块板（F1 洞）
        self.reject = 0
        self.seq = 0
        self._next = 0.0
        self.written = []

    def write(self, data):
        self.written.append(data)
        ftype, _seq, payload = P.unpack_frame(data)
        if ftype == P.TYPE_ESTOP:
            self.mode = 2
        elif ftype == P.TYPE_NAV and self.nav_forces_auto:
            self.mode = 1
        elif ftype == P.TYPE_MODE:
            if P.unpack_mode(payload)[0] == P.MODE_REQ_AUTO:
                if self.refuse_auto is None:
                    self.mode = 1
                else:
                    self.reject = self.refuse_auto

    def read(self, n):
        now = time.time()
        if now < self._next:
            time.sleep(0.002)
            return b''
        self._next = now + 0.01
        self.seq += 1
        if self.status_v == 1:
            payload = P.pack_status(0.0, 0.0, 48.0, 0, self.mode)
        else:
            payload = P.pack_status_v2(0.0, 0.0, 48.0, 0, self.mode, 2, 0, 1,
                                       0x5A, self.reject)
        return P.pack_frame(P.TYPE_STATUS, payload, self.seq)

    def close(self):
        pass


def _run_probe(board, kind, frames, monkeypatch, watch=0.3):
    """把 `_run_serial` 里的 `import serial` 顶掉，整条跑一遍，返回打印。"""
    import sys
    import types
    monkeypatch.setitem(sys.modules, 'serial',
                        types.SimpleNamespace(Serial=lambda *a, **k: board))
    args = types.SimpleNamespace(serial='COM_FAKE', baud=115200, watch=watch, kind=kind)
    lp._run_serial(args, iter(frames))


def test_probe_prints_no_wiring_blame_for_an_estop_transition(capsys, monkeypatch):
    """评审反例二：发 ESTOP 看到 MANUAL->ESTOP 是正确响应，那句"检查接线"不许再出现。"""
    board = _FakeBoard(mode=0)
    _run_probe(board, 'estop', [lp.build('estop', [], 0)], monkeypatch)
    text = capsys.readouterr().out
    assert board.written, '帧没写进串口，这条就没测到发送方向'
    assert '判定：PASS' in text
    assert '接线' not in text


def test_probe_does_not_credit_a_request_when_board_already_auto(capsys, monkeypatch):
    """评审反例一：第一帧本来就是 AUTO，打印必须是 INCONCLUSIVE，不是"收得进"。"""
    board = _FakeBoard(mode=1)
    _run_probe(board, 'mode_auto', [lp.build('mode_auto', [], 0, profile=2)], monkeypatch)
    text = capsys.readouterr().out
    assert '判定：INCONCLUSIVE' in text
    assert '发送前就已经是 AUTO' in text
    assert '判定：PASS' not in text


def test_probe_judges_nav_by_mode_staying_put(capsys, monkeypatch):
    """A2 的落点：nav 期间 mode 一动不动就是 PASS；旧判据在这里报"未观察到预期转移"。"""
    board = _FakeBoard(mode=0)
    _run_probe(board, 'nav', [lp.build('nav', ['0.05', '0.05'], 0)], monkeypatch)
    text = capsys.readouterr().out
    assert '判定：PASS' in text
    assert '未观察到预期转移' not in text


def test_probe_fails_nav_when_the_board_still_treats_nav_as_auto(capsys, monkeypatch):
    """现在烧在板上的就是那块旧板：nav 把 mode 推进 AUTO -> FAIL，读作"还是旧固件"。"""
    board = _FakeBoard(mode=0, nav_forces_auto=True)
    _run_probe(board, 'nav', [lp.build('nav', ['0.05', '0.05'], 0)], monkeypatch)
    text = capsys.readouterr().out
    assert '判定：FAIL' in text
    assert '旧固件' in text
    # Minor-2：打印层面也要看得见"人在旁边动过"这一种可能，否则 FAIL 会被读成固件故障。
    assert '遥控器' in text


def test_probe_names_the_reject_reason_instead_of_the_link(capsys, monkeypatch):
    """现场拨档不在允许位：要说清是哪一条，不能写成"链路不通/一帧都没收到"。"""
    board = _FakeBoard(mode=0, refuse_auto=P.REJECT_FIELD_SWITCH)
    _run_probe(board, 'mode_auto', [lp.build('mode_auto', [], 0, profile=2)], monkeypatch)
    text = capsys.readouterr().out
    assert '判定：FAIL' in text
    assert '现场拨档' in text
    assert '一帧 STATUS 都没' not in text


def test_probe_gives_up_on_mode_frames_when_board_is_pre_e3(capsys, monkeypatch):
    """v1（14 B）板子没有 reject 字段、也不认 MODE 帧 -> 只给 INCONCLUSIVE，不给结论。"""
    board = _FakeBoard(mode=0, status_v=1)
    _run_probe(board, 'mode_auto', [lp.build('mode_auto', [], 0, profile=2)], monkeypatch)
    text = capsys.readouterr().out
    assert '判定：INCONCLUSIVE' in text
    assert 'v1' in text


# ---------------- CLI（main()）那一层：参数校验与两道闸，全都不需要硬件 ----------------

def _cli(monkeypatch, argv, permit=None):
    """把 `main()` 整条跑一遍（假 socket，不发 UDP），返回 (发出去的帧, SystemExit 或 None)。

    这一层以前没有测试：`nav_exceeds_bench_limit(*a.args)` 拿的是**命令行字面串**，
    而 `link_probe nav nan 0` 正是走这条路把 NaN 送进 `pack_nav` 的（最终审查 C-1）。
    只测函数不测 CLI，就等于没测那个原始症状。
    """
    import sys
    sent = []

    class _Sock:
        def sendto(self, frame, addr):
            sent.append((frame, addr))
            return len(frame)

        def close(self):
            pass

    monkeypatch.setattr(lp.socket, 'socket', lambda *a, **k: _Sock())
    if permit is not None:
        monkeypatch.setattr(lp, 'load_permit', lambda path=None: permit)
    monkeypatch.setattr(sys, 'argv', ['link_probe.py'] + argv)
    try:
        lp.main()
    except SystemExit as exc:
        return sent, exc
    return sent, None


def test_cli_refuses_a_nav_speed_that_is_not_finite(monkeypatch):
    """C-1：`nav nan 0` 必须 rc≠0 且**一条帧都不发**。

    改之前 `nav_exceeds_bench_limit('nan', '0')` 那类写法（`float('nan') > 0.20` 恒假）
    会把 NaN 放行到 `pack_nav`，而现固件对一条 NAV 是无条件进 AUTO。
    """
    for bad in ('nan', 'inf'):
        sent, exc = _cli(monkeypatch, ['nav', bad, '0'])
        assert exc is not None and _rc(exc) != 0, bad
        assert sent == [], bad
        assert '有限' in _msg(exc), _msg(exc)
    # `-inf` 到不了这道闸：argparse 先把以 `-` 开头的它当选项拒了（rc=2、一帧不发）。
    # 记在这里是因为读代码的人会问"负无穷呢"——答案是**同样发不出去**，只是换一个出口。
    sent, exc = _cli(monkeypatch, ['nav', '-inf', '0'])
    assert exc is not None and _rc(exc) != 0 and sent == []


def test_cli_refuses_a_nav_above_the_bench_limit(monkeypatch):
    """超限那条同样 rc≠0、不发帧——这是 I-1 那条闸第一次有 CLI 层的证据。"""
    sent, exc = _cli(monkeypatch, ['nav', '0.21', '0'])
    assert exc is not None and _rc(exc) != 0
    assert sent == []
    assert '限速' in _msg(exc)
    # 不是数的参数照实说"不是数"，不让人读到一句假的"超出限速"
    sent, exc = _cli(monkeypatch, ['nav', 'abc', '0'])
    assert exc is not None and _rc(exc) != 0 and sent == []
    assert '不是数' in _msg(exc)


def _rc(exc):
    """`sys.exit(一条中文理由)` 在 Python 里就是 `SystemExit.code = 那条字符串`，
    解释器据此以**非零**码退出。所以"rc≠0"= code 既不是 0 也不是 None。"""
    return 0 if exc.code in (0, None) else 1


def _msg(exc):
    """退出时打给用户看的那句话（`sys.exit(str)` 的参数就是它）。"""
    return exc.code if isinstance(exc.code, str) else str(exc.code)


def test_cli_still_sends_a_legal_nav_speed(monkeypatch):
    """闸收紧之后，正常那条路**必须照走**：`nav 0.05 0.05` 发一帧、不退出。

    这条是给上一个测试当反向控制的——把共享谓词改成"只认数字"之后，如果 CLI 层
    忘了先转 float，这里就会红，而不是安静地拒掉所有 NAV。
    """
    sent, exc = _cli(monkeypatch, ['nav', '0.05', '0.05'])
    assert exc is None, str(exc)
    assert len(sent) == 1
    t, _seq, payload = P.unpack_frame(sent[0][0])
    assert t == P.TYPE_NAV
    assert P.unpack_nav(payload)[:2] == pytest.approx((0.05, 0.05), abs=1e-6)


def test_cli_tool_gate_follows_the_permit(monkeypatch):
    """审查第 7 条（"工具无视 permit"）：门 N 只许 `tool 0 7`，门 F 全放行。"""
    sent, exc = _cli(monkeypatch, ['tool', '0', '7'], permit=wire.GATE_N)
    assert exc is None, str(exc)
    assert len(sent) == 1, '门 N 下这条与闭环会发的完全一样，该放行'

    sent, exc = _cli(monkeypatch, ['tool', '0', '0'], permit=wire.GATE_N)
    assert exc is not None and _rc(exc) != 0
    assert sent == [], '被拒就不许有一个字节上线'
    assert '门 N' in _msg(exc)

    sent, exc = _cli(monkeypatch, ['tool', '5', '1'], permit=wire.GATE_F)
    assert exc is None, str(exc)
    assert len(sent) == 1, '门 F 就是允许落刀与横移，这条不该拒'


def test_cli_tool_gate_fails_closed_when_the_profile_is_unavailable(monkeypatch):
    """档案读不到 ⇒ permit 取不到 ⇒ TOOL 一律拒，**不降级成门 F**（C-1 fail-closed）。"""
    def _boom(path=None):
        raise ValueError('车辆档案不存在')

    monkeypatch.setattr(lp, 'load_permit', _boom)
    sent, exc = _cli(monkeypatch, ['tool', '0', '0'])
    assert exc is not None and _rc(exc) != 0, '取不到许可位不许当作"允许落刀"'
    assert sent == []
    assert '读不到' in _msg(exc)


# ---- T1（2026-10-12）：档案握手与 TELEOP 的入口 ----


def test_new_mode_kinds_belong_to_the_v1_inconclusive_gate():
    """两条新命令**必须**挂在 MODE_REQUEST_KINDS 上，而不是另开一条通道。

    这条归属决定的是"未烧批 1a 的板上会不会出现假 PASS"：`_run_serial()` 用
    `kind in MODE_REQUEST_KINDS and versions == {1}` 把结论压成 INCONCLUSIVE，
    因为 v1 那块板的 switch 里根本没有 TYPE_MODE 这一支、MODE 帧整条被丢。
    握手在那块板上从来没成功过，可"这轮没读到非零 reject"读起来**像**成功
    （spec §6.1 点名的形状就是它）。所以这不是代码组织问题，是判据问题。
    """
    for kind in ('mode_profile', 'mode_teleop'):
        assert kind in lp.MODE_REQUEST_KINDS
        assert kind in lp.EXPECTED          # 不在判据表里，judge() 只会给"没有这一条"
        assert lp.EXPECTED[kind] is None    # 两条都不以 mode 变化为判据


@pytest.mark.parametrize('kind', ['mode_auto', 'mode_manual', 'clear',
                                  'mode_profile', 'mode_teleop'])
def test_mode_commands_still_refuse_a_command_line_profile(kind):
    """T1 不许绕过那条老约束：档案号只能来自 config/vehicle_profile.yaml。

    闸门从 main() 里抽成 check_mode_args() 是为了能被直接钉住——测 main() 里那段
    顺序代码要构造 argv 并真的往发送那一步走，而这条闸门的意义恰恰是**不许走到发送**。
    """
    with pytest.raises(SystemExit):
        lp.check_mode_args(kind, ['2'])
    lp.check_mode_args(kind, [])            # 不传参数才是合法用法


def test_judge_mode_profile_and_teleop_say_different_things():
    """握手的 0x01 有两种成因；TELEOP 的 0x06 只在**旧镜像**上是预期答复——两句不能共用文案。"""
    # 握手：没读到非零 reject = 板子认了这个档案号
    assert lp.judge('mode_profile', 0, [0], [])[0] == 'PASS'
    # 握手：挂着 0x01 —— 要说清"这个号真的不匹配"与"从没握过手"分不开
    verdict, text = lp.judge('mode_profile', 0, [0], [P.REJECT_PROFILE])
    assert verdict == 'FAIL' and '从没' in text
    # 握手：板子回的是别的码 ⇒ 这条码不是握手产生的，不给结论
    assert lp.judge('mode_profile', 0, [0], [P.REJECT_RCS_STALE])[0] == 'INCONCLUSIVE'
    # TELEOP（旧镜像那一版）：0x06 给 PASS，但必须带上"不等于 TELEOP 可用"那句
    verdict, text = lp.judge('mode_teleop', 0, [0], [P.REJECT_NOT_IMPL])
    assert verdict == 'PASS' and 'TELEOP 可用' in text
    # TELEOP：mode 没进 3、reject 也没挂非零码 ⇒ 与"帧整条被丢掉"分不开
    assert lp.judge('mode_teleop', 0, [0], [])[0] == 'INCONCLUSIVE'
    # 两条共同的最外层：一帧 STATUS 都没有，只能说不计结论
    assert lp.judge('mode_profile', 0, [], [])[0] == 'INCONCLUSIVE'
    assert lp.judge('mode_teleop', None, [0], [])[0] == 'INCONCLUSIVE'


def test_judge_mode_teleop_accepts_the_flashed_image_shape():
    """烧了手操档之后，`mode_teleop` 的成功形状是 mode 跳 3 且 reject 归 0。

    这条测试是 10-13 那次判据改动唯一的行为证据。改之前同样入参返回的是
    INCONCLUSIVE，而且理由是"没烧批 1a 的板就是把 MODE 整条丢掉"——那句话说的是
    另一块板。后果不是"少一条结论"，是**台架上真的进了手操档、工具却说判不了，
    并给出一个会把人引向查接线的错因**（§4B 读表须知第 3 句同一个坑）。
    """
    # 正常进档：基线 MANUAL(0) -> 观察到 TELEOP(3)，窗口内 reject 全为 0
    verdict, text = lp.judge('mode_teleop', 0, [0, 3], [])
    assert verdict == 'PASS' and 'TELEOP（mode=3）' in text
    # 因果：没有发送前基线不给 PASS（与通用分支同一把尺）
    assert lp.judge('mode_teleop', None, [0, 3], [])[0] == 'INCONCLUSIVE'
    # 因果：发送前就已经是 3 ⇒ 这次请求没有可观察的效果
    assert lp.judge('mode_teleop', 3, [3], [])[0] == 'INCONCLUSIVE'
    # 同窗口里既看到 3 又挂着非零 reject ⇒ 两个证据互相矛盾，不给结论
    verdict, text = lp.judge('mode_teleop', 0, [0, 3], [P.REJECT_PERMIT])
    assert verdict == 'INCONCLUSIVE' and '更早' in text
    # 被排在前面那道门挡了（手操的三道门之一）：FAIL 要说清"是被挡"不是"未实现"
    verdict, text = lp.judge('mode_teleop', 0, [0], [P.REJECT_ESTOP_LATCHED])
    assert verdict == 'FAIL' and '未实现' not in text


def test_judge_mode_teleop_reads_reject_0x02_as_the_split_defect():
    """0x02 是**被去掉的那一道自己**在拒，不是"被排在它前面的判据挡了"。

    通用那条 FAIL 的文案对 0x02 是假话：手操档的查序是 ① 档案 →（② 只 AUTO 查）→
    ③ 急停 → ④ 主循环，②前面只剩①；一块烧了 10-13 那版的板答 0x02，唯一说得通的
    是 `enter_unmanned()` 里"TELEOP 跳过②"那句没进镜像。这条判据把现场直接引向认版
    （§4B B1），而不是引向"再拨一次遥控/再等一次新鲜"——后者会让人对着一条没拆成的
    门反复试，而 §4B C22 要的恰恰就是"遥控不通时也能进"。

    变异记录（证明这条测试真咬）：把 `last == P.REJECT_RCS_STALE` 改成 `False` 之后，
    0x02 落回通用那条 FAIL，第一条断言当场红；改回全绿。
    """
    verdict, text = lp.judge('mode_teleop', 0, [0], [P.REJECT_RCS_STALE])
    assert verdict == 'FAIL'
    assert '拆档' in text and '遥控' in text
    assert '排在它前面' not in text        # 不许再用通用那句错文案
    # 同一条 0x02 在握手那一格仍是"不是握手产生的、不给结论"（别把两条判据并成一条）
    assert lp.judge('mode_profile', 0, [0], [P.REJECT_RCS_STALE])[0] == 'INCONCLUSIVE'
