"""Build 弹齿齿夹排 through SolidWorks COM and verify it by reading the geometry back.

Why verification is inside the tool: the previous pass logged "plate extruded / bores cut"
for every step, yet the exported STEP held 76 entities and zero points - an empty body.
Silent no-ops happen when the sketch is not the active selection at feature-creation time,
so this version
  * never clears the selection between exiting a sketch and creating its feature,
  * enters/exits sketches through ISketchManager.InsertSketch,
  * calls ForceRebuild3 after each feature and counts features/bodies,
  * re-parses the exported STEP at the end and exits non-zero unless the box is 250x50x12
    and the phi8 / phi7 bores are present.

Design numbers: docs/弹齿齿夹排设计_20261016.md (plate 250x50x12, 5x phi8 tine bores at
pitch 48 mm, 5x phi7 M8-tap-drill clamp bores at mid-height). Known deviation kept in the
log: tine bores are cut through-all here, not blind to 38 mm.
Writes only into cad_work/cad_out/. The user's own CAD files are never modified.
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
TEMPLATE = os.path.join("C:", os.sep + "ProgramData", "SOLIDWORKS", "SOLIDWORKS 2024",
                        "templates", "gb_part.prtdot")
WORK = os.path.join("D:", os.sep + "ai work", "qoder", "cad_work", "cad_out")
GEN = os.path.join(os.environ.get("TEMP", ""), "gen_py", "3.9",
                   "83A33D31-27C5-11CE-BFD4-00400513BB57x0x32x0.py")
TOOLS = os.path.join("D:", os.sep + "ai work", "qoder", "tools")

WIDTH, HEIGHT, THK = 0.250, 0.050, 0.012
PITCH, TINE_R, CLAMP_R, CLAMP_Z = 0.048, 0.004, 0.0035, 0.025
XS = [-2 * PITCH, -PITCH, 0.0, PITCH, 2 * PITCH]
FRONT = ("前视基准面", "Front Plane")
TOP = ("上视基准面", "Top Plane")
DEFAULTS = {"Sd": True, "Flip": False, "Dir": False, "T1": 0, "T2": 0, "D1": 0.0, "D2": 0.0,
            "Dchk1": False, "Dchk2": False, "Ddir1": False, "Ddir2": False, "Dang1": 0.0,
            "Dang2": 0.0, "OffsetReverse1": False, "OffsetReverse2": False,
            "TranslateSurface1": False, "TranslateSurface2": False, "Merge": True,
            "UseFeatScope": True, "UseAutoSelect": True, "T0": False, "StartOffset": 0.0,
            "FlipStartOffset": False, "NormalCut": False, "AssemblyFeatureScope": False,
            "AutoSelectComponents": False, "PropagateFeatureToParts": True,
            "OptimizeGeometry": False, "UseAllContours": False, "AllowCompensation": False,
            "BreakIntersection": False, "FillContour": False, "AutoSelect": True,
            "DepthTemplateFactor": 1.0, "UseDepthTemplate": False, "BaseFeature": None,
            "Pick": False}


def arg_names(method):
    """Read the parameter list out of the makepy source: on a 27-argument call, guessing
    positions silently builds the wrong feature instead of raising."""
    text = io.open(GEN, encoding="utf-8", errors="replace").read()
    m = re.search(r"def " + method + r"\((.*?)\)\s*:\s*$", text, re.S | re.M)
    if not m:
        raise RuntimeError("signature for %s not parsed" % method)
    return [a.strip().split("=")[0].strip() for a in m.group(1).split(",")
            if a.strip() and a.strip() != "self"]


def kwcall(obj, method, values):
    names = arg_names(method)
    bad = [k for k in values if k not in names]
    if bad:
        raise RuntimeError("%s does not accept %s" % (method, bad))
    kw = {n: values[n] if n in values else DEFAULTS.get(n, False) for n in names}
    return getattr(obj, method)(**kw), names


def unprop(obj, name):
    v = getattr(obj, name)
    return v() if callable(v) else v


def feature_names(doc):
    out = []
    try:
        feat = unprop(doc, "FirstFeature")
        guard = 0
        while feat is not None and guard < 120:
            guard += 1
            try:
                out.append((str(unprop(feat, "Name2")), str(unprop(feat, "GetTypeName2"))))
            except Exception:
                break
            try:
                feat = unprop(feat, "GetNextFeature")
            except Exception:
                break
    except Exception as exc:
        out.append(("<enumerate failed>", repr(exc)[:80]))
    return out


def main():
    pythoncom.CoInitialize()
    os.makedirs(WORK, exist_ok=True)
    log = {"template_exists": os.path.exists(TEMPLATE), "steps": [], "states": []}
    mod = EnsureModule(SW_CLSID, 0, 32, 0)
    sw = mod.SldWorks(win32com.client.Dispatch("SldWorks.Application")._oleobj_)
    sw.Visible = False
    res = sw.OpenDoc6(TEMPLATE, 1, 1, "", 0, 0)
    doc = res[0] if isinstance(res, tuple) else res
    if doc is None:
        log["fatal"] = "template did not open"
        print(json.dumps(log, ensure_ascii=True))
        return 1

    def enter(cands):
        for name in cands:
            doc.ClearSelection2(True)
            if doc.Extension.SelectByID2(name, "PLANE", 0, 0, 0, False, 0, None, 0):
                doc.SketchManager.InsertSketch(True)
                return name
        raise RuntimeError("none of %s selectable" % (list(cands),))

    def leave():
        # exit the sketch WITHOUT clearing the selection: clearing it is exactly what made
        # the previous build silently produce an empty body (no contour -> no feature)
        doc.SketchManager.InsertSketch(True)

    def state(tag):
        names = feature_names(doc)
        kinds = {}
        for nm, ty in names:
            kinds[ty] = kinds.get(ty, 0) + 1
        log["states"].append([tag, kinds])

    try:
        entered = enter(FRONT)
        sm = doc.SketchManager
        x1, y1, x2, y2 = -WIDTH / 2.0, -HEIGHT / 2.0, WIDTH / 2.0, HEIGHT / 2.0
        sm.CreateLine(x1, y1, 0.0, x2, y1, 0.0)
        sm.CreateLine(x2, y1, 0.0, x2, y2, 0.0)
        sm.CreateLine(x2, y2, 0.0, x1, y2, 0.0)
        sm.CreateLine(x1, y2, 0.0, x1, y1, 0.0)
        leave()
        _f, names = kwcall(doc.FeatureManager, "FeatureExtrusion3",
                           {"Dir": False, "D1": THK, "D2": 0.0})
        doc.ForceRebuild3(False)
        log["steps"].append("plate on %s, extrude %d args" % (entered, len(names)))
        state("after_plate")
    except Exception as exc:
        log["steps"].append("PLATE FAILED: %r" % (exc,))

    try:
        enter(TOP)
        for x in XS:
            doc.CreateCircleByRadius2(x, THK / 2.0, 0.0, TINE_R)
        leave()
        kwcall(doc.FeatureManager, "FeatureCut4", {"T1": 1, "T2": 1})
        doc.ForceRebuild3(False)
        log["steps"].append("tine bores cut")
        state("after_tines")
    except Exception as exc:
        log["steps"].append("TINE CUT FAILED: %r" % (exc,))

    try:
        enter(FRONT)
        for x in XS:
            doc.CreateCircleByRadius2(x, CLAMP_Z, 0.0, CLAMP_R)
        leave()
        kwcall(doc.FeatureManager, "FeatureCut4", {"Dir": True, "T1": 1, "T2": 1})
        doc.ForceRebuild3(False)
        log["steps"].append("clamp bores cut")
        state("after_clamps")
    except Exception as exc:
        log["steps"].append("CLAMP CUT FAILED: %r" % (exc,))

    for nm in ("弹齿齿夹排.SLDPRT", "弹齿齿夹排.step"):
        target = os.path.join(WORK, nm)
        if os.path.exists(target):
            try:
                os.remove(target)
            except OSError:
                pass
        try:
            r = doc.Extension.SaveAs(target, 0, 1, None, 0, 0)
            log.setdefault("saved", {})[nm] = {"ok": bool(r[0]) if isinstance(r, tuple) else bool(r),
                                               "bytes": os.path.getsize(target) if os.path.exists(target) else 0}
        except Exception as exc:
            log.setdefault("saved", {})[nm] = {"error": repr(exc)[:120]}
    try:
        sw.CloseDoc(str(doc.GetTitle()))
    except Exception:
        pass

    step = os.path.join(WORK, "弹齿齿夹排.step")
    if os.path.exists(step):
        sys.path.insert(0, TOOLS)
        from step_geom_report import TRIPLE, load, last_number
        ent = load(step)
        pts = []
        for _k, (t, a) in ent.items():
            if t == "CARTESIAN_POINT":
                m = TRIPLE.search(a)
                if m:
                    vals = [float(v) for v in m.group(1).split(",")]
                    if len(vals) >= 3:
                        pts.append(tuple(vals[:3]))
        cyls = sorted({round(last_number(a) * 2, 2) for t, a in ent.values()
                       if t == "CYLINDRICAL_SURFACE" and last_number(a)})
        spans = [round(max(p[i] for p in pts) - min(p[i] for p in pts), 1) for i in (0, 1, 2)] if pts else []
        log["readback"] = {"entities": len(ent), "points": len(pts), "spans_mm": spans,
                           "cylinder_diameters": cyls}
        ok_box = sorted(spans, reverse=True) == [250.0, 50.0, 12.0]
        ok_holes = (8.0 in cyls) and (7.0 in cyls)
        log["verdict"] = "OK" if (ok_box and ok_holes) else "FAIL box=%s holes=%s" % (ok_box, ok_holes)
    else:
        log["verdict"] = "NO STEP TO VERIFY"

    io.open(os.path.join(WORK, "build_log.json"), "w", encoding="utf-8").write(
        json.dumps(log, ensure_ascii=False, indent=2))
    print(json.dumps({"steps": log["steps"], "readback": log.get("readback"),
                      "saved": log.get("saved"), "verdict": log["verdict"]}, ensure_ascii=True))
    return 0 if log["verdict"] == "OK" else 2


if __name__ == "__main__":
    sys.exit(main())
