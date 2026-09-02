# -*- coding: utf-8 -*-
"""Shared UDP frame protocol: PC <-> Raspberry Pi <-> STM32.

Frame layout (v0.4 Table 3):
  0xA5 0x5A | len u16 LE | type u8 | seq u16 LE | payload (len-5 bytes) | crc16 u16 LE
  crc16 = CRC-16/CCITT-FALSE over all bytes AFTER the 2-byte header
  (len, type, seq, payload).

Types: 1 NAV, 2 ESTOP, 3 HEARTBEAT, 4 TOOL, 0x10 STATUS.
"""
import struct

HEADER = b'\xA5\x5A'
HEADER_LEN = 2        # header itself, NOT covered by crc
META_LEN = 5          # len(2) + type(1) + seq(2)

TYPE_NAV = 1
TYPE_ESTOP = 2
TYPE_HEARTBEAT = 3
TYPE_TOOL = 4
TYPE_STATUS = 0x10

_MAX_PAYLOAD = 512


def crc16_ccitt_false(data: bytes) -> int:
    """CRC-16/CCITT-FALSE: poly 0x1021, init 0xFFFF, no reflect, xorout 0."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if (crc & 0x8000) else (crc << 1)
            crc &= 0xFFFF
    return crc


def pack_frame(frame_type: int, payload: bytes, seq: int) -> bytes:
    if not 0 <= seq <= 0xFFFF:
        raise ValueError('seq must fit u16')
    if len(payload) > _MAX_PAYLOAD:
        raise ValueError('payload too long: %d' % len(payload))
    body = struct.pack('<HBH', META_LEN + len(payload), frame_type, seq & 0xFFFF) + payload
    return HEADER + body + struct.pack('<H', crc16_ccitt_false(body))


def extract_one(stream: bytes):
    """Extract the first complete valid frame from a raw serial stream.

    Returns (frame_bytes, remainder) or (None, stream) if no full valid
    frame is present. Invalid prefixes are skipped.
    """
    pos = 0
    while True:
        idx = stream.find(HEADER, pos)
        if idx < 0 or len(stream) - idx < HEADER_LEN + META_LEN:
            return None, stream[pos:]
        declared = int.from_bytes(stream[idx + 2:idx + 4], 'little')
        if not META_LEN <= declared <= META_LEN + _MAX_PAYLOAD:
            pos = idx + 1
            continue
        end = idx + HEADER_LEN + declared + 2
        if end > len(stream):
            return None, stream[idx:]
        chunk = stream[idx:end]
        try:
            unpack_frame(chunk)
            return chunk, stream[end:]
        except ValueError:
            pos = idx + 1


def unpack_frame(data: bytes):
    """Return (type, seq, payload). Raises ValueError on any malformation."""
    if len(data) < HEADER_LEN + META_LEN + 2:
        raise ValueError('frame too short: %d bytes' % len(data))
    if data[:2] != HEADER:
        raise ValueError('bad header')
    declared_len, frame_type, seq = struct.unpack('<HBH', data[2:7])
    if declared_len < META_LEN or declared_len > META_LEN + _MAX_PAYLOAD:
        raise ValueError('bad declared length %d' % declared_len)
    frame_end = HEADER_LEN + declared_len + 2
    if len(data) < frame_end:
        raise ValueError('truncated frame: need %d, got %d' % (frame_end, len(data)))
    payload = data[7:HEADER_LEN + declared_len]
    (crc_rx,) = struct.unpack('<H', data[HEADER_LEN + declared_len:frame_end])
    if crc16_ccitt_false(data[2:HEADER_LEN + declared_len]) != crc_rx:
        raise ValueError('crc mismatch')
    return frame_type, seq, payload


# ---- payload builders ----------------------------------------------------

def pack_nav(v_left: float, v_right: float, flags: int = 0) -> bytes:
    """NAV payload: left/right wheel speeds m/s, flags bitfield."""
    return struct.pack('<ffB', v_left, v_right, flags)


def unpack_nav(payload: bytes):
    if len(payload) != 9:
        raise ValueError('nav payload must be 9 bytes')
    return struct.unpack('<ffB', payload)


def pack_tool(offset_mm: float, lift: int) -> bytes:
    """TOOL payload: middle-slide offset mm, lift bitmask (bit0-2 = beam 1-3)."""
    return struct.pack('<fB', offset_mm, lift)


def unpack_tool(payload: bytes):
    if len(payload) != 5:
        raise ValueError('tool payload must be 5 bytes')
    return struct.unpack('<fB', payload)


def pack_status(speed: float, current_a: float, battery_v: float,
                limits: int, mode: int) -> bytes:
    """STATUS (0x10) payload from MCU: wheel speed m/s, motor current A,
    battery V, limit-switch bits, mode (0 manual / 1 auto / 2 estop)."""
    return struct.pack('<fffBB', speed, current_a, battery_v, limits, mode)


def unpack_status(payload: bytes):
    if len(payload) != 14:
        raise ValueError('status payload must be 14 bytes')
    return struct.unpack('<fffBB', payload)
