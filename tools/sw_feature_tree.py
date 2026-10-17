# -*- coding: utf-8 -*-
"""Classify each cylindrical feature of the author's parts as a BORE or a BOSS, from the
SolidWorks feature tree - the same tree he sees on his screen.

Why this exists: the hole maps were built from CYLINDRICAL_SURFACE records in STEP, which
cannot tell a bore from the hub around it. The author's own description of 连杆1 on screen -
five circular features, two of them concentric pairs that are cylinders rather than holes,
leaving one real (threaded) hole for 刀柄1 - is exactly the distinction STEP cylindrical
faces do not carry. The feature tree does: a Cut-* feature removes material (bore), a
Boss-* feature adds it (hub).

Sketch circle radii are length invariants, so they match back onto the STEP axis lines by
diameter without needing the sketch plane transform.

Parts are opened Silent + ReadOnly and never saved. Output: cad_work/feature_tree.json.

Usage:  python -B tools/sw_feature_tree.py            (all parts)
        SW_LIMIT=2 python -B tools/sw_feature_tree.py (smoke test)
"""
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
SW_DOC_PART = 1
SW_OPEN_SILENT = 1
SW_OPEN_READONLY = 2
SW_SKETCH_CIRCLE = 2                      # swSketchSegment_e.swSketchSegment_CIRCLE

SRC = [os.path.join("C:", os.sep + "Users", os.environ.get("USERNAME", ""), "OneDrive",
                    "Desktop", "万园机器人", "移动平台"),
       os.path.join("D:", os.sep + "ai work", "qoder", "cad_work", "cad_out", "缺件")]
OUT = os.path.join("D:", os.sep + "ai work", "qoder", "cad_work", "feature_tree.json")
ERRS = []          # COM member failures, reported instead of silently ending a walk

# GetTypeName2 returns SolidWorks' internal codes, not the display name the author sees: a
# boss-extrude is "Extrusion" and a cut-extrude is "ICE", so neither word shows up in the
# code. Both the code and the localised display name are checked - the display name carries
# 切除 (cut) vs 凸台 (boss), which is the distinction being asked for.
BORE_CODES = ("ice", "irev", "ihelix", "hole", "thread", "cut", "shell", "cosmeticthread")
MASS_CODES = ("extrusion", "revolution", "loft", "sweep", "boundary", "boss", "pad", "cylinder",
              "cone", "sphere", "rib", "thicken")
BORE_WORDS = (u"切除", u"孔", u"螺纹", "cut", "hole", "thread")
MASS_WORDS = (u"凸台", u"旋转", "boss", "pad")


def kind(type_name, display_name=""):
    t = (type_name or "").lower()
    n = (display_name or "").lower()
    if any(k in t for k in BORE_CODES) or any(w in n for w in BORE_WORDS):
        return "bore"
    if any(k in t for k in MASS_CODES) or any(w in n for w in MASS_WORDS):
        return "mass"
    return "other"


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
    sw = mod.SldWorks(raw._oleobj_)
    sw.Visible = False
    return sw, mod


def call(obj, name):
    """Read a SolidWorks member that the API exposes as either method or property.

    Typed wrappers turn IModelDoc2::FirstFeature into a bound method, while the same member
    reached through late binding comes back as its value - and pywin32's CDispatch is itself
    callable (it exists to support `Foo(Param=value)`), so testing `callable()` picks "call it"
    for both and the second one dies with 找不到成员. Only an actual method object gets called.
    """
    a = getattr(obj, name)
    return a() if isinstance(a, (types.MethodType, types.BuiltinFunctionType,
                                types.BuiltinMethodType)) else a


def nxt(feat):
    """Next feature in the tree.

    A failure here ends the walk, so it is recorded rather than swallowed: the first version
    of this tool returned "0 features" for every part because the enumeration got a valid
    handle from the strongly typed doc but its first GetNextFeature call failed, and the
    silent None made an unread tree look like a tree with nothing in it.
    """
    try:
        label = str(call(feat, "Name"))
    except Exception:
        label = "?"
    try:
        return call(feat, "GetNextFeature")
    except Exception as exc:
        ERRS.append("GetNextFeature after %s: %r" % (label, exc))
        return None


def feature_sketch(feat):
    """The profile sketch of an extrude/revolve, via IDisplacementFeature.ProfileFeature."""
    try:
        spec = call(feat, "GetSpecificFeature2")
        sk_feat = call(spec, "ProfileFeature") if spec is not None else None
        if sk_feat is not None:
            return sk_feat
    except Exception:
        pass
    return None


def sketch_circles(sk_feat, mod):
    """Circular segments of a sketch: segment type, length, and implied full-circle diameter.

    ISketchSegment here offers no GetCircle (the gen_py wrapper has no such member, GetCurve
    comes back as the math ICurve, and casting that to ISketchArc throws 发生意外), but
    GetLength works and a full circle's length is its circumference, so diameter = len / pi.
    Checked against 连杆1: 37.70/π = 12.0, 78.54/π = 25.0, 94.25/π = 30.0, 31.42/π = 10.0 -
    all four agree with the φ values measured independently from the STEP circular edges.

    swSketchSegment_e: 0 = line, 1 = arc or circle, 2 = ellipse, 3 = spline.
    """
    if sk_feat is None:
        return []
    try:
        sk = call(sk_feat, "GetSpecificFeature2")
        segs = list(call(sk, "GetSketchSegments")) if sk is not None else []
    except Exception as exc:
        ERRS.append("GetSketchSegments: %r" % (exc,))
        return []
    out = []
    for seg in segs:
        try:
            ts = mod.ISketchSegment(seg._oleobj_)
            t = int(call(ts, "GetType"))
            length = round(float(call(ts, "GetLength")) * 1000.0, 2)
        except Exception:
            continue
        rec = {"type": t, "len_mm": length}
        if t == 1:
            rec["dia_if_full_circle"] = round(length / math.pi, 2)
        out.append(rec)
    return out


def sketch_summary(circles):
    """What a profile sketch amounts to: one full circle of diameter D, or a non-circular shape.

    A single type-1 segment is a complete circle (the bore or the hub). Anything else - two
    arcs plus two lines - is a slot (腰形孔) or a polygon, and its diameter cannot be read off
    one segment, so it is reported as its segment list instead.
    """
    if len(circles) == 1 and circles[0]["type"] == 1:
        return "circle", circles[0]["dia_if_full_circle"]
    if circles and all(c["type"] == 0 for c in circles):
        return "polygon", None
    return "profile", None


def walk(doc, mod):
    """Tree order is sketch-then-feature, so the last sketch seen is the fallback profile."""
    feats, last_sketch = [], None
    try:
        f = call(doc, "FirstFeature")
    except Exception as exc:
        return [{"name": "_walk_failed", "type": repr(exc), "kind": "other"}]
    guard = 0
    while f is not None and guard < 2000:
        guard += 1
        try:
            tn = call(f, "GetTypeName2") or ""
            nm = call(f, "Name") or ""
        except Exception as exc:
            feats.append({"name": "_read_failed", "type": repr(exc), "kind": "other"})
            break
        low = tn.lower()
        rec = {"name": nm, "type": tn, "kind": kind(tn, nm)}
        if low in ("historyfold", "annotationview", "notes", "materialfolder"):
            f = nxt(f)
            continue
        if low in ("profilefeature", "3dprofilefeature", "sketchentity"):
            last_sketch = f
            rec["circles"] = sketch_circles(f, mod)
            feats.append(rec)
        elif rec["kind"] in ("bore", "mass"):
            sk = feature_sketch(f) or last_sketch
            try:
                rec["profile"] = call(sk, "Name") if sk is not None else None
            except Exception:
                rec["profile"] = None
            rec["circles"] = sketch_circles(sk, mod)
            rec["shape"], rec["dia_mm"] = sketch_summary(rec["circles"])
            try:
                rec["suppressed"] = bool(call(f, "IsSuppressed"))
            except Exception:
                rec["suppressed"] = None
            last_sketch = None
            feats.append(rec)
        f = nxt(f)
    return feats


def main():
    limit = int(os.environ.get("SW_LIMIT", "0"))
    only = sys.argv[1] if len(sys.argv) > 1 else None
    pythoncom.CoInitialize()
    paths = []
    for base in SRC:
        if os.path.isdir(base):
            for fn in sorted(os.listdir(base)):
                if fn.upper().endswith(".SLDPRT") and (not only or only in fn):
                    paths.append(os.path.join(base, fn))
    if limit:
        paths = paths[:limit]
    sw, mod = connect()
    result = {"sw_revision": None, "parts": [], "errors": []}
    try:
        result["sw_revision"] = str(call(sw, "RevisionNumber"))
    except Exception as exc:
        result["errors"].append("revision: %r" % (exc,))
    for path in paths:
        name = os.path.splitext(os.path.basename(path))[0]
        t0 = time.time()
        entry = {"part": name, "src": path}
        try:
            res = sw.OpenDoc6(path, SW_DOC_PART, SW_OPEN_SILENT | SW_OPEN_READONLY, "", 0, 0)
            doc, errs = (res[0], res[1]) if isinstance(res, tuple) else (res, -1)
            entry["open_err"] = int(errs) if isinstance(errs, int) else -1
            if doc is None:
                entry["status"] = "open_failed"
            else:
                # The strongly typed doc hands out a first-feature handle whose next-feature
                # call fails, which reads as an empty tree; the late-bound active doc walks
                # the same tree cleanly, so enumerate through that and keep the typed doc only
                # for close/title.
                ldoc = None
                try:
                    ldoc = win32com.client.Dispatch("SldWorks.Application").ActiveDoc
                except Exception as exc:
                    ERRS.append("ActiveDoc: %r" % (exc,))
                before = len(ERRS)
                entry["features"] = walk(ldoc if ldoc is not None else doc, mod)
                if ERRS[before:]:
                    entry["walk_errors"] = ERRS[before:]
                entry["nfeat"] = len(entry["features"])
                entry["status"] = "ok" if entry["features"] else "no_features"
                try:
                    sw.CloseDoc(str(call(doc, "GetTitle")))
                except Exception:
                    pass
        except Exception as exc:
            entry["status"] = "exception"
            entry["error"] = repr(exc)
        entry["seconds"] = round(time.time() - t0, 1)
        result["parts"].append(entry)
    # merge so a filtered re-run cannot wipe a fuller pass already on disk
    if os.path.exists(OUT):
        try:
            prev = json.load(io.open(OUT, encoding="utf-8"))
            mine = {e["part"]: e for e in prev.get("parts", [])}
            mine.update({e["part"]: e for e in result["parts"]})
            result["parts"] = [mine[k] for k in sorted(mine)]
        except Exception as exc:
            result["errors"].append("merge: %r" % (exc,))
    io.open(OUT, "w", encoding="utf-8").write(json.dumps(result, ensure_ascii=False, indent=1))
    ok = sum(1 for e in result["parts"] if e["status"] == "ok")
    print("[ok] this run=%d/%d, file now holds %d parts -> %s" % (
        sum(1 for e in result["parts"] if e["status"] == "ok"), len(paths), ok, OUT))
    for e in result["parts"]:
        if e["status"] != "ok":
            print("   FAIL", e["part"], e["status"], e.get("error", ""))
    return 0 if ok == len(result["parts"]) else 1


if __name__ == "__main__":
    sys.exit(main())
