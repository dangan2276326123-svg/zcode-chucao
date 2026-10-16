"""Per-part geometry summary of the exported STEP files, written as UTF-8 markdown.

Purpose: turn 14 unreadable .SLDPRT into a table of bounding boxes, plate thickness and
hole diameters/positions, then cross-match hole diameters between parts so the missing
connecting hardware becomes visible instead of guessed.

Read-only with respect to the user's CAD: consumes only the STEP copies in cad_work/step.
"""
import glob
import io
import os
import re

from step_geom_report import TRIPLE, load, point_of, last_number, REF

STEP_DIR = os.path.join("D:", os.sep + "ai work", "qoder", "cad_work", "step")
OUT = os.path.join("D:", os.sep + "ai work", "qoder", "docs", "执行机构零件几何摘要_20261016.md")


def part_geometry(path):
    entities = load(path)
    pts = []
    for _eid, (etype, args) in entities.items():
        if etype == "CARTESIAN_POINT":
            t = TRIPLE.search(args)
            if t:
                pts.append(tuple(float(x) for x in t.groups()))
    span = []
    for ax in (0, 1, 2):
        vals = [p[ax] for p in pts]
        span.append((round(min(vals), 1), round(max(vals), 1)) if vals else (0.0, 0.0))
    holes = []
    for _eid, (etype, args) in entities.items():
        if etype != "CYLINDRICAL_SURFACE":
            continue
        r = last_number(args)
        if r is None or not (0.4 < r < 60):
            continue
        loc = None
        for ref in REF.findall(args):
            loc = point_of(entities, int(ref))
            if loc:
                break
        if loc:
            holes.append((round(r * 2, 1), tuple(round(v, 1) for v in loc)))
    return span, holes


def main():
    data = {}
    for f in sorted(glob.glob(os.path.join(STEP_DIR, "*.step"))):
        name = os.path.splitext(os.path.basename(f))[0]
        data[name] = part_geometry(f)

    lines = ["# 执行机构零件几何摘要（2026-10-16，单位 mm）", "",
             "> 来源：作者 2026-04 建模的样机执行机构零件（`%USERPROFILE%\\OneDrive\\Desktop\\移动平台`，14 个 `.SLDPRT`），",
             "> 由 `tools/sw_export_step.py` 以 SolidWorks COM（ReadOnly+Silent）另存为 STEP 后，",
             "> 再用 `tools/sw_hole_pairing.py` 做纯文本解析。**原件未改动，未装配。**", "",
             "> 三条读法限制：①轴向按各零件自身坐标系，跨件不可直接比较，只有孔径与孔数可比；",
             "> ②本表把圆柱面一律计入“孔直径分布”，所以零件外圆（如碎土轮片 D112、圆柱 D50）也出现在里面，",
             "> 不能当成“有个 D112 的孔”；③螺纹底孔按孔径原样列出（D5/D5.1 一类多为 M6 底孔），",
             "> 未与紧固件对照，“孤孔”只表示“该孔径暂无第二个零件与之配对”，不表示缺件。", ""]
    lines += ["| 零件 | X 跨度 | Y 跨度 | Z 跨度 | 最薄向(判断板厚) | 孔直径分布 |",
              "| --- | --- | --- | --- | --- | --- |"]
    for name, (span, holes) in data.items():
        spans = [(span[i][1] - span[i][0]) for i in range(3)]
        thin_i = min(range(3), key=lambda i: spans[i])
        dist = {}
        for d, _loc in holes:
            dist[d] = dist.get(d, 0) + 1
        txt = " ".join("D%g x%d" % (d, n) for d, n in sorted(dist.items(), key=lambda kv: -kv[1]))
        lines.append("| %s | %g | %g | %g | %g (%s) | %s |" % (
            name, spans[0], spans[1], spans[2], spans[thin_i], "XYZ"[thin_i], txt or "—"))

    # cross-part diameter match: a bore that appears in exactly one part has no partner yet
    by_dia = {}
    for name, (_span, holes) in data.items():
        for d, _loc in holes:
            by_dia.setdefault(d, set()).add(name)
    lines += ["", "## 孔径跨件配对（同一孔径出现在 2 个及以上零件 = 可能是一对螺栓孔）", "",
              "| 孔径 mm | 出现件数 | 零件 |", "| --- | --- | --- |"]
    for d, names in sorted(by_dia.items(), key=lambda kv: -len(kv[1])):
        lines.append("| %g | %d | %s |" % (d, len(names), "、".join(sorted(names))))
    solo = [(d, n) for d, names in by_dia.items() for n in names if len(names) == 1]
    lines += ["", "## 孤孔（该孔径只在一个零件上出现，暂无配合对象）", ""]
    if solo:
        for d, n in sorted(solo):
            lines.append("- D%g 仅在 %s" % (d, n))
    else:
        lines.append("- 无（所有出现的孔径都至少有 2 个零件共用）")

    lines += ["", "## 待核对（本表读出的数与已登记事实不一致或缺解释，须作者裁定，不改事实）", ""]
    lines += [
        "- **刃宽方向**：刀头件 X 跨度 213.8、Y 跨度 167.5，刀具件 X 197.5、Y 267.4，"
        "都落不到台账 Hw-18（2026-09-21 现场确认）“鸭掌铲刃宽 25 cm”这个数上。"
        "可能这两个件不是刃口本体，也可能是 4 月模型与现场确认值不同一轮。"
        "结论要等装配后指认“哪两个边是刃口最外缘”再定，本文不据此改刃宽。",
        "- **“圆柱”件的长度**：该件 φ50、最长处 1442 mm。作者口述“两个碎土轮片加多个圆柱就是仿形轮”，"
        "但 1442 mm 不像隔套而像轴/管料。它到底是仿形轮隔套、轮轴，还是刀梁横管，须确认后本表才敢定轮面宽度。",
        "- **同名零件目录不止一处**：`桌面\\移动平台` 14 件，另有一份 21 件的完整集"
        "（多出 车体、车柱、中间杆、基片1/3/4、支架1）。装配需要整套，本表只覆盖 14 件那一份。",
        "- **预紧弹簧无对应零件**：ch02 §2.3.2 设计要点（2）写了可调拉伸弹簧，14 件里没有弹簧件，"
        "正文已就地挂 `<待确认>`（见 chucao_prj 提交 dd77eb8）。",
    ]

    io.open(OUT, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("parts=%d, wrote=%s" % (len(data), OUT))


if __name__ == "__main__":
    main()
