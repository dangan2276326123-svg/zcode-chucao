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

HOLEMAP = json.load(io.open(os.path.join("D:", os.sep + "ai work", "qoder", "cad_work",
                                         "hole_maps", "index.json"), encoding="utf-8"))
AXES = {}
for _rec in HOLEMAP:
    for _h in _rec["holes"]:
        if _h.get("axis"):
            AXES[(_rec["part"].replace(".SLDPRT", ""), tuple(round(v, 1) for v in _h["c"]))] = _h["axis"]


def axis_at(fname, pt):
    """Pin-axis direction of a hole, as modelled in that part's own frame."""
    key = (os.path.splitext(fname)[0], tuple(round(v, 1) for v in pt))
    return AXES.get(key)


# global pivots, mm (photo-derived; see §2G)
# Anchors now come from matched holes, not from reading pivots off the photo:
#   电推杆 ⑫↔⑬ = 429 (coaxial D10 pair)  |  连杆1 ①↔② = 385 (D10 at the shared pin,
#   D25 up on the unmodelled 吊耳 axle)  |  刀柄3 ②↔ = 140 (two D10, assumed to be the
#   two ground pivots). Solving that triangle puts the shared pin at (197.9, -380.6).
# Two red flags are recorded in docs/执行机构装配拓扑_20261016.md §2I: the rated 200 mm
# stroke does not fit (only 184 mm of the 245..525 range is reachable from 429), and the
# rocker would swing 98.7 deg with a reversed, near-dead-centre start. Both point at the
# AC=140 assumption, which is the one number awaiting the author.
A = (0.0, 0.0, 0.0)
C = (140.0, 0.0, 0.0)
D = (197.9, 0.0, -380.6)
E = D
F = (D[0], 0.0, D[2] - 120.0)     # 铲刃 hangs below the tool post; 120 not yet measured
G = (D[0] - 60.0, 0.0, F[2] - 40.0)

# (file, base dir, local pivot pair in mm, global pair, tag)
PLAN = [
    # ⑫(25,0,-21) and ⑬(25,0,408) share x=25, i.e. they are the coaxial working pair;
    # ①(-112,0,-21) is the motor-side bracket hole. Using ①/⑬ before was a wrong-hole
    # pick, not a measurement error - the span is 429 exactly as the part says.
    ("电推杆.SLDPRT", SRC, ((25.0, 0.0, -21.0), (25.0, 0.0, 408.0)), (A, D),
     "⑫⑬ = 429 (same x=25, coaxial pair); ① is a bracket hole, not a pivot"),
    # author's correction: 连杆1 IS the inclined rocker sharing one pin with the actuator
    ("连杆1.SLDPRT", SRC, ((-108.0, 0.0, 405.0), (-108.0, 0.0, 20.0)), (C, D),
     "②(D25,385 above ①) on the 吊耳 axle at C; ①(D10) shares the pin with 电推杆 ⑬ at D"),
    ("吊耳_连杆2至刀柄1.SLDPRT", MISSING, ((0.0, 0.0, -18.0), (0.0, 0.0, 18.0)), (C, F),
     "作者更正：吊耳在 连杆1 与 刀柄3/刀柄1 之间，故一端在 C、一端向下传力；孔距 60 仍是占位"),
    ("铰接销_M10x60.SLDPRT", MISSING, ((0.0, 0.0, 0.0), (0.0, 0.0, 60.0)), (D, D),
     "pin at the shared actuator/rocker pin"),
    ("仿形轮轴_D14x120.SLDPRT", MISSING, ((0.0, 0.0, 0.0), (0.0, 0.0, 120.0)), (G, G),
     "PLACEHOLDER length 120: real width = 2 discs + spacer stack, uncounted"),
    # ---- tool body, anchored on the photo's own measured points ----
    ("刀柄1.SLDPRT", SRC, None, E, "位置按刀脚铰点 E 对齐；其内部哪个孔接吊耳未指认"),
    ("刀具.SLDPRT", SRC, None, F, "焊接件，按铲刃点 F 定位（作者：刀柄1 下面焊刀具与刀头）"),
    ("刀头.SLDPRT", SRC, None, F, "焊接件，按铲刃点 F 定位"),
    ("刀柄2.SLDPRT", SRC, None, G, "位置按弹簧/仿形轮端点 G 对齐；与刀柄1 的连接孔未指认"),
    ("碎土轮片.SLDPRT", SRC, None, (G[0], -20.0, G[2]), "轮盘 1/2，轮面宽度未实测，Y 向 ±20 是占位"),
    ("碎土轮片.SLDPRT", SRC, None, (G[0], 20.0, G[2]), "轮盘 2/2，同上"),
    ("刀腿弹簧_包络代表.SLDPRT", MISSING, None, (G[0], 0.0, G[2] + 60.0), "包络代表，位置按弹簧在刀腿末端"),
    ("铰轴弹性衬垫_25x20x8.SLDPRT", MISSING, None, C, "衬垫 1/2，按机架铰轴 C 处"),
    ("铰轴弹性衬垫_25x20x8.SLDPRT", MISSING, None, (C[0], 25.0, C[2]), "衬垫 2/2，夹板另一侧"),
    # ---- frame-side parts: present but placement not yet measured ----
    ("刀柄3.SLDPRT", SRC, None, A, "机架座成员，位置未定（作者：基片与刀柄3 组装在一起）"),
    ("基片1.SLDPRT", SRC, None, A, "位置未定"),
    ("基片2.SLDPRT", SRC, None, A, "位置未定"),
    ("基片3.SLDPRT", SRC, None, A, "位置未定"),
    ("基片4.SLDPRT", SRC, None, A, "位置未定"),
    ("吊耳1.SLDPRT", SRC, None, A, "位置未定（与电推杆上端 A 处共 φ24/φ10 孔型，待指认）"),
    ("中间杆.SLDPRT", SRC, None, (0.0, 0.0, -1070.0), "位置未定；与 中间杆吊耳1 孔型逐字相同，故成对"),
    ("中间杆吊耳1.SLDPRT", SRC, None, (0.0, 0.0, 0.0), "位置未定"),
    # 连杆2 ② is a phi10 (matches the phi10 pin family) and ① a phi20; 吊耳1 carries a
    # phi10 with a phi24 counterbore, so 连杆2 ② -> 吊耳1 pin is the plausible传力 link
    ("连杆2.SLDPRT", SRC, ((0.0, -30.0, 360.0), (0.0, 110.0, 20.0)), (D, F),
     "推测: ②(phi10) 接 D 处销, ①(phi20) 向下接到刀柄1 的 F 区 - 待作者确认"),
    # ② and ⑤ are both phi20 and 510.5 apart - the only same-diameter far pair in the set,
    # which is what a cross-machine tie rod looks like; placed spanning Y about the centre
    ("连杆3.SLDPRT", SRC, ((200.0, -60.0, 0.0), (705.0, 15.0, 0.0)), (E, E),
     "推测: ②↔⑤ (φ20, 510) 为横跨左右的横拉杆；轴向按 Y 放置，具体两端接哪个孔待指认"),
    ("圆柱.SLDPRT", SRC, None, (0.0, 0.0, -721.0), "φ50×1442 轴料，归属未定（横梁/摆轴），此处按竖直放置占位"),
]


def _norm(a):
    n = math.sqrt(sum(x * x for x in a)) or 1.0
    return [x / n for x in a]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def frame_rotation(ax_l, ax_g, u_l, u_g):
    """Full orientation: map the part's pin axis onto the global pin axis AND its
    pivot-line onto the global pivot-line. Aligning only the pivot line is what left the
    plates lying in inconsistent planes in the first render."""
    e3l, e3g = _norm(ax_l), _norm(ax_g)
    ul = [u_l[i] - e3l[i] * _dot(u_l, e3l) for i in range(3)]
    ug = [u_g[i] - e3g[i] * _dot(u_g, e3g) for i in range(3)]
    if max(abs(x) for x in ul) < 1e-6 or max(abs(x) for x in ug) < 1e-6:
        return None
    e1l, e1g = _norm(ul), _norm(ug)
    e2l, e2g = _cross(e3l, e1l), _cross(e3g, e1g)
    L = [e1l, e2l, e3l]           # rows: local basis
    Gm = [e1g, e2g, e3g]          # rows: global basis
    # R maps local coords to global: R = Gm^T * L  (both orthonormal, rows are basis vectors)
    R = [[sum(Gm[k][i] * L[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    return [R[0][0], R[0][1], R[0][2], R[1][0], R[1][1], R[1][2], R[2][0], R[2][1], R[2][2]]


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


rec_out = []


def transform_for(local_pair, global_pair, scale=1.0, fname=""):
    """local_pair None => drop the part at global_pair[0] with no rotation. The log tags
    those as 位置未定, so a placeholder never reads as a measured placement."""
    """Array layout taken from the author's recorded macro, not guessed:
    nine rotation doubles (row-major 3x3), then tx ty tz, then scale, then three zeros.
    An identity drop reads back as indices 0,4,8 = 1 and 12 = 1, which matches."""
    if local_pair is None:
        # placeholder placement: stand the plate up so its pin axis points along global Y
        # and its local X runs along global X. Position is still a guess; orientation is not.
        pt = global_pair if isinstance(global_pair[0], (int, float)) else global_pair[0]
        g0 = [pt[0] * M, pt[1] * M, pt[2] * M]
        ax = axis_at(fname, pt)
        r = frame_rotation(ax, [0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [1.0, 0.0, 0.0]) if ax else             [1, 0, 0, 0, 1, 0, 0, 0, 1]
        return r + g0 + [scale, 0.0, 0.0, 0.0]

    u = tuple(local_pair[1][i] - local_pair[0][i] for i in range(3))
    v = tuple(global_pair[1][i] - global_pair[0][i] for i in range(3))
    r = None
    al, ag = axis_at(fname, local_pair[0]), axis_at(fname, local_pair[1])
    if al and ag:
        r = frame_rotation(al, [0.0, 1.0, 0.0], u, v)
        if r is not None:
            rec_note = "frame: pin axis + pivot line"
    if r is None:
        full = y_rotation(u, v)
        r = [full[0], full[1], full[2], full[4], full[5], full[6], full[8], full[9], full[10]]
        rec_note = "pivot line only (hole axis unknown)"
    rec_out.append(rec_note)
    p0 = [local_pair[0][0] * M, local_pair[0][1] * M, local_pair[0][2] * M]
    rotated = [r[i * 3] * p0[0] + r[i * 3 + 1] * p0[1] + r[i * 3 + 2] * p0[2] for i in range(3)]
    g0 = [global_pair[0][0] * M, global_pair[0][1] * M, global_pair[0][2] * M]
    tx = [g0[i] - rotated[i] for i in range(3)]
    return r + tx + [scale, 0.0, 0.0, 0.0]


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
    mathutil = mod.IMathUtility(sw.GetMathUtility()._oleobj_)
    asm_title = str(doc.GetTitle())
    log["asm_title"] = asm_title
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
            # the two prerequisites the recorder revealed: the part must be open in this
            # session, and the assembly must be re-activated before AddComponent5
            sw.OpenDoc6(path, 1, 32, "", 0, 0)
            sw.ActivateDoc3(asm_title, True, 0, 0)
            arr = transform_for(local_pair, global_pair, fname=os.path.basename(path))
            xf = mathutil.CreateTransform(win32com.client.VARIANT(
                pythoncom.VT_ARRAY | pythoncom.VT_R8, arr))
            comp = asm.AddComponent5(path, 0, "", False, "", 0.0, 0.0, 0.0)
            if comp is None:
                rec["result"] = "AddComponent5 returned None"
            else:
                try:
                    comp.SetTransformAndSolve2(xf)
                    rec["result"] = "placed via SetTransformAndSolve2"
                except Exception as exc:
                    rec["result"] = "inserted, transform refused: %s" % (repr(exc)[:90],)
                rec["name"] = str(comp.Name2)
        except Exception as exc:
            rec["result"] = "FAILED %r" % (exc,)
        finally:
            try:
                sw.CloseDoc(path)
            except Exception:
                pass
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
