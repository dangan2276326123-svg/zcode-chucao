"""Draw a numbered hole map for each part so the author can name joints in a message.

Each part gets one PNG: its cylindrical features plotted in the plane where they actually
lie, labelled ①②③… with diameter and local coordinates listed beside them. He can then
reply "连杆1 的 ② 接 电推杆 的 ①" and that is unambiguous - which is exactly what the
placement of the remaining 20 components has been waiting on.

Reads only the STEP copies already exported under cad_work/step and cad_work/cad_out/缺件.
"""
import glob
import io
import os
import json
import math
import os

from PIL import Image, ImageDraw, ImageFont

# PIL's built-in bitmap font cannot draw CJK (latin-1 only), so load a system TrueType
FONT = None
for cand in ("C:\Windows\Fonts\msyh.ttc", "C:\Windows\Fonts\simhei.ttf",
             "C:\Windows\Fonts\simsun.ttc", "C:\Windows\Fonts\arial.ttf"):
    if os.path.exists(cand):
        try:
            FONT = ImageFont.truetype(cand, 17)
            break
        except Exception:
            continue

from step_geom_report import TRIPLE, load, point_of, last_number, REF
from sw_hole_spacing import axis_dir

SRC_DIRS = [os.path.join("D:", os.sep + "ai work", "qoder", "cad_work", "step"),
            os.path.join("D:", os.sep + "ai work", "qoder", "cad_work", "cad_out", "缺件")]
OUT = os.path.join("D:", os.sep + "ai work", "qoder", "cad_work", "hole_maps")
INDEX = os.path.join(OUT, "index.json")
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉓㉔㉕㉖㉗㉘㉙㉚"


def holes(path):
    ent = load(path)
    seen, out = set(), []
    for _k, (t, a) in ent.items():
        if t != "CYLINDRICAL_SURFACE":
            continue
        r = last_number(a)
        if r is None or not (2.0 < r < 60.0):      # skip tiny screw-clearance noise and big outer rims
            continue
        loc = None
        for ref in REF.findall(a):
            loc = point_of(ent, int(ref))
            if loc:
                break
        ax = axis_dir(ent, a)
        if loc is None:
            continue
        key = (round(r * 2, 1), tuple(round(v, 1) for v in loc))
        if key in seen:
            continue
        seen.add(key)
        out.append({"d": round(r * 2, 1), "c": [round(v, 1) for v in loc],
                    "axis": [round(v, 2) for v in ax] if ax else None})
    return sorted(out, key=lambda h: (h["c"][0], h["c"][2], h["c"][1]))


def project(hs):
    """Pick the plane that spreads the holes widest, return 2D coords for drawing."""
    best, best_span = None, -1
    for pair in ((0, 2), (0, 1), (1, 2)):
        pts = [(h["c"][pair[0]], h["c"][pair[1]]) for h in hs]
        span = (max(p[0] for p in pts) - min(p[0] for p in pts)) + \
               (max(p[1] for p in pts) - min(p[1] for p in pts))
        if span > best_span:
            best_span, best = span, pair
    return best, [(h["c"][best[0]], h["c"][best[1]]) for h in hs]


def draw_one(name, hs):
    if not hs:
        return None
    axes, pts = project(hs)
    W, H = 1100, 760
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    pad = 120.0
    sx = (W - 2 * pad) / max(max(xs) - min(xs), 1.0)
    sy = (H - 2 * pad) / max(max(ys) - min(ys), 1.0)
    sc = min(sx, sy)
    cx0, cy0 = min(xs), min(ys)

    def px(p):
        return (pad + (p[0] - cx0) * sc, H - pad - (p[1] - cy0) * sc)

    d.text((14, 10), "%s   孔位图（%s 平面，单位 mm）" % (name, "".join("XYZ"[k] for k in axes)),
           fill="black", font=FONT)
    for i, (p, h) in enumerate(zip(pts, hs)):
        x, y = px(p)
        r = max(6.0, h["d"] / 2.0 * sc)
        d.ellipse([x - r, y - r, x + r, y + r], outline="black", width=2)
        tag = CIRCLED[i] if i < len(CIRCLED) else str(i + 1)
        d.text((x + r + 4, y - 8), tag, fill=(200, 0, 0), font=FONT)
        d.text((x + r + 4, y + 8), "D%g" % h["d"], fill=(90, 90, 90), font=FONT)
    lines = []
    for i, h in enumerate(hs[:30]):
        tag = CIRCLED[i] if i < len(CIRCLED) else str(i + 1)
        lines.append("%s D%-5g 局部坐标 (%g, %g, %g)" % (tag, h["d"], h["c"][0], h["c"][1], h["c"][2]))
    for row, t in enumerate(lines):
        d.text((14, 44 + row * 21), t, fill=(30, 30, 30), font=FONT)
    target = os.path.join(OUT, name + ".png")
    im.save(target)
    return {"part": name, "plane": "".join("XYZ"[k] for k in axes),
            "holes": hs, "png": target}


def main():
    os.makedirs(OUT, exist_ok=True)
    index = []
    for base in SRC_DIRS:
        for path in sorted(glob.glob(os.path.join(base, "*.step"))):
            name = os.path.splitext(os.path.basename(path))[0]
            rec = draw_one(name, holes(path))
            if rec:
                index.append(rec)
    io.open(INDEX, "w", encoding="utf-8").write(json.dumps(index, ensure_ascii=False, indent=1))
    print("wrote %d hole maps into %s" % (len(index), OUT))
    for rec in index:
        print("  %-26s %s plane, %d holes" % (rec["part"], rec["plane"], len(rec["holes"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
