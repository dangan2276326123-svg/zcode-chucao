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


def test_mode_name_and_expected_tables_match_the_e3_contract():
    """两张表是 brief 定下的契约：MODE 含 TELEOP，nav 的预期不再是 mode=1。"""
    assert lp.MODE_NAME == {0: 'MANUAL', 1: 'AUTO', 2: 'ESTOP', 3: 'TELEOP'}
    assert lp.EXPECTED == {'nav': None, 'mode_auto': 1, 'mode_manual': 0,
                           'estop': 2, 'clear': 0, 'tool': None, 'beat': None}


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
