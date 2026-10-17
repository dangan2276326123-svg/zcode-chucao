"""Quantify the two competing readings of the lift mechanism before spending time on CAD.

The unresolved question (docs/执行机构装配拓扑_20261016.md §2F) is whether the tool body
rotates while lifting:
  读法② triangle  - 机架 AC, 推杆 AD (variable), 摆杆 CE, with D and E sharing one pin, and
                 the tool body rigid on the 摆杆 ⇒ the body turns with the rocker.
  读法① guided   - the same drive triangle, but a second rocker plus 连杆3 as a cross tie
                 forms a quadrilateral that constrains the body ⇒ body translates only.

Both are driven by the same measured triangle, so the difference is exactly what the
author must settle, and the numbers below are the cost of settling it wrong:

  A(0,0) 推杆上铰   C(+107,-264) 摆杆上铰   |AC| = 285      (photo, 0.629 mm/px)
  |AD| = 449 measured in the photo vs 429 on the part (+4.7%)
  |CE| = 241 is only the VISIBLE length - the rocker continues behind the plate, so the
  rocker span is a lower bound and everything derived from it is bounded, not exact.

Reported per stroke step: actuator length, rocker angle, tool-tip rise, tool attitude
change. Attitude change is the quantity M16 asks for.
"""
import io
import json
import math
import os

OUT = os.path.join("D:", os.sep + "ai work", "qoder", "cad_work", "lift_two_readings.json")
A = (0.0, 0.0)
C = (107.0, -264.0)
S0 = 429.0            # actuator pin-to-pin from the part
STROKE = 200.0        # Hw-9 rated stroke
CE = 241.0            # rocker span: photo lower bound
# tool body fixed points relative to E, taken from the same photo reading
F_OFFSET = (94.0, -65.0)     # 铲刃 relative to E  (F - E from the pixel table)
V_SPEED = 10.0        # mm/s actuator speed, Hw-9


def circle_intersections(p0, r0, p1, r1):
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    d = math.hypot(dx, dy)
    if d < 1e-9 or d > r0 + r1 or d < abs(r0 - r1):
        return []
    a = (r0 * r0 - r1 * r1 + d * d) / (2 * d)
    h2 = r0 * r0 - a * a
    if h2 < 0:
        return []
    h = math.sqrt(h2)
    xm, ym = p0[0] + a * dx / d, p0[1] + a * dy / d
    return [(xm + h * dy / d, ym - h * dx / d), (xm - h * dy / d, ym + h * dx / d)]


def solve(s, ce):
    """D as the intersection of circle(A,s) and circle(C,ce); pick the outer branch."""
    cands = circle_intersections(A, s, C, ce)
    if not cands:
        return None
    return max(cands, key=lambda p: math.hypot(p[0] - C[0], p[1] - C[1]) + 0 * p[0]) if len(cands) == 1 \
        else max(cands, key=lambda p: p[0] ** 2 + p[1] ** 2)


def main():
    rows = []
    base = None
    for i in range(0, 11):
        s = S0 + STROKE * i / 10.0
        D = solve(s, CE)
        if D is None:
            rows.append({"stroke_mm": round(STROKE * i / 10.0, 1), "closed": False})
            continue
        ang = math.degrees(math.atan2(D[1] - C[1], D[0] - C[0]))
        tip = (D[0] + F_OFFSET[0], D[1] + F_OFFSET[1])
        if base is None:
            base = {"ang": ang, "z": tip[1]}
        rows.append({"stroke_mm": round(STROKE * i / 10.0, 1), "closed": True,
                     "rocker_deg": round(ang, 2),
                     "rise_read2_mm": round(tip[1] - base["z"], 1),
                     "attitude_change_deg": round(ang - base["ang"], 2),
                     "rise_read1_mm": round(tip[1] - base["z"], 1)})
    reached = [r for r in rows if r.get("closed")]
    out = {
        "inputs": {"A": A, "C": C, "AC": round(math.hypot(C[0], C[1]), 1), "actuator0": S0,
                   "stroke": STROKE, "rocker_CE_used": CE,
                   "note": "CE=241 is the photo's VISIBLE length, a lower bound"},
        "rows": rows,
        "closes_for_all_steps": len(reached) == len(rows),
        "max_rise_mm": max((r["rise_read2_mm"] for r in reached), default=None),
        "max_attitude_change_deg": max((abs(r["attitude_change_deg"]) for r in reached), default=None),
        "stroke_needed_for_50mm_rise_mm": next(
            (r["stroke_mm"] for r in reached if r["rise_read2_mm"] >= 50.0), None),
    }
    if out["stroke_needed_for_50mm_rise_mm"] is not None:
        out["time_for_50mm_rise_s"] = round(out["stroke_needed_for_50mm_rise_mm"] / V_SPEED, 1)
    io.open(OUT, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=2))
    print(json.dumps(out, ensure_ascii=True, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
