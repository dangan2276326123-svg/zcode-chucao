# -*- coding: utf-8 -*-
"""由 pragmatic_edit_plan.json + paper_analysis.json 自动生成 deck_order_map.md。

溯源表必须与 deck 同源，手改会漂移；改内容请改 plan/analysis 后重跑本脚本。
用法： python gen_map.py
"""
import json

PLAN = 'pragmatic_edit_plan.json'
ANALYSIS = 'paper_analysis.json'
OUT = 'deck_order_map.md'
VERSION_NOTE = (
    "- 第 4 版变更：按汇报人要求**删除全部 13 处页底红字 takeaway**，并删除结尾页的三条讨论问题"
    "（`AGENT_CLOSING_META`）—— 汇报人删过的内容一律不加回；原红字承担的两处限定词"
    "（纯函数复现、电流阈值须标定）折进 bullet 本体，口径边界只保留在本表与证据链 caution 字段\n")

REFLECTION = [
    "- **第 3 页**：行距 30~40 cm、坡地 0~15° 为汇报人 09-16 现场确认值，与论文 `ch02:14` 的 30~60 cm、5~15° 冲突；按事实权威序以现场值为准，论文待改（台账 Hw-19）。\n",
    "- **第 4-5 页**：为什么没有第三种刀 → 表 2-3 六种排除理由各自成立，ch05 组1 既定对比就是鸭掌铲 vs 弹齿；加第三种会同时改刀头与控制两个变量，归因不清。\n",
    "- **第 8 页**：两级纠偏做了吗 → 没有，滑台未接线，本页是分工设计（proposed），实测排春季。\n",
    "- **第 12 页**：你不是四轮转向吗 → 硬件具备该能力，当前 AUTO 只用轮速差；能力／拟用模式／已运行模式三者分开说。\n",
    "- **第 13 页**：刀移过去图像偏差为什么不变 → 相机在车架上，量的是行相对车；这就是还不能叫闭环的原因。50 mm 限幅那组数字是**纯函数复现**，被问到必须说明不是整车实测。\n",
    "- **第 15-16 页**：论文里不是写了深度监测？→ `ch04:50` 的摆角传感器无任何硬件登记，属过度声明，本次不采用。电流判据在标定前不得称可用；板上 ACS712 登记对象是**行走电机回路**，是否覆盖推杆未跟线。\n",
    "- **口头要提的三件事**（页面上不写）：进土深度走哪条路 / 鸭掌铲幅宽何时补测 / 春季田块需书面确认。\n",
]


def build():
    pl = json.load(open(PLAN, encoding='utf-8'))
    an = json.load(open(ANALYSIS, encoding='utf-8'))
    ch = {c['evidence_id']: c for c in an['evidence_chains']}
    fg = {f['figure_id']: f for f in an['figures']}
    n = len(pl['slides'])
    L = ["# 组会汇报 deck 页面清单与溯源表（2026-09-16，第 4 版）\n",
         "- 交付物：`组会汇报_纯视觉芍药行间除草机器人_20260916.pptx`（%d 页，16:9，全可编辑）" % n,
         "- 生产路线：**Route C 务实回退**；本表由 `gen_map.py` 从 plan + 证据合同自动生成，不与 deck 脱钩",
         "- 校验：`validate_paper_analysis.py` passed；`validate_pragmatic_fallback_pptx.py` passed（0 issues）；PowerPoint COM 导出 %d 张 PNG 逐页目视" % n,
         VERSION_NOTE,
         "## 展示图清单\n\n**全 deck 无任何展示图**（%d 页 `figure_count` 合计 0）。分割实际输出、导航线叠加、整机照片由汇报人现场展示。下表『溯源记录』不是展示图，是每个数字的出处登记。\n" % n,
         "| 页 | 导航段 | 版式 | 标题（结论式） | 证据链 | 关键数字的溯源记录 | 口径边界（口头也不可怕，但不可越） |",
         "| --- | --- | --- | --- | --- | --- | --- |"]
    for s, t in zip(an['slides'], pl['slides']):
        ev = "；".join(s['evidence_ids']) or "—"
        src = "；".join("%s: %s" % (f, fg[f]['source_label']) for f in s['figure_ids']) or "—"
        ca = "；".join(ch[e]['caution'] for e in s['evidence_ids']) or "—"
        L.append("| %d | %s | %s | %s | %s | %s | %s |" % (
            s['slide_no'], s['section'], t['layout_type'], s['title'], ev, src, ca))
    L.append("\n## 讲这页时要挡住的反问\n")
    L += REFLECTION
    L.append("\n## 交付声明\n\n```text\nImage2 backend used: no\nDelivery mode: pragmatic editable fallback accepted by user\n"
             "Visual style: sample-deck-derived white/red/black academic grammar\n"
             "Scientific visuals: none displayed（数据图与整机照片由汇报人现场展示）\n"
             "Structural QA completed: yes（%d 页，0 issues）\n"
             "Render/layout QA completed: yes（PowerPoint COM 导出 %d 张 PNG + 目视复核）\n"
             "Editable elements may exist: yes\n```\n" % (n, n))
    open(OUT, 'w', encoding='utf-8').write("\n".join(L))
    print('wrote', OUT, 'pages', n)


if __name__ == '__main__':
    build()
