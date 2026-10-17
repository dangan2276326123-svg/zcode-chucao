# -*- coding: utf-8 -*-
"""Build the 孔/凸台 pairing table the assembly is waiting on, from hole_maps2/index.json.

The author's job is to say which feature of one part goes into which feature of another. To
make that answerable in a few keystrokes this lists every circular feature grouped by DIAMETER
and by 孔/凸台, with its own part's number, axis position and axis direction - so a reply can
be "连杆1 ② ↔ 电推杆 ①" and nothing else needs to be looked up.

It also flags the structural consequence of the corrected kinds: a bore can only mate with a
same-diameter boss or a pin, so any diameter that has bores but no bosses (or the reverse)
narrows the possible joints by itself.

Usage: python -B tools/sw_hole_pairing_table.py
Writes cad_work/hole_maps2/配对表.md
"""
import io
import json
import os

IDX = os.path.join("D:", os.sep + "ai work", "qoder", "cad_work", "hole_maps2", "index.json")
OUT = os.path.join("D:", os.sep + "ai work", "qoder", "cad_work", "hole_maps2", u"配对表.md")
CIRCLED = u"①②③⑤⑥⑦⑨⑩⑪⑬⑭⑮⑰⑱⑲⑳㉑㉒㉓㉔㉕㉖㉗㉙㉚㉛㉜㉝㉞㉟"
LINKAGE = [u"电推杆", u"连杆1", u"连杆2", u"连杆3", u"刀柄1", u"刀柄2", u"刀柄3", u"吊耳1",
           u"吊耳_连杆2至刀柄1", u"铰接销_M10x60", u"铰轴弹性衬垫_25x20x8", u"仿形轮轴_D14x120",
           u"刀腿弹簧_包络代表"]


def axis_name(a):
    for v, n in zip(a, "XYZ"):
        if abs(v) > 0.5:
            return n
    return str(a)


def main():
    idx = json.load(io.open(IDX, encoding="utf-8"))
    by, missing = {}, []
    for rec in idx:
        if rec["part"] not in LINKAGE:
            continue
        for h in rec["features"]:
            tag = h.get("tag")
            if tag is None:
                missing.append(rec["part"])
                tag = "?"
            by.setdefault(h["d"], []).append((rec["part"], tag, h["kind"], h["c"], axis_name(h["a"])))
    lines = [u"# 提刀机构 孔/凸台 配对表（v2，按圆边与面朝向重测）", "",
             u"数据来源：`cad_work/hole_maps2/index.json`，由 `tools/sw_hole_maps2.py` 生成。",
             u"孔=凹面（same_sense .F.），凸台=凸面（.T.）；两判据与 连杆1 的 SolidWorks 特征树一致。",
             u"坐标是各零件自己模型里的局部坐标，不是装配坐标。",
             u"",
             u"**回话只要写配对的编号即可**，例如 `连杆1 ② ↔ 电推杆 ①`。",
             u""]
    only_boss, only_bore = [], []
    for dia in sorted(by, reverse=True):
        rows = by[dia]
        bores = [r for r in rows if r[2] == u"孔"]
        bosses = [r for r in rows if r[2] == u"凸台"]
        # a diameter that appears as nothing but one lone boss (φ64 tube, φ50 seat...) is a
        # body outline, not a joint candidate - list it once at the bottom instead of giving
        # it a table each, which is what made the first version of this file unreadable
        if not bores and len(bosses) <= 1:
            only_boss.append(u"φ%g×%d(%s%s)" % (dia, len(bosses), bosses[0][0] if bosses else u"",
                                                u" " + bosses[0][1] if bosses else u""))
            continue
        if not bosses and len(bores) <= 1:
            only_bore.append(u"φ%g×%d(%s%s)" % (dia, len(bores), bores[0][0], u" " + bores[0][1]))
            continue
        head = u"## φ%g　孔 %d 个 / 凸台 %d 个" % (dia, len(bores), len(bosses))
        if bores and not bosses:
            head += u"　← 没有同径凸台可插，只能配销或衬套"
        elif bosses and not bores:
            head += u"　← 没有同径孔可装它，多半插进别件的孔或销"
        elif len(bores) == 1 and len(bosses) == 1:
            head += u"　← 全机构唯一候选，基本可定死"
        lines.append(head)
        lines.append(u"")
        lines.append(u"| 件 | 号 | 类型 | 轴上一点 (x, y, z) | 轴方向 |")
        lines.append(u"|---|---|---|---|---|")
        for r in sorted(rows, key=lambda x: (x[2] != u"孔", x[0])):
            lines.append(u"| %s | %s | %s | (%g, %g, %g) | %s |" % (
                r[0], r[1], r[2], r[3][0], r[3][1], r[3][2], r[4]))
        lines.append(u"")
    if only_boss:
        lines.append(u"## 只有单个凸台、无同径孔的直径（多半是外形轮廓，不是铰点）")
        lines.append(u"")
        lines.append(u"、".join(only_boss))
        lines.append(u"")
    if only_bore:
        lines.append(u"## 只有单个孔、无同径凸台的直径（要配销/衬套，或插未建件）")
        lines.append(u"")
        lines.append(u"、".join(only_bore))
        lines.append(u"")
    io.open(OUT, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    n = sum(1 for l in lines if l.startswith(u"| "))
    print("[ok] %d feature rows, %d diameter groups -> %s" % (n, len(by), OUT))
    if missing:
        print("   !! %d parts had no stored tag, rerun sw_hole_maps2.py first: %s" % (
            len(missing), sorted(set(missing))[:5]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
