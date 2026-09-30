# -*- coding: utf-8 -*-
"""tools/bench_status.py 的测试。

重点钉两件事：
1. **字段名必须与生产解析器一致**。写这个工具时我就把 `speed_mps` 误写成 `speed`
   ——同一份 STATUS 字典，抄错键名是 KeyError，而台架上正在跑动的时候没人愿意
   现场调试记录器。这里用真实 `pack_status` 走一遍 `StatusReceiver.handle()`，
   键名一错就红。
2. **静默段要能成对记下来**。B2 的 ④⑤⑦⑧ 场景证据本质就是"从断到停的那几秒"，
   gap_start / gap_end 不成对，回来就对不上时间轴。
"""
import os
import time

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
