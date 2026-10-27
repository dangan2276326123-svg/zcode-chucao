# -*- coding: utf-8 -*-
"""手操转向档位（NAV.flags 字节）的行为钉住 —— 2026-10-14 加。

`common/protocol.py:pack_nav` 一直是 `<ffB`（左速 + 右速 + flags），而固件与 PC 都
没用过那个 flags。本批把它用起来当**档位**：0 直行 / 1 左 / 2 右 / 3 横移（10-21 放开）。
这批测试钉的是三件容易做错的事：档位只准在手操档生效、**不认识或没解锁的档位一律
折回直行**（fail-closed）、以及日志里那一列不许用 `0` 冒充"没档位"。
后半段是固件侧的形状：90° 走四个伺服槽的补偿角、共角姿态下轮速按厂商分组取负。
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
    # AUTO / LIFT 不受档位影响：这条通道是手操档专属的。无人档的角度从来不由键盘档位
    # 决定——它是"编译期基准 −90 + 当前持权者那条 NAV 的微调"（retrofit_auto_angle），
    # 遥控器 ch[1] 在 AUTO/TELEOP 里也决定不了方向（Fw-11 那条口径，台账 Hw-30）。
    assert _nav_flags('AUTO', wire.GEAR_LEFT) == 0
    assert _nav_flags('LIFT', wire.GEAR_LEFT) == 0


def test_lateral_gear_is_sent_and_unknown_ones_fold_to_straight():
    """10-14 作者裁定：横移档（3）放开，先按上代车跑；不认识的值（4/7/255/-1）
    仍一律折回直行——这条是"拿不到的量不得当作满足"在 PC 侧的版本，不跟着放开。

    放开的是"能发出去"。形状到 10-21/10-26 才改对：先按厂商那对 20° 发（现场看到的是
    斜行），后来换成厂商横向档本身——同一符号的 90° 补偿角 + 一组对角取负的轮速。
    角度数值不是按实测轮距/轴距算的（Hw-23 没关），样机须重测。
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

    负号这条不是装饰：10-24 把两个 90° 常数从 `+90.0` 改成 `-90.0` 之后，
    原来那个不带符号的写法匹配不到带负号的字面量，`findall` 直接返回空表——
    两个测试一起红，而红的理由是"定义不存在"，不是"符号不对"
    （AGENTS 审查清单第 2 条 b：自检输出"零命中"时先怀疑检查器自己写错了）。
    现在空表照样报错，符号由下面两处 `assert lat < 0` / `assert base < 0` 单独钉。
    """
    import re
    hits = re.findall(r'#\s*define\s+' + name + r'\s+([+-]?[0-9]*\.?[0-9]+)', text)
    assert len(hits) == 1, '%s 应当只有一份定义，实测 %r' % (name, hits)
    return float(hits[0])


def test_lateral_gear_uses_its_own_90_degree_constant():
    """LATERAL 的基准角必须是 **+90°** —— 就是厂商横向档那个"四个轮都正"的 LOOK；
    而且**不许顺手把 LEFT/RIGHT 也带到 90°**。

    钉三件事：
      · 常数存在、幅值 90、**符号为正**。这是 10-27 第五次改判（台账 Hw-30）：作者烧上 −90 配对版后
        报"四个轮都反了"，要求"把四个轮改正"。±90 共用同一条滚动平面，姿态那一定不了朝几 ⇒ 基准角放回
        厂商横向档的 +90（遥控器不推反向键时就是这个样子），**车朝哪一边改由驱动那一半承担**：main.c
        共角分支把四个轮速整体取负 = "横向 + 反向键"，由 test_crab_needs_both_halves_and_one_sign 钉住；
      · 这个常数**由 retrofit.c 的 retrofit_auto_offset() 消费**，不再由 main.c 的 tl 变量写进 angle[]
        （10-26 起 90° 走补偿角那条通道，跟厂商横向档同一个入口；angle[] 在 LATERAL 档归零）；
      · LEFT/RIGHT 仍用 tg（20°）。三档共用一个常数是这个改动最容易顺手做成的错法：那会让 LEFT/RIGHT
        也变成 90°，而"左/右"在 20° 下是斜行、在 90° 下就成了平移，C27 那三条目视判据当场全部失真。
    """
    hdr = _fw_bytes(_FW_H)
    lat = _fw_deg_constant(hdr, 'TELEOP_LATERAL_DEG')
    assert abs(lat) == 90.0, lat
    assert lat > 0, 'TELEOP_LATERAL_DEG 要 +90：厂商横向档的 LOOK；朝哪边由共角分支的四轮取负决定（10-27 第五次改判，台账 Hw-30）'
    assert 'TELEOP_STEER_DEG' in hdr, 'LEFT/RIGHT 那份 20° 常数不许消失'

    main = _fw_bytes(_FW_MAIN)
    i = main.find('case TELEOP_GEAR_LATERAL:')
    assert i > 0, 'LATERAL 分支不见了'
    block = main[i:i + 200]
    assert 'angle[0] = angle[1] = angle[2] = angle[3] = 0.0;' in block, block
    assert '= tl;' not in block, 'LATERAL 不许再往 angle[] 里写 90（那条路会把两组轮镜像）'
    assert 'tg;' not in block, 'LATERAL 不许再用 tg（那是 20° 斜行的量）'
    assert 'tl = TELEOP_LATERAL_DEG' not in main, 'tl 这条变量已经随通道一起删掉'
    c = _fw_bytes(_FW_C)
    assert 'TELEOP_LATERAL_DEG' in c, 'LATERAL 的 90° 现在由 retrofit_auto_offset() 消费'
    # LEFT / RIGHT 两档仍走 tg：数一下整份文件里 tg 的赋值处
    assert main.count('angle[0] = tg;') == 1, 'LEFT 档应当还在用 tg，且只有一处'
    assert main.count('angle[0] = -tg;') == 1, 'RIGHT 档应当还在用 -tg，且只有一处'


def test_auto_crab_constants_and_the_call_site():
    """AUTO 共角的两个常数、四个伺服槽都调它、以及 retrofit.c 的三道守卫。

    钉五件事，每件都对应一个会静默发生的错法：
      · 常数是 **+90** 且只有一个（幅值写歪 = 车不走刀侧；符号写歪 = 四个轮看着反 —— 这两种错台架都
        见过：10-24 那版 +90 作者报"按 A 向 3 行驶"；10-26 配对版 −90 报"四个轮都反了"；写了第二份定义
        就会有两套"朝 1"。行走方向现在由驱动符号决定，不由这个符号决定，见 test_crab_needs_both_halves）；
      · main.c 的 AUTO 分支把 angle[] 归 0，90° 一律走四个伺服槽的 retrofit_auto_offset()：10-26 傍晚
        那一版把它写回 angle[]，作者目视"1、3 反了"，走的正是逐轮 ± 那条镜像路；当晚又换回补偿角；
      · 四个伺服槽**每一个**都带这个条件（少一个 = 那一个轮不转 90°，剩下的三个顶它）；
      · retrofit.c 里 13 字节的读法带**钳位**与 **NaN 兜底**（对 NaN 的一切比较都是 false，
        只钳位会让它原样进伺服角）；
      · 9 字节那一支显式把 trim 归 0，不留着上一帧的值。
    """
    hdr = _fw_bytes(_FW_H)
    base = _fw_deg_constant(hdr, 'AUTO_CRAB_BASE_DEG')
    trim = _fw_deg_constant(hdr, 'AUTO_CRAB_TRIM_MAX')
    assert abs(base) == 90.0, base
    assert base > 0, 'AUTO_CRAB_BASE_DEG 要 +90（四个轮都正的 LOOK）；方向由共角分支的四轮取负承担（10-27 第五次改判，台账 Hw-30）'
    assert 0 < trim <= 30, trim

    main = _fw_bytes(_FW_MAIN)
    i = main.find('if (retrofit_mode() == MODE_AUTO) {')
    assert i > 0
    block = main[i:main.find('} else if', i)]
    assert 'angle[0] = angle[1] = angle[2] = angle[3] = 0.0;' in block, block[-200:]
    assert 'retrofit_auto_angle();' not in block, \
        'AUTO 的 90 不许写回 angle[]：那条路在 main.c 的逐轮 ± 后面会把两组轮镜像'
    assert main.count('?retrofit_auto_offset():Switch_direction)') == 4, \
        '四个伺服槽都要带这个补偿角，少一个就是三个轮顶一个轮'

    c = _fw_bytes(_FW_C)
    assert 'if (len >= 13)' in c and 'nav_crab_deg != nav_crab_deg' in c
    assert 'AUTO_CRAB_TRIM_MAX' in c
    j = c.find('if (len >= 13)')
    assert 'nav_crab_deg = 0.0f;' in c[j:j + 600], '9 字节那一支要显式归 0'
    assert 'double retrofit_auto_angle(void)' in c
    assert 'double retrofit_auto_offset(void)' in c
    assert 'uint8_t retrofit_crab_posture(void)' in c


_SLOT_NEG = u'-((retrofit_mode()==MODE_AUTO||retrofit_mode()==MODE_TELEOP)?' \
            u'retrofit_auto_offset():Switch_direction)'
_SLOT_POS = u'+((retrofit_mode()==MODE_AUTO||retrofit_mode()==MODE_TELEOP)?' \
            u'retrofit_auto_offset():Switch_direction)'


def test_four_servo_slots_get_the_same_signed_offset():
    u"""四个伺服收到的是**同一个数** —— 这才是"四个轮一起转、都是正的"那一眼的代码形状。

    main.c 的四条 send_angle 里有两条整体取负（厂商的逐轮镜像安装补偿）。补偿角必须**写在负号内侧**，
    负负得正，四路才同号；写在括号外面就变成两组反号，也就是作者 10-26 报的"1、3 反了"。这条测试把
    两两相乘后的有效符号算出来看，不看措辞 —— 10-27 那次把基准角从 −90 换回 +90，靠的就是这条：符号
    换了，四个槽仍必须同号，否则又回到"一组看着反"的老形状。
    """
    import re
    main = _fw_bytes(_FW_MAIN)
    slots = [l for l in main.split(u'\n') if l.strip().startswith(u'send_angle(')]
    assert len(slots) == 4, u'main.c 应当只有四条 send_angle，实测 %d' % len(slots)
    eff = {}
    for line in slots:
        m = re.match(u'\\s*send_angle\\((\\d),(-?)\\(', line)
        assert m, line[:60]
        addr, outer = m.group(1), (-1 if m.group(2) else 1)
        if _SLOT_NEG in line:
            inner = -1
        elif _SLOT_POS in line:
            inner = 1
        else:
            raise AssertionError(u'这个槽既不带 -TERM 也不带 +TERM：%s' % line[:80])
        eff[addr] = outer * inner
    assert sorted(eff) == [u'1', u'2', u'3', u'4'], sorted(eff)
    assert all(v == 1 for v in eff.values()), \
        u'四路有效符号必须全为 +，实测 %r：有一个是 - 就有一组轮镜像' % eff


def test_crab_needs_both_halves_and_one_sign():
    u"""共角要**两半都在**，而"朝哪一边"只许**一个杠杆** —— 10-27 起这根杠杆是轮速，不是转角符号。

    10-26 一天里两条"只做一半"的形状都上台架跑过：
      · 四个伺服同号 + 轮速不配对 ⇒ 左右两边互相顶（作者原话"别劲"）；
      · 转角打在 angle[]（两组反号）+ 轮速不配对 ⇒ 车能走，但有两组轮看着镜像（"1、3 反了"）。
    厂商那条活路是两半都在：横向档 = 同号补偿角 + 按 (−vr,+vr,+vl,−vl) 分组的轮速。10-27 第五次改判
    在这两半之上再叠"整体取负"（= 横向 + 反向键：path_plan.c:721-731 的后退支把四个 veloc 都写成
    −velocity），因为作者要把四个轮"改正"，而 ±90 是同一条滚动平面、姿态答不了朝几，能改的只有驱动符号。
    所以这条测试钉三件事：
      ① 转角通道还在（四个伺服槽都带 retrofit_auto_offset()）；
      ② 共角分支的轮速写成 (vr, −vr, −vl, vl) 这一组，而 else 支仍是不配对的差速；
      ③ 没有第三根杠杆：main.c 里不许出现 vl = -vl / vr = -vr 那种就地整侧取负。
    """
    main = _fw_bytes(_FW_MAIN)
    c = _fw_bytes(_FW_C)
    hdr = _fw_bytes(_FW_H)

    # 第一半：补偿角走四个伺服槽（上一条测试已经逐槽验过符号，这里只钉"通道还在"）
    assert main.count(u'?retrofit_auto_offset():Switch_direction)') == 4
    # 第二半：共角姿态下的轮速 = 厂商横向档 (+v,-v,-v,+v)，即"横向 + 反向键"那一组
    i = main.find(u'if (retrofit_crab_posture()) {')
    assert i > 0, u'共角判据没接进驱动点：转角与速度两半会各走各的'
    end = main.find(u'} else if (retrofit_mode() == MODE_ESTOP)', i)
    assert end > i, u'驱动点的分支结构变了，这条测试的窗口要先重看'
    block = main[i:end]
    for frag in (u'veloc[0] =  vr;', u'veloc[1] = -vr;',
                 u'veloc[2] = -vl;', u'veloc[3] =  vl;'):
        assert frag in block, frag
    assert u'veloc[0] = veloc[2] = vl;' in block and u'veloc[1] = veloc[3] = vr;' in block, \
        u'else 分支必须还是原来的差速，LEFT/RIGHT/直行不许被共角改掉'

    # 没有第三根杠杆
    assert u'vl = -vl' not in main and u'vr = -vr' not in main, \
        u'整侧取负是第二根杠杆：它的成因（转角打错地方）已经由上面两条钉死'

    # 判据本身：只有 AUTO 和 TELEOP 的 LATERAL 算共角，MANUAL/ESTOP/LIFT 都不算
    j = c.find(u'uint8_t retrofit_crab_posture(void)')
    body = c[j:c.find(u'\n}', j)]
    assert u'MODE_AUTO' in body and u'MODE_TELEOP' in body and u'TELEOP_GEAR_LATERAL' in body
    assert body.count(u'return 1') == 2 and u'return 0' in body, body
    assert u'MODE_ESTOP' not in body and u'nav_link_ok' not in body, \
        u'共角判据不许顺手接管急停或链路：那是另外两条闸门'

    # 说明必须留在头文件里，不然下一个人会把两条死路再走一遍
    assert u'The 90 degrees and the wheel speeds are PAIRED' in hdr
    base = _fw_deg_constant(hdr, 'AUTO_CRAB_BASE_DEG')
    lat = _fw_deg_constant(hdr, 'TELEOP_LATERAL_DEG')
    assert base > 0 and lat > 0, (base, lat)
