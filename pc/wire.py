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
]


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
      "允许落刀"。依据是计划 Global Constraints——任何拿不到的量都不得当作满足；
      批 1a 之前固件侧还没有 REJECT_PERMIT，PC 这一关是唯一闸门。
    """
    if state not in HOLDING:
        if state == 'ESTOP':
            return []
        return [(P.TYPE_HEARTBEAT, b'')]

    if not usable or state == 'LIFT':
        vl, vr, tool_mm = 0.0, 0.0, 0.0

    if permit == GATE_N:
        off, lift = 0.0, 0x07
    elif permit == GATE_F:
        off = tool_mm
        lift = 0x00 if (state == 'AUTO' and usable) else 0x07
    else:
        raise ValueError('unknown permit %r' % permit)

    return [(P.TYPE_NAV, P.pack_nav(vl, vr)),
            (P.TYPE_TOOL, P.pack_tool(off, lift))]


def run_log_row(t_rel, fid, state, res, lat_m, lat_comp_m, vl, vr, tool_mm,
                latency_ms, st, feed_snapshot, permit,
                rx_good='', rx_bad='', recv_timeouts='', link_drops=''):
    """按 RUN_LOG_COLUMNS 的顺序拼一行。st 可以是 None（无 STATUS）或 v1 字典。"""
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
    ]
