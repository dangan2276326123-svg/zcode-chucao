"""Hole-group geometry per part: positions, same-diameter pairwise distances, circles.

Purpose: the assembly and the missing shafts/pins/springs can only be built off real
numbers. This reads the STEP copies (mm) and reports, per part, every cylindrical
feature's diameter and location, the distances between same-diameter holes (those are
link lengths and bolt spacings), and whether a set of holes lies on a common circle
(that's a bolt circle, e.g. a wheel hub or a tine clamp).

Read-only: consumes STEP copies in cad_work/step written by tools/sw_export_step.py.
"""
import glob
import io
import math
import os
import re

from step_geom_report import TRIPLE, load, point_of, last_number, REF

STEP_DIR = os.path.join("D:", os.sep + "ai work", "qoder", "cad_work", "step")
OUT = os.path.join("D:", os.sep + "ai work", "qoder", "docs", "执行机构孔系几何_20261016.md")
AXIS_REF = re.compile(r"#(\d+)")


def axis_dir(entities, args):
    """Direction of a cylindrical surface's axis, from its placement's Z axis if present."""
    for ref in AXIS_REF.findall(args):
        eid = int(ref)
        if eid in entities and entities[eid][0] == "AXIS2_PLACEMENT_3D":
            sub = AXIS_REF.findall(entities[eid][1])
            for s in sub:
                sid = int(s)
                if sid in entities and entities[sid][0] == "DIRECTION":
                    t = re.search(r"\(([^)]*)\)", entities[sid][1])
                    if t:
                        vals = [float(x) for x in t.group(1).split(",")]
                        if len(vals) == 3:
                            return tuple(vals)
    return None


def features(path):
    entities = load(path)
    holes = []
    for eid, (etype, args) in entities.items():
        if etype != "CYLINDRICAL_SURFACE":
            continue
        r = last_number(args)
        if r is None or not (0.4 < r < 400):
            continue
        loc = None
        for ref in AXIS_REF.findall(args):
            loc = point_of(entities, int(ref))
            if loc:
                break
        if loc:
            holes.append((round(r * 2, 2), tuple(round(v, 2) for v in loc), axis_dir(entities, args)))
    span = []
    pts = []
    for _eid, (etype, args) in entities.items():
        if etype == "CARTESIAN_POINT":
            t = TRIPLE.search(args)
            if t:
                pts.append(tuple(float(x) for x in t.groups()))
    for ax in (0, 1, 2):
        vals = [p[ax] for p in pts]
        span.append((round(min(vals), 2), round(max(vals), 2)) if vals else (0.0, 0.0))
    return holes, span


def fit_circle(points):
    """Least-squares circle fit (algebraic, linearised). Returns (cx, cy, r, max_residual)."""
    import numpy as np
    n = len(points)
    if n < 3:
        return None
    xy = np.asarray(points, dtype=float)
    x, y = xy[:, 0], xy[:, 1]
    A = np.column_stack([x, y, np.ones(n)])
    b = x ** 2 + y ** 2
    coef, _res, _rank, _sv = np.linalg.lstsq(A, b, rcond=None)
    D, E, F = coef
    cx, cy = D / 2.0, E / 2.0
    r2 = F + cx * cx + cy * cy
    if r2 <= 0:
        return None
    rad = math.sqrt(r2)
    resid = np.abs(np.hypot(x - cx, y - cy) - rad)
    return (round(float(cx), 2), round(float(cy), 2), round(float(rad), 2), round(float(resid.max()), 2))


def main():
    lines = ["# 执行机构孔系几何（2026-10-16，单位 mm）", "",
             "> 由 `tools/sw_export_step.py` 只读导出的 STEP 副本解析，`tools/sw_hole_spacing.py` 生成。",
             "> 模型按实物绘制，所以这里的每个数都可以当作整机几何的设计值使用；",
             "> 未画出的件（弹簧、轴、销、安装座等）在正文里仍标待确认，不因本表存在而升格为已验证。", ""]
    for path in sorted(glob.glob(os.path.join(STEP_DIR, "*.step"))):
        name = os.path.splitext(os.path.basename(path))[0]
        holes, span = features(path)
        if not holes:
            continue
        groups = {}
        for d, loc, axd in holes:
            groups.setdefault(d, []).append(loc)
        lines.append("## %s" % name)
        lines.append("")
        lines.append("包围盒：X %g..%g，Y %g..%g，Z %g..%g" % (
            span[0][0], span[0][1], span[1][0], span[1][1], span[2][0], span[2][1]))
        lines.append("")
        lines.append("| 孔径 | 个数 | 孔心位置 | 同径孔心距 | 共圆拟合 |")
        lines.append("| --- | --- | --- | --- | --- |")
        for d in sorted(groups, key=lambda k: -len(groups[k])):
            pts = groups[d]
            uniq = sorted(set(pts))
            pos = "；".join("(%g, %g, %g)" % p for p in uniq[:6])
            if len(uniq) > 6:
                pos += "；…"
            dists = []
            for i in range(len(uniq)):
                for j in range(i + 1, len(uniq)):
                    dd = math.dist(uniq[i], uniq[j])
                    if dd > 0.01:
                        dists.append(round(dd, 1))
            dtxt = "、".join(str(x) for x in sorted(set(dists))[:8]) or "—"
            circ = ""
            if len(uniq) >= 3:
                for axpair in ((0, 1), (0, 2), (1, 2)):
                    proj = [(p[axpair[0]], p[axpair[1]]) for p in uniq]
                    f = fit_circle(proj)
                    if f and f[3] < 0.6:
                        circ = "半径 %g（残差 %g，%s 面）" % (f[2], f[3], "".join("XYZ"[k] for k in axpair))
                        break
            lines.append("| D%g | %d | %s | %s | %s |" % (d, len(pts), pos, dtxt, circ or "—"))
        lines.append("")
    io.open(OUT, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("wrote %s lines=%d" % (OUT, len(lines)))


if __name__ == "__main__":
    main()
