# -*- coding: utf-8 -*-
"""Complete spring-tine weeding tool, second attempt at the per-station offset.

What was wrong in attempt 1 (both COM and the GUI macro): CreatePlaneAtOffset3 creates the
offset plane but does NOT leave it selected, so InsertSketch went back to the Right plane and
all 11 tines stacked at x=0 (verified: every tine-region vertex at x in {0,8}).

Fix here: after creating the offset plane, select it BY POINT - SelectByID2 with an empty name,
type PLANE and a point (x,0,0) that lies on that plane and on no other. Fall back to selecting
by the returned feature's name. Also use NewDocument (not OpenDoc6 on the template) so the
sketches can never land in whatever document happens to be active in the author's session.

Layout: X across the row, Y forward, Z up. Beam 500x40x12 on Front; flange 140x60x8 on Top;
11 tines at 48 pitch on offset Right planes, side profile in sketch coords (x=-v, y=u):
shank 160, C-bend R70x90 (radii 67/73), leg 100, point 26, section 6 thick x 8 wide.
Sockets NOT cut (reference). All dims design choices; 幅宽 500 对等 is the confirmed one (Hw-38).

Usage: python -B tools/sw_build_tine_bar.py
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
OUT = os.path.join("D:", os.sep + "ai work", "qoder", "cad_work", "cad_out", "缺件")
TPL = os.path.join("C:", os.sep + "ProgramData", "SOLIDWORKS", "SOLIDWORKS 2024",
                   "templates", "gb_part.prtdot")
PI = math.pi


def profile():
    h = 3.0
    pts = [(0.0, h), (160.0, h)]
    n = 14
    for i in range(1, n + 1):
        a = PI * (180 + 90 * i / n) / 180
        pts.append((160 - 67 * math.sin(a), 70 + 67 * math.cos(a)))
    pts += [(227, 70), (227, 170), (230, 196), (233, 170), (233, 70)]
    for i in range(1, n + 1):
        a = PI * (270 - 90 * i / n) / 180
        pts.append((160 - 73 * math.sin(a), 70 + 73 * math.cos(a)))
    pts += [(160, -h), (0, -h)]
    return pts


def sel_plane(doc, names):
    for pn in names:
        doc.ClearSelection2(True)
        if doc.Extension.SelectByID2(pn, "PLANE", 0, 0, 0, False, 0, None, 0):
            return True
    return False


def rect(sm, x1, y1, x2, y2):
    p = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
    for i in range(4):
        a, b = p[i], p[(i + 1) % 4]
        sm.CreateLine(a[0] * M, a[1] * M, 0.0, b[0] * M, b[1] * M, 0.0)


def poly(sm, pts):
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        sm.CreateLine(a[0] * M, a[1] * M, 0.0, b[0] * M, b[1] * M, 0.0)


def extrude(doc, depth):
    return doc.FeatureManager.FeatureExtrusion2(True, False, False, 0, 0, depth * M, 0.0,
                                                False, False, False, False, 0.0, 0.0,
                                                False, False, False, False, True, True, True,
                                                0, 0, False)


def main():
    pythoncom.CoInitialize()
    mod = EnsureModule(SW_CLSID, 0, 32, 0)
    sw = mod.SldWorks(win32com.client.Dispatch("SldWorks.Application")._oleobj_)
    sw.Visible = False
    doc = sw.NewDocument(TPL, 0, 0.0, 0.0)
    if doc is None:
        print("NewDocument failed")
        return 1
    # NewDocument hands back a late-bound dispatch; SelectByID2's Callout=None only marshals
    # correctly through the typed IModelDoc2 wrapper (late-bound raises 类型不匹配 at arg 8).
    doc = mod.IModelDoc2(doc._oleobj_)
    sm = doc.SketchManager
    steps = []

    sel_plane(doc, ("Front Plane", "前视基准面"))
    sm.InsertSketch(True)
    rect(sm, -250, -20, 250, 20)
    sm.InsertSketch(True)
    steps.append(("beam", bool(extrude(doc, 12))))

    sel_plane(doc, ("Top Plane", "上视基准面"))
    sm.InsertSketch(True)
    rect(sm, -70, 12, 70, 72)
    sm.InsertSketch(True)
    steps.append(("flange", bool(extrude(doc, 8))))

    pts = profile()
    for i in range(11):
        x = -240.0 + i * 48.0
        sel_plane(doc, ("Right Plane", "右视基准面"))
        rp = doc.CreatePlaneAtOffset3(abs(x) * M, x < 0, True)  # negative offset needs FlipDir
        # select the NEW plane by a point that lies on it and on no other plane
        doc.ClearSelection2(True)
        ok = doc.Extension.SelectByID2("", "PLANE", x * M, 0, 0, False, 0, None, 0)
        how = "point"
        if not ok and rp is not None:
            ok = doc.Extension.SelectByID2(str(rp.Name), "PLANE", 0, 0, 0, False, 0, None, 0)
            how = "name"
        if not ok:
            steps.append(("tine%d" % i, "plane select failed"))
            continue
        sm.InsertSketch(True)
        poly(sm, pts)
        sm.InsertSketch(True)
        steps.append(("tine%d" % i, "%s:%s" % (how, bool(extrude(doc, 8)))))

    doc.ForceRebuild3(False)
    name = "弹齿除草刀_整组v2"
    p = os.path.join(OUT, name + ".SLDPRT")
    doc.Extension.SaveAs(p, 0, 1, None, 0, 0)
    doc.Extension.SaveAs(os.path.join(OUT, name + ".step"), 0, 1, None, 0, 0)
    log = {"part": name, "steps": steps, "saved": os.path.exists(p)}
    io.open(os.path.join(OUT, "tine_bar_v2_log.json"), "w", encoding="utf-8").write(
        json.dumps(log, ensure_ascii=False, indent=1))
    try:
        sw.CloseDoc(str(doc.GetTitle()))
    except Exception:
        pass
    print(json.dumps(log, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
