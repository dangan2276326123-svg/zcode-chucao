# -*- coding: utf-8 -*-
"""Measure hinge spans between PIN AXIS LINES, from CIRCLE edges.

Two mistakes this replaces, both of which the author caught:

* The hole maps listed every CYLINDRICAL_SURFACE, so a boss and the bore inside it each got
  their own number - 连杆1 read as "5 holes" when only one of them is a hole.
* Those features were positioned by the cylinder placement, which may sit anywhere along the
  axis. So a "distance between two features" picked up a meaningless along-axis component:
  连杆1's 385 survived only because the two pins happen to be parallel, and the X=-108 that
  went with it was pure noise (the real φ10 bore runs X -20..30).

Here every circular edge is resolved to its true centre and normal (step_circles), edges are
grouped into concentric families = one axis each, and spans are the perpendicular distance
between two axis lines, which is what a pin-to-pin hinge distance actually is.

Run:  python tools/sw_circle_spans.py [part-substring]
"""
import glob
import io
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from step_circles import circle_features, groups  # noqa: E402

SRC = ["cad_work/step", "cad_work/cad_out/缺件"]
MIN_DIA = 4.0                      # ignore M-screw pilot circles below φ4
CLAIMS = {
    "电推杆": (429.0, "两端 φ10 铰孔"),
    "连杆1": (385.0, "φ10 端孔 ↔ φ25 座"),
    "刀柄3": (140.0, "两个 φ10"),
    "连杆3": (510.5, "两个 φ20"),
    "连杆2": (351.8, "①↔③"),
    "刀柄1": (241.0, "照片可见段下界"),
}


def families(path):
    """One entry per axis line: (diameters, representative point, unit axis, axial stations)."""
    feats = [f for f in circle_features(path) if f["d"] >= MIN_DIA]
    out = []
    for fam in groups(feats):
        ds = sorted({round(x["d"], 1) for x in fam["feats"]})
        st = sorted({round(sum(x["c"][k] * fam["a"][k] for k in range(3)), 1) for x in fam["feats"]})
        # representative point = the family centre, pulled onto the axis through the first edge
        out.append({"d": ds, "c": fam["c"], "a": fam["a"], "stations": st, "n": len(fam["feats"])})
    return out


def line_dist(f1, f2):
    """Perpendicular distance between two infinite axis lines (0 when they intersect)."""
    a1, a2 = f1["a"], f2["a"]
    cx = (a1[1] * a2[2] - a1[2] * a2[1], a1[2] * a2[0] - a1[0] * a2[2], a1[0] * a2[1] - a1[1] * a2[0])
    n = math.sqrt(sum(x * x for x in cx))
    d = tuple(f2["c"][k] - f1["c"][k] for k in range(3))
    if n < 1e-6:                                     # parallel: |Δp × a|
        px = (d[1] * a1[2] - d[2] * a1[1], d[2] * a1[0] - d[0] * a1[2], d[0] * a1[1] - d[1] * a1[0])
        return round(math.sqrt(sum(x * x for x in px)), 1), "parallel"
    return round(abs(sum(d[k] * cx[k] for k in range(3))) / n, 1), "skew"


def paths(only=None):
    for base in SRC:
        for p in sorted(glob.glob(os.path.join(base, "*.step"))):
            name = os.path.splitext(os.path.basename(p))[0]
            if not only or only in name:
                yield name, p


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    lines = []
    for name, path in paths(only):
        fams = families(path)
        if not fams:
            continue
        lines.append("== %s：%d 条轴线（按圆边归并，非圆柱面）==" % (name, len(fams)))
        for i, f in enumerate(sorted(fams, key=lambda x: -max(x["d"])), 1):
            lines.append("   F%-2d φ%-14s 轴方向%-16s 轴向站 %s" % (
                i, str(f["d"]), tuple(round(v, 2) for v in f["a"]), f["stations"]))
        spans = []
        for i in range(len(fams)):
            for j in range(i + 1, len(fams)):
                d, how = line_dist(fams[i], fams[j])
                if 20.0 < d < 800.0:
                    spans.append((d, how, fams[i], fams[j]))
        spans.sort(key=lambda s: -s[0])
        lines.append("   轴线间距（铰距候选，>20mm）:")
        for d, how, f1, f2 in spans[:8]:
            lines.append("      φ%s ↔ φ%s = %.1f  (%s)" % (f1["d"], f2["d"], d, how))
        if name in CLAIMS:
            claimed, what = CLAIMS[name]
            hit = [s for s in spans if abs(s[0] - claimed) < 2.0]
            lines.append("   先前声称 %.1f (%s) -> %s" % (
                claimed, what,
                ("轴线间距复核通过: %.1f" % hit[0][0]) if hit else "复核不通过，作废"))
    txt = "\n".join(lines)
    out = "cad_work/circ.txt" if not only else "cad_work/circ_selected.txt"
    io.open(out, "w", encoding="utf-8").write(txt + "\n")
    print("[ok] %d lines -> %s" % (len(lines), out))


if __name__ == "__main__":
    main()
