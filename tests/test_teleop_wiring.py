# -*- coding: utf-8 -*-
"""手操档在 pc/main.py 里的接线证据（键位 → MODE 申请 → 线上 NAV 真的带速度）。

单独放一个文件是因为它要复用 `tests/test_control.py` 的 `_drive_main` 假环境，
而 `test_teleop.py` 那批是纯函数级的单测，两批的节奏不一样：这一批证明的是**装配**，
不是判据。装配最容易犯的错是"分支写了、键没接""键接了、速度没落到帧上"，
纯函数测试对这两种都无感。
"""
import struct

from common import protocol as P
from pc import wire

from test_control import _BLIND, _USABLE, _drive_main


def _nav_pairs(sent):
    """harness 记的是 (beat, ftype, payload, addr)——按 beat 排序取每拍最后一帧 NAV。

    同一拍可能有多帧 NAV？不会：`frames_for_state()` 一拍只给一条 NAV。
    但**开机那一拍有 MODE 握手**，所以 MODE 与 NAV 要分开取。
    """
    by_beat = {}
    for beat, ftype, payload, _addr in sent:
        if ftype == P.TYPE_NAV:
            by_beat[beat] = struct.unpack('<ff', payload[:8])
    return [by_beat[b] for b in sorted(by_beat)]


def _mode_requests(sent):
    return [payload[0] for _beat, ftype, payload, _addr in sent
            if ftype == P.TYPE_MODE]


def test_teleop_key_asks_mode_teleop_and_operator_speed_reaches_the_wire(tmp_path, monkeypatch):
    """[T] 点头之后才把申请发上线；随后按住的 W 必须真的变成线上的一对轮速。

    这条钉的是两个"看着都写了其实没接上"的点：
      - 键位处理在**拍尾**，所以按下 [T] 那一拍的帧仍是旧状态给的——只有下一拍才该出现
        TELEOP 的 NAV；
      - 手操的速度不许被视觉那条链覆盖掉（`usable` 参与不参与，只有装配层能验出来）。
    """
    r = _drive_main(tmp_path, monkeypatch,
                    results=[_BLIND, _BLIND, _BLIND, _BLIND],
                    keys=[-1, ord('t'), ord('w'), ord('w')],
                    permit=wire.GATE_N, gui=True)

    assert P.MODE_REQ_TELEOP in _mode_requests(r['sent']), \
        '按 [T] 之后线上没有 MODE(0x02) 申请'
    assert r['sm'].state == 'TELEOP'

    # 第四拍（按 W 之后的那一拍）线上必须出现非零、且不超过 0.1 的速度
    moving = [p for p in _nav_pairs(r['sent']) if p != (0.0, 0.0)]
    assert moving, '按住 W 之后线上一对轮速都还是 0——键到帧这条链没接上'
    for vl, vr in moving:
        assert abs(vl - wire.TELEOP_MAX_MPS) < 1e-5, (vl, vr)
        assert abs(vr - wire.TELEOP_MAX_MPS) < 1e-5, (vl, vr)


def test_teleop_is_not_entered_while_estop_latched(tmp_path, monkeypatch):
    """急停锁存下按 [T]：**先问状态机**，它不许就一帧都不发。

    旧写法（先无条件发申请、再问状态机）的症状是 PC 停在 ESTOP 一帧不发，
    而 MCU 已经收到申请——四条件一旦成立就授权。这条测试就是那个症状的探针。
    """
    r = _drive_main(tmp_path, monkeypatch,
                    results=[_USABLE, _USABLE, _USABLE, _USABLE],
                    keys=[-1, ord('e'), ord('t'), ord('t')],
                    permit=wire.GATE_N, gui=True)

    assert P.MODE_REQ_TELEOP not in _mode_requests(r['sent'])
    assert r['sm'].state == 'ESTOP'


def test_gate_f_config_does_not_open_the_knife_during_teleop(tmp_path, monkeypatch):
    """**手操绑门 N**（作者决定 B3）：就算 permit 被配成门 F，手操也不许落刀、不许横移。

    这一条在纯函数层已经钉过（`test_teleop.py`），这里要钉的是**装配层**——
    main 把 `permit` 一路传下去，如果哪天有人在 main 里"顺手"给手操也走 GATE_F 那条分支，
    纯函数测试不会红，这条会。
    """
    r = _drive_main(tmp_path, monkeypatch,
                    results=[_BLIND, _BLIND, _BLIND, _BLIND],
                    keys=[-1, ord('t'), ord('w'), ord('w')],
                    permit=wire.GATE_F, gui=True)
    assert r['sm'].state == 'TELEOP'
    tools = [payload for _beat, ftype, payload, _addr in r['sent']
             if ftype == P.TYPE_TOOL]
    assert tools, '手操期间一帧 TOOL 都没发——提刀状态没上线'
    for pl in tools:
        assert pl[4] == 0x07, '手操下刀位字节不是全提 0x07'
        assert struct.unpack('<f', pl[:4])[0] == 0.0, '手操下横移不许非零'


# 关于"松手归零"：它的判据是**墙上时钟超时**（`wire.TELEOP_HOLD_S`），
# 而 `_drive_main` 这套假环境没有可控时钟（五拍跑完不到 1 ms，超时永远不会到），
# 所以归零这一条目前只在**纯函数层**钉着（`tests/test_teleop.py::test_teleop_releases_to_zero_after_the_hold_window`），
# main 里的接线是"每拍把 `time.time() - tele_key_t` 交进去"这一行，未经装配层证明。
# 台账里要把这条写成"已编码 + 待台架"，不许因为纯函数绿了就写"松手即停已验"。
