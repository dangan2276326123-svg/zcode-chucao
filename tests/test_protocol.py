# -*- coding: utf-8 -*-
import pytest
from common import protocol as P
from common import uart_vectors as uv


def test_crc_known_vectors():
    # CRC-16/CCITT-FALSE check values ("123456789" -> 0x29B1)
    assert P.crc16_ccitt_false(b'123456789') == 0x29B1
    assert P.crc16_ccitt_false(b'') == 0xFFFF


def test_nav_roundtrip():
    data = P.pack_frame(P.TYPE_NAV, P.pack_nav(0.25, -0.25, 0x01), seq=42)
    t, seq, payload = P.unpack_frame(data)
    assert t == P.TYPE_NAV and seq == 42
    assert P.unpack_nav(payload) == (pytest.approx(0.25), pytest.approx(-0.25), 0x01)


def test_tool_roundtrip():
    data = P.pack_frame(P.TYPE_TOOL, P.pack_tool(-12.5, 0b010), seq=7)
    t, seq, payload = P.unpack_frame(data)
    assert (t, seq) == (P.TYPE_TOOL, 7)
    off, lift = P.unpack_tool(payload)
    assert off == pytest.approx(-12.5) and lift == 0b010


def test_status_roundtrip():
    payload = P.pack_status(0.14, 3.2, 47.8, 0b101, 1)
    data = P.pack_frame(P.TYPE_STATUS, payload, seq=1000)
    t, seq, pl = P.unpack_frame(data)
    speed, cur, bat, limits, mode = P.unpack_status(pl)
    assert (speed, cur, bat, limits, mode) == (pytest.approx(0.14), pytest.approx(3.2),
                                               pytest.approx(47.8), 0b101, 1)


def test_empty_payload_heartbeat():
    data = P.pack_frame(P.TYPE_HEARTBEAT, b'', seq=1)
    t, seq, payload = P.unpack_frame(data)
    assert (t, seq, payload) == (P.TYPE_HEARTBEAT, 1, b'')


def test_bad_header_rejected():
    data = bytearray(P.pack_frame(P.TYPE_HEARTBEAT, b'', 1))
    data[0] = 0x00
    with pytest.raises(ValueError):
        P.unpack_frame(bytes(data))


def test_crc_corruption_rejected():
    data = bytearray(P.pack_frame(P.TYPE_NAV, P.pack_nav(0.1, 0.1), 1))
    data[10] ^= 0xFF
    with pytest.raises(ValueError):
        P.unpack_frame(bytes(data))


def test_truncated_rejected():
    data = P.pack_frame(P.TYPE_NAV, P.pack_nav(0.1, 0.1), 1)
    with pytest.raises(ValueError):
        P.unpack_frame(data[:-1])


def test_payload_too_long_rejected():
    with pytest.raises(ValueError):
        P.pack_frame(P.TYPE_NAV, b'\x00' * 600, 1)


def test_seq_out_of_range():
    with pytest.raises(ValueError):
        P.pack_frame(P.TYPE_NAV, b'', 0x10000)


# ---- E3 批 1b（spec §3）：MODE 帧与 STATUS v2 按长度分派 -------------------

def test_mode_roundtrip():
    data = P.pack_frame(P.TYPE_MODE, P.pack_mode(P.MODE_REQ_AUTO, P.PROFILE_PREV), seq=11)
    t, seq, payload = P.unpack_frame(data)
    assert (t, seq) == (P.TYPE_MODE, 11)
    assert P.unpack_mode(payload) == (P.MODE_REQ_AUTO, P.PROFILE_PREV)
    assert len(data) == 11          # 2+2+1+2+2+2


def test_mode_payload_length_guard():
    with pytest.raises(ValueError):
        P.unpack_mode(b'\x01')


def test_status_v2_roundtrip_and_wire_size():
    payload = P.pack_status_v2(0.14, 0.0, 48.0, 0b101, 1,
                               P.PROFILE_REAL, P.AUTH_PC_GRANTED,
                               7, 0x3A, P.REJECT_NONE)
    assert len(payload) == P.STATUS_V2_LEN == 19
    data = P.pack_frame(P.TYPE_STATUS, payload, seq=5)
    assert len(data) == 28
    st = P.unpack_status_any(P.unpack_frame(data)[2])
    assert st['v'] == 2
    assert st['speed_mps'] == pytest.approx(0.14)
    assert (st['limits'], st['mode']) == (0b101, 1)
    assert (st['profile'], st['authority'], st['loop_alive'],
            st['build_id'], st['reject']) == (
        P.PROFILE_REAL, P.AUTH_PC_GRANTED, 7, 0x3A, P.REJECT_NONE)


def test_unpack_status_any_dispatches_v1_and_leaves_e3_keys_none():
    """A8 混跑用例一：旧固件帧 + 新 PC。不得崩，且不得把 limits 当成 profile。"""
    old = P.pack_status(0.1, 0.0, 48.0, 0b011, 0)     # 14 bytes
    st = P.unpack_status_any(old)
    assert st['v'] == 1 and st['mode'] == 0 and st['limits'] == 0b011
    assert st['profile'] is None and st['authority'] is None
    assert st['loop_alive'] is None and st['build_id'] is None
    assert st['reject'] is None


def test_unpack_status_any_rejects_other_lengths():
    for bad in (b'', b'\x00' * 13, b'\x00' * 15, b'\x00' * 18, b'\x00' * 20):
        with pytest.raises(ValueError):
            P.unpack_status_any(bad)


def test_wire_len_helper():
    assert P.wire_len(0) == 9 and P.wire_len(2) == 11
    assert P.wire_len(14) == 23 and P.wire_len(19) == 28


def test_reject_text_covers_every_code():
    codes = [P.REJECT_NONE, P.REJECT_PROFILE, P.REJECT_RCS_STALE,
             P.REJECT_FIELD_SWITCH, P.REJECT_ESTOP_LATCHED,
             P.REJECT_LOOP_STALLED, P.REJECT_NOT_IMPL,
             P.REJECT_FIELD_LATCHED, P.REJECT_PERMIT]
    assert set(P.REJECT_TEXT) == set(codes)
    assert all(isinstance(v, str) for v in P.REJECT_TEXT.values())
    # brief 原文这里写的是 `all(isinstance(v, str) and v for v in ...)`（所有值非空），
    # 与同一条 brief 的实现 `REJECT_NONE: ''` 直接矛盾，也与计划第 771 行 Task 4 的
    # `assert rx.reject_text() == ''`（reject=0 时 HUD 不显示文案）矛盾。
    # 以实现与 Task 4 为准：0 码文案必须为空，**非 0 码一律要有非空人话**。
    assert P.REJECT_TEXT[P.REJECT_NONE] == ''
    assert all(v for k, v in P.REJECT_TEXT.items() if k != P.REJECT_NONE)


def test_uart_vectors_cover_mode_and_status_v2():
    """spec §3.4 第三处：对拍向量里有 MODE 帧与 19 B STATUS，且类型没被猜错。

    sender() 旧逻辑按名字前缀猜帧类型，mode_/status_ 会掉进 HEARTBEAT 分支，
    即"发出去的是 NAV/HEARTBEAT"那种坑；这里钉住每个向量解出来的类型。
    """
    vecs = dict(uv.build_vectors())
    assert 'mode_auto' in vecs and 'mode_clear' in vecs and 'status_v2' in vecs
    assert vecs['mode_auto'] == P.pack_frame(
        P.TYPE_MODE, P.pack_mode(P.MODE_REQ_AUTO, P.PROFILE_PREV), 9)
    assert vecs['mode_clear'] == P.pack_frame(
        P.TYPE_MODE, P.pack_mode(P.MODE_REQ_CLEAR_ESTOP, P.PROFILE_PREV), 10)
    assert len(vecs['status_v2']) == P.wire_len(P.STATUS_V2_LEN) == 28
    # 名字 -> 期望帧类型（sender() 用的就是这个名字表，不再猜）
    expect = {'heartbeat': P.TYPE_HEARTBEAT, 'nav_straight': P.TYPE_NAV,
              'nav_turn': P.TYPE_NAV, 'nav_stop': P.TYPE_NAV,
              'tool_offset_lift': P.TYPE_TOOL, 'estop': P.TYPE_ESTOP,
              'mode_auto': P.TYPE_MODE, 'mode_clear': P.TYPE_MODE,
              'status_v2': P.TYPE_STATUS}
    for name, data in vecs.items():
        if 'must_reject' in name:
            continue
        assert name in expect, name
        frame_type, _seq, payload = P.unpack_frame(data)
        assert frame_type == expect[name], (name, frame_type)
        assert len(data) == P.wire_len(len(payload))
        if name == 'status_v2':
            assert len(payload) == P.STATUS_V2_LEN
            assert P.unpack_status_any(payload)['v'] == 2
        if name.startswith('mode'):
            assert len(payload) == 2
