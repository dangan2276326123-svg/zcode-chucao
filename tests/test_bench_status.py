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
from pc import wire
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
    v0 = bs.verdict(0, 0, 0, 0, 60.0, rx_rows=0)[0]
    assert '一行都没收到' in v0 and 'bridge' in v0
    # 有重同步：直接判"板子在复位"，并指到 Hw-26/Hw-27
    v1 = bs.verdict(111, 0, 305, 6, 20.0, rx_rows=111)
    assert any('序号反复回退' in l for l in v1) and any('Hw-26' in l for l in v1)
    # 帧率不足但没重同步：说明中间有静默段
    v2 = bs.verdict(200, 0, 0, 0, 60.0, rx_rows=240)      # 3.3 帧/秒
    assert any('断流' in l for l in v2)
    # 健康：才允许做场景实验
    v3 = bs.verdict(1200, 0, 0, 0, 60.0, rx_rows=1200)
    assert any('链路稳定' in l for l in v3)


def test_verdict_does_not_pass_dirty_counters_or_trailing_loss():
    """09-30 复审给的两个反例，原样钉成回归（当时两者都输出"链路稳定"）。"""
    # 反例一：10 秒 201 帧，之后 60 秒什么都没有 —— 结尾断流必须算进结论
    v = bs.verdict(201, 0, 0, 0, 70.0, rx_rows=201, active=10.0)
    assert not any('链路稳定' in l for l in v), v
    assert any('断流' in l for l in v), v
    # 反例二：好帧够，但坏帧/旧序号一大堆 —— 计数不为零就不许放行
    v2 = bs.verdict(201, 1000, 200, 0, 10.0, rx_rows=1401, active=10.0)
    assert not any('链路稳定' in l for l in v2), v2
    assert any('坏帧 1000' in l for l in v2), v2


def test_verdict_rates_over_the_frame_stream_not_the_wall_clock():
    """09-29 现场：启动后 49 秒才有第一帧，之后 135 秒是标准 20Hz。
    按"总时长"算出 14.6 帧/秒，于是判定叫我们去看根本不存在的 gap 行——分母用错，
    判据自己打自己脸，还把注意力从"链路其实是好的"引开。钉住分母。"""
    v = bs.verdict(2703, 0, 0, 0, 185.0, rx_rows=2703, active=135.1)
    assert any('20.0 帧/秒' in l for l in v), v
    assert any('落在帧流之外' in l for l in v), v
    # 09-30 修正：窗口外的沉默**不再被豁免**，它照样是断流，只是不污染平均速率
    assert any('断流' in l for l in v), '开机等待可以剔除，结尾/开头的长断流必须仍然报警'
    # 没传 active 时退回旧行为（总时长），不能因为加了参数就静默改判据
    v0 = bs.verdict(2703, 0, 0, 0, 185.0, rx_rows=2703)
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


def test_note_listener_routes_bang_lines_to_tx_and_others_to_notes(tmp_path, monkeypatch,
                                                                   capsys):
    """stdin 的分派是这轮唯一的入口：! 开头 = 组帧发出，其它行仍然当场景标记。

    尾部必须再喂一条**普通标记**：原来 `!nope` 排在最后，线程就算在那一行被打死，
    前面两行也已经落账，断言照样绿——"线程还活着"这件事从来没被证明过。现在
    `!nope` 与越界的 `!tool 0 256` 都排在尾部标记之前，线程一死最后那条 note 就没了。
    """
    log = _mklog(tmp_path)
    sock = _FakeSock()
    s = bs.TxSender('192.168.127.10', 9000, sock=sock)
    monkeypatch.setattr(sys, 'stdin', io.StringIO(
        '!nav 0.14 0.12\n场景标记\n!nope\n!tool 0 256\n\n尾部标记\n'))
    bs._note_listener(log, threading.Event(), s, 1)
    rows = _rows(log)
    assert [r['kind'] for r in rows] == ['tx_nav', 'note', 'note'], \
        '解析不了的 ! 行不该变成标记，但线程必须活到下一行'
    assert rows[-1]['note'] == '尾部标记', '最后一条必须是标记——它证明线程没被打死'
    assert rows[1]['note'] == '场景标记'
    assert rows[0]['seq'] == '0'
    assert len(sock.sent) == 1 and sock.sent[0][1] == ('192.168.127.10', 9000)
    assert s.unparsed == 2, '!nope 与越界的 !tool 0 256 都该计入 unparsed'
    assert s.sent == 1 and s.seq == 1
    log.close()


def test_tx_rows_are_not_evidence_of_reception():
    """安全面第三条：verdict 的结论不许因为"我发了"而变松。
    ①发了 40 条一帧没收到 ⇒ 仍然必须是"一行都没收到、先查发送端"那一支；
    ②真有帧流时，带不带 tx 行数给出的判据**逐行相同**（tx 不参与任何分支）。"""
    v = bs.verdict(0, 0, 0, 0, 30.0, rx_rows=0, tx_rows=40)
    assert any('一行都没收到' in l for l in v), v
    assert not any('链路稳定' in l for l in v), v
    assert any('发出' in l for l in v), '要说清那 40 条只是发出去的，不是收到的'

    healthy = bs.verdict(1200, 0, 0, 0, 60.0, rx_rows=1200)
    assert any('链路稳定' in l for l in healthy)
    assert bs.verdict(1200, 0, 0, 0, 60.0, rx_rows=1200, tx_rows=500) == healthy
    # 脏计数不会因为"有发送"而放过
    assert not any('链路稳定' in l
                   for l in bs.verdict(201, 1000, 200, 0, 10.0, rx_rows=1401,
                                       tx_rows=9))


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
    lines = bs.verdict(2, 0, 0, 0, 30.0, rx_rows=log.rx_rows, tx_rows=log.tx_rows)
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


# ============ fix round 1：审查发现的 I-1 / I-2 / M-1 / M-3 / M-4 / M-6 ============


def _rows_at(path):
    import csv
    with open(str(path), encoding='utf-8') as f:
        return list(csv.DictReader(f))


def _install_wiring(monkeypatch, lines):
    """把 `socket.socket` 换成记账假对象、stdin 换成脚本行，返回"被创建过的 socket"。

    两个细节都是为了让断言不赌时序：
      · `recvfrom` 先等 stdin 那条线程把行喂完（drained 事件）再抛 KeyboardInterrupt，
        这正是按 Ctrl-C 时主线程发生的事；线程若半路死了，事件不来，2 秒后照样收尾，
        那种情况会被"某一行的 kind 不见了"抓到，而不是把测试挂住。
      · pc_ip 自检另开一只 socket 去 bind 试探，与本判据无关，直接让它不参与——
        这样"只创建了 N 只 socket"才是干净的断言。
    """
    made = []
    drained = threading.Event()

    class _Sock:
        def __init__(self, *args, **kwargs):
            self.calls = []
            made.append(self)

        def bind(self, addr):
            self.calls.append(('bind', addr))

        def setsockopt(self, *args):
            self.calls.append(('setsockopt',) + args)

        def settimeout(self, value):
            self.calls.append(('settimeout', value))

        def sendto(self, frame, addr):
            self.calls.append(('sendto', frame, addr))
            return len(frame)

        def recvfrom(self, bufsize):
            drained.wait(2.0)
            raise KeyboardInterrupt

        def close(self):
            self.calls.append(('close',))

    class _Stdin:
        def __init__(self, scripted):
            self.lines = list(scripted)
            self.i = 0

        def readline(self):
            if self.i >= len(self.lines):
                drained.set()
                return ''
            line = self.lines[self.i]
            self.i += 1
            return line

    monkeypatch.setattr(socket, 'socket', _Sock)
    monkeypatch.setattr(sys, 'stdin', _Stdin(lines))
    monkeypatch.setattr(bs, 'configured_pc_ip', lambda root=None: None)
    return made


def _run_main(monkeypatch, argv):
    monkeypatch.setattr(sys, 'argv', ['bench_status.py'] + argv)
    bs.main()


def test_main_without_to_flag_never_builds_a_sending_socket(tmp_path, monkeypatch, capsys):
    """M-1：把 %TEMP% 那组冒烟的形状搬进仓库，"默认禁用"从此有**接线层**的证明。
    以前只问到 `sender_from_target(None) is None`——那是构造函数；main() 真的只用
    收帧那一只、一个字节都不 sendto，这件事在仓库里没有证据。"""
    made = _install_wiring(monkeypatch, ['场景标记\n', '!nav 0.14 0.12\n'])
    _run_main(monkeypatch, ['--out', str(tmp_path / 'run')])
    out = capsys.readouterr().out
    assert len(made) == 1, '不带 --to 时 main 不该再开第二只 socket'
    names = [c[0] for c in made[0].calls]
    assert 'sendto' not in names, '一个字节都不许外发'
    assert ('bind', ('0.0.0.0', 9100)) in made[0].calls
    assert 'send: DISABLED' in out
    assert '[TX DISABLED]' in out, '那句 !nav 要有可见的解释，不能静默吞掉'
    rows = _rows_at(tmp_path / 'run' / 'bench_log.csv')
    assert [r['kind'] for r in rows] == ['note'], '没上线的帧不许落 tx 行'


def test_send_enabled_banner_states_the_bench_hazards(tmp_path, monkeypatch, capsys):
    """I-2 + I-1 的操作员可见面：开机那行是台架上唯一会被读的风险说明，必须带上
    限速、轮子离地、以及桥那条"单条命令 0.5 秒后自注 ESTOP"。
    顺带在接线层验一次速度闸：0.9 的 !nav 根本到不了 socket。"""
    made = _install_wiring(monkeypatch, ['!nav 0.9 0\n'])
    _run_main(monkeypatch, ['--to', '127.0.0.1:19123', '--out', str(tmp_path / 'run')])
    out = capsys.readouterr().out
    assert len(made) == 2, '给了 --to 才是两只：收帧那只 + 发送那只'
    # 按"谁 bind 了"来分，不按创建顺序——main() 在绑端口**之前**就把发送那只建出来了
    # （--to 写错要在碰任何资源之前退出），所以列表顺序根本不是"收帧那只在前"。
    bound = [s for s in made if any(c[0] == 'bind' for c in s.calls)]
    assert len(bound) == 1, '只有收帧那一只许 bind'
    assert ('bind', ('0.0.0.0', 9100)) in bound[0].calls
    tx = [s for s in made if s is not bound[0]][0]
    assert [c[0] for c in tx.calls] == ['close'], '发送那只不 bind，也没发出任何东西'
    assert not any(c[0] == 'sendto' for s in made for c in s.calls), \
        '0.9 的 NAV 被限速闸拦下，一个字节都不该到 socket'
    assert 'send: ENABLED' in out
    assert 'wheels OFF the ground' in out
    assert '0.20 m/s' in out, '限速要写在开机行上，不只是写在 docstring 里'
    assert 'ESTOP' in out and '0.5' in out
    assert 'TX REFUSED' in out and 'refused=1' in out


def test_nav_beyond_bench_limit_is_refused_not_sent(tmp_path, capsys):
    """I-1：现在烧在板上的固件，一条 NAV 就是 `mode = MODE_AUTO` 且把 cmd_vl/cmd_vr
    钳到 **±1.0 m/s**（`firmware/retrofit.c:93` 早退、`:98-101` 钳制、`:102` 进 AUTO），
    行走斜率 SLEW_ACC=0.2 m/s²（:140）
    ⇒ 一条 0.9 的命令 4.5 秒后真的把车推到 0.9 m/s。兄弟发送器 `tools/link_probe.py:377`
    早就把 0.20 写成硬闸——同一个 bridge:9000 入口，两个 PC 侧发送器不许一个有闸一个没闸。"""
    log = _mklog(tmp_path)
    sock = _FakeSock()
    s = bs.TxSender('192.168.127.10', 9000, sock=sock)
    for line in ('!nav 0.9 0', '!nav -0.9 0', '!nav 0.0 1.5', '!nav nan 0',
                 '!nav 0 inf'):
        assert s.send_line(line, 1, log) is None, line
    out = capsys.readouterr().out
    assert 'TX REFUSED' in out and 'bench limit' in out and 'nothing sent' in out
    assert sock.sent == [] and s.sent == 0
    assert s.refused == 5 and s.errors == 0 and s.unparsed == 0
    assert s.seq == 0, '拒发不消耗发送序号，也不许占号'
    assert _rows(log) == [] and log.rows == 0 and log.tx_rows == 0
    # `!nav nan 0` 这一条是 C-1 的原始症状：pack 成 f32 NaN 再回读还是 NaN，
    # 旧谓词 `NaN > 0.20+1e-6` 恒假 ⇒ 放行。现在它跟超限同一条出口：**拒发，
    # 不发不落地**（上面 refused/sent/序号/tx 行四个数一起断，少一个都算没闭环）。
    # 限值以内照发，含"正好等于 0.20"这条边界（与 link_probe 的 `> 0.20` 同一口径）
    assert s.send_line('!nav 0.2 0.2', 1, log) is not None
    assert s.send_line('!nav -0.199 0.199', 1, log) is not None
    assert s.sent == 2 and s.refused == 5 and len(sock.sent) == 2
    # 闸只管 NAV；TOOL/BEAT/MODE 的权限在板上，不在这里悄悄扩权
    # （permit 显式给门 F：门 N 下 TOOL 另有 C-1 那道闸管，见下面那条测试，
    #   这里要验的是"NAV 那道闸不越界去管 TOOL/BEAT/MODE"）
    s.permit = wire.GATE_F
    for line in ('!tool 5 1', '!beat', '!auto'):
        assert s.send_line(line, 1, log) is not None
    assert s.sent == 5 and s.refused == 5
    log.close()


def test_tool_gate_matches_what_the_closed_loop_would_send():
    """C-1 的一致性：手动工具那道许可位闸，判据必须与闭环**同一个**——
    `pc/wire.py:frames_for_state` 在 GATE_N 下强制 (0.0, 0x07)，所以那一对必须被
    `tool_command_allowed` 放行；否则两个通道各有一套"门 N"，读代码的人分不清
    哪一关生效（AGENTS 清单第 6 条）。
    """
    from tools.bench_limits import tool_command_allowed
    for state in ('AUTO', 'LIFT'):
        for usable in (True, False):
            frames = wire.frames_for_state(state, usable, 12.0, -7.0, 40.0,
                                           permit=wire.GATE_N)
            payload = dict(frames)[P.TYPE_TOOL]
            off, lift = P.unpack_tool(payload)
            assert tool_command_allowed(wire.GATE_N, off, lift), (state, usable)
        frames = wire.frames_for_state(state, True, 0.0, 0.0, 0.0,
                                       permit=wire.GATE_F)
        off, lift = P.unpack_tool(dict(frames)[P.TYPE_TOOL])
        assert tool_command_allowed(wire.GATE_F, off, lift), state


def test_tool_command_is_refused_under_gate_n_and_allowed_under_gate_f(tmp_path,
                                                                       capsys):
    """C-1（人打的字那一半）+ 审查第 7 条：`!tool mm lift` 过去**完全不查许可位**。

    闭环在门 N 下没有选择（`pc/wire.py:91-95` 把横移强制 0.0、刀位强制 0x07），
    而同一块板子上的手动通道按一个键就能落刀——门 N 的字面含义就没了。
    现在三个许可位形态都要有答案：门 N 只许 (0, 0x07)、门 F 全放行、**取不到 = 一律拒**。
    """
    log = _mklog(tmp_path)
    sock = _FakeSock()
    n = bs.TxSender('192.168.127.10', 9000, sock=sock, permit=wire.GATE_N)
    assert n.send_line('!tool 0 0', 1, log) is None, '门 N 下落刀必须拒'
    assert n.send_line('!tool 5 7', 1, log) is None, '门 N 下横移必须拒'
    assert n.send_line('!tool 0 3', 1, log) is None, '只提两把刀也算落了一把'
    assert sock.sent == [] and n.sent == 0 and n.refused == 3
    assert _rows(log) == [] and log.tx_rows == 0, '被拒的帧不许落 tx 行'
    assert n.seq == 0, '拒发不占发送序号'
    assert n.send_line('!tool 0 7', 1, log) is not None, '门 N 要放行的正是闭环那一套'
    assert n.send_line('!tool 0 0x07', 1, log) is not None, '写法不同、上线的是同一对字节'
    assert n.sent == 2 and n.refused == 3

    f = bs.TxSender('192.168.127.10', 9001, sock=sock, permit=wire.GATE_F)
    assert f.send_line('!tool 0 0', 1, log) is not None, '门 F 就是允许落刀'
    assert f.sent == 1

    # 档案读不到 / 许可位未知：一律拒。**这一条是本测试的核心**——"拿不到"若当成
    # "允许落刀"，闸门就自己开了（批 1a 之前固件不看 TOOL 的许可位，PC 是唯一一关）。
    for unknown in (None, 0, '', 'gate_n', True):
        u = bs.TxSender('192.168.127.10', 9002, sock=sock, permit=unknown)
        assert u.send_line('!tool 0 0', 1, log) is None, repr(unknown)
        assert u.refused == 1, repr(unknown)
    out = capsys.readouterr().out
    assert out.count('[TX REFUSED] tool') >= 5, '拒发要看得见，不许静默'
    log.close()


def test_main_passes_the_profile_permit_into_the_sender(tmp_path, monkeypatch, capsys):
    """接线层闭环：闸在 `TxSender` 里，而 permit 只有 `main()` 会去档案里取——
    只测构造函数就等于没测"记录器真拿到了许可位"（AGENTS 清单第 2 条的闭环核对）。
    """
    made = _install_wiring(monkeypatch, ['开工标记\n', '!tool 0 0\n'])
    monkeypatch.setattr(bs, 'load_permit', lambda path=None: wire.GATE_N)
    _run_main(monkeypatch, ['--to', '127.0.0.1:19123', '--out', str(tmp_path / 'run')])
    out = capsys.readouterr().out
    assert any(c[0] == 'sendto' for s in made for c in s.calls) is False, \
        '门 N 下这条 !tool 一个字节都不许上线'
    assert '[TX REFUSED] tool' in out
    assert 'permit=1' in out, '开机那行要印出许可位——操作员只看这几行'
    rows = _rows_at(tmp_path / 'run' / 'bench_log.csv')
    assert [r['kind'] for r in rows] == ['note'], '被拒的帧不许落 tx 行'


def test_main_refuses_tool_when_the_profile_cannot_be_read(tmp_path, monkeypatch,
                                                           capsys):
    """同一接线的另一支：档案读不到 → permit=None → TOOL 一律拒，**不降级成门 F**。"""
    def _boom(path=None):
        raise ValueError('车辆档案读不进去')

    made = _install_wiring(monkeypatch, ['!tool 0 7\n'])
    monkeypatch.setattr(bs, 'load_permit', _boom)
    _run_main(monkeypatch, ['--to', '127.0.0.1:19124', '--out', str(tmp_path / 'run')])
    out = capsys.readouterr().out
    assert 'permit unavailable' in out, '读不到要看得见，不许静默当门 F'
    assert any(c[0] == 'sendto' for s in made for c in s.calls) is False
    assert '[TX REFUSED] tool' in out


def test_nav_bench_limit_is_one_shared_constant():
    """0.20 只能有一个出处（AGENTS 清单第 6 条：消灭单一事实源漂移）。
    两个发送器各写一份字面量，下一次就是改了一份没改另一份。"""
    from tools import bench_limits as BL
    from tools import link_probe as LP
    assert BL.NAV_BENCH_LIMIT_MPS == 0.20
    assert bs.NAV_BENCH_LIMIT_MPS is BL.NAV_BENCH_LIMIT_MPS
    assert LP.NAV_BENCH_LIMIT_MPS is BL.NAV_BENCH_LIMIT_MPS


def test_nav_gate_is_fail_closed_on_non_finite_and_non_numeric():
    """C-1（最终整枝审查）：这条谓词是三个手动发送器共用的**唯一**硬闸，
    所以它必须 fail-closed——拿不到一个有限、装得进 f32 的数，就按超限处理（拒发）。

    改之前它是 `max(abs(float(vl)), abs(float(vr))) > 0.20 + 1e-6`：NaN 的任何比较都是
    False，`link_probe nav nan 0` 与 `!nav nan 0` 就这样过了闸。现固件对一条 NAV 是无
    条件 `mode = MODE_AUTO`（`firmware/retrofit.c:93` 早退、`:98-101` 四次钳制对 NaN 一
    次都不触发、`:102` 进 AUTO），于是 `cmd_vl` 留成 NaN = 一台既没停车也没跑的车，
    正是 B2 里最难归因的那一类。
    """
    from tools import bench_limits as BL
    nan, inf = float('nan'), float('inf')
    # 非有限 => 判为超限（拒发），两个槽位任一中毒都算
    assert BL.nav_exceeds_bench_limit(nan, 0.0)
    assert BL.nav_exceeds_bench_limit(0.0, nan)
    assert BL.nav_exceeds_bench_limit(inf, 0.0)
    assert BL.nav_exceeds_bench_limit(-inf, 0.0)
    # 不是数字就不是数字：谓词不替调用方猜类型（'0.1' 看着无害，但它没经过入参层）
    assert BL.nav_exceeds_bench_limit('0.1', 0.0)
    assert BL.nav_exceeds_bench_limit(None, 0.0)
    # 超出 f32 范围：`pack_nav` 会抛 struct.error，而调用方是 sys.exit/[TX REFUSED]——
    # 一条可执行的中文理由比一个裸 traceback 有用（这是设计选择，写进谓词 docstring）。
    assert BL.nav_exceeds_bench_limit(1e39, 0.0)
    # 限值以内仍然放行，含 f32 那条留了余量的边界
    assert not BL.nav_exceeds_bench_limit(0.20, 0.20)
    assert not BL.nav_exceeds_bench_limit(0.20 + 1e-7, 0.20)
    assert BL.nav_exceeds_bench_limit(0.21, 0.0)
    # 返回 bool、**不抛**：它是谓词不是校验器（三个调用方各自决定怎么退出）
    assert BL.nav_exceeds_bench_limit(nan, nan) is True
    assert BL.nav_exceeds_bench_limit(0.1, 0.1) is False


def test_directed_broadcast_and_network_targets_are_refused():
    """M-3：`192.168.127.255` 在台架那个 /24 上就是**定向广播**（PC .100、X5 .10），
    后果与被拒的 255.255.255.255 完全一样——一条命令对整个网段上所有会动的板子下指令，
    不能因为它"看着像单播"就放行。`a.b.c.0` 是网络号，不是任何一台主机。"""
    for bad in ('192.168.127.255:9000', '10.0.0.255:9000'):
        with pytest.raises(ValueError) as e:
            bs.resolve_target(bad)
        assert '定向广播' in str(e.value), str(e.value)
    for bad in ('192.168.127.0:9000', '10.0.0.0:9000'):
        with pytest.raises(ValueError) as e:
            bs.resolve_target(bad)
        assert '网络号' in str(e.value), str(e.value)
    for ok in ('192.168.127.10:9000', '192.168.127.100:9000', '127.0.0.1:19124'):
        assert bs.resolve_target(ok) is not None, ok


def test_note_listener_announces_its_own_death(tmp_path, monkeypatch, capsys):
    """M-4：旧写法 `except (EOFError, OSError): pass` 包住整个循环 ⇒ 磁盘满、文件被
    占住时线程**无声退出**，之后的模式跳变与场景标记全丢，而屏幕上什么都看不出来。
    至少喊一声再退（异常本身也不许抛出去吓到人）。"""
    log = _mklog(tmp_path)

    class _Boom:
        def __init__(self):
            self.n = 0

        def readline(self):
            self.n += 1
            if self.n == 1:
                return '场景标记\n'
            raise OSError(28, 'No space left on device')

    monkeypatch.setattr(sys, 'stdin', _Boom())
    bs._note_listener(log, threading.Event(), None, 1)      # 不该把异常抛给调用方
    out = capsys.readouterr().out
    assert 'NOTE LISTENER DEAD' in out, out
    assert 'OSError' in out, '要带上是哪类异常，否则下次还得猜'
    assert '场景标记' in _rows(log)[0]['note'], '死之前那一条要已经落账'
    log.close()


def test_verdict_denominator_is_a_named_keyword():
    """M-6：旧签名第 5 个位置参数叫 `rows`，语义却已经是"**收到的**帧行数"。
    下一个调用方（Task 9 的 D1/D2）照字面传 log.rows（CSV 总行数，含 tx_*/note/gap）
    就会把"一帧都没收到"那一支救活——正是本任务明令防的那件事。
    改名 + 只能按关键字传：写法一错，当场 TypeError，而不是静默给出一条错判据。"""
    import inspect
    params = inspect.signature(bs.verdict).parameters
    assert 'rows' not in params
    assert params['rx_rows'].kind is inspect.Parameter.KEYWORD_ONLY
    with pytest.raises(TypeError):
        bs.verdict(0, 0, 0, 0, 0, 30.0)          # 旧写法：把行数按位置塞进来
    v = bs.verdict(0, 0, 0, 0, 30.0, rx_rows=0, tx_rows=40)
    assert any('一行都没收到' in l for l in v), v
