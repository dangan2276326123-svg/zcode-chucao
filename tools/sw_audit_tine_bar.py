# -*- coding: utf-8 -*-
"""Audit the exported spring-tine bar STEP: is every tine the same, and is the bend an arc?

Reads the STEP text directly (no CAD kernel) through tools/step_circles.py and reports, per
tine station (a 8 mm-wide slice of X), the circular-edge radii found there. A polyline bend has
no circle at r=67/73; a true arc has two edges per bend face, so a correct tine shows the same
radius multiset at every station. Also prints the whole-part bounding box and the count of
distinct stations.

Usage: python -B tools/sw_audit_tine_bar.py [path.step]
"""
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.join("D:", os.sep + "ai work", "qoder", "tools"))
import step_circles as sc  # noqa: E402

DEF = os.path.join("D:", os.sep + "ai work", "qoder", "cad_work", "cad_out", "缺件",
                   "弹齿除草刀_整组v4.step")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEF
    if not os.path.exists(path):
        print(json.dumps({"err": "missing " + path}))
        return 1
    recs = sc.records(path)
    pts = []
    for num, (t, args) in recs.items():
        if t == "CARTESIAN_POINT" and len(args) > 1:
            tri = sc._triple(args[1])
            if tri:
                pts.append(tri)
    bbox = [[round(min(p[i] for p in pts), 2), round(max(p[i] for p in pts), 2)]
            for i in range(3)] if pts else None
    feats = sc.circle_features(path)
    xs = [f["c"][0] for f in feats]
    # BEND_DIAMETERS = 2 x the C-bend radii 67 / 73. A polyline bend has no such circle at all.
    bend = (134.0, 146.0)
    stations = {}
    for f in feats:
        key = round(f["c"][0] / 8.0) * 8.0
        stations.setdefault(key, []).append(f["d"])
    per_station = {}
    for k in sorted(stations):
        ds = stations[k]
        per_station["%.0f" % k] = {
            "n_circle_edges": len(ds),
            "bend_edges": sum(1 for d in ds if d in bend),
            "other_diameters": sorted(set(d for d in ds if d not in bend)),
        }
    hist = {}
    for f in feats:
        hist[f["d"]] = hist.get(f["d"], 0) + 1
    identical = len(set(json.dumps(v, sort_keys=True) for v in per_station.values())) == 1
    out = {"file": os.path.basename(path), "bbox_mm": bbox,
           "n_circle_edges": len(feats), "n_stations": len(per_station),
           "all_stations_identical": identical, "per_station": per_station,
           "diameter_histogram": dict(sorted(hist.items(), key=lambda kv: -kv[1])[:12]),
           "x_of_circle_centres": [round(min(xs), 2), round(max(xs), 2)] if xs else None}
    print(json.dumps(out, ensure_ascii=True, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
