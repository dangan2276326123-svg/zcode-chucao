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
# TELEOP（2026-10-13 手操档）必须在持权名单里：漏了它，手操期间这一拍会掉进
# else 发 HEARTBEAT，而固件收心跳就把权限交回遥控——PC 屏幕写着手操、车上其实是遥控，
# 那正是 E3 契约记过的"codex 新发现一"的形状，不许在这里重犯一遍。
HOLDING = ('AUTO', 'TELEOP', 'LIFT')

# 手操档的速度包络（spec §5，作者 10-13 当场定 0.1；**同日台架真机后改 0.2**：
# 0.1 m/s = 每秒 10 cm，落地带动力推不动这台 3.25 m 的上代车——命令层 CSV 里
# 连续 350 拍都是 0.100，轮子只转了一下、车没行走。改判留痕见 spec §5 与台账 §4）。
# 这个值 PC 与固件**各写一份**（另一份是 `retrofit.h:RETRO_TELEOP_MAX`），只改一层
# 必然无效：PC 发 0.2 会被固件钳回 0.1。两边不许漂，由 tests/test_teleop.py 里
# test_teleop_cap_matches_the_firmware_constant 钉住。
# 钳位放在**发帧层**而不是调用方：线上来什么速度不能假定发送方自觉。
# 第一阶段只放前进，负值钳成 0——四轮行走方向那张实测表没填完之前，
# "给负值四轮是不是真反、左右对不对称"没有任何凭据（Hw-26/27 的复位循环
# 已经把行走方向的定案作废过一次）。
TELEOP_MAX_MPS = 0.2
TELEOP_NEGATIVE_LOCKED = True

# 松手归零的超时（spec §4）。cv2.waitKey 在按住时靠系统重复投递，"松开"没有可靠事件，
# 所以这里按"最后一次按键距今多久"判：超过这个窗口就归零。
# ⚠️ 这个值**还没在真机上量过**（spec §12 第一行），100 ms 是设计初值而不是标定值。
TELEOP_HOLD_S = 0.1

# ---- 手操转向档位（2026-10-14 加，走 NAV 载荷里那个一直没人读的 flags 字节） ----
# 低 2 bit 是档位：0 直行 / 1 左 / 2 右 / 3 横移（四轮同角）。作者 10-14 裁定：先按上代车跑，
# 看现场表现再改，所以本批放开 3；未知档位（4 及以上）折回直行这条不跟着放开。
# 档位→四轮转角落在固件 `main.c` 的 TELEOP 分支。**10-15 按厂商活通路订正过形状**：左右档是
# 「一对前轮同一符号」（`path_plan.c:651-681` 左转时两个前角都为正），不是 10-14 抄的那对 ±20
# （`path_plan.c:97-110` 是油门关断时的残留，它注释里「前轮/后轮转向」实为「前进/后退」）。
# 横移档形状没变——厂商斜行 `path_plan.c:920-927` 也是四角同值，但它自己注明「不是理论的高速
# 斜行」；真 90° 平移要连四轮速度一起重排。数值仍不是按真实轮距/轴距算的（实测 B=3010 /
# L=1620，固件常数对不上，见 Hw-23）⇒ 这一档现在跑出来是「斜行 20 度」，不是 90 度平移。
GEAR_STRAIGHT = 0
GEAR_LEFT = 1
GEAR_RIGHT = 2
GEAR_LATERAL = 3            # 保留，本批不可用
GEAR_NAMES = {GEAR_STRAIGHT: 'STRAIGHT', GEAR_LEFT: 'LEFT',
              GEAR_RIGHT: 'RIGHT', GEAR_LATERAL: 'LATERAL'}
GEAR_MAX = GEAR_LATERAL       # > 这个值 = 未知或保留，一律 fail-closed 到直行


def gear_text(gear):
    return GEAR_NAMES.get(gear, 'UNKNOWN-%d' % gear)


_GEAR_CYCLE = (GEAR_STRAIGHT, GEAR_LEFT, GEAR_RIGHT, GEAR_LATERAL)


def cycle_gear(gear):
    """`g` 键循环：直行 -> 左 -> 右 -> 横移 -> 直行（作者 10-14 放开横移档）。

    不认识的值一律回到直行，不顺着往下走——按键的人手一抖就该回到最保守那一档。
    """
    if gear not in _GEAR_CYCLE:
        return GEAR_STRAIGHT
    return _GEAR_CYCLE[(_GEAR_CYCLE.index(gear) + 1) % len(_GEAR_CYCLE)]


# 手操键位 → (左轮, 右轮)。第一阶段不配后退键：按了不动比"能按"更容易被读成坏了。
_TELEOP_KEY_SPEEDS = {
    'w': (TELEOP_MAX_MPS, TELEOP_MAX_MPS),   # 直行前进
    's': (0.0, TELEOP_MAX_MPS),              # 左转（差速，不是转角）
    'd': (TELEOP_MAX_MPS, 0.0),              # 右转
}


def teleop_speeds(key, held_s):
    """把"按住哪个键 + 按住多久"翻成两侧轮速。纯函数，好单测。

    没有匹配键、或按键已超出 `TELEOP_HOLD_S` 窗口 ⇒ (0, 0)。
    **不用松开事件**：那会让车在事件丢失时多走一段，而那一段在田间是压苗。
    """
    if key is None or held_s is None or held_s > TELEOP_HOLD_S:
        return 0.0, 0.0
    return _TELEOP_KEY_SPEEDS.get(key, (0.0, 0.0))


def clamp_teleop(v):
    """手操速度钳位：上限 TELEOP_MAX_MPS（0.2），第一阶段负值钳成 0。"""
    v = min(v, TELEOP_MAX_MPS)
    if TELEOP_NEGATIVE_LOCKED:
        v = max(v, 0.0)
    return v


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
    # ---- 2026-10-14 手操转向档位：这一拍发出去的 NAV.flags ----
    # 仍然追加在末尾。没有这一列，事后无法区分"按了 g 但车没转"与"g 根本没发出去"。
    'nav_flags',
    # ---- 2026-10-14 台架停拍追查：这一拍距上一拍隔了多久（秒，未钳位） ----
    # 停拍期间一行都不写，所以这一列是**停拍之后那一行**才变大；它把"靠 t 差分
    # 反推"升成"表里的记录"。回放/第一拍留空，不写 0（0 会读成"节拍完美"）。
    'beat_gap_s',
    # ---- 台账 Pc-10（2026-10-15）：这一行的数据属于哪台车 ----
    # 仍然追加在末尾，跟着上面那条位置规矩走。加它的理由不是补功能，是**补回一件
    # 被取消的东西**：作者同日裁定取消 E3 的车辆档案握手（`MODE(0x20)`／`PROFILE_ID`／
    # `REJ_PROFILE`），但 v1.0 §4.1 那条"凡横向指标不得跨车引用"仍然成立——上代车
    # 轮距 301 cm、样机 191 cm，两批横向数据一旦混在同一张 CSV 里就再也分不开。
    # 握手砍掉之后，这一列是唯一的凭据，所以它的值来自 config（PC 侧），
    # 不依赖固件回传，也不参与任何准入判定。
    'vehicle_tag',
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
    P.REJECT_GEAR: 'GEAR',
}


def reject_short(code):
    """拒绝码 -> HUD 短码。None（v1 固件没有这个字段）给空串 = 不显示；
    未知码给 UNKNOWN-<十进制> = 显示"有个说不清的拒绝"，绝不装作没事。"""
    if code is None:
        return ''
    return REJECT_SHORT.get(code, 'UNKNOWN-%d' % code)


def frames_for_state(state, usable, vl, vr, tool_mm, permit=GATE_N, gear=GEAR_STRAIGHT):
    """返回 [(frame_type, payload), ...]。

    规则（spec §5.1 表）：
      - 持权（AUTO/TELEOP/LIFT）→ 必须发 NAV+TOOL，**永不发 HEARTBEAT**；
        AUTO/LIFT 在视觉不可用或处于 LIFT 时速度锁零、刀位提刀；
        **TELEOP 不锁零**（速度来自人，见 2026-10-13 手操 spec §2），且刀/横移绑死门 N。
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

    if state == 'TELEOP':
        # 档位进 NAV 的 flags 字节。未知/保留档位在这里就折回直行 —— 发出去的那一帧
        # 永远只带 0/1/2，固件侧还有一道同样的检查，两层各不自责（与限速两层同钳同理）。
        nav_gear = gear if gear in (GEAR_STRAIGHT, GEAR_LEFT, GEAR_RIGHT,
                              GEAR_LATERAL) else GEAR_STRAIGHT
        # 手操档（2026-10-13 spec §2/§5，作者 B3/B4）：
        #   速度来自**人按住的那个键**，所以 `usable` 不参与锁零——把 AUTO 那套
        #   "瞎了就锁零"套到人手开车上，等于他一丢墙方向盘就被抽走，现场会读成板子抽风；
        #   刀与横移**绑死门 N**：不进档条件里不查刀，进来之后三路刀钉提位、横移恒 0，
        #   即使 permit 被配成门 F 也不放开（手操档不是落刀的入口）。
        # 钳位放在这里而不是调用方：线来的速度不能假定发送方自觉。
        return [(P.TYPE_NAV, P.pack_nav(clamp_teleop(vl), clamp_teleop(vr), nav_gear)),
                (P.TYPE_TOOL, P.pack_tool(0.0, 0x07))]

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
                l1_events=0, tx_frames='-', nav_flags='', beat_gap_s='',
                vehicle_tag=''):
    """按 RUN_LOG_COLUMNS 的顺序拼一行。st 可以是 None（无 STATUS）或 v1 字典。

    l1_events 是**累计的 L1 降级事件数**（spec §5.2，I-6），由调用方维护，
    这里只负责落到自己那一列（10-12 的 T2 之后末位是 tx_frames，它不再是末位）。它写整数而不是空串：这一列的用法是"求和/看趋势"，
    空串会让读日志的人把"没有降级"和"没接线"混成一回事。默认 0 = "没进入过 L1"，
    与 main 的初始值同一个语义。

    `tx_frames` 是这一拍**真的写进 socket** 的帧型串（T2），由调用方从 `send()`
    的出口收集；缺省 `'-'` = "这一拍线上一个字节都没有"，含义与上面 `l1_events`
    那句一样：不能拿空串当"没接线"，也不能拿它当"发过了"。

    `vehicle_tag` 是台账 Pc-10 那一列：这一行的数据属于哪台车（`prev` = 上代调试
    平台 3.25 m，`prototype` = 样机 2.15 m）。值来自 `config/vehicle_profile.yaml`
    的 `log_tag`，由调用方读一次传进来，**每行都写同一个值**——它的用途是事后与
    `run_log.csv` 一起归档时认车，不是运行时判定。这里的缺省 `''` 表示"这一版程序
    没把它接上"，与"接上了但车没标"（那种情况 `load()` 会直接报错、走不到这里）
    是两回事，所以留空串而不是留 `unknown`：空串一眼就是漏接线。
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
        nav_flags,
        beat_gap_s,
        vehicle_tag,
    ]
