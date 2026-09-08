# -*- coding: utf-8 -*-
"""P0-3 regression: online preprocessing must match training normalization."""
import numpy as np

from pc.perception import preprocess_rgb


def test_preprocess_output_in_image_net_range():
    # worst-case pixels (all-0 and all-255) must stay within ~[-2.2, 2.7]
    lo = preprocess_rgb(np.zeros((4, 4, 3), np.uint8))
    hi = preprocess_rgb(np.full((4, 4, 3), 255, np.uint8))
    assert -2.2 <= float(lo.min()) <= float(lo.max()) <= 2.7


def test_preprocess_midgrey_near_zero():
    mid = preprocess_rgb(np.full((4, 4, 3), 128, np.uint8))
    assert abs(float(mid.mean())) < 0.3
