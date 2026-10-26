# -*- coding: utf-8 -*-
"""手操转向档位（NAV.flags 字节）的行为钉住 —— 2026-10-14 加。

`common/protocol.py:pack_nav` 一直是 `<ffB`（左速 + 右速 + flags），而固件与 PC 都
没用过那个 flags。本批把它用起来当**档位**：0 直行 / 1 左 / 2 右 / 3 保留（横移）。
这批测试钉的是三件容易做错的事：档位只准在手操档生效、**不认识或没解锁的档位一律
折回直行**（fail-closed）、以及日志里那一列不许用 `0` 冒充"没档位"。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import protocol as P          # noqa: E402
from pc import wire                       # noqa: E402


def _nav_flags(state, gear, usable=True, permit=wire.GATE_N):
    """从 frames_for_state 的返回值里把 NAV 载荷的第 9 字节（flags）抠出来。"""
    for ftype, payload in wire.frames_for_state(state, usable, 0.1, 0.1, 0.0,
                                                permit, gear=gear):
        if ftype == P.TYPE_NAV:
            assert len(payload) == 9, payload
            return payload[8]
    return None


def test_gear_reaches_the_wire_only_in_teleop():
    assert _nav_flags('TELEOP', wire.GEAR_STRAIGHT) == 0
    assert _nav_flags('TELEOP', wire.GEAR_LEFT) == 1
    assert _nav_flags('TELEOP', wire.GEAR_RIGHT) == 2
    # AUTO / LIFT 不受档位影响：转角这条通道是手操档专属的，
    # 无人档的转角由 path_plan 决定，不该被一个键盘按键改掉。
    assert _nav_flags('AUTO', wire.GEAR_LEFT) == 0
    assert _nav_flags('LIFT', wire.GEAR_LEFT) == 0


def test_lateral_gear_is_sent_and_unknown_ones_fold_to_straight():
    """10-14 作者裁定：横移档（3）放开，先按上代车跑；不认识的值（4/7/255/-1）
    仍一律折回直行——这条是"拿不到的量不得当作满足"在 PC 侧的版本，不跟着放开。

    放开的是"能发出去"，不是"角度算对了"：这一档的角度抄的是厂商那对 20 度，
    所以现场应当看到**斜行**而不是 90 度平移，下一版按现场表现改。
    """
    assert _nav_flags('TELEOP', wire.GEAR_LATERAL) == wire.GEAR_LATERAL
    for bad in (4, 7, 255, -1):
        assert _nav_flags('TELEOP', bad) == 0, bad


def test_cycle_gear_visits_all_four_gears_and_resets_on_junk():
    g = wire.GEAR_STRAIGHT
    seen = [g]
    for _ in range(8):
        g = wire.cycle_gear(g)
        seen.append(g)
    assert set(seen) == {wire.GEAR_STRAIGHT, wire.GEAR_LEFT,
                         wire.GEAR_RIGHT, wire.GEAR_LATERAL}
    # 手一抖传进一个不认识的值：回直行，不是"下一个"
    assert wire.cycle_gear(42) == wire.GEAR_STRAIGHT


def test_gear_text_is_ascii_and_says_lateral_is_locked():
    assert wire.gear_text(0) == 'STRAIGHT'
    assert wire.gear_text(3) == 'LATERAL'
    assert wire.gear_text(42) == 'UNKNOWN-42'      # 未知档位要看得见，不许静默变空
    for g in (0, 1, 2, 3, 42):
        assert all(ord(c) < 128 for c in wire.gear_text(g))   # cv2.putText 画不出中文


def test_run_log_row_nav_flags_defaults_empty_not_zero():
    """非手操拍这一列留空：写 `0` 会被读成"这一拍发了直行档"，而实际是"这一拍没有档位"。"""
    res = {'status': 'dual', 'confidence': 0.9, 'lateral_px': 3.0}
    args = (1.0, 7, 'AUTO', res, 0.01, 0.02, 0.07, 0.07, 0.0, 12.0, None,
            ({}, 0, None), wire.GATE_N)
    i = wire.RUN_LOG_COLUMNS.index('nav_flags')   # 按列名取，不再按末位（10-14 之后末位是 beat_gap_s）
    row = wire.run_log_row(*args)
    assert row[i] == ''
    assert wire.run_log_row(*args, nav_flags='2')[i] == '2'


def test_beat_gap_column_keeps_its_slot_and_defaults_empty():
    """`beat_gap_s` 缺省必须是空串，不是 `0.000`。

    0 会被读成"这一拍节拍完美"，而空串才是"这一列没有可用记录"（回放模式、第一拍）。
    这条与 `tx_frames` 的 `'-'`、`nav_flags` 的 `''` 是同一条纪律：不拿默认值冒充读数。

    函数名里的 `is_last` 今天去掉了——它从写下那天起就没真当过末位（先后让位给
    `vehicle_tag`、`veh_speed_mps`、`auth_mismatch` 三列），一个说谎的名字比没名字更糟。
    """
    assert wire.RUN_LOG_COLUMNS[-4] == 'beat_gap_s'   # 追加链：vehicle_tag → veh_speed_mps → auth_mismatch
    res = {'status': 'dual', 'confidence': 0.9, 'lateral_px': 3.0}
    args = (1.0, 7, 'AUTO', res, 0.01, 0.02, 0.07, 0.07, 0.0, 12.0, None,
            ({}, 0, None), wire.GATE_N)
    col = wire.RUN_LOG_COLUMNS.index('beat_gap_s')   # 按列名取，不靠末位（末位已两度让位）
    assert wire.run_log_row(*args)[col] == ''
    assert wire.run_log_row(*args, beat_gap_s='4.169')[col] == '4.169'


# ---- 固件侧：LATERAL 档的角度（2026-10-21 从 20° 斜行改成 90° 平移） ----

_FW_H = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     'firmware', '大车proj', '大车', 'HARDWARE', 'retrofit', 'retrofit.h')
_FW_MAIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'firmware', '大车proj', '大车', 'USER', 'main.c')
_FW_C = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'firmware', '大车proj', '大车', 'HARDWARE', 'retrofit', 'retrofit.c')


def _fw_bytes(path):
    """字节级读 + latin-1 解：`firmware/` 下的文件是 GBK（AGENTS 审查清单第 4 条），
    按文本编码读会抛或静默换字；这里只找 ASCII 的 `#define` 与赋值，中文注释不参与。"""
    with open(path, 'rb') as f:
        return f.read().decode('latin-1')


def _fw_deg_constant(text, name):
    """取 `#define <name> 数值` 那一条，**允许前面带正负号**，且命中数必须是 1。

    符号这条不是装饰：10-24 把两个 90° 常数改成 `-90.0` 之后，原来那个不带符号的写法
    匹配不到带负号的字面量，`findall` 直接返回空表——两个测试一起红，红的理由是
    "定义不存在"而不是"符号不对"（AGENTS 审查清单第 2 条 b：自检输出"零命中"时先怀疑
    检查器自己写错了）。现在空表照样报错，符号由下面单独的 `assert deg < 0` 钉。
    """
    import re
    hits = re.findall(r'#\s*define\s+' + name + r'\s+([+-]?[0-9]*\.?[0-9]+)', text)
    assert len(hits) == 1, '%s 应当只有一份定义，实测 %r' % (name, hits)
    return float(hits[0])


def test_lateral_gear_uses_its_own_90_degree_constant():
    """手操横移档必须是 **−90°**，而且**不能顺手把 LEFT/RIGHT 也带到 90°**。

    符号今天在 `+90 / -90` 之间来回过三次，理由都记在台账 Hw-30，这里只钉最终口径与
    它为什么是这个符号：作者 2026-10-26 在台架上把**遥控器**拨到横向、给油门、不按反向，
    车**朝"3"走**——那是厂商自己的 `Switch_direction=+90` 落在四个伺服**同号**上的形状。
    作业方向是"1" ⇒ 我们沿用同一个机制、把符号取反 ⇒ `TELEOP_LATERAL_DEG = -90.0`。
    10-26 另一处改动：这个 90 不再写进 `angle[]`（那会经过逐轮 ± ⇒ 两组伺服反号，
    就是他眼里"哪个轮转反了"），改成走补偿角那条通道，四个伺服收到同一个数。
    LEFT/RIGHT 仍是 20°、仍走 `angle[]` 与逐轮 ±，那才是真转向。
    """
    hdr = _fw_bytes(_FW_H)
    lat = _fw_deg_constant(hdr, 'TELEOP_LATERAL_DEG')
    assert abs(lat) == 90.0, lat
    assert lat < 0, ('TELEOP_LATERAL_DEG 要 -90：厂商 +90 的形状台架实测朝"3"，作业方向是"1"（台账 Hw-30）')
    assert 'TELEOP_STEER_DEG' in hdr, 'LEFT/RIGHT 那份 20° 常数不许消失'

    main = _fw_bytes(_FW_MAIN)
    j = main.find('case TELEOP_GEAR_LATERAL:')
    assert j > 0, 'LATERAL 分支不见了'
    block = main[j:j + 220]
    assert 'angle[0] = angle[1] = angle[2] = angle[3] = 0.0;' in block, block
    assert 'tl' not in block, 'LATERAL 不许再往 angle[] 里写 90（那会经过逐轮 ±，四个伺服就分成两组反号）'
    assert 'TELEOP_LATERAL_DEG' not in main, '90 这个量已经改走补偿角通道，main.c 里不该再引用它'
    c = _fw_bytes(_FW_C)
    assert 'TELEOP_LATERAL_DEG' in c, '补偿角函数里必须真的用这个常数（不是在 main.c 里）'
    # LEFT / RIGHT 两档仍走 tg
    assert main.count('angle[0] = tg;') == 1, 'LEFT 档应当还在用 tg，且只有一处'
    assert main.count('angle[0] = -tg;') == 1, 'RIGHT 档应当还在用 -tg，且只有一处'


def test_auto_crab_constants_and_the_call_site():
    """AUTO 共角：常数是 −90、`main.c` 的 AUTO 分支把 `angle[]` 归零、90 走补偿角通道。

    钉五件事，每件对一个会静默发生的错法：
      · 常数存在、幅值 90、**符号为负**（同上一条的理由），且只有一份定义；
      · `main.c` 的 AUTO 分支把四个 `angle[]` 写成 0.0——这条**不是回退到 Fw-11**，
        Fw-11 的"抹 0"抹的是遥控来的方向，这里 0.0 是"转角通道不用"，方向在补偿角上；
      · 四条 `send_angle` 都带 `retrofit_auto_offset()`，MANUAL 那一支仍是 `Switch_direction`
        ⇒ 无人模式的方向永远来自编译期常数 + 当前持权者的 NAV，遥控 `ch[1]` 插手不进来；
      · `retrofit.c` 里 13 字节的读法带**钳位**与 **NaN 兜底**（对 NaN 的一切比较都是
        false，只钳位会让它原样进伺服角）；9 字节那一支显式把 trim 归 0；
      · **只有一个杠杆**：`main.c` 里不许出现把轮速取负的写法（10-26 曾加过一版，撤了；
        转角与驱动同时翻 = 等于没翻）。
    """
    hdr = _fw_bytes(_FW_H)
    base = _fw_deg_constant(hdr, 'AUTO_CRAB_BASE_DEG')
    trim = _fw_deg_constant(hdr, 'AUTO_CRAB_TRIM_MAX')
    assert abs(base) == 90.0, base
    assert base < 0, 'AUTO_CRAB_BASE_DEG 要 -90：厂商 +90 的形状实测朝"3"（台账 Hw-30）'
    assert 0 < trim <= 30, trim

    main = _fw_bytes(_FW_MAIN)
    i = main.find('if (retrofit_mode() == MODE_AUTO) {')
    assert i > 0
    block = main[i:main.find('} else if', i)]
    assert 'angle[0] = angle[1] = angle[2] = angle[3] = 0.0;' in block, block[-260:]
    assert 'retrofit_auto_angle();' not in block, 'AUTO 的 90 不该再写进 angle[]（见 test_lateral 那条说明）'
    assert main.count(')?retrofit_auto_offset():Switch_direction)') == 4, \
        '四条 send_angle 都要走补偿角通道，实测 %d' % main.count(')?retrofit_auto_offset():Switch_direction)')
    assert 'vl = -vl;' not in main and 'vr = -vr;' not in main, '只许一个杠杆：驱动不许取负'

    c = _fw_bytes(_FW_C)
    assert 'if (len >= 13)' in c and 'nav_crab_deg != nav_crab_deg' in c
    assert 'AUTO_CRAB_TRIM_MAX' in c
    j = c.find('if (len >= 13)')
    assert 'nav_crab_deg = 0.0f;' in c[j:j + 600], '9 字节那一支要显式归 0'
    assert 'double retrofit_auto_angle(void)' in c
    assert 'double retrofit_auto_offset(void)' in c


def test_crab_offset_reaches_all_four_servos_with_the_same_sign():
    """补偿角这一改的核心判据：**四个伺服收到同一个符号**，所以四个轮"都是正的"。

    `main.c` 四条 `send_angle` 里有两条是整体取负的写法（左前、右后），
    补偿角在那两条里位于 `-(... - offset)` ⇒ 负负得正 ⇒ 四路出来都是 `+offset`。
    这正是作者用遥控器拨横向时看到的形状，也是他说"为什么不能四个都正"的依据。
    钉错法：如果把 90 写回 `angle[]`，它就落在外层负号里面 ⇒ 两路 +90 两路 -90，
    四个轮就分成两组反号（10-24/10-26 那两版的样子）。
    """
    main = _fw_bytes(_FW_MAIN)
    lines = [l for l in main.split(chr(10)) if 'send_angle(' in l and 'retrofit_auto_offset' in l]
    assert len(lines) == 4, len(lines)
    neg_outer = [l for l in lines if 'send_angle(4,' in l or 'send_angle(3,' in l]
    pos_outer = [l for l in lines if 'send_angle(1,' in l or 'send_angle(2,' in l]
    assert len(neg_outer) == 2 and len(pos_outer) == 2, (neg_outer, pos_outer)
    for l in neg_outer:
        assert 'send_angle(%s,-(angle[' % l.split('send_angle(')[1][0] in l, l[:120]
        assert '-((retrofit_mode()' in l, l[:160]      # 外层负号里再减补偿角 ⇒ 净效果 +offset
    for l in pos_outer:
        assert '+((retrofit_mode()' in l, l[:160]      # 直接加 ⇒ +offset
    # MANUAL 那一支没被动过：遥控器自己拨横向时仍由厂商的 Switch_direction 说话
    assert main.count(':Switch_direction)') == 4
