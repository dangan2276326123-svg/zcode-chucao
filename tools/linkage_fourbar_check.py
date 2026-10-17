"""Four-bar lift closure check, driven by the photo-derived topology hypothesis.

Topology read off the photo (see docs/执行机构装配拓扑_20261016.md §2C): each station shows
a vertical actuator plus TWO symmetric inclined side bars carrying the tool body, so the
planar loop is  ground(机架) - actuator(电推杆) - link(连杆) - tool body(刀体边),
and 连杆3 (725 mm long, holes 510 apart, 4x phi20 at +-60) reads as a transverse tie rod
joining the left and right side bars rather than as a member of the planar loop.

Bar lengths come from the parts' own hole readings (mm):
  actuator pin-to-pin  429  (电推杆 phi10 holes)
  link                 385  (连杆1 D25<->D10)  and 352 (连杆2) - the two side bars, read
                            33 mm apart, which is itself a flag, not a number to average
  tie rod              510  (连杆3)

The ground span g and the tool-body span c are NOT readable from the parts, so they are
swept over a plausible band and the question asked is: does the loop close at all, and if
it does, how much does the tool lift and how much does its attitude rotate?

What this CAN be used for: whether the bar lengths make the loop impossible at all.
What it CANNOT: the "lift" column is a max over all solution-branch pairings (no continuous
branch is tracked), so it is an upper bound of a geometric range, NOT the machine's lift
travel - do not quote it in the thesis or in a report. Fixing it needs the real joint map
(see docs/执行机构装配拓扑_20261016.md §2C), not a finer grid.
"""
import io
import json
import math
import os

import numpy as np

OUT = os.path.join("D:", os.sep + "ai work", "qoder", "cad_work", "fourbar_check.json")
S_DOWN = 429.0          # actuator pin-to-pin at the modelled (retracted-ish) state
STROKE = 200.0          # 电推杆 rated stroke, Hw-9
LINKS = (385.0, 352.0)  # the two side-bar readings
G_BAND = (200.0, 250.0, 300.0, 350.0, 400.0)
C_BAND = (250.0, 300.0, 350.0, 400.0, 450.0)


def solve(s, l, g, c):
    """Return list of (alpha_deg, theta_deg, Q1, Q2) solutions of the loop."""
    sols = []
    alphas = np.arange(-175.0, -5.0, 0.25)      # actuator points downward
    thetas = np.arange(0.0, 360.0, 0.5)         # tool-body orientation
    A = np.stack([np.cos(np.radians(alphas)) * s, np.sin(np.radians(alphas)) * s], axis=1)
    for th in thetas:
        ct, st = math.cos(math.radians(th)), math.sin(math.radians(th))
        Q2 = A + np.array([c * ct, c * st])
        r = np.hypot(Q2[:, 0] - g, Q2[:, 1]) - l
        hit = np.where(np.abs(r) < 0.6)[0]
        for i in hit:
            sols.append((float(alphas[i]), float(th), tuple(np.round(A[i], 1)), tuple(np.round(Q2[i], 1))))
    return sols


def main():
    rows = []
    for g in G_BAND:
        for c in C_BAND:
            for l in LINKS:
                lo = solve(S_DOWN, l, g, c)
                hi = solve(S_DOWN + STROKE, l, g, c)
                if not lo or not hi:
                    rows.append({"g": g, "c": c, "link": l, "closed": bool(lo) and bool(hi),
                                 "note": "no closure in swept band"})
                    continue
                # lift = vertical travel of the tool pivot Q1 between the two states
                lift = max(abs(a[2][1] - b[2][1]) for a in lo for b in hi)
                minlift = min(abs(a[2][1] - b[2][1]) for a in lo for b in hi)
                att = [abs(a[1] - b[1]) for a in lo for b in hi if abs(a[2][1] - b[2][1] - minlift) < 1.0]
                rows.append({"g": g, "c": c, "link": l, "closed": True,
                             "solutions": len(lo),
                             "lift_max_mm": round(lift, 1),
                             "lift_min_mm": round(minlift, 1),
                             "att_change_deg_at_min_lift": round(min(att), 1) if att else None})
    ok = [r for r in rows if r.get("closed")]
    summary = {
        "grid": len(rows), "closing": len(ok),
        "lift_range_over_closing_cases": [min(r["lift_max_mm"] for r in ok),
                                          max(r["lift_max_mm"] for r in ok)] if ok else None,
        "rows": rows,
    }
    io.open(OUT, "w", encoding="utf-8").write(json.dumps(summary, ensure_ascii=False, indent=2))
    summary["warning"] = ("lift_* columns are branch-pair maxima, not physical lift travel;"
                          " only the closed/not-closed verdict is usable")
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, ensure_ascii=True))
    for r in rows:
        if r.get("closed"):
            print("g=%g c=%g l=%g lift<=%g (min %g) dtheta=%s" % (
                r["g"], r["c"], r["link"], r["lift_max_mm"], r["lift_min_mm"],
                r["att_change_deg_at_min_lift"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
