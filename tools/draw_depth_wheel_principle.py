# -*- coding: utf-8 -*-
"""Two-panel schematic: what the depth wheel actually does on this machine.

Left  = no wheel: the blade hangs from a toolbar at a FIXED world height, so its depth below
        the surface changes with every bump and dip (bump -> deeper, dip -> misses).
Right = with wheel: wheel and blade are one rigid body (刀柄1/刀柄2), the wheel rides the
        surface, so the blade stays a fixed distance below the CONTACT POINT everywhere.

Numbers are illustrative (30 mm set depth, +35/-25 mm ground), not measurements. The mechanism
is the one written in docs/执行机构装配拓扑_20261016.md §3 and ch02 §被动限深仿形机构设计.

CAUTION (2026-11-12, 台账 Hw-39): the author now says the passive depth-limit profiling may not
exist on this machine ("被动限深仿形可能也不存在，应该要靠电推杆调节入土深度"), and the thesis
wording has been changed to "depth set by the electric pusher stroke". The right-hand panel below
therefore rests on a premise that is NOT confirmed. Keep the script and the PNG (they record the
earlier design reading), but do NOT use this figure as thesis/report evidence until the author
confirms on the machine whether the wheel actually rides the ground and constrains depth.

UPDATE (2026-11-12 later, same ledger row, Hw-39 closed): the author has now ruled "仿形轮我觉得
很难起作用，因为电推杆断电即停，可以控制深度，靠电推杆行程控制吧" -- depth is set by the electric
pusher stroke and the profiling wheel is treated as NOT participating in depth limiting. This is
a design ruling (based on his verified power-off-stops fact, Hw-36), not a measurement that the
wheel never touches the ground. The right-hand panel's premise is therefore rejected by ruling;
the script and PNG stay as a historical record only, never as thesis/report evidence.

Usage: python -B tools/draw_depth_wheel_principle.py
"""
import math
import os

from PIL import Image, ImageDraw, ImageFont

OUT = os.path.join("D:", os.sep + "ai work", "qoder", "cad_work", "cad_out",
                   "限深轮原理_对比.png")
FONT = "C:/Windows/Fonts/simhei.ttf"
W, H = 1280, 690
Y0 = 430.0          # image y of the flat ground line
SET = 30.0          # set depth, mm (illustrative)
R = 34.0            # wheel radius, px
STATIONS = (130.0, 330.0, 520.0)


def h(x):
    """Ground height above the flat line: a bump and a dip, in mm-as-px."""
    return 35.0 * math.exp(-((x - 330.0) / 80.0) ** 2) - 25.0 * math.exp(-((x - 520.0) / 80.0) ** 2)


def surf(x):
    return Y0 - h(x)


def text(d, xy, s, size=20, fill=(30, 30, 30), anchor="la"):
    d.text(xy, s, font=ImageFont.truetype(FONT, size), fill=fill, anchor=anchor)


def ground(d, x0, x1, ox):
    pts = [(x, surf(x - ox)) for x in range(int(x0), int(x1) + 1, 4)]
    d.polygon(pts + [(x1, H - 40), (x0, H - 40)], fill=(232, 214, 188))
    d.line(pts, fill=(120, 90, 60), width=3)


def blade(d, x, tip_y):
    """Duckfoot-ish sweep: horizontal cutting edge at tip_y, short shank above."""
    d.polygon([(x - 30, tip_y - 12), (x + 30, tip_y - 12), (x + 12, tip_y), (x - 12, tip_y)],
              fill=(90, 90, 95))
    d.rectangle([x - 5, tip_y - 60, x + 5, tip_y - 12], fill=(90, 90, 95))


def depth_arrow(d, x, y_surf, y_tip, label, colour):
    d.line([(x + 46, y_surf), (x + 46, y_tip)], fill=colour, width=3)
    for yy, s in ((y_surf, 1), (y_tip, -1)):
        d.polygon([(x + 46, yy), (x + 41, yy + 8 * s), (x + 51, yy + 8 * s)], fill=colour)
    text(d, (x + 56, (y_surf + y_tip) / 2 - 12), label, 22, colour)


def panel(d, ox, with_wheel):
    x0, x1 = ox + 30, ox + 610
    ground(d, x0, x1, ox)
    if not with_wheel:
        d.rectangle([x0, 120, x1, 136], fill=(150, 150, 155))
        text(d, (x0 + 6, 96), "刀梁高度固定（推杆停在哪就是哪）", 19, (70, 70, 75))
    for i, sx in enumerate(STATIONS):
        x = ox + sx
        g = surf(sx)
        if with_wheel:
            tip = g + SET                      # fixed distance below the contact point
            hub = g - R
            d.ellipse([x - R, hub - R, x + R, hub + R], outline=(60, 60, 65), width=5)
            d.ellipse([x - 6, hub - 6, x + 6, hub + 6], fill=(60, 60, 65))
            d.line([(x, hub), (x, tip - 55)], fill=(60, 60, 65), width=7)   # rigid 刀柄2->刀柄1
            d.line([(x - 70, 150), (x, hub)], fill=(150, 150, 155), width=5)  # swinging arm
            depth_arrow(d, x, g, tip, "30", (0, 120, 60))
        else:
            tip = Y0 + SET                     # fixed WORLD height
            d.rectangle([x - 5, 136, x + 5, tip - 55], fill=(150, 150, 155))
            depth_arrow(d, x, g, tip, "%d" % round(SET + h(sx)), (190, 40, 40))
        blade(d, x, tip)
    if with_wheel:
        text(d, (x0 + 6, 96), "轮踩地、铲跟轮：轮—刀距离是结构固定的", 19, (0, 100, 50))
        text(d, (x0 + 6, 150), "斜杆＝四连杆，只负责让它能上下摆", 17, (110, 110, 115))
    else:
        text(d, (x0 + 6, 150), "地面鼓起来＝铲更深，凹下去＝铲空", 17, (150, 60, 60))


def main():
    im = Image.new("RGB", (W, H), (250, 250, 250))
    d = ImageDraw.Draw(im)
    text(d, (30, 24), "没有限深轮：入土深度跟着地面走", 26, (150, 40, 40))
    text(d, (670, 24), "有限深轮：深度＝轮接地点到刃口那段固定距离", 26, (0, 100, 50))
    panel(d, 0, False)
    panel(d, 640, True)
    d.line([(640, 60), (640, H - 60)], fill=(200, 200, 200), width=2)
    text(d, (30, H - 56), "示意数字：设定耕深 30、地面鼓 +35 / 凹 -25（毫米）。机构关系按实物装配：",
         17, (90, 90, 90))
    text(d, (30, H - 30), "推杆—四连杆—刀柄1（焊铲）—刀柄2—限深轮，轮与铲同一个刚体；弹簧另管撞障退让。",
         17, (90, 90, 90))
    im.save(OUT)
    print(OUT)


if __name__ == "__main__":
    main()
