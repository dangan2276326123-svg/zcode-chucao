# -*- coding: utf-8 -*-
"""R3: shared TCP multipart-MJPEG frame parser (common/mjpeg.py)."""
from common.mjpeg import latest_jpeg


def test_no_eoi_returns_none():
    assert latest_jpeg(b'\xff\xd8abc') == (None, 0)


def test_eoi_without_soi_consumes_through():
    # a lone EOI with no preceding SOI: nothing decodable, but drop up to it
    assert latest_jpeg(b'xyz\xff\xd9') == (None, 5)


def test_single_complete_frame():
    frame = b'\xff\xd8' + b'A' * 4 + b'\xff\xd9'
    jpeg, consumed = latest_jpeg(frame + b'trailing')
    assert jpeg == frame
    assert consumed == len(frame)


def test_two_frames_returns_last_and_drops_first():
    f1 = b'\xff\xd8X\xff\xd9'
    f2 = b'\xff\xd8YY\xff\xd9'
    jpeg, consumed = latest_jpeg(f1 + f2)
    assert jpeg == f2
    assert consumed == len(f1) + len(f2)
