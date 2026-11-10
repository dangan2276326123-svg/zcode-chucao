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
11 tines at 48 pitch on offset Right planes, the side outline turned by rot() so the shank
runs rearward and the leg hangs down: shank 160, C-bend R70x90 (radii 67/73), leg 126,
point 26, section 6 thick x 8 wide.
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


def rect(sm, x1, y1, x2, y2):
    p = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
    for i in range(4):
        a, b = p[i], p[(i + 1) % 4]
        sm.CreateLine(a[0] * M, a[1] * M, 0.0, b[0] * M, b[1] * M, 0.0)


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


def rot(p):
    """Profile coords (u = the outline's own x, v = its y) -> Right-plane sketch coords.

    Measured from the exported STEP, not assumed: on the Right plane of this build,
    sketch x -> model -Z and sketch y -> model +Y (the untransformed v2/v3 outline came out
    with the tine point aimed HORIZONTALLY along +Y, which tills nothing).  (u, v) -> (v, -u)
    is a proper rotation (det +1), so the arc direction flags below keep their meaning and the
    shank ends up running rearward along -Y while the leg hangs down along -Z.
    """
    return (p[1], -p[0])


def draw_profile(sm):
    """Closed side outline with TWO TRUE ARCS for the C-bend.

    v2 used a 14-segment polyline for the bend (visible facets) AND repeated each arc's end
    point as the next line's start, creating zero-length segments; SolidWorks' sketch solver
    resolves those degenerate segments differently per sketch, which is why every tine's bend
    showed a different kink. True arcs remove both problems: smooth bend, no duplicate points.
    Profile coords before rot(): shank 0..160 along u, bend centre (160,70) with inner r67 and
    outer r73, leg u 70..196 at v 227..233, point tip at (230,196). Direction +1 goes
    counter-clockwise from start to end, so inner (-90 deg -> 0 deg) is +1 and outer
    (0 deg -> -90 deg) is -1; each arc is exactly a quarter circle.
    """
    P = lambda u, v: rot((u, v))
    line(sm, P(0, 3), P(160, 3))
    arc(sm, P(160, 70), P(160, 3), P(227, 70), 1)
    for a, b in zip([(227, 70), (227, 170), (230, 196), (233, 170)],
                    [(227, 170), (230, 196), (233, 170), (233, 70)]):
        line(sm, P(*a), P(*b))
    arc(sm, P(160, 70), P(233, 70), P(160, -3), -1)
    line(sm, P(160, -3), P(0, -3))
    line(sm, P(0, -3), P(0, 3))


def extrude(doc, depth):
    return doc.FeatureManager.FeatureExtrusion2(True, False, False, 0, 0, depth * M, 0.0,
                                                False, False, False, False, 0.0, 0.0,
                                                False, False, False, False, True, True, True,
                                                0, 0, False)


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
        draw_profile(sm)
        sm.InsertSketch(True)
        steps.append(("tine%d" % i, "%s:%s" % (how, bool(extrude(doc, 8)))))

    doc.ForceRebuild3(False)
    name = "弹齿除草刀_整组v3"
    p = os.path.join(OUT, name + ".SLDPRT")
    doc.Extension.SaveAs(p, 0, 1, None, 0, 0)
    doc.Extension.SaveAs(os.path.join(OUT, name + ".step"), 0, 1, None, 0, 0)
    log = {"part": name, "steps": steps, "saved": os.path.exists(p)}
    io.open(os.path.join(OUT, "tine_bar_v3_log.json"), "w", encoding="utf-8").write(
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
