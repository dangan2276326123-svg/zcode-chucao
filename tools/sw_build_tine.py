# -*- coding: utf-8 -*-
"""Build a reference spring tine (弹齿) so the author can SEE the shape he asked about, and
render it. Flat spring-steel form: side profile = straight shank + 90 deg C-bend + working leg
+ chisel point, extruded to the bar width. The round-rod form is the same centreline swept with
a phi8 circle - one Sweep click in the GUI; this headless route has no solid-sweep member, so
the reference is the flat-bar version (a legitimate spring-tine form in its own right).

All numbers here are DESIGN CHOICES, not measurements: shank 160, bend R70 x 90 deg, leg 100,
bar 6 thick x 8 wide, point 26 long. They are labelled as such in the log and in the reply.

Opened from the part template, saved only under cad_work/cad_out/缺件. Never touches his files.
Usage: python -B tools/sw_build_tine.py
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

SHANK = 160.0     # straight mounting shank
R = 70.0          # C-bend radius
LEG = 100.0       # working leg after the bend
T = 6.0           # bar thickness (side view)
W = 8.0           # bar width (extrusion)
POINT = 26.0      # chisel point length


def profile():
    """Closed side-view outline: offset the line-arc-line centreline by T/2 both sides."""
    h = T / 2.0
    cx, cy = R, -SHANK
    pts = [(h, 0.0), (h, -SHANK)]
    n = 14
    for i in range(1, n + 1):                      # inner arc r=R-h, 180->270 deg
        a = math.radians(180.0 + 90.0 * i / n)
        pts.append((cx + (R - h) * math.cos(a), cy + (R - h) * math.sin(a)))
    pts.append((R, -SHANK - R + h))
    pts.append((R + LEG, -SHANK - R + h))
    pts.append((R + LEG + POINT, -SHANK - R))       # chisel point
    pts.append((R + LEG, -SHANK - R - h))
    pts.append((R, -SHANK - R - h))
    for i in range(1, n + 1):                      # outer arc r=R+h, 270->180 deg
        a = math.radians(270.0 - 90.0 * i / n)
        pts.append((cx + (R + h) * math.cos(a), cy + (R + h) * math.sin(a)))
    pts.append((-h, -SHANK))
    pts.append((-h, 0.0))
    return pts


def main():
    pythoncom.CoInitialize()
    mod = EnsureModule(SW_CLSID, 0, 32, 0)
    sw = mod.SldWorks(win32com.client.Dispatch("SldWorks.Application")._oleobj_)
    sw.Visible = False
    res = sw.OpenDoc6(TPL, 1, 1, "", 0, 0)
    doc = res[0] if isinstance(res, tuple) else res
    if doc is None:
        print("template failed")
        return 1
    for pn in ("右视基准面", "Right Plane"):
        doc.ClearSelection2(True)
        if doc.Extension.SelectByID2(pn, "PLANE", 0, 0, 0, False, 0, None, 0):
            break
    sm = doc.SketchManager
    sm.InsertSketch(True)
    pts = [(-v, u) for u, v in profile()]  # RIGHT: sketch x->Z, y->Y; -v so the tine hangs down
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        sm.CreateLine(x1 * M, y1 * M, 0.0, x2 * M, y2 * M, 0.0)
    sm.InsertSketch(True)
    ok = doc.FeatureManager.FeatureExtrusion2(True, False, False, 0, 0, W * M, 0.0,
                                            False, False, False, False, 0.0, 0.0,
                                            False, False, False, False, True, True, True,
                                            0, 0, False)
    doc.ForceRebuild3(False)
    name = "弹齿_参照_扁钢6x8"
    p = os.path.join(OUT, name + ".SLDPRT")
    r = doc.Extension.SaveAs(p, 0, 1, None, 0, 0)
    st = os.path.join(OUT, name + ".step")
    doc.Extension.SaveAs(st, 0, 1, None, 0, 0)
    bb = doc.GetPartBox(False) if hasattr(doc, "GetPartBox") else None
    log = {"part": name, "extrude_ok": bool(ok), "saved": os.path.exists(p),
           "dims_design_not_measured": {"shank": SHANK, "bend_R": R, "bend_deg": 90,
                                        "leg": LEG, "thick": T, "width": W, "point": POINT},
           "profile_points": len(pts)}
    io.open(os.path.join(OUT, "tine_log.json"), "w", encoding="utf-8").write(
        json.dumps(log, ensure_ascii=False, indent=1))
    print(json.dumps(log, ensure_ascii=True))
    return 0 if log["saved"] else 1


if __name__ == "__main__":
    sys.exit(main())
