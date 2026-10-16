"""Parse SolidWorks-exported STEP files without any CAD library.

Extracts per part: bounding box (all CARTESIAN_POINT), and cylindrical surfaces /
circles (radius + axis location) which is where bolt holes and pin bores live.
STEP entity syntax is `#12 = CYLINDRICAL_SURFACE('',#13,#14,5.);` so every record is
resolved through an id -> (type, args) map. Coordinates come out in mm.
Pure text parsing: enough to read real sizes and hole positions off a part, not to
rebuild the B-rep or decide how parts mate.
"""
import glob
import io
import os
import re
import sys

RECORD = re.compile(r"^\s*#(\d+)\s*=\s*([A-Z0-9_]+)\s*\((.*)\)\s*;\s*$")
TRIPLE = re.compile(r"\(\s*([-\d.eE+]+)\s*,\s*([-\d.eE+]+)\s*,\s*([-\d.eE+]+)\s*\)")
REF = re.compile(r"#(\d+)")


def load(path):
    entities = {}
    for line in io.open(path, "r", encoding="utf-8", errors="replace"):
        m = RECORD.match(line)
        if m:
            entities[int(m.group(1))] = (m.group(2), m.group(3))
    return entities


def point_of(entities, eid, depth=0):
    """Follow refs until a CARTESIAN_POINT triple is found."""
    if depth > 6 or eid not in entities:
        return None
    etype, args = entities[eid]
    if etype == "CARTESIAN_POINT":
        t = TRIPLE.search(args)
        if t:
            return tuple(float(x) for x in t.groups())
        return None
    for ref in REF.findall(args):
        p = point_of(entities, int(ref), depth + 1)
        if p:
            return p
    return None


def last_number(args):
    nums = re.findall(r"[-\d][\d.eE+-]*", args)
    return float(nums[-1]) if nums else None


def report(path):
    entities = load(path)
    pts = []
    for eid, (etype, args) in entities.items():
        if etype == "CARTESIAN_POINT":
            t = TRIPLE.search(args)
            if t:
                pts.append(tuple(float(x) for x in t.groups()))
    out = [os.path.basename(path), "  entities=%d points=%d" % (len(entities), len(pts))]
    if pts:
        for ax, label in ((0, "X"), (1, "Y"), (2, "Z")):
            vals = [p[ax] for p in pts]
            out.append("  %s: %9.2f .. %9.2f  (span %9.2f mm)" % (label, min(vals), max(vals), max(vals) - min(vals)))
    feats = []
    for eid, (etype, args) in entities.items():
        if etype in ("CYLINDRICAL_SURFACE", "CIRCLE"):
            rad = last_number(args)
            loc = None
            for ref in REF.findall(args):
                loc = point_of(entities, int(ref))
                if loc:
                    break
            if rad is not None and loc is not None and 0.4 < rad < 200:
                feats.append((etype, round(rad, 2), tuple(round(v, 1) for v in loc)))
    counts = {}
    for etype, rad, loc in feats:
        counts[(etype, rad)] = counts.get((etype, rad), 0) + 1
    out.append("  circular/cylindrical features=%d" % len(feats))
    for (etype, rad), n in sorted(counts.items(), key=lambda kv: -kv[1]):
        out.append("    %-20s R=%6.2f mm  x%d" % (etype, rad, n))
    shown = set()
    for etype, rad, loc in feats[:14]:
        key = (etype, rad, loc)
        if key in shown:
            continue
        shown.add(key)
        out.append("    %s R=%6.2f @ (%8.1f, %8.1f, %8.1f)" % (etype[:4], rad, loc[0], loc[1], loc[2]))
    return "\n".join(out)


if __name__ == "__main__":
    for f in sorted(glob.glob(sys.argv[1])):
        print(report(f))
