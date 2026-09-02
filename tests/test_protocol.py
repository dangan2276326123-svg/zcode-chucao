# -*- coding: utf-8 -*-
import pytest
from common import protocol as P


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
