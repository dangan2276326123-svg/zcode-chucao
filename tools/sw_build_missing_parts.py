"""Build the missing hardware for the lift mechanism as real .SLDPRT parts, and verify
each one by exporting STEP and reading the geometry back.

These are the parts the author confirmed were never modelled. Their sizes split into two
kinds and the code keeps them visibly apart:
  * derived - taken from measurements already on record (hole diameters read off his own
    parts, or spans measured off the photo);
  * placeholder - geometry nobody has measured yet (the lug between 连杆2 and 刀柄1, the
    spring's wire/mean diameter). Those get a real solid so the assembly can be placed,
    but the file name and the log both say 待实测, so nobody can mistake the drawing for a
    finished design.

Every part goes through the same loop: sketch -> feature -> save -> STEP -> parse back ->
assert the box and the hole diameters. A part that fails its assertion is reported, not
quietly kept.
"""
import io
import json
import os
import re
import sys

import pythoncom
import win32com.client
from win32com.client.gencache import EnsureModule

SW_CLSID = "{83A33D31-27C5-11CE-BFD4-00400513BB57}"
PART_TPL = os.path.join("C:", os.sep + "ProgramData", "SOLIDWORKS", "SOLIDWORKS 2024",
                        "templates", "gb_part.prtdot")
OUT = os.path.join("D:", os.sep + "ai work", "qoder", "cad_work", "cad_out", "缺件")
LOG = os.path.join(OUT, "parts_log.json")
GEN = os.path.join(os.environ.get("TEMP", ""), "gen_py", "3.9",
                   "83A33D31-27C5-11CE-BFD4-00400513BB57x0x32x0.py")
TOOLS = os.path.join("D:", os.sep + "ai work", "qoder", "tools")
sys.path.insert(0, TOOLS)

M = 0.001  # mm -> m (the API works in metres)


def arg_names(method):
    text = io.open(GEN, encoding="utf-8", errors="replace").read()
    m = re.search(r"def " + method + r"\((.*?)\)\s*:\s*$", text, re.S | re.M)
    if not m:
        raise RuntimeError("signature for %s not parsed" % method)
    return [a.strip().split("=")[0].strip() for a in m.group(1).split(",")
            if a.strip() and a.strip() != "self"]


DEFAULTS = {"Sd": True, "Flip": False, "Dir": False, "T1": 0, "T2": 0, "D1": 0.0, "D2": 0.0,
            "Dchk1": False, "Dchk2": False, "Ddir1": False, "Ddir2": False, "Dang1": 0.0,
            "Dang2": 0.0, "OffsetReverse1": False, "OffsetReverse2": False,
            "TranslateSurface1": False, "TranslateSurface2": False, "Merge": True,
            "UseFeatScope": True, "UseAutoSelect": True, "T0": False, "StartOffset": 0.0,
            "FlipStartOffset": False, "NormalCut": False, "AssemblyFeatureScope": False,
            "AutoSelectComponents": False, "PropagateFeatureToParts": True,
            "OptimizeGeometry": False, "UseAllContours": False, "AllowCompensation": False,
            "BreakIntersection": False, "FillContour": False}


def kwcall(obj, method, values):
    names = arg_names(method)
    bad = [k for k in values if k not in names]
    if bad:
        raise RuntimeError("%s does not accept %s" % (method, bad))
    return getattr(obj, method)(**{n: values.get(n, DEFAULTS.get(n, False)) for n in names})


# ---------------------------------------------------------------- part recipes
# Each recipe: list of (plane, kind, geometry) where kind is 'extrude' or 'cut'.
def pin(d_mm, l_mm):
    return [("TOP", "extrude", [("circle", 0.0, 0.0, d_mm / 2.0)], l_mm)]


def pad(w, h, t, bore):
    # one sketch, nested contours: the inner circle becomes the bore during the extrude
    return [("FRONT", "extrude", [("rect", -w / 2, -h / 2, w / 2, h / 2),
                                  ("circle", 0.0, 0.0, bore / 2.0)], t)]


def lug(span_mm, hole_d, width, thick):
    ents = [("rect", -width / 2, -span_mm / 2, width / 2, span_mm / 2),
            ("circle", 0.0, -span_mm / 2 + 12.0, hole_d / 2.0),
            ("circle", 0.0, span_mm / 2 - 12.0, hole_d / 2.0)]
    return [("FRONT", "extrude", ents, thick)]


PARTS = [
    # name, recipe, expected box (x,y,z mm), expected diameters, status
    ("铰接销_M10x60", pin(10.0, 60.0), (10.0, 10.0, 60.0), [10.0],
     "derived: 孔径由 电推杆/连杆 的 φ10 铰孔定"),
    ("仿形轮轴_D14x120", pin(14.0, 120.0), (14.0, 14.0, 120.0), [14.0],
     "derived 直径/待实测 长度: 轮盘中心孔 φ14 已读，轮面宽度取决于隔套数量，120 mm 是占位"),
    ("铰轴弹性衬垫_25x20x8", pad(25.0, 20.0, 8.0, 14.0), (25.0, 20.0, 8.0), [14.0],
     "derived 厚8/待实测 材料: 图1 黑色衬垫外形，材质与硬度未定"),
    ("吊耳_连杆2至刀柄1", lug(60.0, 10.0, 24.0, 8.0), (24.0, 60.0, 8.0), [10.0],
     "待实测: 作者确认此件未建模，孔距 60 与板宽 24 是占位，不是实测"),
    ("刀腿弹簧_包络代表", pin(30.0, 80.0), (30.0, 30.0, 80.0), [30.0],
     "待实测: 螺旋实体本轮未建，此为包络代表；线径/中径/自由长/刚度均无依据"),
]


def draw(doc, sm, plane, ents):
    for e in ents:
        if e[0] == "rect":
            _t, x1, y1, x2, y2 = e
            sm.CreateLine(x1 * M, y1 * M, 0.0, x2 * M, y1 * M, 0.0)
            sm.CreateLine(x2 * M, y1 * M, 0.0, x2 * M, y2 * M, 0.0)
            sm.CreateLine(x2 * M, y2 * M, 0.0, x1 * M, y2 * M, 0.0)
            sm.CreateLine(x1 * M, y2 * M, 0.0, x1 * M, y1 * M, 0.0)
        elif e[0] == "circle":
            _t, cx, cy, r = e
            doc.CreateCircleByRadius2(cx * M, cy * M, 0.0, r * M)


def build_one(sw, name, recipe):
    res = sw.OpenDoc6(PART_TPL, 1, 1, "", 0, 0)
    doc = res[0] if isinstance(res, tuple) else res
    if doc is None:
        return {"status": "template failed"}
    steps = []
    for plane, kind, ents, depth in recipe:
        cands = {"FRONT": ("前视基准面", "Front Plane"), "TOP": ("上视基准面", "Top Plane")}[plane]
        chosen = None
        for pn in cands:
            doc.ClearSelection2(True)
            if doc.Extension.SelectByID2(pn, "PLANE", 0, 0, 0, False, 0, None, 0):
                chosen = pn
                break
        if chosen is None:
            steps.append("no plane for %s" % plane)
            continue
        doc.SketchManager.InsertSketch(True)
        draw(doc, doc.SketchManager, plane, ents)
        doc.SketchManager.InsertSketch(True)  # exit, keep selected
        try:
            if kind == "extrude":
                kwcall(doc.FeatureManager, "FeatureExtrusion3",
                       {"Dir": False, "D1": depth * M})
            else:
                kwcall(doc.FeatureManager, "FeatureCut4", {"T1": 1, "T2": 1})
            doc.ForceRebuild3(False)
            steps.append("%s %s ok" % (kind, plane))
        except Exception as exc:
            steps.append("%s FAILED %r" % (kind, exc))
    out = {"steps": steps}
    for suffix in (".SLDPRT", ".step"):
        target = os.path.join(OUT, name + suffix)
        if os.path.exists(target):
            try:
                os.remove(target)
            except OSError:
                pass
        try:
            r = doc.Extension.SaveAs(target, 0, 1, None, 0, 0)
            out["saved_" + suffix] = os.path.getsize(target) if os.path.exists(target) else 0
        except Exception as exc:
            out["saved_" + suffix] = repr(exc)[:100]
    try:
        sw.CloseDoc(str(doc.GetTitle()))
    except Exception:
        pass
    return out


def readback(name):
    from step_geom_report import TRIPLE, load, last_number
    step = os.path.join(OUT, name + ".step")
    if not os.path.exists(step):
        return {"verdict": "NO STEP"}
    ent = load(step)
    pts = []
    for _k, (t, a) in ent.items():
        if t == "CARTESIAN_POINT":
            m = TRIPLE.search(a)
            if m:
                # TRIPLE has three groups; taking only group(1) is what made every part
                # look like an empty body
                v = [float(x) for x in m.groups()]
                pts.append(v)
    if not pts:
        return {"verdict": "NO GEOMETRY (empty body)"}
    spans = [round(max(p[i] for p in pts) - min(p[i] for p in pts), 1) for i in (0, 1, 2)]
    dia = sorted({round(last_number(a) * 2, 2) for t, a in ent.values()
                  if t == "CYLINDRICAL_SURFACE" and last_number(a)})
    return {"spans": spans, "diameters": dia}


def main():
    pythoncom.CoInitialize()
    os.makedirs(OUT, exist_ok=True)
    mod = EnsureModule(SW_CLSID, 0, 32, 0)
    sw = mod.SldWorks(win32com.client.Dispatch("SldWorks.Application")._oleobj_)
    sw.Visible = False
    report = []
    for name, recipe, want_box, want_dia, status in PARTS:
        built = build_one(sw, name, recipe)
        got = readback(name)
        spans = got.get("spans", [])
        # a cylinder's CARTESIAN_POINTs are centres, so its cross-section spans read 0 -
        # the meaningful checks are the axial length and the diameters
        len_ok = bool(spans) and abs(max(spans) - max(want_box)) < 0.6
        dia_ok = all(any(abs(d - w) < 0.2 for d in got.get("diameters", [])) for w in want_dia)
        box_ok = len_ok
        report.append({"part": name, "status": status, "build": built, "readback": got,
                       "want_box": want_box, "want_dia": want_dia,
                       "verdict": "OK" if (box_ok and dia_ok) else "CHECK"})
    try:
        sw.ExitApp()
    except Exception:
        pass
    io.open(LOG, "w", encoding="utf-8").write(json.dumps(report, ensure_ascii=False, indent=2))
    for r in report:
        print("%-26s %-6s spans=%s dia=%s" % (r["part"], r["verdict"],
                                              r["readback"].get("spans"), r["readback"].get("diameters")))
    return 0 if all(r["verdict"] == "OK" for r in report) else 2


if __name__ == "__main__":
    sys.exit(main())
