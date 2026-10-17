# -*- coding: utf-8 -*-
"""Hole maps, second version: features come from circular EDGES, and each one is labelled
孔 or 凸台 instead of being guessed.

The first version listed every CYLINDRICAL_SURFACE and positioned it by that surface's
placement point. Both halves were wrong in ways the author could see on his own screen:

* placement points sit anywhere along the axis, so the coordinates printed beside each number
  were partly noise (连杆1's φ10 was printed at x=-108; the bore actually runs x=-20..30);
* a bore and the hub around it are two cylindrical surfaces on one axis, so a part with one
  hole and two bosses came out looking like it had five holes to mate.

This version takes positions from CIRCLE edges (exact centres), takes the direction from the
edge normal, groups concentric edges into one axis, and decides 孔 vs 凸台 from the
ADVANCED_FACE same_sense flag of the cylindrical face on that axis: .T. is convex material
(凸台), .F. is concave void (孔). That agreement was checked against 连杆1's own feature tree,
which says 切除-拉伸1=D12, 切除-拉伸2=D10, 凸台-拉伸2=D25, 凸台-拉伸3=D30, and the faces say
D12/D10 .F. and D25/D30 .T. - two independent sources, same answer.

Hinge spans in the legend are perpendicular distances between bore AXES, which is what a
pin-to-pin distance is; distances between placement points are not.

Usage:
    python -B tools/sw_hole_maps2.py [part-substring]
Writes cad_work/hole_maps2/*.png, cad_work/hole_maps2/index.json.
"""
import glob
import io
import json
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from step_circles import circle_features, groups, records, _ref, placement  # noqa: E402

FONT = None
for cand in ("C:\\Windows\\Fonts\\msyh.ttc", "C:\\Windows\\Fonts\\simhei.ttf",
             "C:\\Windows\\Fonts\\simsun.ttc"):
    if os.path.exists(cand):
        try:
            FONT = ImageFont.truetype(cand, 17)
            break
        except Exception:
            continue

SRC_DIRS = [os.path.join("D:", os.sep + "ai work", "qoder", "cad_work", "step"),
            os.path.join("D:", os.sep + "ai work", "qoder", "cad_work", "cad_out", "缺件")]
OUT = os.path.join("D:", os.sep + "ai work", "qoder", "cad_work", "hole_maps2")
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕㉖㉗㉘㉙㉚㉛㉜㉝㉞㉟"
AXISNAME = {(1.0, 0.0, 0.0): "X", (-1.0, 0.0, 0.0): "X",
            (0.0, 1.0, 0.0): "Y", (0.0, -1.0, 0.0): "Y",
            (0.0, 0.0, 1.0): "Z", (0.0, 0.0, -1.0): "Z"}


def cylinder_faces(path):
    """Cylindrical faces as (diameter, point on axis, unit axis, same_sense flag)."""
    recs = records(path)
    cyl = {}
    for n, (t, a) in recs.items():
        if t != "CYLINDRICAL_SURFACE" or len(a) < 3:
            continue
        loc, ax = placement(recs, _ref(a[1]))
        try:
            dia = round(float(a[2]) * 2, 2)
        except ValueError:
            continue
        if loc and ax:
            cyl[n] = (dia, loc, ax)
    out = []
    for n, (t, a) in recs.items():
        if t != "ADVANCED_FACE" or len(a) < 4:
            continue
        sf = _ref(a[2])
        if sf not in cyl:
            continue
        dia, loc, ax = cyl[sf]
        flag = a[3].strip().upper()
        out.append({"d": dia, "c": loc, "a": ax, "sense": flag})
    return out


def axis_line_dist(p1, a1, p2, a2):
    """Perpendicular distance between two infinite lines; None if they are not comparable."""
    cx = (a1[1] * a2[2] - a1[2] * a2[1], a1[2] * a2[0] - a1[0] * a2[2], a1[0] * a2[1] - a1[1] * a2[0])
    n = math.sqrt(sum(x * x for x in cx))
    d = tuple(p2[k] - p1[k] for k in range(3))
    if n < 1e-6:
        px = (d[1] * a1[2] - d[2] * a1[1], d[2] * a1[0] - d[0] * a1[2], d[0] * a1[1] - d[1] * a1[0])
        return round(math.sqrt(sum(x * x for x in px)), 1), "parallel"
    return round(abs(sum(d[k] * cx[k] for k in range(3))) / n, 1), "skew"


def features(path):
    """One entry per (axis, diameter): exact position, direction, 孔/凸台, axial stations."""
    fams = [f for f in groups(circle_features(path)) if f["a"] is not None]
    faces = cylinder_faces(path)
    out = []
    for fam in fams:
        for dia in sorted({round(x["d"], 1) for x in fam["feats"] if x["d"] >= 4.0}):
            on_axis = [fc for fc in faces if abs(fc["d"] - dia) < 0.15
                       and axis_line_dist(fam["c"], fam["a"], fc["c"], fc["a"])[0] < 0.3]
            senses = {fc["sense"] for fc in on_axis}
            kind = "孔" if ".F." in senses else ("凸台" if ".T." in senses else "未定")
            stations = sorted({round(sum(x["c"][k] * fam["a"][k] for k in range(3)), 1)
                               for x in fam["feats"] if abs(round(x["d"], 1) - dia) < 0.15})
            out.append({"d": dia, "kind": kind, "c": fam["c"], "a": tuple(round(v, 2) for v in fam["a"]),
                        "stations": stations, "n_edge": len(fam["feats"]), "faces": len(on_axis)})
    out.sort(key=lambda h: (h["kind"] != u"孔", -h["d"], h["c"][2], h["c"][0], h["c"][1]))
    # the tag is written INTO the record: a consumer that re-derives it from its own copy of
    # the circled-digit string gets a different number the moment that copy is one glyph short
    for i, h in enumerate(out):
        h["tag"] = CIRCLED[i] if i < len(CIRCLED) else str(i + 1)
    return out


def bore_pairs(hs):
    """Pin-to-pin distances between the bores of this part (axes, not placement points)."""
    bores = [h for h in hs if h["kind"] == u"孔"]
    rows = []
    for i in range(len(bores)):
        for j in range(i + 1, len(bores)):
            d, how = axis_line_dist(bores[i]["c"], bores[i]["a"], bores[j]["c"], bores[j]["a"])
            rows.append({"a": CIRCLED[i], "b": CIRCLED[j], "d": d, "how": how,
                         "dia": (bores[i]["d"], bores[j]["d"])})
    return rows


def draw_one(name, hs):
    if not hs or FONT is None:
        return None
    planes = ((0, 2), (0, 1), (1, 2))
    best, best_span = None, -1
    for pair in planes:
        pts = [(h["c"][pair[0]], h["c"][pair[1]]) for h in hs]
        span = (max(p[0] for p in pts) - min(p[0] for p in pts)) +                (max(p[1] for p in pts) - min(p[1] for p in pts))
        if span > best_span:
            best_span, best = span, pair
    pts = [(h["c"][best[0]], h["c"][best[1]]) for h in hs]

    rows = []
    for i, h in enumerate(hs[:34]):
        tag = CIRCLED[i] if i < len(CIRCLED) else str(i + 1)
        rows.append("%s φ%g %-4s 轴过(%g, %g, %g) 方向%s 站位%s" % (
            tag, h["d"], h["kind"], h["c"][0], h["c"][1], h["c"][2],
            AXISNAME.get(tuple(h["a"]), str(tuple(h["a"]))), h["stations"]))
    pairs = bore_pairs(hs)
    for pr in pairs:
        rows.append("   铆距 %s↔%s = %.1f (%s), φ%g/φ%g" % (
            pr["a"], pr["b"], pr["d"], pr["how"], pr["dia"][0], pr["dia"][1]))

    pad = 90.0
    top, plot_h = 56, 430
    legend_y = top + plot_h + 20
    W = 1240
    H = int(legend_y + 22 * (len(rows) + 1))
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    sc = min((W - 2 * pad) / max(max(xs) - min(xs), 1.0),
             (plot_h - 60.0) / max(max(ys) - min(ys), 1.0))
    x0, y0 = min(xs), min(ys)

    def px(p):
        return (pad + (p[0] - x0) * sc, top + plot_h - 30 - (p[1] - y0) * sc)

    d.text((14, 10), "%s  孔位图 v2（%s 平面，mm；孔=实线黑，凸台=虚线灰）" % (
        name, "".join("XYZ"[k] for k in best)), fill="black", font=FONT)
    d.line([(14, legend_y - 14), (W - 14, legend_y - 14)], fill=(205, 205, 205))
    for i, (p, h) in enumerate(zip(pts, hs)):
        x, y = px(p)
        r = max(8.0, h["d"] / 2.0 * sc)
        tag = CIRCLED[i] if i < len(CIRCLED) else str(i + 1)
        if h["kind"] == u"孔":
            d.ellipse([x - r, y - r, x + r, y + r], outline="black", width=3)
        else:
            for k in range(16):              # dashed ring: PIL has no dashed ellipse
                a1 = k * 22.5
                d.arc([x - r, y - r, x + r, y + r], a1, a1 + 13, fill="gray", width=2)
        off = 22 * sum(1 for q in pts[:i] if abs(q[0] - p[0]) < 6 and abs(q[1] - p[1]) < 6)
        d.text((x + r + 6, y - 10 + off), "%s %g %s" % (tag, h["d"], h["kind"]),
               fill=(200, 0, 0) if h["kind"] == u"孔" else (110, 110, 110), font=FONT)
    for row, t in enumerate(rows):
        d.text((14, legend_y + row * 22), t, fill=(25, 25, 25), font=FONT)
    target = os.path.join(OUT, name + ".png")
    im.save(target)
    return {"part": name, "plane": "".join("XYZ"[k] for k in best),
            "features": hs, "bore_pairs": pairs, "png": target}


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    os.makedirs(OUT, exist_ok=True)
    index, existing = [], {}
    ipath = os.path.join(OUT, "index.json")
    if os.path.exists(ipath):
        try:
            existing = {r["part"]: r for r in json.load(io.open(ipath, encoding="utf-8"))}
        except Exception:
            existing = {}
    for base in SRC_DIRS:
        for path in sorted(glob.glob(os.path.join(base, "*.step"))):
            name = os.path.splitext(os.path.basename(path))[0]
            if only and only not in name:
                continue
            hs = features(path)
            rec = draw_one(name, hs)
            if rec:
                existing[name] = rec
    index = [existing[k] for k in sorted(existing)]
    io.open(ipath, "w", encoding="utf-8").write(json.dumps(index, ensure_ascii=False, indent=1))
    nb = sum(1 for r in index if any(h["kind"] == u"孔" for h in r["features"]))
    print("[ok] maps=%d (with at least one bore: %d) -> %s" % (len(index), nb, OUT))
    for r in index:
        if only and only not in r["part"]:
            continue
        print("  %-22s %s plane  孔%d 凸台%d 未定%d" % (
            r["part"], r["plane"],
            sum(1 for h in r["features"] if h["kind"] == u"孔"),
            sum(1 for h in r["features"] if h["kind"] == u"凸台"),
            sum(1 for h in r["features"] if h["kind"] == u"未定")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
