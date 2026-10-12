# -*- coding: utf-8 -*-
"""E3 契约 §5.1/§5.3：这一拍往线上发什么帧，由"是否持权"决定，不由视觉决定。

抽成独立模块的理由：原来的判定散在 pc/main.py 的三个分支里
（:243 AUTO+usable / :253 LIFT / :261 else），"AUTO 但这一帧不可用且未满 2 秒"
会掉进 else 发 HEARTBEAT，固件收到心跳就把权限交回遥控（retrofit.c:70-73），
而 PC 状态与 run_log 仍写着 AUTO —— 这就是 codex 新发现一。
纯函数化之后这条规则可以被单测钉住。
"""
from common import protocol as P

# 执行许可位（spec §2 / A5）：编译期常量在固件侧，这里是 PC 侧镜像，
# 只决定"PC 该发什么"；两边不一致时以固件为准（固件会 reject=REJECT_PERMIT）。
GATE_N = 1     # 只许沿行空跑：刀强制提、横移强制禁
GATE_F = 2     # 允许落刀作业与横移

PERMIT_BY_NAME = {'gate_n': GATE_N, 'gate_f': GATE_F}

# 持权的 PC 状态。ESTOP 不持权（谁都不能动），MANUAL 是遥控持权。
HOLDING = ('AUTO', 'LIFT')

RUN_LOG_COLUMNS = [
    't', 'frame_id', 'state', 'status', 'lat_m', 'lat_comp_m',
    'vL', 'vR', 'tool_mm', 'conf', 'latency_ms',
    'mcu_mode', 'batt_v', 'rx_good', 'rx_bad',
    'frame_age_s', 'recv_timeouts', 'link_drops',
    # ---- E3 新增（spec §5.4）----
    'profile', 'authority', 'reject', 'loop_alive', 'build_id', 'permit',
    # ---- E3 Task 6 fix round 1 / I-6：L1 降级事件计数（spec §5.2）----
    # 追加在**末尾**：前面各列的下标不变，按位置读日志的旧消费者不受影响。
    'l1_events',
    # ---- T2（2026-10-12 台架就绪）：这一拍 PC 真发上线的帧型 ----
    # 同样追加在**末尾**，跟着上面那条规矩走。§4B 的 C2 与 C18 要靠它把
    # "线上只有 HEARTBEAT""交回之后 PC 还在发"从旁证升成字节级证据，
    # 所以取值是帧型串而不是计数。列名快照与位置判据在 tests/test_wire.py。
    'tx_frames',
]

# HUD 用的 ASCII 短码（fix round 1 I-4）。cv2.putText 画不出 CJK——
# protocol.REJECT_TEXT 那串中文进了 HUD 就是一排方框，比不显示还难排障；
# 所以进 HUD 的是短码，CSV 的 reject 列存的是**数字码**。中文全文目前**没有**生产
# 调用点（`status_rx.reject_text()` 只有单测在调，`pc/main.py` 的 stdout 也没打它；
# 打整句的是 `tools/link_probe.py`，它读的是 `protocol.REJECT_TEXT` 那本字典）——
# spec §5.4 那句"人话"按批 1b 的收口口径是「已编码 + 待联调」。短码仍然是"人话"，
# **不是十六进制**（spec §5.4 明令）。表与 protocol 的 REJECT_* 常量一一对应；将来固件加了
# 新原因码而这里缺项时，reject_short() 给可见的 UNKNOWN-<十进制> 兜底，
# 不抛、也不静默变空。
REJECT_SHORT = {
    P.REJECT_NONE: '',
    P.REJECT_PROFILE: 'PROFILE',
    P.REJECT_RCS_STALE: 'RCS-STALE',
    P.REJECT_FIELD_SWITCH: 'FIELD-SWITCH',
    P.REJECT_ESTOP_LATCHED: 'ESTOP-LATCH',
    P.REJECT_LOOP_STALLED: 'LOOP-STALLED',
    P.REJECT_NOT_IMPL: 'NOT-IMPL',
    P.REJECT_FIELD_LATCHED: 'FIELD-LATCH',
    P.REJECT_PERMIT: 'PERMIT',
}


def reject_short(code):
    """拒绝码 -> HUD 短码。None（v1 固件没有这个字段）给空串 = 不显示；
    未知码给 UNKNOWN-<十进制> = 显示"有个说不清的拒绝"，绝不装作没事。"""
    if code is None:
        return ''
    return REJECT_SHORT.get(code, 'UNKNOWN-%d' % code)


def frames_for_state(state, usable, vl, vr, tool_mm, permit=GATE_N):
    """返回 [(frame_type, payload), ...]。

    规则（spec §5.1 表）：
      - 持权（AUTO/LIFT）→ 必须发 NAV+TOOL，**永不发 HEARTBEAT**；
        视觉不可用或处于 LIFT 时速度锁零、刀位提刀。
      - MANUAL → 只发 HEARTBEAT。
      - ESTOP → 稳态不发帧（跳变那一拍由调用方发一次 ESTOP 帧）。
    许可位（spec §5.3）：GATE_N 下横移恒 0、刀位恒 0x07；
      GATE_F 下只有 "AUTO 且视觉可用" 才允许落刀（lift=0）。
    未知许可位一律 ValueError（fail-closed）：0 / None / '' / 名字串都不等于
      "允许落刀"。依据 = `docs/superpowers/plans/2026-10-08-e3-batch-1a-firmware.md:18`
      那条 fail-closed 约束（"任何拿不到的量都不得当作满足"）——**那句是给固件写的**，
      批 1b 计划的 Global Constraints 里没有它；PC 侧照搬是 E3 批 1b 的任务内决定。
      批 1a 之前固件侧还没有 REJECT_PERMIT，PC 这一关是唯一闸门。
      校验在**函数入口**、对**每个状态**都做（Task 3 审查第 3 条）：旧实现只在
      持权分支里抛，MANUAL/ESTOP 先 return，于是"permit 配错了"这件事在非持权
      状态下静默通过，而文案写的是"一律"。pc/main.py 每个状态都显式传 permit，
      配错就是配错，不该等到进 AUTO 才炸。ESTOP 的既有语义不变：合法 permit 下
      稳态仍然返回 []（一帧不发）。
    """
    if permit not in (GATE_N, GATE_F):
        raise ValueError('unknown permit %r' % permit)

    if state not in HOLDING:
        if state == 'ESTOP':
            return []
        return [(P.TYPE_HEARTBEAT, b'')]

    if not usable or state == 'LIFT':
        vl, vr, tool_mm = 0.0, 0.0, 0.0

    if permit == GATE_N:
        off, lift = 0.0, 0x07
    else:                       # 入口已校验过，这里只剩 GATE_F
        off = tool_mm
        lift = 0x00 if (state == 'AUTO' and usable) else 0x07

    return [(P.TYPE_NAV, P.pack_nav(vl, vr)),
            (P.TYPE_TOOL, P.pack_tool(off, lift))]


# 帧型 → 本列用的短名。与 REJECT_SHORT 同一个理由：CSV 与 HUD 都要 ASCII，
# 而 `NAV+TOOL` 这种写法能直接对上 frames_for_state() 的返回顺序。
TX_FRAME_NAMES = {
    P.TYPE_NAV: 'NAV',
    P.TYPE_TOOL: 'TOOL',
    P.TYPE_HEARTBEAT: 'HB',
    P.TYPE_ESTOP: 'ESTOP',
    P.TYPE_MODE: 'MODE',
}


def tx_frames_text(ftypes):
    """把这一拍**真的写进 socket** 的帧型拼成一列文本：`NAV+TOOL` / `HB` / `-`。

    `'-'` 的意思是"这一拍线上确实一个字节都没有"——ESTOP 稳态是这种（E3 §5.1：
    稳态由 `frames_for_state('ESTOP', …)` 返回空列表，ESTOP 帧只在跳变那一拍发一次），
    回放模式也是这种（`pc/main.py` 的 `send()` 在 `sock is None` 时直接 return）。
    **它不是缺数据**：写成空串就会让人把"急停稳态的静默"当"日志坏了"，
    而把回放写成 `NAV+TOOL` 更糟——那是在给"这帧上线过"造一条假证据
    （spec §6.1 点名的就是这个形状：工具伪装成被测机制）。

    认不出的帧型原样给数字，不替它编名字。
    """
    if not ftypes:
        return '-'
    return '+'.join(TX_FRAME_NAMES.get(t, str(t)) for t in ftypes)


def run_log_row(t_rel, fid, state, res, lat_m, lat_comp_m, vl, vr, tool_mm,
                latency_ms, st, feed_snapshot, permit,
                rx_good='', rx_bad='', recv_timeouts='', link_drops='',
                l1_events=0, tx_frames='-'):
    """按 RUN_LOG_COLUMNS 的顺序拼一行。st 可以是 None（无 STATUS）或 v1 字典。

    l1_events 是**累计的 L1 降级事件数**（spec §5.2，I-6），由调用方维护，
    这里只负责落到自己那一列（10-12 的 T2 之后末位是 tx_frames，它不再是末位）。它写整数而不是空串：这一列的用法是"求和/看趋势"，
    空串会让读日志的人把"没有降级"和"没接线"混成一回事。默认 0 = "没进入过 L1"，
    与 main 的初始值同一个语义。

    `tx_frames` 是这一拍**真的写进 socket** 的帧型串（T2），由调用方从 `send()`
    的出口收集；缺省 `'-'` = "这一拍线上一个字节都没有"，含义与上面 `l1_events`
    那句一样：不能拿空串当"没接线"，也不能拿它当"发过了"。
    """
    st = st or {}
    _feed, _seq, age = feed_snapshot if feed_snapshot else ({}, 0, None)

    def _e3(key):
        v = st.get(key)
        return '' if v is None else v

    return [
        '%.3f' % t_rel, fid, state,
        res.get('status', ''),
        '' if lat_m is None else '%.4f' % lat_m,
        '' if lat_comp_m is None else '%.4f' % lat_comp_m,
        '%.3f' % vl, '%.3f' % vr, '%.2f' % tool_mm,
        '%.3f' % res.get('confidence', 0.0),
        '%.1f' % latency_ms,
        st.get('mode', ''),
        '%.2f' % st['battery_v'] if 'battery_v' in st else '',
        rx_good, rx_bad,
        '' if age is None else '%.3f' % age,
        recv_timeouts, link_drops,
        _e3('profile'), _e3('authority'), _e3('reject'),
        _e3('loop_alive'), _e3('build_id'), permit,
        '%d' % l1_events,
        tx_frames,
    ]
