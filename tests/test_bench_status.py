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
