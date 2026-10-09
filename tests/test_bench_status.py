# -*- coding: utf-8 -*-
"""tools/bench_status.py 的测试。

重点钉两件事：
1. **字段名必须与生产解析器一致**。写这个工具时我就把 `speed_mps` 误写成 `speed`
   ——同一份 STATUS 字典，抄错键名是 KeyError，而台架上正在跑动的时候没人愿意
   现场调试记录器。这里用真实 `pack_status` 走一遍 `StatusReceiver.handle()`，
   键名一错就红。
2. **静默段要能成对记下来**。B2 的 ④⑤⑦⑧ 场景证据本质就是"从断到停的那几秒"，
   gap_start / gap_end 不成对，回来就对不上时间轴。
3. **发送是 opt-in，且发出去的不算收到的证据**（Task 8）。不填 `--to` 就一个字节
   都不许外发；填了就用**独立的 socket 与独立的序号计数器**，`verdict()` 的结论
   也不许因为"我发了 NAV"而变松。
"""
import io
import os
import socket
import sys
import threading
import time

import pytest

from common import protocol as P
from pc.status_rx import StatusReceiver
from tools import bench_status as bs


def _status_frame(seq, speed=0.0, current=1.2, batt=48.0, limits=0, mode=0):
    return P.pack_frame(P.TYPE_STATUS,
                        P.pack_status(speed, current, batt, limits, mode), seq)


def _rows(log):
    import csv
    with open(log.path, encoding='utf-8') as f:
        return list(csv.DictReader(f))


def _mklog(tmp_path):
    p = os.path.join(str(tmp_path), 'bench_log.csv')
    return bs.BenchLog(p)


def test_classify_kinds():
    assert bs.classify(None, 0) == 'first'
    assert bs.classify(0, 0) == 'frame'
    assert bs.classify(0, 2) == 'mode_change'      # MANUAL -> ESTOP
    assert bs.classify(1, 0) == 'mode_change'      # AUTO 掉回 MANUAL


def test_real_status_frame_flows_through_without_keyerror(tmp_path):
    """键名钉桩：这里任何一处 st[...] 拼错都会在这里炸，而不是在台架上炸。"""
    log = _mklog(tmp_path)
    rx = StatusReceiver()
    st = rx.handle(_status_frame(seq=100, speed=0.125, current=2.34,
                                 batt=47.6, limits=0x03, mode=1))
    assert st is not None
    assert bs.classify(None, st['mode']) == 'first'
    log.frame(st, peer='192.168.127.10')
    r = _rows(log)
    assert len(r) == 1 and r[0]['kind'] == 'first'
    assert r[0]['mode'] == '1' and r[0]['seq'] == '100'
    assert r[0]['speed'] == '0.125' and r[0]['current_a'] == '2.34'
    assert r[0]['batt_v'] == '47.60' and r[0]['peer'] == '192.168.127.10'
    log.close()


def test_mode_change_is_its_own_row(tmp_path):
    log, rx = _mklog(tmp_path), StatusReceiver()
    for seq, mode in ((1, 0), (2, 1), (3, 1), (4, 2)):
        log.frame(rx.handle(_status_frame(seq=seq, mode=mode)), peer='x')
    kinds = [r['kind'] for r in _rows(log)]
    assert kinds == ['first', 'mode_change', 'frame', 'mode_change']
    log.close()


def test_note_lands_on_the_same_timeline(tmp_path):
    log = _mklog(tmp_path)
    log.note('④(a) 关接收机')
    log.note('④(b) 线断悬空出乱码')
    r = _rows(log)
    assert [x['kind'] for x in r] == ['note', 'note']
    assert r[0]['note'] == '④(a) 关接收机'
    assert log.rows == 2                     # rows 是"已落账行数"，两条都在
    log.close()


def test_silence_becomes_a_paired_gap(tmp_path):
    log = _mklog(tmp_path)
    base = 1000.0
    log.t0 = base
    st = {'seq': 1, 'speed_mps': 0.0, 'current_a': 1.0, 'battery_v': 48.0,
          'limits': 0, 'mode': 0}
    log.last_rx = base
    log.prev_mode = 0
    assert log.check_gap(now=base + 0.5) is False       # 还没到阈值
    assert log.check_gap(now=base + 1.4) is True        # 静默开始
    kinds = [r['kind'] for r in _rows(log)]
    assert kinds == ['gap_start']
    # 恢复收帧 -> gap_end，且带时长
    log.last_rx = base + 1.4
    st2 = dict(st, seq=2)
    log.prev_mode = 0
    t_saved = log.last_rx
    log.gap_open_at = t_saved
    import time as _t
    real = _t.time
    _t.time = lambda: t_saved + 2.0                # 模拟"2 秒后链路回来"
    try:
        log.frame(st2, peer='x')
    finally:
        _t.time = real
    kinds = [r['kind'] for r in _rows(log)]
    # gap_end 必须紧挨在帧行之前——它标记的是"这一帧到达=静默结束"
    assert kinds == ['gap_start', 'gap_end', 'frame'], kinds
    end = [r for r in _rows(log) if r['kind'] == 'gap_end'][0]
    assert '2.00 s' in end['note']
    log.close()


def test_gap_left_open_at_close_is_still_marked(tmp_path):
    """结束时仍没信号，是最常见的一种"其实没测到"——必须留痕。"""
    log = _mklog(tmp_path)
    log.last_rx = 100.0
    log.gap_open_at = 100.0
    log.close()
    kinds = [r['kind'] for r in _rows(log)]
    assert kinds == ['gap_end']
    assert '仍未收到新帧' in _rows(log)[0]['note']


def test_pump_once_checks_gap_even_when_every_frame_is_rejected(tmp_path):
    """09-28 实测盲点的回归测试。

    那天大板每 2.95 秒重启一次（台账 Hw-26），重启后序号从 0 重来，这些帧在
    StatusReceiver 里**全部算旧的、被拒收**，所以主循环一路走 `st is None` 分支，
    永远进不了 `except socket.timeout` —— 而旧代码只在 timeout 分支里调 check_gap。
    结果：屏幕上明明有六段 2.95 秒空窗，CSV 里 gap_start/gap_end **一行都没有**
    （那份文件的 kind 只有 first 1 行 + frame 110 行）。④⑤⑦⑧ 的场景证据本质就是
    "从断到停的那几秒"，这个盲点正对着它，所以钉在这里：静默判定必须在每一轮都做，
    与这一帧有没有被接受无关。
    """
    log, rx = _mklog(tmp_path), StatusReceiver()
    ctr = {'rejected': 0}
    base = time.time()
    peer = ('192.168.127.10', 5555)
    kind, st = bs.pump_once(_status_frame(seq=500), peer, rx, log, ctr, now=base)
    assert kind == 'first' and st is not None
    for i, seq in enumerate((0, 1, 2)):                 # "重启"后的旧序号
        k2, s2 = bs.pump_once(_status_frame(seq=seq), peer, rx, log, ctr,
                              now=base + 0.5 + 0.4 * i)
        assert s2 is None, '序号回退的帧应当被拒收（这是前提，不是缺陷）'
    rows = _rows(log)
    starts = [r for r in rows if r['kind'] == 'gap_start']
    assert len(starts) == 1, '到达但全被拒收的这段时间也必须记一条静默'
    assert '全被拒收' in starts[0]['note'], '要写明链路并没有真的没人发'
    assert ctr['rejected'] == 3
    log.close()


def test_true_silence_does_not_claim_rejected_traffic(tmp_path):
    """反例：真的一个报文都没有时，那句"全被拒收"不许出现，否则会把断线读成重启。"""
    log, rx = _mklog(tmp_path), StatusReceiver()
    ctr = {'rejected': 0}
    base = time.time()
    bs.pump_once(_status_frame(seq=7), ('192.168.127.10', 1), rx, log, ctr,
                 now=base)
    bs.pump_once(None, None, rx, log, ctr, now=base + 1.5)
    starts = [r for r in _rows(log) if r['kind'] == 'gap_start']
    assert len(starts) == 1
    assert '全被拒收' not in starts[0]['note']
    assert starts[0]['note'].startswith('STATUS 静默')
    log.close()


def test_local_has_ip_does_not_confuse_absent_with_present():
    """pc_ip 自检的实现必须能分清"有"和"没有"——它替代的是那句"请先去确认 pc_ip"。"""
    assert bs.local_has_ip('127.0.0.1') is True
    assert bs.local_has_ip('240.0.0.1') is False       # 不属于本机，bind 应失败


def test_verdict_turns_counters_into_a_decision():
    """车边上不该用心算：4 个分支各自给一句能照着做的话。"""
    # 0 行：先查发送端，不许写成"接线不通"
    v0 = bs.verdict(0, 0, 0, 0, 0, 60.0)[0]
    assert '一行都没收到' in v0 and 'bridge' in v0
    # 有重同步：直接判"板子在复位"，并指到 Hw-26/Hw-27
    v1 = bs.verdict(111, 0, 305, 6, 111, 20.0)
    assert any('序号反复回退' in l for l in v1) and any('Hw-26' in l for l in v1)
    # 帧率不足但没重同步：说明中间有静默段
    v2 = bs.verdict(200, 0, 0, 0, 240, 60.0)          # 3.3 帧/秒
    assert any('断流' in l for l in v2)
    # 健康：才允许做场景实验
    v3 = bs.verdict(1200, 0, 0, 0, 1200, 60.0)
    assert any('链路稳定' in l for l in v3)


def test_verdict_does_not_pass_dirty_counters_or_trailing_loss():
    """09-30 复审给的两个反例，原样钉成回归（当时两者都输出"链路稳定"）。"""
    # 反例一：10 秒 201 帧，之后 60 秒什么都没有 —— 结尾断流必须算进结论
    v = bs.verdict(201, 0, 0, 0, 201, 70.0, active=10.0)
    assert not any('链路稳定' in l for l in v), v
    assert any('断流' in l for l in v), v
    # 反例二：好帧够，但坏帧/旧序号一大堆 —— 计数不为零就不许放行
    v2 = bs.verdict(201, 1000, 200, 0, 1401, 10.0, active=10.0)
    assert not any('链路稳定' in l for l in v2), v2
    assert any('坏帧 1000' in l for l in v2), v2


def test_verdict_rates_over_the_frame_stream_not_the_wall_clock():
    """09-29 现场：启动后 49 秒才有第一帧，之后 135 秒是标准 20Hz。
    按"总时长"算出 14.6 帧/秒，于是判定叫我们去看根本不存在的 gap 行——分母用错，
    判据自己打自己脸，还把注意力从"链路其实是好的"引开。钉住分母。"""
    v = bs.verdict(2703, 0, 0, 0, 2703, 185.0, active=135.1)
    assert any('20.0 帧/秒' in l for l in v), v
    assert any('落在帧流之外' in l for l in v), v
    # 09-30 修正：窗口外的沉默**不再被豁免**，它照样是断流，只是不污染平均速率
    assert any('断流' in l for l in v), '开机等待可以剔除，结尾/开头的长断流必须仍然报警'
    # 没传 active 时退回旧行为（总时长），不能因为加了参数就静默改判据
    v0 = bs.verdict(2703, 0, 0, 0, 2703, 185.0)
    assert any('14.6 帧/秒' in l for l in v0), v0


def test_existing_evidence_is_never_overwritten(tmp_path):
    """09-30 复审指出：默认目录只到分钟，同一分钟重跑会把上一份证据静默清空，
    而台账里可能已经引用过那个路径。宁可另存，绝不覆盖。"""
    path = os.path.join(str(tmp_path), 'bench_log.csv')
    first = bs.BenchLog(path)
    first.note('第一轮证据')
    first.close()
    before = open(path, 'rb').read()

    raised = False
    try:
        bs.BenchLog(path)
    except FileExistsError:
        raised = True
    assert raised, 'BenchLog 必须以独占创建打开，拒绝覆盖已存在的证据'
    assert open(path, 'rb').read() == before, '被拒绝的那一次不许动旧文件一个字节'

    alt = bs.unique_path(path)
    assert alt != path and not os.path.exists(alt)
    bs.BenchLog(alt).close()
    assert os.path.exists(alt)
    assert bs.unique_path(alt) != alt          # 再来一次又要换名，不能回头覆盖


def test_alarm_lands_even_when_no_frame_is_good(tmp_path):
    """ALARM 设计要抓的唯一场景就是"坏帧持续到达"，可它原来挂在有效帧之后 ——
    st 为 None 就 continue，永远走不到。钉住拒收分支上的这条路径。"""
    log, rx = _mklog(tmp_path), StatusReceiver()
    ctr = {'rejected': 0}
    junk = bytes([0xA5, 0x5A, 0x03, 0x00, 0x10, 0x00, 0x00, 0xFF, 0xFF])   # 长度与 CRC 都不对
    base = time.time()
    for i in range(8):
        bs.pump_once(junk, ('127.0.0.1', 1), rx, log, ctr, now=base + 0.01 * i)
    notes = [r['note'] for r in _rows(log) if r['kind'] == 'note']
    assert any('ALARM' in n for n in notes), '坏帧洪水必须落一条 note'
    assert len([n for n in notes if 'ALARM' in n]) == 1, '洪水期间要有冷却，别淹掉时间轴'
    log.close()


# ============ Task 8：能发（opt-in）、发出的帧落同一张 CSV、带 E3 列 ============
#
# 三条安全判据各自有钉子，别让它们只活在注释里：
#   A. 不填 --to = 一个字节都不发（test_tx_is_disabled_unless_a_target_is_given 等）
#   B. 发送序号与接收序号是两套计数（test_tx_sequence_is_a_separate_counter 等）
#   C. 发出去的不算收到的证据（test_tx_rows_are_not_evidence_of_reception）


class _FakeSock:
    """假发送 socket：记下每一对 (frame, addr)；fail=True 时 sendto 抛 OSError。"""

    def __init__(self, fail=False):
        self.sent = []
        self.fail = fail
        self.closed = False

    def sendto(self, frame, addr):
        if self.fail:
            raise OSError(10065, 'No route to host')
        self.sent.append((frame, addr))
        return len(frame)

    def close(self):
        self.closed = True


def _sender(sock=None):
    return bs.TxSender('192.168.127.10', 9000, sock=sock or _FakeSock())


def test_build_command_parses_each_kind():
    kind, frame = bs.build_command('!nav 0.14 0.12', 1, 5)
    assert kind == 'tx_nav'
    t, seq, payload = P.unpack_frame(frame)
    assert (t, seq) == (P.TYPE_NAV, 5)
    # f32 存不下 0.14/0.12（roundtrip 给 0.14000000059…），按精确相等比就是假红。
    assert P.unpack_nav(payload)[:2] == pytest.approx((0.14, 0.12), abs=1e-6)

    kind, frame = bs.build_command('!tool -3.5 7', 1, 6)
    assert kind == 'tx_tool'
    assert P.unpack_tool(P.unpack_frame(frame)[2]) == (-3.5, 7)

    for text, want_type in (('!beat', P.TYPE_HEARTBEAT),
                            ('!auto', P.TYPE_MODE),
                            ('!manual', P.TYPE_MODE),
                            ('!clear', P.TYPE_MODE)):
        kind, frame = bs.build_command(text, 1, 7)
        assert P.unpack_frame(frame)[0] == want_type
        assert kind.startswith('tx_')


def test_build_command_rejects_garbage():
    for bad in ('', '!nav', '!nav x y', '!nope', 'nav 0.1 0.1'):
        assert bs.build_command(bad, 1, 1) is None


def test_auto_command_carries_profile_id():
    _kind, frame = bs.build_command('!auto', 2, 9)
    assert P.unpack_mode(P.unpack_frame(frame)[2]) == (P.MODE_REQ_AUTO, 2)


def test_benchlog_header_has_e3_columns(tmp_path):
    log = bs.BenchLog(str(tmp_path / 'b.csv'))
    log.tx('tx_nav', None)
    log.f.close()
    header = open(str(tmp_path / 'b.csv'), encoding='utf-8').readline().strip().split(',')
    for col in ('profile', 'authority', 'reject', 'loop_alive', 'build_id', 'kind'):
        assert col in header
    rows = open(str(tmp_path / 'b.csv'), encoding='utf-8').read().strip().split('\n')
    assert len(rows[1].split(',')) == len(header)


def test_build_command_out_of_range_number_is_not_a_frame(tmp_path):
    """struct.error / OverflowError 都不是 ValueError 的子类：漏接它们不会"只是解析失败"，
    而是把 stdin 那条线程**整个打死** —— 之后场景标记与 !命令都不再进时间轴，而这正是
    本工具存在的理由。所以越界的 lift（256 / -1）与装不进 f32 的速度都得给 None。"""
    for bad in ('!tool 0 256', '!tool 0 -1', '!tool 0 07', '!nav 1e39 0'):
        assert bs.build_command(bad, 1, 1) is None, bad
    # 而 0x07 这种写法的位掩码是**合法**的（台架上就是要能提三把刀）
    kind, frame = bs.build_command('!tool 0 0x07', 1, 3)
    assert kind == 'tx_tool' and P.unpack_tool(P.unpack_frame(frame)[2]) == (0.0, 7)


def test_mode_rows_are_the_only_tx_rows_carrying_a_profile(tmp_path):
    """档案号只在 MODE 帧里（spec §3.1）。NAV/TOOL 行留空而不是填一个数：
    写了就是给线上根本没带的字段造证据。"""
    log = _mklog(tmp_path)
    s = _sender()
    for line in ('!nav 0.1 0.1', '!auto', '!beat'):
        assert s.send_line(line, 2, log) is not None
    rows = _rows(log)
    assert [r['kind'] for r in rows] == ['tx_nav', 'tx_auto', 'tx_beat']
    assert rows[1]['profile'] == '2'
    assert rows[0]['profile'] == '' and rows[2]['profile'] == ''
    log.close()


def test_tx_sequence_is_a_separate_counter_from_the_receiver(tmp_path):
    """接收侧靠 STATUS 的 seq 判新鲜度（out_of_order / resynced / RESYNC_RUN）。
    发送如果复用那套计数，就是自己给自己的判据喂假数据 ⇒ 两套计数器必须互不相干，
    发送序号从 0 自己往上走，接收侧看不到任何变化。"""
    log, rx = _mklog(tmp_path), StatusReceiver()
    st = rx.handle(_status_frame(seq=500))
    assert st is not None
    log.frame(st, peer='192.168.127.10')
    s = _sender()
    assert s.seq == 0, '发送计数器的起点是自己那个 0，不是接收到的 500'
    got = []
    for _ in range(3):
        kind, seq = s.send_line('!nav 0.1 0.1', 1, log)
        got.append(seq)
    assert got == [0, 1, 2] and s.seq == 3
    assert s.sent == 3
    assert (rx.good, rx.bad, rx.out_of_order, rx.resynced) == (1, 0, 0, 0)
    assert [r['seq'] for r in _rows(log)] == ['500', '0', '1', '2']
    log.close()


def test_tx_sequence_wraps_at_16_bits_without_creating_a_frame(tmp_path):
    log = _mklog(tmp_path)
    sock = _FakeSock()
    s = bs.TxSender('192.168.127.10', 9000, sock=sock)
    s.seq = 0xFFFF
    kind, seq = s.send_line('!beat', 1, log)
    assert kind == 'tx_beat' and seq == 0xFFFF and s.seq == 0
    assert P.unpack_frame(sock.sent[0][0])[1] == 0xFFFF
    s.send_line('!beat', 1, log)
    assert P.unpack_frame(sock.sent[1][0])[1] == 0
    log.close()


def test_failed_send_is_not_recorded_as_sent(tmp_path):
    """sendto 抛了就不许写 tx 行 —— 记了就是"这帧上线过"的假证据；序号也不许消耗。"""
    log = _mklog(tmp_path)
    sock = _FakeSock(fail=True)
    s = bs.TxSender('192.168.127.10', 9000, sock=sock)
    assert s.send_line('!nav 0.1 0.1', 1, log) is None
    assert _rows(log) == [] and log.tx_rows == 0 and log.rows == 0
    assert s.sent == 0 and s.errors == 1 and s.seq == 0
    log.close()


def test_unparsable_command_line_is_counted_not_recorded(tmp_path):
    log = _mklog(tmp_path)
    s = _sender()
    assert s.send_line('!nav 0.1', 1, log) is None
    assert s.unparsed == 1 and s.sent == 0 and s.seq == 0
    assert _rows(log) == []
    log.close()


def test_tx_is_disabled_unless_a_target_is_given(tmp_path):
    """安全面第一条：缺省 = 彻底禁用。sender 为 None 时 !nav 既不发也不落 tx 行，
    并且要看得见一句解释（静默吞掉输入会让人以为自己在发）。"""
    log = _mklog(tmp_path)
    assert bs.sender_from_target(None) is None
    assert bs.handle_command_line('!nav 0.14 0.12', log, None, 1) is None
    assert log.rows == 0 and log.tx_rows == 0
    # 反过来：给了目标才真有发送
    s = _sender()
    assert bs.handle_command_line('!nav 0.14 0.12', log, s, 1) is not None
    assert s.sent == 1 and log.tx_rows == 1
    log.close()


def test_to_flag_defaults_to_none():
    """opt-in 的载体就是 argparse 的默认值：默认 None ⇒ 记录器出厂只收不发。"""
    a = bs.build_argparser().parse_args([])
    assert a.to is None and a.port == 9100
    b = bs.build_argparser().parse_args(['--to', '192.168.127.10:9000'])
    assert b.to == '192.168.127.10:9000'


def test_bad_target_is_an_error_not_a_silent_switch_to_receive_only():
    """安全面第一条的另一半：填了但填错（缺端口、端口非数字）必须**报错退出**，
    不能静默降级成"只收" —— 那样人会以为自己正在发 NAV，而板上一个字节都没收到。"""
    for bad in ('192.168.127.10', '192.168.127.10:', 'host:abc', ':9000', '',
                '192.168.127.10:0', '192.168.127.10:70000'):
        with pytest.raises(ValueError):
            bs.sender_from_target(bad)
    assert bs.sender_from_target('192.168.127.10:9000') is not None


def test_broadcast_and_self_echo_targets_are_refused():
    """广播 = 一条命令指挥整个网段上所有会动的板子；打到本机 9100 = 记录器收到自己
    发的 NAV，被 StatusReceiver 当坏帧计进 bad/ALARM —— 两者都不是"发个测试帧"。"""
    for bad in ('255.255.255.255:9000', '0.0.0.0:9000', '224.0.0.1:9000',
                '239.255.255.250:9000'):
        with pytest.raises(ValueError):
            bs.resolve_target(bad)
    with pytest.raises(ValueError):
        bs.resolve_target('192.168.127.100:9100', avoid_port=9100)
    assert bs.resolve_target('192.168.127.10:9000', avoid_port=9100) == \
        ('192.168.127.10', 9000)


def test_tx_socket_is_a_second_socket_that_is_never_bound(tmp_path, monkeypatch):
    """发送**绝不复用**收帧那个 socket（它带 SO_EXCLUSIVEADDRUSE 独占 0.0.0.0:9100）。
    Windows 上对未 bind 的 UDP socket 调 `getsockname()` 会抛 WinError 10022，
    所以这里不去看端口号，直接记"这个新建的 socket 有没有被 bind/设过选项"。"""
    made = []

    class _Recorder:
        def __init__(self, *args, **kwargs):
            self.calls = []
            made.append(self)

        def bind(self, addr):
            self.calls.append(('bind', addr))

        def setsockopt(self, *args):
            self.calls.append(('setsockopt',) + args)

        def sendto(self, frame, addr):
            self.calls.append(('sendto', frame, addr))

        def close(self):
            self.calls.append(('close',))

    monkeypatch.setattr(socket, 'socket', _Recorder)
    log = _mklog(tmp_path)
    s = bs.TxSender('192.168.127.10', 9000)
    assert made and s.sock is made[0]
    assert made[0].calls == [], '新建发送 socket 不该 bind，也不该带收帧那些选项'
    s.send_line('!beat', 1, log)
    assert made[0].calls[0][0] == 'sendto'
    assert made[0].calls[0][2] == ('192.168.127.10', 9000), '发给的是 --to 那个地址'
    assert bs.TxSender('127.0.0.1', 1).sock is not s.sock, '各自一个 socket，不共用'
    log.close()


def test_note_listener_routes_bang_lines_to_tx_and_others_to_notes(tmp_path, monkeypatch):
    """stdin 的分派是这轮唯一的入口：! 开头 = 组帧发出，其它行仍然当场景标记。"""
    log = _mklog(tmp_path)
    sock = _FakeSock()
    s = bs.TxSender('192.168.127.10', 9000, sock=sock)
    monkeypatch.setattr(sys, 'stdin', io.StringIO(
        '!nav 0.14 0.12\n场景标记\n!nope\n\n'))
    bs._note_listener(log, threading.Event(), s, 1)
    rows = _rows(log)
    assert [r['kind'] for r in rows] == ['tx_nav', 'note'], '解析不了的 ! 行不该变成标记'
    assert rows[0]['seq'] == '0' and rows[1]['note'] == '场景标记'
    assert len(sock.sent) == 1 and sock.sent[0][1] == ('192.168.127.10', 9000)
    log.close()


def test_tx_rows_are_not_evidence_of_reception():
    """安全面第三条：verdict 的结论不许因为"我发了"而变松。
    ①发了 40 条一帧没收到 ⇒ 仍然必须是"一行都没收到、先查发送端"那一支；
    ②真有帧流时，带不带 tx 行数给出的判据**逐行相同**（tx 不参与任何分支）。"""
    v = bs.verdict(0, 0, 0, 0, 0, 30.0, tx_rows=40)
    assert any('一行都没收到' in l for l in v), v
    assert not any('链路稳定' in l for l in v), v
    assert any('发出' in l for l in v), '要说清那 40 条只是发出去的，不是收到的'

    healthy = bs.verdict(1200, 0, 0, 0, 1200, 60.0)
    assert any('链路稳定' in l for l in healthy)
    assert bs.verdict(1200, 0, 0, 0, 1200, 60.0, tx_rows=500) == healthy
    # 脏计数不会因为"有发送"而放过
    assert not any('链路稳定' in l
                   for l in bs.verdict(201, 1000, 200, 0, 1401, 10.0, tx_rows=9))


def test_rx_rows_count_only_accepted_frames(tmp_path):
    """verdict 的分母换成了 log.rx_rows：它必须只数**收到的帧行**。
    tx / note / gap 行都不算，否则发送一多就把"一帧都没收到"这一支救活了。"""
    log, rx = _mklog(tmp_path), StatusReceiver()
    sock = _FakeSock()
    s = bs.TxSender('127.0.0.1', 9000, sock=sock)
    assert log.rx_rows == 0
    s.send_line('!nav 0.1 0.1', 1, log)
    log.note('场景标记')
    assert log.rx_rows == 0 and log.tx_rows == 1
    log.frame(rx.handle(_status_frame(seq=1)), peer='x')
    log.frame(rx.handle(_status_frame(seq=2)), peer='x')
    assert log.rx_rows == 2 and log.rows == 4
    lines = bs.verdict(2, 0, 0, 0, log.rx_rows, 30.0, tx_rows=log.tx_rows)
    assert not any('一行都没收到' in l for l in lines), lines
    assert any('好帧 2' in l for l in lines), lines
    log.check_gap(now=log.last_rx + 5.0)
    assert log.gap_open_at is not None and log.rx_rows == 2
    log.close()


def test_every_row_write_holds_the_log_lock(tmp_path):
    """发送行来自 stdin 线程、帧行来自主线程，而 ②③⑧ 的场景就是**在 20 Hz 帧流里
    敲 !nav** —— 两个线程同时写同一张 CSV。撕裂的一行就是丢掉的一条证据。"""
    log = _mklog(tmp_path)

    class _SpyLock:
        def __init__(self):
            self.entered = 0

        def __enter__(self):
            self.entered += 1
            return self

        def __exit__(self, *exc):
            return False

    log._lock = _SpyLock()
    rx = StatusReceiver()
    log.frame(rx.handle(_status_frame(seq=3)), peer='x')
    log.note('标记')
    log.tx('tx_beat', st={'seq': 0})
    log.check_gap(now=log.last_rx + 5.0)
    assert log._lock.entered == 4, '每一行都必须整体在锁里写'
    log.close()
