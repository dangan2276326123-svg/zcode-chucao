#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Draw the four block diagrams the thesis chapters promise but never had.

Why PIL and not matplotlib
--------------------------
This repo's README「运行环境」records that **matplotlib is unusable in both Python
environments** (numpy 2.0.2 vs a compiled-1.x build -> ImportError), which is also why
`tools/eval_test_set.py` has to stub it out before importing the training script. PIL is
available and Windows ships CJK fonts, so a box-and-arrow diagram is drawn directly with
ImageDraw instead.

The rule these figures live by
------------------------------
**Every box and every arrow must come from the chapter text, and nothing may be added.**
Each builder below names the paragraph it renders. That matters because these are
"设计记录" figures: a block diagram that quietly gains a component becomes a claim the
design never made, and a reviewer reading the text next to the figure will notice.
So: no invented sensor, no invented bus, no number that is not already in the chapter.

Outputs go to `thesis_cau/04_figures/` and are registered in `figures_manifest.md`,
which `make_thesis_docx.py` reads to decide embed-vs-placeholder.

Usage:  python -B tools/make_thesis_diagrams.py
"""
import os

from PIL import Image, ImageDraw, ImageFont

THESIS = os.environ.get('THESIS_DIR') or r'D:\JetBrains\chucao_prj\thesis_cau'
OUT = os.path.join(THESIS, '04_figures')

FONT = r'C:\Windows\Fonts\msyh.ttc'
FONT_BOLD = r'C:\Windows\Fonts\msyhbd.ttc'
SCALE = 3            # draw at 3x then keep it: print width ~15 cm, so this is >300 dpi
INK = (30, 30, 30)
LIGHT = (120, 120, 120)
FILL = (248, 248, 248)
GROUP = (250, 250, 250)


def _font(size, bold=False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT, int(size * SCALE))


class Canvas(object):
    def __init__(self, w, h):
        self.im = Image.new('RGB', (int(w * SCALE), int(h * SCALE)), 'white')
        self.d = ImageDraw.Draw(self.im)

    def text_size(self, s, size, bold=False):
        bb = self.d.textbbox((0, 0), s, font=_font(size, bold))
        return bb[2] - bb[0], bb[3] - bb[1]

    def box(self, x, y, w, h, label, size=10.5, bold=False, dashed=False):
        X, Y, W, H = (v * SCALE for v in (x, y, w, h))
        if dashed:
            self._dash_rect(X, Y, W, H)
        else:
            self.d.rounded_rectangle([X, Y, X + W, Y + H], radius=6 * SCALE,
                                     outline=INK, width=2 * SCALE, fill=FILL)
        lines = label.split('\n')
        tw, th = self.text_size(max(lines, key=len), size, bold)
        line_h = th + 6 * SCALE
        total = line_h * len(lines)
        cy = Y + (H - total) // 2
        for ln in lines:
            w1, _ = self.text_size(ln, size, bold)
            self.d.text((X + (W - w1) // 2, cy), ln, font=_font(size, bold), fill=INK)
            cy += line_h

    def group(self, x, y, w, h, label=None, size=9.5):
        X, Y, W, H = (v * SCALE for v in (x, y, w, h))
        self.d.rectangle([X, Y, X + W, Y + H], outline=LIGHT, width=SCALE, fill=GROUP)
        if label:
            self.d.text((X + 8 * SCALE, Y + 4 * SCALE), label,
                        font=_font(size, True), fill=INK)

    def arrow(self, x1, y1, x2, y2, label=None, size=9):
        A, B = (x1 * SCALE, y1 * SCALE), (x2 * SCALE, y2 * SCALE)
        self.d.line([A, B], fill=INK, width=2 * SCALE)
        import math
        ang = math.atan2(B[1] - A[1], B[0] - A[0])
        L = 9 * SCALE
        for da in (ang + 2.6, ang - 2.6):
            self.d.line([B, (B[0] + L * math.cos(da), B[1] + L * math.sin(da))],
                        fill=INK, width=2 * SCALE)
        if label:
            mx, my = (A[0] + B[0]) // 2, (A[1] + B[1]) // 2
            w1, h1 = self.text_size(label, size)
            self.d.text((mx - w1 // 2, my - h1 * 2), label, font=_font(size), fill=INK)

    def line(self, x1, y1, x2, y2):
        """Plain connector (no head) — used where one output feeds two boxes and only
        the last segment should carry the arrowhead."""
        self.d.line([(x1 * SCALE, y1 * SCALE), (x2 * SCALE, y2 * SCALE)],
                    fill=INK, width=2 * SCALE)

    def note(self, x, y, s, size=9):
        self.d.text((x * SCALE, y * SCALE), s, font=_font(size), fill=INK)

    def _dash_rect(self, X, Y, W, H):
        step = 10 * SCALE
        for x in range(X, X + W, step * 2):
            self.d.line([(x, Y), (min(x + step, X + W), Y)], fill=INK, width=2 * SCALE)
            self.d.line([(x, Y + H), (min(x + step, X + W), Y + H)], fill=INK,
                        width=2 * SCALE)
        for y in range(Y, Y + H, step * 2):
            self.d.line([(X, y), (X, min(y + step, Y + H))], fill=INK, width=2 * SCALE)
            self.d.line([(X + W, y), (X + W, min(y + step, Y + H))], fill=INK,
                        width=2 * SCALE)

    def save(self, name):
        p = os.path.join(OUT, name)
        self.im.save(p, 'PNG', optimize=True)
        return p, self.im.size


def chain(c, x, y, w, h, gap, labels, size=10.5):
    """Lay out a horizontal chain of boxes with arrows between them."""
    pos = []
    cx = x
    for lb in labels:
        c.box(cx, y, w, h, lb, size=size)
        pos.append((cx, cx + w))
        cx += w + gap
    for i in range(len(pos) - 1):
        c.arrow(pos[i][1], y + h / 2.0, pos[i + 1][0], y + h / 2.0)
    return pos


# --------------------------------------------------------------------- 图 1-1
def fig_route():
    """1.3 节：'需求分析→总体方案→机械系统设计→感知算法开发与训练→控制系统设计→
    台架验证→田间试验→统计分析'（原文八项，逐项照搬，不增不减）。"""
    steps = ['需求分析', '总体方案', '机械系统\n设计', '感知算法\n开发与训练',
             '控制系统\n设计', '台架验证', '田间试验', '统计分析']
    c = Canvas(760, 145)
    w, h, gap = 78, 46, 16
    x0 = (760 - (w * 8 + gap * 7)) / 2.0
    pos = chain(c, x0, 40, w, h, gap, steps, size=10)
    c.note(x0, 110, '注：流程为 1.3 节所述技术路线的逐项对应，'
                    '各阶段的验收判据见对应章节。')
    return c.save('fig1-1_technical_route.png')


# --------------------------------------------------------------------- 图 2-1
def fig_architecture():
    """2.1.2 节的数据流原文（"单目相机 → 树莓派（采集编码推流）→ 无线链路 → 地面站 PC
    （去畸变、语义分割、逆透视变换、导航线解算）→ 无线链路（UDP 控制帧）→ 树莓派
    （协议桥接）→ STM32 车载控制器（指令解析与安全联锁）→ 底层 PID 速度环 → 四轮 PWM
    驱动；除草刀升降与中间刀滑轨由 STM32 直接驱动"）与"感知上移、执行下沉"原则。

    分带按"东西装在哪台机器上"划，不按数据流方向划：相机与树莓派推流在**车上**，
    解算在**地面站**，闭环执行又回到**车上**。第一版把相机和树莓派圈进了地面站框，
    那是按流向分组造成的错，所以这里显式分三条带并给每条带标载体。
    """
    c = Canvas(760, 360)
    # 带 1：车端感知侧
    c.group(20, 24, 720, 86, '车端 · 感知采集侧')
    c.box(40, 56, 130, 40, '单目相机')
    c.box(220, 56, 160, 40, '树莓派\n采集编码推流')
    c.arrow(170, 76, 220, 76)
    c.box(440, 56, 130, 40, '无线链路')
    c.arrow(380, 76, 440, 76)
    # 带 2：地面站
    c.group(20, 126, 720, 86, '地面站 PC · 感知上移')
    c.box(40, 158, 530, 40, '去畸变 · 语义分割 · 逆透视变换 · 导航线解算')
    c.arrow(505, 112, 300, 158, '视频流')
    c.box(610, 158, 130, 40, '无线链路')
    c.arrow(570, 178, 610, 178, 'UDP 控制帧', size=8.5)
    # 带 3：车端执行侧
    c.group(20, 228, 720, 100, '车端 · 执行下沉')
    c.box(40, 258, 140, 40, '树莓派\n协议桥接')
    c.box(210, 258, 150, 40, 'STM32\n解析与安全联锁')
    c.box(390, 258, 130, 40, 'PID 速度环')
    c.box(550, 258, 120, 40, '四轮 PWM')
    c.arrow(675, 198, 110, 258, '串口')
    c.arrow(180, 278, 210, 278)
    c.arrow(360, 278, 390, 278)
    c.arrow(520, 278, 550, 278)
    c.box(210, 306, 150, 18, '刀升降与中间刀滑轨', size=8)
    c.arrow(285, 298, 285, 306)
    c.note(390, 312, '急停硬线回路与 SBUS 遥控通道保留为独立兜底层（见 2.5.3 节）')
    c.note(20, 340, '注：本图只画 2.1.2 节点列的环节与连接，未增加任何部件；'
                    '分带依据是各部件实际安装在哪一台设备上。')
    return c.save('fig2-1_system_architecture.png')


# --------------------------------------------------------------------- 图 3-1
def fig_perception_chain():
    """3.1 节处理链原文：'图像采集→去畸变→DeepLabV3+ 二分类分割→逆透视变换→双墙提取→
    远/近场导航线解算'，以及输出分别用于底盘轨迹跟踪与中间刀对行。"""
    c = Canvas(760, 210)
    steps = ['图像采集', '去畸变', 'DeepLabV3+\n二分类分割', '逆透视\n变换',
             '双墙提取', '远/近场\n导航线解算']
    w, h, gap = 104, 48, 18
    x0 = (760 - (w * 6 + gap * 5)) / 2.0
    pos = chain(c, x0, 40, w, h, gap, steps, size=10)
    # 分叉点落在"远/近场导航线解算"这一格底下。第一版取的是整行的水平中点，那个 x
    # 正好在"逆透视变换"下面，读图的人会以为远/近场是在 IPM 处一分为二的。
    fx = (pos[-1][0] + pos[-1][1]) / 2.0
    c.line(fx, 40 + h, fx, 112)
    c.line(x0 + 140, 112, fx, 112)
    c.arrow(x0 + 140, 112, x0 + 140, 138)
    c.arrow(x0 + 440, 112, x0 + 440, 138)
    c.box(x0 + 40, 140, 200, 36, '远场读数 → 底盘横向偏差', size=9.5)
    c.box(x0 + 340, 140, 200, 36, '近场读数 → 中间刀对行', size=9.5)
    c.note(x0, 186, '注：远、近场是同一条拟合中线在不同纵深的读数，非两种几何量（见 3.5.2 节）。')
    return c.save('fig3-1_perception_chain.png')


# --------------------------------------------------------------------- 图 4-1
def fig_control_loops():
    """4.1 节原文：'底盘轨迹跟踪 + 入土控制 + 除草装置控制'三回路架构，
    '三回路通过车载状态机统一调度，安全联锁对各回路拥有最高优先级'。"""
    c = Canvas(760, 320)
    c.box(40, 30, 150, 40, '远场导航线')
    c.box(40, 90, 150, 40, '近场导航线')
    c.box(40, 150, 150, 40, '深度档位设定')
    c.box(250, 30, 210, 40, '底盘轨迹跟踪回路\n转角分配 + 轮速映射')
    c.box(250, 90, 210, 40, '除草装置控制回路\n中间刀横向对行')
    c.box(250, 150, 210, 40, '入土控制回路\n仿形为主 · 微调为辅')
    for i, y in enumerate((50, 110, 170)):
        c.arrow(190, y, 250, y)
    c.box(520, 30, 200, 40, '四轮转角与轮速')
    c.box(520, 90, 200, 40, '中间刀滑轨位置指令')
    c.box(520, 150, 200, 40, '提刀 / 落刀')
    for y in (50, 110, 170):
        c.arrow(460, y, 520, y)
    # 状态机带只占 y=210..270，题注必须落在它下边（第一版把题注画在 y=240，
    # 与带内文字同高，两条长句横向叠在一起成了不可读的糊字）。
    c.group(250, 210, 470, 60, '车载状态机统一调度 · 安全联锁具有最高优先级')
    c.note(258, 240, '急停锁存 / 心跳超时 / 视觉丢失三条已编码待台架复验，'
                     '过流保护待启用（见 2.5.3、4.3.2 节）')
    c.arrow(355, 190, 355, 210)
    c.note(40, 288, '注：图中"刀位实测反馈"一项缺失，故中间刀对行在作业效果层面为开环'
                    '（见 4.4.1 节）。')
    return c.save('fig4-1_control_loops.png')


def main():
    if not os.path.isdir(OUT):
        os.makedirs(OUT)
    for fn in (fig_route, fig_architecture, fig_perception_chain, fig_control_loops):
        p, size = fn()
        print('%-42s %dx%d  %7d B'
              % (os.path.basename(p), size[0], size[1], os.path.getsize(p)))


if __name__ == '__main__':
    main()
