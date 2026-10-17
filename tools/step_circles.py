# -*- coding: utf-8 -*-
"""Parse circular EDGE geometry out of a SolidWorks STEP (AP203) file.

Two facts drive this module, and both bit me once:

* A CYLINDRICAL_SURFACE's placement point can sit anywhere along its axis, so distances
  measured along the axis between two such placements mean nothing. Every hinge distance
  that came from cylinder placements is therefore untrustworthy (that is how 连杆1's "385"
  and 刀柄3's "140" were produced).
* A CIRCLE entity's placement point IS the exact centre of that circular edge, and its
  AXIS2_PLACEMENT_3D carries the true edge normal. Circle centres are what real geometry
  can be measured from.

Parsing notes: SolidWorks wraps records over several lines, so the DATA section is split on
';' rather than on newlines, and CIRCLE's second argument is an AXIS2_PLACEMENT_3D (not a
CARTESIAN_POINT) - resolving that indirection is the whole point of ``circle_features``.
"""
import io
import math
import re

_DATA = re.compile(r"DATA;(.*?)ENDSEC;", re.S)
_REC = re.compile(r"#(\d+)\s*=\s*([A-Z_0-9]+)\s*\((.*?)\)\s*$", re.S)


def records(path):
    """Return {number: (type, [args...])} for every entity in the DATA section."""
    text = io.open(path, encoding="utf-8", errors="replace").read()
    body = _DATA.search(text)
    if not body:
        return {}
    out = {}
    for chunk in body.group(1).split(";"):
        m = re.match(r"\s*#(\d+)\s*=\s*([A-Z_0-9]+)\s*\((.*)\)\s*$", chunk, re.S)
        if not m:
            continue
        out[int(m.group(1))] = (m.group(2), _split_args(m.group(3)))
    return out


def _split_args(s):
    """Split a parameter list on top-level commas only (nested parens are kept together)."""
    args, depth, cur = [], 0, []
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            args.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if "".join(cur).strip():
        args.append("".join(cur).strip())
    return args


def _triple(s):
    """'( a, b, c )' -> tuple of floats; returns None if it is not a numeric triple."""
    m = re.match(r"^\s*\((.*)\)\s*$", s, re.S)
    if not m:
        return None
    try:
        v = tuple(float(x) for x in m.group(1).split(","))
    except ValueError:
        return None
    return v if len(v) == 3 else None


def point(recs, num):
    """CARTESIAN_POINT -> (x, y, z). Args are ( name, (x,y,z) ), so the triple is index 1."""
    r = recs.get(num)
    if not r or r[0] != "CARTESIAN_POINT" or len(r[1]) < 2:
        return None
    return _triple(r[1][1])


def direction(recs, num):
    """DIRECTION -> unit vector. Same (name, triple) argument order as CARTESIAN_POINT."""
    r = recs.get(num)
    if not r or r[0] != "DIRECTION" or len(r[1]) < 2:
        return None
    v = _triple(r[1][1])
    if not v:
        return None
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return tuple(x / n for x in v)


def placement(recs, num):
    """AXIS2_PLACEMENT_3D -> (location, axis) ; falls back to the raw point if it is one.

    Argument order is ( name, location, axis, refDirection ), so the location is index 1 -
    reading index 0 picks up the 'NONE' label and silently yields nothing.
    """
    r = recs.get(num)
    if r and r[0] == "AXIS2_PLACEMENT_3D" and len(r[1]) >= 3:
        return point(recs, _ref(r[1][1])), direction(recs, _ref(r[1][2]))
    p = point(recs, num)
    return p, None


def _ref(arg):
    m = re.match(r"^#(\d+)$", arg.strip())
    return int(m.group(1)) if m else None


def circle_features(path, min_diameter=1.0):
    """Every circular edge as dicts: d (diameter mm), c (centre), a (unit normal).

    Concentric duplicates are collapsed by (diameter, axis-line) so a bore that shows up as
    two edges on two faces still counts once.
    """
    recs = records(path)
    feats = []
    for num, (typ, args) in recs.items():
        if typ != "CIRCLE" or len(args) < 3:
            continue
        ref = _ref(args[1])
        if ref is None:
            continue
        loc, axis = placement(recs, ref)
        if loc is None:
            continue
        try:
            dia = round(float(args[2]) * 2.0, 2)
        except ValueError:
            continue
        if dia < min_diameter:
            continue
        feats.append({"d": dia, "c": tuple(round(v, 2) for v in loc), "a": axis})
    return feats


def axis_key(c, a, tol=0.02):
    """Canonical key for the infinite line through c with direction a.

    Two features share a key only if their directions are parallel AND the vector between
    their centres is parallel to that direction - i.e. they really are concentric.
    """
    if a is None:
        return None
    s = 1.0 if a[0] > tol or (abs(a[0]) <= tol and a[1] > tol) or (
        abs(a[0]) <= tol and abs(a[1]) <= tol and a[2] > tol) else -1.0
    u = tuple(round(x * s, 3) for x in a)
    return u


def groups(features):
    """Group features into concentric families: {(axis_key, point_on_line): [features]}.

    The line position is taken as the component-wise midpoint of the family so far, which is
    stable enough to cluster collinear centres without merging genuinely separate bores.
    """
    fams = []
    for f in features:
        k = axis_key(f["c"], f["a"])
        placed = False
        for fam in fams:
            if fam["key"] != k or f["a"] is None:
                continue
            d = tuple(f["c"][i] - fam["c"][i] for i in range(3))
            cross = (d[1] * f["a"][2] - d[2] * f["a"][1],
                     d[2] * f["a"][0] - d[0] * f["a"][2],
                     d[0] * f["a"][1] - d[1] * f["a"][0])
            if math.sqrt(sum(x * x for x in cross)) < 0.05:
                n = len(fam["feats"]) + 1
                fam["c"] = tuple(round((fam["c"][i] * (n - 1) + f["c"][i]) / n, 2) for i in range(3))
                fam["feats"].append(f)
                placed = True
                break
        if not placed:
            fams.append({"key": k, "c": f["c"], "a": f["a"], "feats": [f]})
    return [f for f in fams if f["a"] is not None]
