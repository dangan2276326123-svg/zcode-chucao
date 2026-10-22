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


def _fw_bytes(path):
    """字节级读 + latin-1 解：`firmware/` 下的文件是 GBK（AGENTS 审查清单第 4 条），
    按文本编码读会抛或静默换字；这里只找 ASCII 的 `#define` 与赋值，中文注释不参与。"""
    with open(path, 'rb') as f:
        return f.read().decode('latin-1')


def test_lateral_gear_uses_its_own_90_degree_constant():
    """LATERAL 必须是 90°，而且**不能顺手把 LEFT/RIGHT 也带到 90°**。

    钉的是两件事：① 常数存在且是 90.0（作者 10-21 口径：无人作业方向 = 刀那一面 = "1"，
    而正常档零位是"2"，差的就是厂商 `path_plan.c:218` 那个 `Switch_direction=1.570796`）；
    ② `main.c` 的 `TELEOP_GEAR_LATERAL` 分支用的是 `tl`，LEFT/RIGHT 仍用 `tg`。
    把三档共用一个常数是这个改动最容易顺手做成的形状——那会让 LEFT/RIGHT 也变成 90°，
    而"左/右"在 20° 下是斜行、在 90° 下就成了平移，C27 那三条目视判据当场全部失真。
    """
    import re
    hdr = _fw_bytes(_FW_H)
    hits = re.findall(r'#\s*define\s+TELEOP_LATERAL_DEG\s+([0-9]*\.?[0-9]+)', hdr)
    assert len(hits) == 1, 'TELEOP_LATERAL_DEG 应当只有一份定义，实测 %r' % (hits,)
    assert abs(float(hits[0]) - 90.0) < 1e-9, hits[0]
    assert 'TELEOP_STEER_DEG' in hdr, 'LEFT/RIGHT 那份 20° 常数不许消失'

    main = _fw_bytes(_FW_MAIN)
    i = main.find('case TELEOP_GEAR_LATERAL:')
    assert i > 0, 'LATERAL 分支不见了'
    block = main[i:i + 200]
    assert 'angle[0] = tl;' in block and 'angle[3] = tl;' in block, block
    assert 'tg;' not in block, 'LATERAL 不许再用 tg（那是 20° 斜行的量）'
    assert 'tl = TELEOP_LATERAL_DEG' in main, 'tl 必须由 LATERAL 自己的常数算出来'
    # LEFT / RIGHT 两档仍走 tg：数一下整份文件里 tg 的赋值处
    assert main.count('angle[0] = tg;') == 1, 'LEFT 档应当还在用 tg，且只有一处'
    assert main.count('angle[0] = -tg;') == 1, 'RIGHT 档应当还在用 -tg，且只有一处'
