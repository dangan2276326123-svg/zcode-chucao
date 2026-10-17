"""Turn the photo's pivot pixels into millimetres and test them against the CAD hinge spans.

Calibration is self-consistent rather than assumed: the actuator tube reads ~70 px wide, and
taking its diameter as the model's D44 gives 0.63 mm/px; with that scale the pin-to-pin
distance measured along the same actuator in the photo comes out ~450 mm against the model's
429 mm - a 5% agreement, which is what makes the scale usable for the other spans.

Every pixel below is my reading off the gridded crop (cad_work/photo/station1_grid.png), so
anyone can re-measure and disagree with a number instead of a vibe.
"""
import io
import json
import math
import os

OUT = os.path.join("D:", os.sep + "ai work", "qoder", "cad_work", "photo_pivots.json")
TUBE_PX = 70.0
TUBE_MM = 44.0            # 电推杆 model: D44 cylindrical feature
SCALE = TUBE_MM / TUBE_PX  # mm per crop pixel

# crop-grid coordinates (px) as read off station1_grid.png
P = {
    "A_推杆上端铰(立在黄色立板上)": (390, 560),
    "B_顶部斜摇臂上铰": (455, 300),
    "C_斜杆上铰(立板下部)": (560, 980),
    "D_推杆下端铰(杆端叉)": (310, 1270),
    "E_斜杆下端(刀脚)": (350, 1300),
    "F_铲刃可见最低点": (500, 1400),
    "G_弹簧下端尖": (390, 1450),
}

# hinge spans read off the parts (docs/执行机构孔系几何_20261016.md)
CAD = {
    "电推杆 两端铰孔": 429.0,
    "连杆1 D25<->D10": 385.0,
    "连杆2 D20<->D30": 351.8,
    "连杆3 D20<->D10": 510.5,
}


def d(p, q):
    return math.hypot(P[p][0] - P[q][0], P[p][1] - P[q][1]) * SCALE


def main():
    A = "A_推杆上端铰(立在黄色立板上)"
    B = "B_顶部斜摇臂上铰"
    C = "C_斜杆上铰(立板下部)"
    D = "D_推杆下端铰(杆端叉)"
    E = "E_斜杆下端(刀脚)"
    F = "F_铲刃可见最低点"
    G = "G_弹簧下端尖"
    pairs = [
        (A, D, "推杆 两端铰距（同时用来校标尺）"),
        (B, A, "机架边 g：摇臂上铰 ↔ 推杆上铰"),
        (C, E, "斜杆两端距（照片读出的连杆长）"),
        (A, C, "机架上两铰点距"),
        (D, E, "刀脚上两铰点距 c"),
        (A, F, "推杆上铰到铲刃（挂高）"),
        (F, G, "铲刃与弹簧尖的相对高差"),
    ]
    rows = []
    for p, q, what in pairs:
        mm = round(d(p, q), 1)
        rows.append({"what": what, "px": round(math.hypot(P[p][0] - P[q][0], P[p][1] - P[q][1]), 1),
                     "mm": mm, "from": p, "to": q})
    out = {"scale_mm_per_px": round(SCALE, 4), "pivots_px": P, "spans": rows,
           "cad_hinge_spans_mm": CAD,
           "checks": {
               "推杆 照片/模型": round(rows[0]["mm"] / CAD["电推杆 两端铰孔"], 3),
               "照片斜杆 对 连杆1": round(rows[2]["mm"] / CAD["连杆1 D25<->D10"], 3),
               "照片斜杆 对 连杆2": round(rows[2]["mm"] / CAD["连杆2 D20<->D30"], 3),
           }}
    io.open(OUT, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=2))
    print(json.dumps(out, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
