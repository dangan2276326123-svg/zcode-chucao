# -*- coding: utf-8 -*-
"""Read the author's own hand-built assemblies and derive the joint list from their geometry.

Why not just read the mates: I tried, and the API will not give them up. The mate FEATURES are
readable (12 in 刀架.SLDASM, with type and name - MateCoincident / MateConcentric), but every
path to the two referenced entities is broken in this build: IMate.GetMateEntities is write-only
(无法读只写属性), IMate2.GetMateEntityCount resolves to the mate's NAME instead of a count, and
IMate2.MateEntity(k) returns None without raising. So the answer comes from geometry instead.

What is read: each component's 4x4 transform (IMathTransform.ArrayData = 9 rotation values +
3 translation + scale, metres) and each part's bore/boss AXES as measured from its circular
edges (cad_work/hole_maps2). A component's axes are carried into assembly space by that matrix;
two axes belonging to different components that come out coincident (parallel and within TOL mm)
are a joint. That is his assembly's own truth, not my guess about it.

Opened Silent + ReadOnly; nothing is saved or moved. Output: cad_work/asm_read/<name>.json.

Usage: python -B tools/sw_read_assembly.py [file-or-folder]
"""
import glob
import io
import json
import math
import os
import sys
import time
import types

import pythoncom
import win32com.client
from win32com.client.gencache import EnsureModule

SW_CLSID = "{83A33D31-27C5-11CE-BFD4-00400513BB57}"
SW_DOC_ASSEMBLY = 2
SW_OPEN_SILENT = 1
SW_OPEN_READONLY = 2
SRC = os.path.join("C:", os.sep + "Users", os.environ.get("USERNAME", ""), "OneDrive",
                   "Desktop", "移动平台")
OUT = os.path.join("D:", os.sep + "ai work", "qoder", "cad_work", "asm_read")
MAPS = os.path.join("D:", os.sep + "ai work", "qoder", "cad_work", "hole_maps2", "index.json")
TOL = 0.6          # mm: how close two axes must be to count as one pin axis
ERRS = []


def connect():
    mod = None
    for mj, mn in ((32, 0), (31, 0), (30, 0), (29, 0)):
        try:
            mod = EnsureModule(SW_CLSID, 0, mj, mn)
            break
        except Exception:
            continue
    if mod is None:
        raise RuntimeError("SolidWorks makepy wrapper unavailable")
    raw = win32com.client.Dispatch("SldWorks.Application")
    # OpenDoc6 needs the strong-typed SldWorks (late-bound rejects the two ByRef out-params
    # with 类型不匹配 at arg 5); ActiveDoc must then come back late-bound, because only that
    # handle's feature/component enumeration chain works. Same split as sw_feature_tree.py.
    sw = mod.SldWorks(raw._oleobj_)
    sw.Visible = False
    return sw, raw, mod


def call(obj, name):
    """Member arrives as a bound method from typed wrappers, as its value from late binding.
    pywin32's CDispatch is itself callable, so only a real method object may be called."""
    a = getattr(obj, name)
    return a() if isinstance(a, (types.MethodType, types.BuiltinFunctionType,
                                types.BuiltinMethodType)) else a


def load_axes():
    idx = json.load(io.open(MAPS, encoding="utf-8"))
    return {r["part"]: r["features"] for r in idx}


def mat_of(tf):
    data = [float(x) for x in list(call(tf, "ArrayData"))]
    return [data[0:3], data[3:6], data[6:9]], [data[9] * 1000.0, data[10] * 1000.0, data[11] * 1000.0]


def apply(r, t, p):
    return [sum(r[i][k] * p[k] for k in range(3)) + t[i] for i in range(3)]


def line_dist(p1, a1, p2, a2):
    cx = [a1[1] * a2[2] - a1[2] * a2[1], a1[2] * a2[0] - a1[0] * a2[2], a1[0] * a2[1] - a1[1] * a2[0]]
    n = math.sqrt(sum(x * x for x in cx))
    d = [p2[k] - p1[k] for k in range(3)]
    if n < 1e-6:
        px = [d[1] * a1[2] - d[2] * a1[1], d[2] * a1[0] - d[0] * a1[2], d[0] * a1[1] - d[1] * a1[0]]
        return math.sqrt(sum(x * x for x in px)), "parallel"
    return abs(sum(d[k] * cx[k] for k in range(3))) / n, "skew"


def components(asm):
    top = None
    for attempt in (lambda: asm.GetComponents(True), lambda: call(asm, "GetComponents")):
        try:
            top = list(attempt())
            break
        except Exception:
            continue
    if top is None:
        ERRS.append("GetComponents(True) failed")
        return []
    out = []

    def walk(cs, depth, parent):
        for c in cs:
            rec = {"depth": depth, "parent": parent}
            try:
                rec["name"] = str(call(c, "Name"))
                rec["file"] = os.path.basename(str(call(c, "GetPathName")))
                rec["suppressed"] = bool(call(c, "IsSuppressed"))
            except Exception as exc:
                rec["_err"] = repr(exc)[:100]
            try:
                r, t = mat_of(call(c, "Transform"))
                rec["rot"] = [[round(v, 4) for v in row] for row in r]
                rec["xyz_mm"] = [round(v, 2) for v in t]
            except Exception as exc:
                rec["_tf_err"] = repr(exc)[:100]
            out.append(rec)
            try:
                kids = list(call(c, "GetChildren"))
            except Exception:
                kids = []
            if kids:
                walk(kids, depth + 1, rec.get("name"))
    walk(top, 0, None)
    return out


def mate_features(doc, mod):
    """Names and types only - the referenced entities are unreadable (see module header)."""
    out = []
    try:
        f = call(doc, "FirstFeature")
    except Exception as exc:
        ERRS.append("FirstFeature: %r" % (exc,))
        return out
    grp, guard = None, 0
    while f is not None and guard < 300:
        guard += 1
        try:
            if str(call(f, "GetTypeName2")) == "MateGroup":
                grp = mod.IFeature(f._oleobj_)
                break
        except Exception:
            pass
        try:
            f = call(f, "GetNextFeature")
        except Exception:
            break
    if grp is None:
        return [{"_note": "没有 MateGroup：该装配可能完全浮动（无配合，只靠拖放位置）"}]
    try:
        sub = grp.GetFirstSubFeature()
    except Exception as exc:
        ERRS.append("GetFirstSubFeature: %r" % (exc,))
        return []
    n = 0
    while sub is not None and n < 500:
        n += 1
        try:
            out.append({"type": str(call(sub, "GetTypeName2")), "name": str(call(sub, "Name"))})
        except Exception as exc:
            out.append({"_err": repr(exc)[:80]})
            break
        try:
            sub = mod.IFeature(sub._oleobj_).GetNextSubFeature()
        except Exception:
            sub = None
    return out


def carry_axes(comps, axes):
    carried = []
    for c in comps:
        if c.get("suppressed") or "rot" not in c:
            continue
        stem = os.path.splitext(c.get("file", ""))[0]
        inst = c["name"]
        feats = axes.get(stem)
        if not feats:
            carried.append({"comp": inst, "part": stem,
                            "_note": "无 v2 孔位图（新零件，需先重导 STEP 再跑 sw_hole_maps2）"})
            continue
        rows = []
        for h in feats:
            p = apply(c["rot"], c["xyz_mm"], h["c"])
            a = [sum(c["rot"][i][k] * h["a"][k] for k in range(3)) for i in range(3)]
            n = math.sqrt(sum(x * x for x in a)) or 1.0
            rows.append({"tag": h.get("tag"), "d": h["d"], "kind": h["kind"],
                         "p": [round(v, 2) for v in p], "a": [round(v / n, 3) for v in a]})
        carried.append({"comp": inst, "part": stem, "xyz": c["xyz_mm"], "axes": rows})
    return carried


def find_joints(carried):
    flat = [(c["comp"], ax) for c in carried if c.get("axes") for ax in c["axes"]]
    joints = []
    for i in range(len(flat)):
        for j in range(i + 1, len(flat)):
            (c1, a1), (c2, a2) = flat[i], flat[j]
            if c1 == c2:
                continue
            d, how = line_dist(a1["p"], a1["a"], a2["p"], a2["a"])
            if d <= TOL and how == "parallel":
                joints.append({"comp1": c1, "tag1": a1["tag"], "kind1": a1["kind"], "dia1": a1["d"],
                               "comp2": c2, "tag2": a2["tag"], "kind2": a2["kind"], "dia2": a2["d"],
                               "dist_mm": round(d, 3), "at": a1["p"], "axis": a1["a"]})
    joints.sort(key=lambda r: (r["dia1"], r["comp1"]))
    return joints


def read_one(sw, raw, mod, path, axes):
    res = sw.OpenDoc6(path, SW_DOC_ASSEMBLY, SW_OPEN_SILENT | SW_OPEN_READONLY, "", 0, 0)
    doc, errs = (res[0], res[1]) if isinstance(res, tuple) else (res, -1)
    if doc is None:
        return {"assembly": os.path.basename(path), "status": "open_failed",
                "open_err": int(errs) if isinstance(errs, int) else -1}
    try:
        target = raw.ActiveDoc
    except Exception:
        target = doc
    asm = None
    try:
        asm = mod.IAssemblyDoc(target._oleobj_)
    except Exception as exc:
        ERRS.append("IAssemblyDoc: %r" % (exc,))
    comps = components(asm) if asm is not None else []
    data = {"assembly": os.path.basename(path),
            "open_err": int(errs) if isinstance(errs, int) else -1,
            "components": comps,
            "mates": mate_features(target, mod) if asm is not None else []}
    data["axes_in_assembly"] = carry_axes(comps, axes)
    data["joints"] = find_joints(data["axes_in_assembly"])
    try:
        sw.CloseDoc(str(call(doc, "GetTitle")))
    except Exception:
        pass
    return data


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else SRC
    paths = sorted(glob.glob(os.path.join(arg, "*.SLDASM"))) if os.path.isdir(arg) else [arg]
    os.makedirs(OUT, exist_ok=True)
    pythoncom.CoInitialize()
    sw, raw, mod = connect()
    axes = load_axes()
    for path in paths:
        t0 = time.time()
        try:
            data = read_one(sw, raw, mod, path, axes)
        except Exception as exc:
            data = {"assembly": os.path.basename(path), "error": repr(exc)}
        stem = os.path.splitext(os.path.basename(path))[0]
        io.open(os.path.join(OUT, stem + ".json"), "w", encoding="utf-8").write(
            json.dumps(data, ensure_ascii=False, indent=1))
        print("[ok] %-14s comps=%-3d mates=%-3d joints=%-3d %.1fs" % (
            stem, len(data.get("components", [])), len(data.get("mates", [])),
            len(data.get("joints", [])), time.time() - t0))
    if ERRS:
        io.open(os.path.join(OUT, "_errs.txt"), "w", encoding="utf-8").write("\n".join(ERRS))
        print("   COM failures: %d -> _errs.txt" % len(ERRS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
