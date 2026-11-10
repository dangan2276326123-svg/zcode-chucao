# -*- coding: utf-8 -*-
"""Complete spring-tine weeding tool, second attempt at the per-station offset.

What was wrong in attempt 1 (both COM and the GUI macro): CreatePlaneAtOffset3 creates the
offset plane but does NOT leave it selected, so InsertSketch went back to the Right plane and
all 11 tines stacked at x=0 (verified: every tine-region vertex at x in {0,8}).

Fix here: after creating the offset plane, select it BY POINT - SelectByID2 with an empty name,
type PLANE and a point (x,0,0) that lies on that plane and on no other. Fall back to selecting
by the returned feature's name. Also use NewDocument (not OpenDoc6 on the template) so the
sketches can never land in whatever document happens to be active in the author's session.

Layout: X across the row, Y forward, Z up.  One body carries everything: the 夹排 L section
(立板 12 thick x 50 tall + 顶板 40 deep x 12 thick, from 弹齿齿夹排设计 §二) drawn on the offset
Right plane at x=-250 and extruded 500 across the working width, then 11 tines at 48 pitch on
offset Right planes.  Each tine is a vertical mounting shank 160, a quarter C-bend R70x90
(radii 67/73), a horizontal working leg 126 and a 26 chisel point, section 6 x 8.
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


def sel_plane(doc, names):
    for pn in names:
        doc.ClearSelection2(True)
        if doc.Extension.SelectByID2(pn, "PLANE", 0, 0, 0, False, 0, None, 0):
            return True
    return False


def line(sm, a, b):
    sm.CreateLine(a[0] * M, a[1] * M, 0.0, b[0] * M, b[1] * M, 0.0)


def arc(sm, c, p, q, direction):
    """Bend arc as ISketch.CreateArc(XC,YC,Zc, X1,Y1,Z1, X2,Y2,Z2, Direction).

    Measured, not assumed (tools/sw_probe_profile.py, 9 combinations of profile x plane):
    the 3-point overload sm.Create3PointArc(start, mid, end) produces a sketch whose vertex
    graph reads CLOSED and whose segments all report the right endpoints, yet
    FeatureExtrusion2 returns None every time - on the Right plane, on offset +48 and on
    offset -240. The centre/radius overload extrudes on all three. So state the radius.
    """
    sm.CreateArc(c[0] * M, c[1] * M, 0.0, p[0] * M, p[1] * M, 0.0, q[0] * M, q[1] * M, 0.0,
                 direction)


def draw_profile(sm):
    """Closed side outline with TWO TRUE ARCS for the C-bend, in Right-plane sketch coords.

    Mapping measured from the exported STEP: on this build's Right plane a sketch point
    (sx, sy) lands at model Z = -sx and model Y = +sy.  So sx reads as DEPTH below the clamp
    face and sy as FORWARD reach - which is the whole point of this outline:

      sx 0..160, sy ~0     the mounting shank, VERTICAL, goes up into the 立板's socket
      quarter C-bend       centre (160,70), inner r67 / outer r73
      sy 70..196, sx ~230  the working leg, HORIZONTAL, sweeping forward under the surface
      (230,196)            the chisel point

    That is the shape `docs/弹齿齿夹排设计_20261016.md` §二 requires (铅垂盲孔 holds the shank,
    so the shank must be vertical) and the one tools/sw_build_tine.py documents ("straight
    mounting shank + 90 deg C-bend + working leg + chisel point").

    RETRACTED, kept because I shipped it once: v3 put a rot() in front of this and turned the
    tine 90 deg so the leg hung vertically and the point aimed straight down, on the argument
    "a tine that sweeps horizontally tills nothing".  That argument was mine - not the author's,
    not the design doc's - and it is wrong for this tool: the horizontal sweep IS the weeding
    action, the same duty the 鸭掌铲 it is compared against performs.  v3 is void.

    v2's other defect is real and stays fixed: its bend was a 14-segment polyline (visible
    facets) whose end point was also repeated as the next line's start, creating zero-length
    segments; the sketch solver resolves those differently per sketch, which is why all 11
    bends kinked differently.  True arcs remove both.  Direction +1 goes counter-clockwise from
    start to end, so the inner arc (-90 deg -> 0 deg) is +1 and the outer (0 deg -> -90 deg) is
    -1; each is exactly a quarter circle.
    """
    line(sm, (0, 3), (160, 3))
    arc(sm, (160, 70), (160, 3), (227, 70), 1)
    for a, b in zip([(227, 70), (227, 170), (230, 196), (233, 170)],
                    [(227, 170), (230, 196), (233, 170), (233, 70)]):
        line(sm, a, b)
    arc(sm, (160, 70), (233, 70), (160, -3), -1)
    line(sm, (160, -3), (0, -3))
    line(sm, (0, -3), (0, 3))


def clamp_profile():
    """The L from 夹排设计 §二, in the same (sx = -Z, sy = Y) sketch coords, one closed outline.

    立板 12 thick (Y -6..6) x 50 tall (Z 0..50) - the tine sockets are cut UP into it from its
    bottom face, 38 deep, which is why the tall member is the one holding the tines.
    顶板 40 deep (Y -6..34) x 12 thick (Z 50..62) - the face that meets the 刀梁 quick-change
    seat; the 4xM8 腰孔 + 2xφ8 销 go there (still not cut, 孔距待与刀梁面板对).
    """
    return [(0, -6), (0, 6), (-50, 6), (-50, 34), (-62, 34), (-62, -6)]


def extrude(doc, depth):
    return doc.FeatureManager.FeatureExtrusion2(True, False, False, 0, 0, depth * M, 0.0,
                                                False, False, False, False, 0.0, 0.0,
                                                False, False, False, False, True, True, True,
                                                0, 0, False)


def offset_right(doc, x):
    """Create the Right-plane offset at model x and leave IT selected; returns how it was
    selected, or None.  Two bugs live here and were both measured: CreatePlaneAtOffset3 does
    not leave the new plane selected, and a NEGATIVE offset returns None - hence abs() plus
    FlipDir=(x < 0)."""
    sel_plane(doc, ("Right Plane", "右视基准面"))
    rp = doc.CreatePlaneAtOffset3(abs(x) * M, x < 0, True)
    doc.ClearSelection2(True)
    if doc.Extension.SelectByID2("", "PLANE", x * M, 0, 0, False, 0, None, 0):
        return "point"
    if rp is not None and doc.Extension.SelectByID2(str(rp.Name), "PLANE", 0, 0, 0,
                                                    False, 0, None, 0):
        return "name"
    return None


def main():
    pythoncom.CoInitialize()
    mod = EnsureModule(SW_CLSID, 0, 32, 0)
    sw = mod.SldWorks(win32com.client.Dispatch("SldWorks.Application")._oleobj_)
    was_visible = bool(sw.Visible)  # this attaches to the author's running session
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

    # clamp body: the L section once, extruded across the whole 500 working width
    how = offset_right(doc, -250.0)
    sm.InsertSketch(True)
    cp = clamp_profile()
    for a, b in zip(cp, cp[1:] + cp[:1]):
        line(sm, a, b)
    sm.InsertSketch(True)
    steps.append(("clamp", "%s:%s" % (how, bool(extrude(doc, 500)))))

    for i in range(11):
        x = -240.0 + i * 48.0
        how = offset_right(doc, x)
        if how is None:
            steps.append(("tine%d" % i, "plane select failed"))
            continue
        sm.InsertSketch(True)
        draw_profile(sm)
        sm.InsertSketch(True)
        steps.append(("tine%d" % i, "%s:%s" % (how, bool(extrude(doc, 8)))))

    doc.ForceRebuild3(False)
    name = "弹齿除草刀_整组v4"
    p = os.path.join(OUT, name + ".SLDPRT")
    doc.Extension.SaveAs(p, 0, 1, None, 0, 0)
    doc.Extension.SaveAs(os.path.join(OUT, name + ".step"), 0, 1, None, 0, 0)
    log = {"part": name, "steps": steps, "saved": os.path.exists(p)}
    io.open(os.path.join(OUT, "tine_bar_v4_log.json"), "w", encoding="utf-8").write(
        json.dumps(log, ensure_ascii=False, indent=1))
    try:
        sw.CloseDoc(str(doc.GetTitle()))
    except Exception:
        pass
    sw.Visible = was_visible
    print(json.dumps(log, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
