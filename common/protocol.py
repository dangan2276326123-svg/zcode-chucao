# -*- coding: utf-8 -*-
"""Shared UDP frame protocol: PC <-> Raspberry Pi <-> STM32.

Frame layout (v0.4 Table 3):
  0xA5 0x5A | len u16 LE | type u8 | seq u16 LE | payload (len-5 bytes) | crc16 u16 LE
  crc16 = CRC-16/CCITT-FALSE over all bytes AFTER the 2-byte header
  (len, type, seq, payload).

Types: 1 NAV, 2 ESTOP, 3 HEARTBEAT, 4 TOOL, 5 MODE (E3), 0x10 STATUS.
STATUS payload is 14 B on firmware before E3 and 19 B after; unpack_status_any()
dispatches on payload length (spec §3.5).
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

TYPE_MODE = 5           # E3: 权限申请/交回/解除急停/档案握手（spec §3.1）

# MODE.request（spec §3.1）
MODE_REQ_MANUAL = 0x00        # 交回人工
MODE_REQ_AUTO = 0x01          # 申请无人
MODE_REQ_TELEOP = 0x02        # 申请遥操作（批 2 实现；固件回 REJECT_NOT_IMPL）
MODE_REQ_CLEAR_ESTOP = 0x10   # 解除急停（A3 单确认）
MODE_REQ_PROFILE = 0x20       # 档案握手，profile 字段有效

# 车辆档案（spec §2 / §6）
PROFILE_NONE = 0
PROFILE_PREV = 1        # 上代车 3.25 m
PROFILE_REAL = 2        # 样机 2.15 m

# STATUS.authority = 最近一次权限变迁的原因（spec §3.2）
AUTH_BOOT = 0
AUTH_PC_GRANTED = 1
AUTH_FIELD_TAKEOVER = 2
AUTH_RCS_LOST = 3
AUTH_LINK_LOST_ESTOP = 4
AUTH_PC_CLEAR_ESTOP = 5
AUTH_PC_RELEASE = 6
AUTH_HEARTBEAT_RELEASE = 7

# STATUS.reject（spec §3.3）
REJECT_NONE = 0
REJECT_PROFILE = 1
REJECT_RCS_STALE = 2
REJECT_FIELD_SWITCH = 3
REJECT_ESTOP_LATCHED = 4
REJECT_LOOP_STALLED = 5
REJECT_NOT_IMPL = 6
REJECT_FIELD_LATCHED = 7
REJECT_PERMIT = 8

REJECT_TEXT = {
    REJECT_NONE: '',
    REJECT_PROFILE: '档案不符（PC 与固件不是同一台车）',
    REJECT_RCS_STALE: '遥控不新鲜（接收机断链或未同步）',
    REJECT_FIELD_SWITCH: '现场拨档不在"允许无人"位',
    REJECT_ESTOP_LATCHED: '急停仍锁存',
    REJECT_LOOP_STALLED: '执行面停摆（主循环计数不变，见 Fw-21）',
    REJECT_NOT_IMPL: '该模式本批未实现',
    REJECT_FIELD_LATCHED: '已被现场夺权，锁存中',
    REJECT_PERMIT: '许可位拒绝（门 N 下不许落刀/横移）',
}

STATUS_V1_LEN = 14
STATUS_V2_LEN = 19
STATUS_V1_FMT = '<fffBB'
STATUS_V2_FMT = '<fffBBBBBBB'   # + profile, authority, loop_alive, build_id, reject

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
        if idx < 0:
            return None, stream[pos:]
        if len(stream) - idx < HEADER_LEN + META_LEN:
            # a header was found but the frame is still incomplete: keep the
            # remainder FROM THE HEADER so a partial frame survives the next
            # read (review 2026-09-09 #6 — stream[pos:] would drop it).
            return None, stream[idx:]
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
    battery V, limit-switch bits, mode (0 manual / 1 auto / 2 estop).

    形态与长度都引用 `STATUS_V1_FMT` / `STATUS_V1_LEN`（:72-75），不在这里再写一遍
    字面量——写第二份就是给"改了一份没改另一份"留位子（AGENTS 清单第 6 条），
    而这一份漂了的代价是 v1/v2 分派按长度读错位字段。
    """
    return struct.pack(STATUS_V1_FMT, speed, current_a, battery_v, limits, mode)


def unpack_status(payload: bytes):
    if len(payload) != STATUS_V1_LEN:
        raise ValueError('status payload must be %d bytes' % STATUS_V1_LEN)
    return struct.unpack(STATUS_V1_FMT, payload)


# ---- E3 批 1b：MODE 帧与 STATUS v2（spec §3.1 / §3.2 / §3.5）--------------

def wire_len(payload_len: int) -> int:
    """线上总字节 = 载荷 + 9（2 头 + 2 长 + 1 型 + 2 序 + 2 CRC）。"""
    return payload_len + HEADER_LEN + META_LEN + 2


def pack_mode(request: int, profile: int = 0) -> bytes:
    """MODE payload: request code + 档案号（只在 MODE_REQ_PROFILE 时有意义）。"""
    return struct.pack('<BB', request, profile)


def unpack_mode(payload: bytes):
    if len(payload) != 2:
        raise ValueError('mode payload must be 2 bytes')
    return struct.unpack('<BB', payload)


def pack_status_v2(speed: float, current_a: float, battery_v: float,
                   limits: int, mode: int, profile: int, authority: int,
                   loop_alive: int, build_id: int, reject: int) -> bytes:
    """STATUS v2 (19 B) — spec §3.2。loop_alive/build_id/reject 都是 u8。"""
    return struct.pack(STATUS_V2_FMT, speed, current_a, battery_v, limits, mode,
                       profile, authority, loop_alive & 0xFF,
                       build_id & 0xFF, reject)


def unpack_status_any(payload: bytes) -> dict:
    """按载荷长度分派（A8）：14 B = v1（E3 之前的固件），19 B = v2。

    v1 时 E3 那五个键返回 None，这样调用方能区分"旧固件"与"新固件报了 0"。
    其它长度一律 ValueError —— 字段错位必须炸，不能静默读歪。
    """
    if len(payload) == STATUS_V1_LEN:
        speed, cur, bat, limits, mode = struct.unpack(STATUS_V1_FMT, payload)
        return {'speed_mps': speed, 'current_a': cur, 'battery_v': bat,
                'limits': limits, 'mode': mode, 'profile': None,
                'authority': None, 'loop_alive': None, 'build_id': None,
                'reject': None, 'v': 1}
    if len(payload) == STATUS_V2_LEN:
        (speed, cur, bat, limits, mode, profile, authority,
         loop_alive, build_id, reject) = struct.unpack(STATUS_V2_FMT, payload)
        return {'speed_mps': speed, 'current_a': cur, 'battery_v': bat,
                'limits': limits, 'mode': mode, 'profile': profile,
                'authority': authority, 'loop_alive': loop_alive,
                'build_id': build_id, 'reject': reject, 'v': 2}
    raise ValueError('status payload must be %d or %d bytes, got %d'
                     % (STATUS_V1_LEN, STATUS_V2_LEN, len(payload)))
