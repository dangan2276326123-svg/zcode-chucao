# -*- coding: utf-8 -*-
"""R4 (2026-09-14): Ackermann4WS geometry must be self-consistent.

The re-review showed the old rear-counter-steer made the four wheels NOT share
one ICC (left/right pairs differed by the track width).  The fix is
front-wheel Ackermann + rear straight; these tests assert the rigid-body
properties that must hold: one common ICC, straight rear wheels, per-wheel
speed proportional to its radius to that ICC, left/right mirror, and the
straight-line limit.
"""
import numpy as np
import pytest

from network.nav_control import Ackermann4WS

L, TF, TR = 1.2, 0.8, 0.8
POS = {'fl': (L, TF / 2), 'fr': (L, -TF / 2),
       'rl': (0.0, TR / 2), 'rr': (0.0, -TR / 2)}


def _pos(w):
    return np.array(POS[w], dtype=float)


def _perp(w, angles):
    th = angles[w]
    return np.array([-np.sin(th), np.cos(th)])   # radius-to-ICC direction


def _icc_from_two(a, b, angles):
    d1, d2 = _perp(a, angles), _perp(b, angles)
    A = np.column_stack([d1, -d2])
    t_s = np.linalg.solve(A, _pos(b) - _pos(a))
    return _pos(a) + t_s[0] * d1


def test_straight_limit():
    g = Ackermann4WS(L, TF, TR)
    ang, sp = g.compute(0.0, 0.14)
    assert all(abs(v) < 1e-12 for v in ang.values())
    assert all(abs(v - 0.14) < 1e-12 for v in sp.values())


def test_rear_wheels_straight():
    g = Ackermann4WS(L, TF, TR)
    for d in (0.2, -0.2, 0.08):
        ang, _ = g.compute(d, 0.14)
        assert ang['rl'] == 0.0 and ang['rr'] == 0.0


def test_all_four_wheels_share_one_icc():
    g = Ackermann4WS(L, TF, TR)
    for d in (0.2, -0.2, 0.08):
        ang, _ = g.compute(d, 0.14)
        icc = _icc_from_two('fl', 'fr', ang)
        assert abs(icc[0]) < 1e-6                       # on the rear-axle line
        for w in POS:                                   # every wheel points at it
            th = ang[w]
            x, y = POS[w]
            resid = np.cos(th) * (icc[0] - x) + np.sin(th) * (icc[1] - y)
            assert abs(resid) < 1e-6


def test_speeds_rigid_about_icc():
    g = Ackermann4WS(L, TF, TR)
    v = 0.14
    for d in (0.2, -0.2, 0.08):
        ang, sp = g.compute(d, v)
        icc = _icc_from_two('fl', 'fr', ang)
        omega = v / np.hypot(icc[0], icc[1])           # rear-axle center at origin
        for w in POS:
            r = np.hypot(icc[0] - POS[w][0], icc[1] - POS[w][1])
            assert sp[w] == pytest.approx(omega * r, rel=1e-6)


def test_left_right_mirror():
    g = Ackermann4WS(L, TF, TR)
    ang_p, sp_p = g.compute(0.2, 0.14)
    ang_n, sp_n = g.compute(-0.2, 0.14)
    assert ang_n['fl'] == pytest.approx(-ang_p['fr'])
    assert ang_n['fr'] == pytest.approx(-ang_p['fl'])
    assert sp_n['fl'] == pytest.approx(sp_p['fr'])
    assert sp_n['fr'] == pytest.approx(sp_p['fl'])
    assert sp_n['rl'] == pytest.approx(sp_p['rr'])
