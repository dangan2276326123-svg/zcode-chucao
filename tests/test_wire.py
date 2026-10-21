# -*- coding: utf-8 -*-
"""E3 §5.1/§5.3：线上语义由"是否持权"决定，不由视觉决定。"""
import pytest

from common import protocol as P
from pc import wire


def _kinds(frames):
    return [f[0] for f in frames]


def test_manual_emits_only_heartbeat():
    frames = wire.frames_for_state('MANUAL', True, 0.2, 0.2, 5.0)
    assert _kinds(frames) == [P.TYPE_HEARTBEAT]


def test_auto_with_vision_emits_nav_and_tool():
    frames = wire.frames_for_state('AUTO', True, 0.14, 0.14, 3.0, wire.GATE_F)
    assert _kinds(frames) == [P.TYPE_NAV, P.TYPE_TOOL]
    # 线上 NAV 是 float32（pack_nav '<ff'），0.14 落不进精确值，故用 approx
    # ——与 tests/test_protocol.py:25 同一口径。
    assert P.unpack_nav(frames[0][1])[:2] == pytest.approx((0.14, 0.14))


def test_auto_without_vision_still_holds_authority():
    """codex 新发现一的正解：这一拍不许掉到 HEARTBEAT。"""
    frames = wire.frames_for_state('AUTO', False, 0.14, 0.14, 3.0)
    assert P.TYPE_HEARTBEAT not in _kinds(frames)
    assert _kinds(frames) == [P.TYPE_NAV, P.TYPE_TOOL]
    vl, vr, _flags = P.unpack_nav(frames[0][1])
    assert (vl, vr) == (0.0, 0.0)          # 速度锁零
    off, lift = P.unpack_tool(frames[1][1])
    assert off == 0.0 and lift == 0x07     # 提刀


def test_gate_n_forces_knives_up_and_no_lateral_even_in_auto():
    """Pc-8 的正解：门 N 下 AUTO 也只发提刀、横移恒 0。"""
    frames = wire.frames_for_state('AUTO', True, 0.14, 0.12, -8.0, wire.GATE_N)
    off, lift = P.unpack_tool(frames[1][1])
    assert off == 0.0 and lift == 0x07


def test_gate_f_allows_knives_down_only_when_auto_and_usable():
    down = wire.frames_for_state('AUTO', True, 0.1, 0.1, 2.0, wire.GATE_F)
    assert P.unpack_tool(down[1][1]) == (2.0, 0x00)
    # 同样 GATE_F，但视觉不可用 -> 仍然提刀、速度零
    up = wire.frames_for_state('AUTO', False, 0.1, 0.1, 2.0, wire.GATE_F)
    assert P.unpack_nav(up[0][1])[:2] == (0.0, 0.0)
    assert P.unpack_tool(up[1][1]) == (0.0, 0x07)


# 审查 Important #1（任务审查 a1579e8）：permit 是本任务唯一的"执行许可"闸门。
# 旧实现 `if permit == GATE_N: ... else: <GATE_F 语义>` 是 fail-open——实测
# permit=0 / None / 'gate_f' / 'gate_n'（字符串）全都返回 TOOL(off=5.0, lift=0x00)，
# 也就是门 N 的样机静默落刀 + 横移，而固件侧的 REJECT_PERMIT 要到批 1a 烧录后才存在。
# 计划 Global Constraints 写的是"任何拿不到的量都不得当作满足 / fail-closed"，
# 所以这里不猜：未知许可位一律 ValueError。（数值上等于 1/2 的 1.0/2.0/True 仍按
# 相等的档位处理，因为那是 Python 的 ==，不是本模块的宽容。）
@pytest.mark.parametrize('permit',
                         [0, None, '', 3, -1, 2.5, 'gate_n', 'gate_f', 'GATE_F'])
def test_unknown_permit_is_rejected_not_read_as_gate_f(permit):
    with pytest.raises(ValueError):
        wire.frames_for_state('AUTO', True, 0.2, 0.2, 5.0, permit)


def test_lift_state_holds_authority_with_zero_speed():
    frames = wire.frames_for_state('LIFT', False, 0.0, 0.0, 0.0, wire.GATE_F)
    assert _kinds(frames) == [P.TYPE_NAV, P.TYPE_TOOL]
    assert P.unpack_tool(frames[1][1]) == (0.0, 0x07)
    # 审查 Important #2（任务审查 a1579e8）：上面传的仍是 usable=False，于是
    # "LIFT 专属保护"零覆盖——把 wire.py 的 `or state == 'LIFT'` 删掉，或把
    # `lift = 0x00 if (state == 'AUTO' and usable)` 削成 `if usable`，10 条全绿
    # （变异验证见 task-2-report.md「fix round 1」）。而 usable=True 的 LIFT 在现网
    # 可达：pc/main.py 从未调用 vision_ok()，视觉恢复后状态会停在 LIFT 且 usable 为真。
    # 测试名叫 ..._with_zero_speed，就必须真的查 NAV 速度——下面把两条都钉住。
    held = wire.frames_for_state('LIFT', True, 0.2, 0.2, 5.0, wire.GATE_F)
    assert _kinds(held) == [P.TYPE_NAV, P.TYPE_TOOL]
    assert P.unpack_nav(held[0][1])[:2] == (0.0, 0.0)   # 速度锁零
    assert P.unpack_tool(held[1][1]) == (0.0, 0x07)     # 刀锁提


def test_estop_emits_nothing_every_beat():
    """ESTOP 帧只在状态跳变那一拍由 main.py 发一次，稳态不发帧。"""
    assert wire.frames_for_state('ESTOP', True, 0.0, 0.0, 0.0) == []


def test_run_log_columns_cover_the_e3_fields():
    for col in ('profile', 'mcu_mode', 'authority', 'reject',
                'loop_alive', 'build_id', 'permit'):
        assert col in wire.RUN_LOG_COLUMNS


def test_run_log_row_matches_column_count():
    st = {'seq': 3, 'speed_mps': 0.0, 'current_a': 0.0, 'battery_v': 48.0,
          'limits': 0, 'mode': 1, 'profile': 2, 'authority': 1,
          'loop_alive': 9, 'build_id': 0x3A, 'reject': 0, 'v': 2}
    res = {'status': 'dual', 'confidence': 0.5, 'lateral_px': 3.0}
    row = wire.run_log_row(1.0, 7, 'AUTO', res, 0.01, 0.02, 0.1, 0.1, 0.0,
                           12.0, st, ({}, 0, None), wire.GATE_N)
    assert len(row) == len(wire.RUN_LOG_COLUMNS)


def test_run_log_row_tolerates_v1_status_and_no_status():
    res = {'status': 'none', 'confidence': 0.0, 'lateral_px': None}
    row_none = wire.run_log_row(1.0, 1, 'MANUAL', res, 0.0, 0.0, 0.0, 0.0,
                                0.0, 5.0, None, ({}, 0, None), wire.GATE_N)
    row_v1 = wire.run_log_row(1.0, 2, 'MANUAL', res, 0.0, 0.0, 0.0, 0.0,
                              0.0, 5.0, {'seq': 1, 'mode': 0, 'v': 1},
                              ({}, 0, None), wire.GATE_N)
    assert len(row_none) == len(row_v1) == len(wire.RUN_LOG_COLUMNS)


# ---- Task 6 前置（Task 3 审查第 3 条）：许可位校验提到函数入口 ----
@pytest.mark.parametrize('state', ['MANUAL', 'ESTOP', 'LIFT', 'AUTO'])
def test_permit_is_validated_at_the_entry_for_every_state(state):
    """docstring 写的是"未知许可位一律 ValueError"，旧实现只在**持权分支**里抛：
    MANUAL/ESTOP 先 return，配错的 permit 在这两个状态下静默通过。
    main.py 现在每个状态都显式传 permit，所以 fail-closed 的位置必须与文案一致。
    """
    for bad in (0, None, '', 3, 'gate_n', 'gate_f'):
        with pytest.raises(ValueError):
            wire.frames_for_state(state, True, 0.1, 0.1, 1.0, bad)


def test_estop_still_emits_nothing_for_both_valid_permits():
    """上提校验不许改掉 ESTOP 的既有语义：合法 permit 下 ESTOP 稳态仍是**不发帧**
    （ESTOP 帧由调用方在跳变那一拍发一次）。"""
    assert wire.frames_for_state('ESTOP', True, 0.0, 0.0, 0.0, wire.GATE_N) == []
    assert wire.frames_for_state('ESTOP', False, 0.0, 0.0, 0.0, wire.GATE_F) == []


# ---- Task 6 fix round 1：I-6 的新列 + I-4 的 HUD 短码表（wire 层的那一半）----
def test_run_log_row_carries_l1_events_and_reject_short_codes():
    """l1_events 是第 25 列（控制器批准的偏差），reject_short 是 HUD 的 ASCII 短码表。

    两件事都在 wire 层钉：列数与**默认值**。默认给 0 而不是空串——"这一列没接线"
    和"这一趟没降级"必须是两件能区分的事，而读日志的人只会看到一格空白或一个 0。
    短码表覆盖 protocol 的每一个 REJECT_* 常量（缺项就走 UNKNOWN-<十进制> 兜底：
    宁可显示一条说不清的拒绝，也不静默变空），且全是 ASCII——cv2.putText 画不出
    中文。CSV 的 reject 列存的是**数字码**；中文全文（`common/protocol.py:REJECT_TEXT`）
    目前没有生产调用点，只有 `tools/link_probe.py` 在 stdout 打整句。
    """
    assert 'l1_events' in wire.RUN_LOG_COLUMNS
    assert wire.RUN_LOG_COLUMNS[-6] == 'l1_events'   # 五次追加（tx_frames、nav_flags、beat_gap_s、vehicle_tag、veh_speed_mps）之后
    res = {'status': 'left_only', 'confidence': 0.9, 'lateral_px': 3.0}
    _args = (1.0, 7, 'AUTO', res, 0.01, 0.02, 0.07, 0.07, 0.0, 12.0, None,
             ({}, 0, None), wire.GATE_N)
    row = wire.run_log_row(*_args)
    assert len(row) == len(wire.RUN_LOG_COLUMNS)     # 列数由 test_tx_frames_is_appended_* 那条按快照钉
    col = wire.RUN_LOG_COLUMNS.index('l1_events')
    assert row[col] == '0'
    assert wire.run_log_row(*_args, l1_events=3)[col] == '3'

    # 按 protocol 里的常量表枚举，不再手写名单：10-14 加 REJECT_GEAR 时，手写名单
    # 会安静地漏掉新码，而漏掉的码正是现场最需要看得懂的那一个。
    for code in sorted(v for k, v in vars(P).items()
                         if k.startswith('REJECT_') and isinstance(v, int)
                         and v != P.REJECT_NONE):   # NONE 的短码按设计是空串，由下面单独钉
        # isinstance 这一道不可省：`REJECT_TEXT` 也是 REJECT_* 开头的名字，
        # 把它当码喂进去，短码表只会回 UNKNOWN-<dict> —— 那是自造的红，不是缺陷。
        short = wire.reject_short(code)
        assert short and short == short.upper()
        assert all(ord(c) < 128 for c in short)
        assert len(short) <= 12            # 单片段过长的话 HUD 那一行就折不开了
    assert wire.reject_short(P.REJECT_NONE) == ''      # 没有拒绝 = 不占一行
    assert wire.reject_short(None) == ''               # v1 固件没这个字段
    assert wire.reject_short(200) == 'UNKNOWN-200'     # 未知码：可见兜底，不是空


# ---- T2（docs/superpowers/specs/2026-10-12-bench-readiness-sync-design.md §4）----
# `tx_frames` **追加之前**的列名快照。这张表是"位置契约"的锚：判据是
# "前 len(快照) 列与快照逐个相等、且总长恰好多 1"，而不是把列数写死在断言里。
# 为什么需要锚而不是靠人眼看 diff：`pc/wire.py` 的注释自己写着"前面各列的下标不变，
# 按位置读日志的旧消费者不受影响"，而这句话一旦被破坏，**没有任何一条既有测试会红**
# （既有测试全部按列名取数）。
_PRE_TX_FRAMES_COLUMNS = [
    't', 'frame_id', 'state', 'status', 'lat_m', 'lat_comp_m',
    'vL', 'vR', 'tool_mm', 'conf', 'latency_ms',
    'mcu_mode', 'batt_v', 'rx_good', 'rx_bad',
    'frame_age_s', 'recv_timeouts', 'link_drops',
    'profile', 'authority', 'reject', 'loop_alive', 'build_id', 'permit',
    'l1_events',
]


def test_tx_frames_is_appended_without_moving_earlier_columns():
    """位置锚：前 n 列一字不动，之后每追加一列只许往末尾挂。

    10-14 手操档位又追加了一列 `nav_flags` ⇒ 这里从 `n + 1` 改成 `n + 2`、
    `tx_frames` 从末位让到倒数第二。10-15（台账 Pc-10）再加 `vehicle_tag` ⇒ `n + 4`。
    **改的是锚，不是历史**：快照本身没动，
    所以"前面那些列的列位被动过"这种破坏照样会红。
    """
    n = len(_PRE_TX_FRAMES_COLUMNS)
    assert wire.RUN_LOG_COLUMNS[:n] == _PRE_TX_FRAMES_COLUMNS
    assert len(wire.RUN_LOG_COLUMNS) == n + 5
    assert wire.RUN_LOG_COLUMNS[-5] == 'tx_frames'
    assert wire.RUN_LOG_COLUMNS[-4] == 'nav_flags'
    assert wire.RUN_LOG_COLUMNS[-3] == 'beat_gap_s'
    assert wire.RUN_LOG_COLUMNS[-2] == 'vehicle_tag'
    assert wire.RUN_LOG_COLUMNS[-1] == 'veh_speed_mps'


def test_run_log_row_puts_tx_frames_last_and_defaults_to_the_silent_marker():
    """缺省 `'-'` 的含义是"这一拍线上确实一个字节都没走"，**不是缺数据**。

    ESTOP 稳态与回放模式都是这种。把它写成空串，读日志的人就会把"急停稳态的
    静默"当"日志坏了"；反过来把它写成 `NAV+TOOL`，回放模式就会声称发过东西。
    """
    res = {'status': 'dual', 'confidence': 0.9, 'lateral_px': 3.0}
    args = (1.0, 7, 'AUTO', res, 0.01, 0.02, 0.07, 0.07, 0.0, 12.0, None,
            ({}, 0, None), wire.GATE_N)
    row = wire.run_log_row(*args)
    assert len(row) == len(wire.RUN_LOG_COLUMNS)
    # 按列名取，不按末位算偏移：10-15 加 `vehicle_tag` 之后，这里原来写的
    # `len(...) - 3` 会静默指到 `nav_flags` 上——偏移量是会被追加吃掉的，
    # 而这条测试的本意是"tx_frames 的缺省值是 '-'（线上真的一个字节都没有）"。
    i = wire.RUN_LOG_COLUMNS.index('tx_frames')
    assert row[i] == '-'
    assert wire.run_log_row(*args, tx_frames='NAV+TOOL')[i] == 'NAV+TOOL'
    assert row[wire.RUN_LOG_COLUMNS.index('nav_flags')] == ''   # 非手操拍留空，不写 0


def test_tx_frames_text_names_each_frame_type():
    assert wire.tx_frames_text([]) == '-'
    assert wire.tx_frames_text([P.TYPE_HEARTBEAT]) == 'HB'
    assert wire.tx_frames_text([P.TYPE_NAV, P.TYPE_TOOL]) == 'NAV+TOOL'
    assert wire.tx_frames_text([P.TYPE_ESTOP]) == 'ESTOP'
    assert wire.tx_frames_text([P.TYPE_MODE]) == 'MODE'
    # 认不出的帧型原样给数字，不替它编名字（与 wire.REJECT_SHORT 同一口径）。
    assert wire.tx_frames_text([99]) == '99'
    assert wire.tx_frames_text([P.TYPE_TOOL, P.TYPE_NAV]) == 'TOOL+NAV'


# ---------- 台账 Pc-10（2026-10-15）：run_log 的车型列 ----------

def test_vehicle_tag_lands_in_its_own_column():
    """传了就落在 `vehicle_tag` 那一列，且不影响任何前面的列位。"""
    res = {'status': 'dual', 'confidence': 0.9, 'lateral_px': 3.0}
    args = (1.0, 7, 'AUTO', res, 0.01, 0.02, 0.07, 0.07, 0.0, 12.0, None,
            ({}, 0, None), wire.GATE_N)
    row = wire.run_log_row(*args, vehicle_tag='prototype')
    assert len(row) == len(wire.RUN_LOG_COLUMNS)
    assert row[wire.RUN_LOG_COLUMNS.index('vehicle_tag')] == 'prototype'


def test_vehicle_tag_defaults_to_empty_not_a_guess():
    """没接线时留**空串**，不填 'unknown'、不填 'prev'。

    空串一眼就是"这一版程序没把它接上"；而任何具体默认值都会伪装成"记过了"，
    事后无法与真记了的区分——那正是取消档案握手后唯一不能发生的事
    （v1.0 §4.1：认不出车，"横向数据不得跨车引用"这条规则就无法执行）。
    """
    res = {'status': 'dual', 'confidence': 0.9, 'lateral_px': 3.0}
    args = (1.0, 7, 'AUTO', res, 0.01, 0.02, 0.07, 0.07, 0.0, 12.0, None,
            ({}, 0, None), wire.GATE_N)
    row = wire.run_log_row(*args)
    assert row[wire.RUN_LOG_COLUMNS.index('vehicle_tag')] == ''


def test_veh_speed_column_is_last_and_reads_status_wheel_speed():
    """末列 `veh_speed_mps` = STATUS 回读的车载轮速；**没 STATUS 时留空，不写 0**。

    这一列是 C25/C26 的测量手段（10-21）：表里原来只有 PC **给定**的 vL/vR，
    车**测到**的速度（TIM3 四轮均值，`STATUS` 载荷第 0-3 字节）没有落表，
    所以"按下 `[E]` 到真停住"这段时间只能靠肉眼，作者当场报"测不出来"。
    派生写在 `run_log_row` 里而不是调用处，跟 `batt_v`/`mcu_mode` 同一套路——
    数据源只有一个（`st`），不许两处各读一遍。
    """
    assert wire.RUN_LOG_COLUMNS[-1] == 'veh_speed_mps'
    base = (1.0, 7, 'TELEOP', {'status': 'dual', 'confidence': 0.9, 'lateral_px': 3.0},
            0.01, 0.02, 0.2, 0.2, 0.0, 12.0, None, ({}, 0, None), wire.GATE_N)
    row = wire.run_log_row(*base)
    assert row[-1] == '', "没 STATUS 的一拍要留空——0 会被读成'车停着'，而当时可能只是没接线"
    v1 = {'speed_mps': 0.152, 'current_a': 1.0, 'battery_v': 12.0, 'limits': 0,
          'mode': 3, 'v': 1}
    with_v1 = wire.run_log_row(*(base[:10] + (v1,) + base[11:]))
    assert with_v1[-1] == '0.152'
    v2 = dict(v1, profile=1, authority=1, loop_alive=42, build_id=100, reject=0)
    assert wire.run_log_row(*(base[:10] + (v2,) + base[11:]))[-1] == '0.152'
    # v1 那台旧固件也带 speed：不许因为它没有 E3 那五个键就把这一格留空。
    # （顺带记一口真实形状：`mcu_mode` 那一列存的是**原始 int**，由 csv writer 转字符串，
    #  与新加的 `veh_speed_mps`（在 wire 里就格式化成串）不同——这是既有行为，本批不统一。）
    assert with_v1[wire.RUN_LOG_COLUMNS.index('mcu_mode')] == 3
