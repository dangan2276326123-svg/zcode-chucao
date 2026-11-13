# -*- coding: utf-8 -*-
"""断面开挖量什么、入土角在哪量：两联示意图。

左：横断面（垂直行驶方向挖沟）——耕深 h = 地表到沟底；扰土带宽 b = 松土区水平宽度。
右：侧视（沿行方向看）——入土角 α = 刀面与地表夹角，在刀上按实际耕深档位量。
PIL + SimHei（本机 matplotlib 坏）；减号用 ASCII '-'。
Usage: python -B tools/draw_section_measurement.py
"""
import os
from PIL import Image, ImageDraw, ImageFont

OUT = os.path.join(os.path.dirname(__file__), "..", "cad_work", "cad_out",
                   "断面测量_三量示意.png")
W, H = 1280, 760
SOIL = (150, 110, 70)
LOOSE = (196, 158, 112)
FURROW = (246, 241, 231)
BLADE = (70, 70, 78)
INK = (30, 30, 30)
RED = (190, 40, 40)
BLUE = (30, 90, 170)


def font(sz):
    return ImageFont.truetype("C:/Windows/Fonts/simhei.ttf", sz)


def dashed(d, p, q, fill, width=2, dash=10, gap=7):
    import math
    x0, y0 = p
    x1, y1 = q
    L = math.hypot(x1 - x0, y1 - y0)
    if L == 0:
        return
    ux, uy = (x1 - x0) / L, (y1 - y0) / L
    t = 0.0
    while t < L:
        t2 = min(t + dash, L)
        d.line([(x0 + ux * t, y0 + uy * t), (x0 + ux * t2, y0 + uy * t2)],
               fill=fill, width=width)
        t = t2 + gap


def arrow(d, p, q, fill, width=3, head=12):
    import math
    d.line([p, q], fill=fill, width=width)
    ang = math.atan2(q[1] - p[1], q[0] - p[0])
    for sgn in (+1, -1):
        a = ang + sgn * 2.6
        d.line([q, (q[0] + head * math.cos(a), q[1] + head * math.sin(a))],
               fill=fill, width=width)


def main():
    im = Image.new("RGB", (W, H), (252, 250, 245))
    d = ImageDraw.Draw(im)
    d.text((W // 2, 28), "断面开挖 + 标尺拍照：三个量各在哪量", font=font(30),
           fill=INK, anchor="mm")

    # ---------------- 左：横断面 ----------------
    d.text((330, 80), "横断面：垂直行驶方向挖一条沟", font=font(24), fill=INK,
           anchor="mm")
    gy = 300
    d.rectangle([40, gy, 620, 640], fill=SOIL)          # 原状土
    d.line([(40, gy), (620, gy)], fill=INK, width=3)    # 地表
    d.text((70, gy - 16), "地表", font=font(18), fill=INK, anchor="lm")
    # 松土区（扰土带）：比沟宽、颜色浅
    loose = [(190, gy), (470, gy), (452, 445), (208, 445)]
    d.polygon(loose, fill=LOOSE)
    dashed(d, (190, gy), (208, 445), INK, 2)
    dashed(d, (470, gy), (452, 445), INK, 2)
    dashed(d, (208, 445), (452, 445), INK, 2)
    d.text((215, 330), "松土区", font=font(18), fill=INK)
    # 沟（刀切出的空腔）+ 刀片断面
    d.polygon([(265, gy), (395, gy), (385, 410), (275, 410)], fill=FURROW)
    d.rectangle([270, 402, 390, 412], fill=BLADE)
    d.text((330, 430), "刀片", font=font(16), fill=INK, anchor="mm")
    # 耕深 h
    dashed(d, (390, 410), (525, 410), RED, 2)
    arrow(d, (510, gy + 2), (510, 408), RED)
    arrow(d, (510, 408), (510, gy + 2), RED)
    d.text((530, 355), "耕深 h", font=font(22), fill=RED, anchor="lm")
    d.text((530, 382), "地表→沟底", font=font(16), fill=RED, anchor="lm")
    # 扰土带宽 b
    dashed(d, (190, 445), (190, 492), BLUE, 2)
    dashed(d, (470, 445), (470, 492), BLUE, 2)
    arrow(d, (192, 480), (468, 480), BLUE)
    arrow(d, (468, 480), (192, 480), BLUE)
    d.text((330, 505), "扰土带宽 b：松土区的水平宽度", font=font(20), fill=BLUE,
           anchor="mm")
    d.text((330, 560), "松土比原状土颜色浅、质地松，边界肉眼可辨", font=font(18),
           fill=INK, anchor="mm")
    d.text((330, 588), "h 用钢尺直接读；b 沿趟量 3-5 处取平均", font=font(18),
           fill=INK, anchor="mm")
    d.text((330, 616), "沟底草根：切断 / 拔起 / 翻埋，逐处记", font=font(18),
           fill=INK, anchor="mm")

    # ---------------- 右：侧视，入土角 ----------------
    d.text((950, 80), "侧视：沿行方向看，入土角在刀上量", font=font(24),
           fill=INK, anchor="mm")
    gy2 = 320
    d.rectangle([660, gy2, 1240, 640], fill=SOIL)
    d.line([(660, gy2), (1240, gy2)], fill=INK, width=3)
    d.text((1180, gy2 - 16), "地表", font=font(18), fill=INK, anchor="lm")
    # 刀面：尖端 T 在土里，上端 U 出地面；与地表交点 P
    T = (790, 410)
    U = (1010, 190)
    P = (880, gy2)
    d.line([T, U], fill=BLADE, width=10)                # 刀面
    d.line([U, (1062, 138)], fill=BLADE, width=14)      # 刀柄
    d.text((1030, 230), "刀面", font=font(20), fill=INK, anchor="lm")
    # 夹角弧：P→T 方向（左下）与地表向左方向之间
    d.arc([P[0] - 70, P[1] - 70, P[0] + 70, P[1] + 70], 135, 180, fill=RED,
          width=4)
    d.text((802, 352), "α", font=font(26), fill=RED, anchor="mm")
    d.text((950, 470), "入土角 α = 刀面与地表的夹角", font=font(22), fill=RED,
           anchor="mm")
    d.text((950, 505), "量角器 / 角度尺贴刀面，对地表读角；", font=font(18),
           fill=INK, anchor="mm")
    d.text((950, 533), "或侧拍一张照片，照片里以地表为基准量", font=font(18),
           fill=INK, anchor="mm")
    d.text((950, 575), "必须在实际耕深档位量：四连杆姿态随提刀高度变，", font=font(18),
           fill=INK, anchor="mm")
    d.text((950, 603), "提起状态的读数不算；断面切面若保形可作旁证", font=font(18),
           fill=INK, anchor="mm")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    im.save(OUT)
    print("saved:", os.path.abspath(OUT))


if __name__ == "__main__":
    main()