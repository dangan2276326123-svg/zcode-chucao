# -*- coding: utf-8 -*-
"""Diagnose why v3's arc-based tine profile extrudes as None while v2's polyline did not.

Two axes are varied at once, because the builder differs from the probe in BOTH of them:
  * profile: polyline (v2) / 3-point arcs (v3) / centre-radius arcs
  * plane:   the Right plane itself / offset +48 / offset -240 (FlipDir)
For each combination: is the sketch closed, and does FeatureExtrusion2 hand back a feature?

Usage: python -B tools/sw_probe_profile.py
"""
import io
import json
import math
import os
import sys

import pythoncom
import win32com.client
from win32com.client.gencache import EnsureModule

SW_CLSID = "{83A33D31-27C5-11CE-BFD4-00400513BB57}"
M = 0.001
OUT = os.path.join("D:", os.sep + "ai work", "qoder", "cad_work", "probe_profile.json")
TPL = os.path.join("C:", os.sep + "ProgramData", "SOLIDWORKS", "SOLIDWORKS 2024",
                   "templates", "gb_part.prtdot")
TYPE = {0: "unknown", 1: "line", 2: "arc", 3: "ellipse", 4: "spline", 5: "cloud",
        6: "parametric", 7: "polyline", 8: "mirror_surface", 9: "offset_entities",
        10: "construction"}


def _call_or_get(obj, name):
    v = getattr(obj, name, None)
    if callable(v):
        try:
            v = v()
        except Exception:
            return None
    if isinstance(v, tuple):
        v = v[0] if v else None
    return v


def _call_raw(obj, name):
    v = getattr(obj, name, None)
    if callable(v):
        try:
            v = v()
        except Exception:
            return None
    return v


def _as_list(v):
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return list(v)
    return [v]


def _endpts(s):
    """Endpoints live on the typed entity (ISketchLine/ISketchArc.GetStartPoint2 etc)."""
    out = []
    for getter in ("GetStartPoint2", "GetEndPoint2"):
        p = _call_raw(s, getter)
        try:
            out.append(None if p is None else (round(p.X / M, 6), round(p.Y / M, 6)))
        except Exception:
            out.append(None)
    return out


def sketch_state(doc):
    sk = _call_or_get(doc, "GetActiveSketch2")
    if sk is None:
        return {"err": "no active sketch"}
    segs = _as_list(_call_raw(sk, "GetSketchSegments"))
    deg, rows = {}, []
    for s in segs:
        t = _call_or_get(s, "SegmentType")
        try:
            t = int(t)
        except Exception:
            t = -1
        a, b = _endpts(s)
        row = {"type": TYPE.get(t, t), "start": a, "end": b}
        for v in (a, b):
            if v is not None:
                deg[v] = deg.get(v, 0) + 1
        rows.append(row)
    loose = {str(k): v for k, v in deg.items() if v != 2}
    return {"n_seg": len(rows), "closed": not loose, "loose_vertices": loose,
            "segs": rows}


def line(sm, a, b):
    sm.CreateLine(a[0] * M, a[1] * M, 0.0, b[0] * M, b[1] * M, 0.0)


def draw_poly(sm):
    h, n = 3.0, 14
    pts = [(0.0, h), (160.0, h)]
    for i in range(1, n + 1):
        a = math.pi * (180 + 90 * i / n) / 180
        pts.append((160 - 67 * math.sin(a), 70 + 67 * math.cos(a)))
    pts += [(227, 70), (227, 170), (230, 196), (233, 170), (233, 70)]
    for i in range(1, n + 1):
        a = math.pi * (270 - 90 * i / n) / 180
        pts.append((160 - 73 * math.sin(a), 70 + 73 * math.cos(a)))
    pts += [(160, -h), (0, -h), (0.0, h)]
    for a, b in zip(pts, pts[1:]):
        line(sm, a, b)


def draw_arc3(sm):
    ri, ro = 67.0, 73.0
    k = math.sqrt(2.0) / 2.0
    line(sm, (0, 3), (160, 3))
    sm.Create3PointArc(160 * M, 3 * M, 0.0, (160 + ri * k) * M, (70 - ri * k) * M, 0.0,
                       227 * M, 70 * M, 0.0)
    for a, b in zip([(227, 70), (227, 170), (230, 196), (233, 170)],
                    [(227, 170), (230, 196), (233, 170), (233, 70)]):
        line(sm, a, b)
    sm.Create3PointArc(233 * M, 70 * M, 0.0, (160 + ro * k) * M, (70 - ro * k) * M, 0.0,
                       160 * M, -3 * M, 0.0)
    line(sm, (160, -3), (0, -3))
    line(sm, (0, -3), (0, 3))


def draw_arc_c(sm):
    ri, ro = 67.0, 73.0
    line(sm, (0, 3), (160, 3))
    sm.CreateArc(160 * M, 70 * M, 0.0, 160 * M, 3 * M, 0.0, 227 * M, 70 * M, 0.0, 1)
    for a, b in zip([(227, 70), (227, 170), (230, 196), (233, 170)],
                    [(227, 170), (230, 196), (233, 170), (233, 70)]):
        line(sm, a, b)
    sm.CreateArc(160 * M, 70 * M, 0.0, 233 * M, 70 * M, 0.0, 160 * M, -3 * M, 0.0, -1)
    line(sm, (160, -3), (0, -3))
    line(sm, (0, -3), (0, 3))


def extrude(doc, depth):
    return doc.FeatureManager.FeatureExtrusion2(True, False, False, 0, 0, depth * M, 0.0,
                                                False, False, False, False, 0.0, 0.0,
                                                False, False, False, False, True, True, True,
                                                0, 0, False)


def on_plane(doc, mode):
    """mode: right | pos(+48) | neg(-240 via FlipDir) - exactly what the builder does."""
    doc.ClearSelection2(True)
    for pn in ("Right Plane", "右视基准面"):
        if doc.Extension.SelectByID2(pn, "PLANE", 0, 0, 0, False, 0, None, 0):
            break
    if mode == "right":
        return "right"
    x = 48.0 if mode == "pos" else -240.0
    rp = doc.CreatePlaneAtOffset3(abs(x) * M, x < 0, True)
    doc.ClearSelection2(True)
    if doc.Extension.SelectByID2("", "PLANE", x * M, 0, 0, False, 0, None, 0):
        return "point"
    if rp is not None and doc.Extension.SelectByID2(str(rp.Name), "PLANE", 0, 0, 0,
                                                    False, 0, None, 0):
        return "name"
    return "SELECT_FAILED"


def main():
    pythoncom.CoInitialize()
    mod = EnsureModule(SW_CLSID, 0, 32, 0)
    sw = mod.SldWorks(win32com.client.Dispatch("SldWorks.Application")._oleobj_)
    was_visible = bool(sw.Visible)
    sw.Visible = False
    doc = mod.IModelDoc2(sw.NewDocument(TPL, 0, 0.0, 0.0)._oleobj_)
    sm = doc.SketchManager
    res = []
    for pname in ("right", "pos", "neg"):
        for label, draw in (("polyline", draw_poly), ("arc3", draw_arc3), ("arcC", draw_arc_c)):
            how = on_plane(doc, pname)
            sm.InsertSketch(True)
            draw(sm)
            st = sketch_state(doc)
            sm.InsertSketch(True)
            f = extrude(doc, 8)
            st.update({"profile": label, "plane": pname, "select": how,
                       "extrude": "None" if f is None else "feature"})
            st.pop("segs", None)
            res.append(st)
    io.open(OUT, "w", encoding="utf-8").write(
        json.dumps({"rows": res, "n_bodies": _call_or_get(doc, "GetBodyCount")},
                   ensure_ascii=False, indent=1))
    sw.CloseDoc(str(doc.GetTitle()))
    sw.Visible = was_visible
    print(json.dumps([{"p": r["profile"], "pl": r["plane"], "sel": r["select"],
                       "closed": r["closed"], "x": r["extrude"]} for r in res], indent=0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
