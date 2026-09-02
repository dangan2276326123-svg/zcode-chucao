# -*- coding: utf-8 -*-
"""STM32 UART test vectors for firmware bring-up (对拍用).

The firmware developer (user) can paste these byte streams into a serial
terminal / test harness to verify the 0xA5 0x5A frame parser before the
Raspberry Pi bridge exists.  Also provides a small Python sender for use
with a USB-TTL adapter.

Usage (loopback or direct to STM32):
  python common/uart_vectors.py COM5            # interactive sender
  python common/uart_vectors.py --dump          # print hex vectors only
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import protocol as P  # noqa: E402


def build_vectors():
    vecs = []
    # 1. heartbeat (empty payload)
    vecs.append(('heartbeat', P.pack_frame(P.TYPE_HEARTBEAT, b'', 1)))
    # 2. nav straight: vL=vR=0.14 m/s, flags=0
    vecs.append(('nav_straight', P.pack_frame(P.TYPE_NAV, P.pack_nav(0.14, 0.14), 2)))
    # 3. nav turn: vL=0.10, vR=0.18
    vecs.append(('nav_turn', P.pack_frame(P.TYPE_NAV, P.pack_nav(0.10, 0.18), 3)))
    # 4. nav stop
    vecs.append(('nav_stop', P.pack_frame(P.TYPE_NAV, P.pack_nav(0.0, 0.0), 4)))
    # 5. tool: offset -12.5mm, lift beams 1+3
    vecs.append(('tool_offset_lift', P.pack_frame(P.TYPE_TOOL, P.pack_tool(-12.5, 0b101), 5)))
    # 6. estop
    vecs.append(('estop', P.pack_frame(P.TYPE_ESTOP, b'', 6)))
    # 7. corrupted CRC frame (parser must reject)
    good = bytearray(P.pack_frame(P.TYPE_NAV, P.pack_nav(0.1, 0.1), 7))
    good[-1] ^= 0xFF
    vecs.append(('bad_crc_must_reject', bytes(good)))
    # 8. truncated frame (parser must reject)
    vecs.append(('truncated_must_reject', P.pack_frame(P.TYPE_NAV, P.pack_nav(0.1, 0.1), 8)[:-2]))
    return vecs


def dump():
    for name, data in build_vectors():
        print('%-20s %3d B  %s' % (name, len(data), data.hex(' ')))


def sender(port, baud=115200, interval=0.1):
    import serial  # pyserial
    ser = serial.Serial(port, baud, timeout=0.1)
    seq = 0
    print('sending to %s @%d, Ctrl+C to stop' % (port, baud))
    while True:
        for name, data in build_vectors():
            if 'must_reject' in name:
                continue
            frame = P.pack_frame(P.TYPE_NAV if name.startswith('nav') else
                                 P.TYPE_TOOL if name.startswith('tool') else
                                 P.TYPE_ESTOP if name.startswith('estop') else
                                 P.TYPE_HEARTBEAT, data[7:-2], seq)
            ser.write(frame)
            print('%s seq=%d %d B' % (name, seq, len(frame)))
            seq = (seq + 1) & 0xFFFF
            import time
            time.sleep(interval)


if __name__ == '__main__':
    if '--dump' in sys.argv:
        dump()
    elif len(sys.argv) > 1:
        sender(sys.argv[1])
    else:
        dump()
