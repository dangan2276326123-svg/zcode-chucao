# -*- coding: utf-8 -*-
"""Raspberry Pi bridge: UDP <-> UART with link watchdog.

PC sends NAV/TOOL/ESTOP/HEARTBEAT UDP frames -> this relays them to the
STM32 over serial.  MCU STATUS (0x10) frames are relayed back as UDP.
If no PC frame arrives within LINK_TIMEOUT_MS while auto_forward is on,
this process itself injects an ESTOP frame to the MCU (second safety net,
in addition to the MCU's own 500 ms watchdog).

Pure-python core (parse/decide) separated from I/O so it is testable
without hardware.
"""
import os
import sys
import socket
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from common import protocol as P  # noqa: E402

LINK_TIMEOUT_MS = 500
PC_IP = '192.168.1.2'
PC_PORT = 9100
UDP_PORT = 9000


def decide_forward(raw, now_ms, last_pc_ms, auto_on):
    """Return (forward_bytes_or_None, estop_inject_bool, new_last_pc_ms).

    Called for every received UDP datagram AND periodically with raw=None
    (heartbeat check).  Watchdog: no PC frame for LINK_TIMEOUT_MS while
    auto is on -> inject estop.
    """
    inject = False
    if raw is not None:
        last_pc_ms = now_ms
        return raw, False, last_pc_ms
    if auto_on and (now_ms - last_pc_ms) > LINK_TIMEOUT_MS:
        inject = True
        # reset timer so we inject once per timeout window
        last_pc_ms = now_ms
    return None, inject, last_pc_ms


def relay_once(ser, sock, buf, last_pc_ms, auto_on, now_ms=None):
    """One poll iteration: read UDP (non-blocking via settimeout earlier),
    forward to serial; read serial, forward status to PC. Returns updated
    last_pc_ms and whether estop was injected (for logging)."""
    now_ms = now_ms if now_ms is not None else _ms()
    data = buf.get_udp()
    fwd, inject, last_pc_ms = decide_forward(data, now_ms, last_pc_ms, auto_on)
    if fwd:
        ser.write(fwd)
    if inject:
        estop = P.pack_frame(P.TYPE_ESTOP, b'', seq=_seq())
        ser.write(estop)
    # serial -> udp
    frame = buf.get_serial()
    if frame is not None:
        try:
            sock.sendto(frame, (PC_IP, PC_PORT))
        except OSError:
            pass
    return last_pc_ms, inject


def extract_one_stream(frame_bytes):
    """Validate a single frame; returns it if valid else raises ValueError."""
    P.unpack_frame(frame_bytes)
    return frame_bytes


def _ms():
    return int(time.monotonic() * 1000)


def _seq():
    _seq.n = getattr(_seq, 'n', 0) + 1
    return _seq.n & 0xFFFF


class BridgeBuffers:
    """Abstracts socket/serial reads so logic is testable.  In production
    wired to real endpoints in main(); in tests fed with lists."""

    def __init__(self, udp_iter=None, serial_iter=None):
        self._udp = iter(udp_iter or [])
        self._ser = iter(serial_iter or [])
        self.serial_written = []
        self.udp_sent = []

    def get_udp(self):
        return next(self._udp, None)

    def get_serial(self):
        return next(self._ser, None)

    # write hooks used by relay_once
    def write(self, data):
        self.serial_written.append(data)


def main():
    """Production loop (Raspberry Pi)."""
    import serial  # pyserial
    import yaml
    cfg_path = os.path.join(os.path.dirname(__file__), 'config.yaml')
    cfg = {}
    if os.path.exists(cfg_path):
        with open(cfg_path, encoding='utf-8') as f:
            cfg = yaml.safe_load(f)

    ser = serial.Serial(cfg.get('serial_dev', '/dev/ttyAMA0'),
                        cfg.get('baud', 115200), timeout=0)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('0.0.0.0', cfg.get('udp_port', UDP_PORT)))
    sock.settimeout(0.002)
    pc = (cfg.get('pc_ip', PC_IP), cfg.get('pc_port', PC_PORT))
    last_pc = _ms()
    print('bridge up: udp:%d -> %s' % (cfg.get('udp_port', UDP_PORT), ser.port))
    while True:
        try:
            raw, _ = sock.recvfrom(2048)
        except socket.timeout:
            raw = None
        now = _ms()
        fwd, inject, last_pc = decide_forward(raw, now, last_pc, auto_on=True)
        if fwd:
            ser.write(fwd)
        if inject:
            ser.write(P.pack_frame(P.TYPE_ESTOP, b'', seq=_seq()))
        try:
            sdata = ser.read(256)
        except OSError:
            sdata = b''
        # naive stream split: forward whole frames only
        if sdata:
            frame = P.extract_one(sdata) if hasattr(P, 'extract_one') else None
            if frame:
                try:
                    sock.sendto(frame, pc)
                except OSError:
                    pass


if __name__ == '__main__':
    main()
