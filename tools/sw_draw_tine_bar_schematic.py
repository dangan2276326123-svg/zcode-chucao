# -*- coding: utf-8 -*-
import io, math, os, sys
sys.path.insert(0, os.path.join('D:', os.sep+'ai work','qoder','tools'))
from PIL import Image, ImageDraw, ImageFont
from sw_build_tine import profile
W,H = 1400,900
im = Image.new('RGB',(W,H),'white'); d = ImageDraw.Draw(im)
F = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 20)
c30, s30 = math.cos(math.radians(30)), math.sin(math.radians(30))
SC = 1.5
def P(x,y,z):
    return (W/2 + (x - y)*c30*SC, H*0.42 + ((x + y)*s30 - z)*SC)
def box(x1,x2,y1,y2,z1,z2,fill=(235,235,235)):
    top=[P(x1,y1,z2),P(x2,y1,z2),P(x2,y2,z2),P(x1,y2,z2)]
    d.polygon(top, fill=fill, outline='black')
    for a,b in ((P(x1,y1,z2),P(x1,y1,z1)),(P(x2,y1,z2),P(x2,y1,z1)),(P(x2,y2,z2),P(x2,y2,z1))):
        d.line([a,b], fill='black', width=2)
    d.polygon([P(x1,y1,z1),P(x2,y1,z1),P(x2,y1,z2),P(x1,y1,z2)], fill=(210,210,210), outline='black')
    d.polygon([P(x2,y1,z1),P(x2,y2,z1),P(x2,y2,z2),P(x2,y1,z2)], fill=(225,225,225), outline='black')
# beam 500 x 40 x 12 ; flange 140 x 8 x 60 standing on beam
box(-250,250,-20,20,0,12)
box(-70,70,-4,4,12,72,(245,245,245))
prof = profile()
for i in range(11):
    x = -240 + i*48
    poly = [P(x, u, v+12) for u,v in prof]
    d.polygon(poly, fill=(250,250,250), outline='black')
    poly2 = [P(x+8, u, v+12) for u,v in prof]
    d.line(poly2+[poly2[0]], fill=(120,120,120), width=1)
    for k in (0, len(prof)//2):
        d.line([poly[k], poly2[k]], fill=(120,120,120), width=1)
d.text((30,20),'弹齿除草刀（整组参照）：500 幅宽夹排 + 11 齿 @48 + 后立安装板', fill='black', font=F)
d.text((30,52),'侧视每齿：直柄160 插入夹排 -> C 弯 R70x90 -> 工作段100 -> 凿尖26；条截面 6x8', fill=(60,60,60), font=F)
d.text((30,84),'安装板孔系照鸭掌铲快换座：4xM8 + 2 定位销（待对孔）；夹排实际需开 11 个 8.2x6.2 方孔', fill=(60,60,60), font=F)
im.save(os.path.join('D:', os.sep+'ai work','qoder','cad_work','cad_out','弹齿除草刀_示意_iso.png'))
print('saved')
