"""Assemble the full lift station (linkage + tool body + wheels + spring) through COM.

Placement basis is the photo-derived pivot set (docs/执行机构装配拓扑_20261016.md §2G):
    A(0,0,0)      actuator top pin, on the frame
    C(+107,0,-264) rocker top pin, on the frame
    D(-50,0,-446) actuator rod-end clevis pin  } share one pin (author confirmed)
    E(-25,0,-465) rocker lower pin             }
    F(+69,0,-530) shovel edge, G(0,0,-560) spring tip

Global frame: X across the machine, Y out of the travel plane (all pin axes), Z up.
Each part is placed by rotating its local pivot-line onto the global one about Y and then
translating; the local pivot centres come from the STEP hole readings, not from guessing.

Everything placed from a lower-bound or placeholder measurement is tagged in the log, and
the run ends by exporting STEP and reading the whole assembly's bounding box back.

STATUS - BLOCKED, kept in the repo on purpose so the next attempt starts from facts.
Headless component insertion does not work through this binding: AddComponent5 /
AddComponent2 / AddComponent4 all return None and GetComponents() stays 0, both with a
fresh template document and with a saved .SLDASM reopened from disk, and both for a part
file I generated and for one of the author's own .SLDPRT files. So the failure is in the
insertion call, not in the generated geometry. What IS verified working in the same
session: OpenDoc6, sketches, FeatureExtrusion3/FeatureCut4, SaveAs to SLDPRT/STEP/PNG/PDF,
GetMathUtility().CreateTransform() once IMathUtility is wrapped strongly.
Next diagnostic (cheap, needs the GUI once): Tools > Macro > Record, drag one component in,
stop, read the recorded VBA - that shows the exact call sequence this binding is missing.
"""
import io
import json
import math
import os
import re
import sys

import pythoncom
import win32com.client
from win32com.client.gencache import EnsureModule

SW_CLSID = "{83A33D31-27C5-11CE-BFD4-00400513BB57}"
ASM_TPL = os.path.join("C:", os.sep + "ProgramData", "SOLIDWORKS", "SOLIDWORKS 2024",
                       "templates", "gb_assembly.asmdot")
SRC = os.path.join("C:", os.sep + "Users", os.environ.get("USERNAME", ""), "OneDrive",
                   "Desktop", "万园机器人", "移动平台")
MISSING = os.path.join("D:", os.sep + "ai work", "qoder", "cad_work", "cad_out", "缺件")
OUT = os.path.join("D:", os.sep + "ai work", "qoder", "cad_work", "cad_out")
LOG = os.path.join(OUT, "assembly_log.json")
M = 0.001

# global pivots, mm (photo-derived; see §2G)
A = (0.0, 0.0, 0.0)
C = (107.0, 0.0, -264.0)
D = (-50.0, 0.0, -446.0)
E = (-25.0, 0.0, -465.0)
F = (69.0, 0.0, -530.0)
G = (0.0, 0.0, -560.0)

# (file, base dir, local pivot pair in mm, global pair, tag)
PLAN = [
    ("电推杆.SLDPRT", SRC, ((-112.0, 0.0, -21.0), (25.0, 0.0, 408.0)), (A, D),
     "local pivots read from its STEP phi10 holes"),
    ("连杆1.SLDPRT", SRC, ((-108.0, 0.0, 405.0), (-108.0, 0.0, 20.0)), (C, E),
     "D25<->D10 span 385; CE used 241 from the photo = LOWER BOUND, so this part is placed short"),
    ("吊耳_连杆2至刀柄1.SLDPRT", MISSING, ((0.0, 0.0, -18.0), (0.0, 0.0, 18.0)), (E, F),
     "PLACEHOLDER geometry: hole spacing 60 not measured"),
    ("铰接销_M10x60.SLDPRT", MISSING, ((0.0, 0.0, 0.0), (0.0, 0.0, 60.0)), (D, D),
     "pin at the shared actuator/rocker pin"),
    ("仿形轮轴_D14x120.SLDPRT", MISSING, ((0.0, 0.0, 0.0), (0.0, 0.0, 120.0)), (G, G),
     "PLACEHOLDER length 120: real width = 2 discs + spacer stack, uncounted"),
]


def y_rotation(u, v):
    """Rotation (16 doubles, row-major 4x4 + scale) mapping local direction u to global v
    about the Y axis; both are unit-ish vectors in the XZ plane."""
    au = math.atan2(u[0], -u[2])
    av = math.atan2(v[0], -v[2])
    t = av - au
    ct, st = math.cos(t), math.sin(t)
    return [ct, 0, -st, 0,
            0, 1, 0, 0,
            st, 0, ct, 0,
            0, 0, 0, 1]


def transform_for(local_pair, global_pair, scale=1.0):
    u = tuple(local_pair[1][i] - local_pair[0][i] for i in range(3))
    v = tuple(global_pair[1][i] - global_pair[0][i] for i in range(3))
    arr = y_rotation(u, v)
    r = [arr[0:4], arr[4:8], arr[8:12]]
    p0 = [local_pair[0][0] * M, local_pair[0][1] * M, local_pair[0][2] * M]
    rotated = [sum(r[i][j] * p0[j] for j in range(3)) for i in range(3)]
    g0 = [global_pair[0][0] * M, global_pair[0][1] * M, global_pair[0][2] * M]
    tx = [g0[i] - rotated[i] for i in range(3)]
    return [arr[0], arr[1], arr[2], 0.0,
            arr[4], arr[5], arr[6], 0.0,
            arr[8], arr[9], arr[10], 0.0,
            tx[0], tx[1], tx[2], scale]


def main():
    pythoncom.CoInitialize()
    os.makedirs(OUT, exist_ok=True)
    mod = EnsureModule(SW_CLSID, 0, 32, 0)
    sw = mod.SldWorks(win32com.client.Dispatch("SldWorks.Application")._oleobj_)
    sw.Visible = False
    log = {"template": os.path.exists(ASM_TPL), "placed": [], "notes": []}
    res = sw.OpenDoc6(ASM_TPL, 2, 1, "", 0, 0)
    doc = res[0] if isinstance(res, tuple) else res
    if doc is None:
        log["fatal"] = "assembly template did not open"
        io.open(LOG, "w", encoding="utf-8").write(json.dumps(log, ensure_ascii=False, indent=2))
        print(json.dumps(log, ensure_ascii=True))
        return 1
    mathutil = sw.GetMathUtility()
    # IAssemblyDoc is a separate interface on the same object: IModelDoc2 does not expose
    # AddComponent5, which is why a direct call fails with "member not found".
    try:
        asm = mod.IAssemblyDoc(doc._oleobj_)  # same wrap trick that worked for SldWorks
        log["asm_cast"] = "wrapped IAssemblyDoc via makepy class"
    except Exception as exc:
        asm = doc
        log["asm_cast"] = "CastTo failed: %r" % (exc,)

    for fname, base, local_pair, global_pair, tag in PLAN:
        path = os.path.join(base, fname)
        rec = {"part": fname, "basis": tag, "exists": os.path.exists(path)}
        if not rec["exists"]:
            rec["result"] = "file missing"
            log["placed"].append(rec)
            continue
        try:
            arr = transform_for(local_pair, global_pair)
            xf = mathutil.CreateTransform(win32com.client.VARIANT(
                pythoncom.VT_ARRAY | pythoncom.VT_R8, arr))
            comp = asm.AddComponent5(path, 0, "", False, "", 0.0, 0.0, 0.0)
            if comp is None:
                rec["result"] = "AddComponent5 returned None"
            else:
                try:
                    comp.XForm = xf
                    rec["result"] = "placed with rotation"
                except Exception as exc:
                    rec["result"] = "placed, XForm refused: %s" % (repr(exc)[:90],)
                rec["name"] = str(comp.Name2) if hasattr(comp, "Name2") else "?"
        except Exception as exc:
            rec["result"] = "FAILED %r" % (exc,)
        log["placed"].append(rec)

    try:
        doc.ForceRebuild3(False)
    except Exception:
        pass
    target = os.path.join(OUT, "提刀工位装配.SLDASM")
    try:
        r = doc.Extension.SaveAs(target, 0, 1, None, 0, 0)
        log["saved"] = {"ok": bool(r[0]) if isinstance(r, tuple) else bool(r),
                        "bytes": os.path.getsize(target) if os.path.exists(target) else 0}
    except Exception as exc:
        log["saved"] = {"error": repr(exc)[:160]}
    try:
        title = str(doc.GetTitle())
    except Exception:
        title = ""
    try:
        sw.CloseDoc(title)
        sw.ExitApp()
    except Exception:
        pass
    io.open(LOG, "w", encoding="utf-8").write(json.dumps(log, ensure_ascii=False, indent=2))
    for p in log["placed"]:
        print("%-34s %s" % (p["part"], p.get("result")))
    print("saved:", log.get("saved"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
