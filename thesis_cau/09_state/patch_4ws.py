# -*- coding: utf-8 -*-
"""按 specs/2026-09-09-4ws-steering-design.md §5 修订论文：滑移转向 → 4WS 阿克曼。"""
import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from pathlib import Path

CH = Path(__file__).resolve().parent.parent / '03_chapters'

# ---------- ch02 ----------
p = CH / 'ch02_draft.md'
t = p.read_text(encoding='utf-8')
reps = [
 ("整机由四轮独立驱动滑移转向底盘、三刀并行除草装置",
  "整机由四轮独立驱动-独立转向（4WD-4WS）底盘、三刀并行除草装置"),
 ("样机移动平台为四轮独立驱动滑移转向底盘。四轮由四台直流有刷电机经减速器独立驱动，电机端配置霍尔传感器用于轮速测量；转向不设转向机构，依靠左右侧轮速差实现滑移转向。底盘主要参数如表 2-2 所示。",
  "样机移动平台为四轮独立驱动-四轮独立转向（4WD-4WS）底盘。四轮由四台直流有刷电机经减速器独立驱动，电机端配置霍尔传感器用于轮速测量；四个车轮各由一路转向舵机独立偏转（舵机经 UART4 总线、19200 bps 指令驱动，带零位标定与转角限幅）。本文主作业模式采用全 4WS 方式，四轮转角按阿克曼（Ackermann）几何关系分配。底盘主要参数如表 2-2 所示。"),
 ("| 驱动方式 | 四轮独立驱动，滑移转向 |",
  "| 驱动/转向方式 | 四轮独立驱动（4WD）＋四轮独立转向（4WS，舵机×4，UART4 19200 bps） |"),
 ("滑移转向底盘结构简单、横向尺寸紧凑、原地转向能力强，适合窄行行间掉头与短地块作业；其缺点是松软地面上存在滑移率，转向动力学存在不确定性，该问题在第 4 章运动学建模与控制中处理。",
  "4WD-4WS 构型横向尺寸紧凑、转弯半径小，四轮转角独立可控，对窄行行间掉头与短地块作业适应性强；需要关注的是松软地面的滑移及转向舵机的响应品质，相关运动学建模与控制策略在第 4 章处理。需要说明的是，本项目前期方案曾将底盘误判为无转向机构的滑移转向构型并据此规划差速纠偏输出，后经实车固件源码核对确认四路转向舵机链路在位，本文统一修正为 4WS 阿克曼模型，该调整与开题报告中“四转向轮期望偏角”的设定一致。"),
 ("介绍四轮滑移转向移动平台及其半线控基础",
  "介绍四轮独立驱动-独立转向移动平台及其半线控基础"),
 ("导航输出采用左右侧轮速对", "导航输出采用四轮转角与轮速分配"),
]
for old, new in reps:
    if old in t:
        t = t.replace(old, new)
    else:
        print('ch02 skip(未命中):', old[:30])
p.write_text(t, encoding='utf-8')
print('ch02 done')

# ---------- ch04 ----------
p = CH / 'ch04_draft.md'
t = p.read_text(encoding='utf-8')
# 整节替换：从 "### 滑移转向运动学建模" 到 "### 横向偏差卡尔曼滤波估计"
m = re.search(r'### 滑移转向运动学建模.*?(?=### 横向偏差卡尔曼滤波估计)', t, re.S)
assert m, 'ch04 滑移转向小节未找到'
new_sec = """### 4WS 阿克曼运动学建模

底盘为四轮独立驱动-四轮独立转向（4WD-4WS）构型。作业速度低（小于 1 m/s），轮胎侧偏角可忽略，四个车轮绕同一瞬时转动中心（ICC）转动的阿克曼几何成立。设轴距为 [[SYM:L]]，前/后轮距为 [[SYM:B_f]]、[[SYM:B_r]]，取底盘中心等效转角 [[SYM:delta]]（左转为正），则绕 ICC 的后轴中心转弯半径为

[[EQ:R=\\frac{L}{\\tan\\delta}]]

四轮转角按阿克曼几何分配：前外轮与后轮（后轮反向偏转）分别为

[[EQ:\\delta_{fr}=\\arctan\\frac{L}{R+B_f/2},\\quad \\delta_{fl}=\\arctan\\frac{L}{R-B_f/2}]]

[[EQ:\\delta_{rl}=-\\arctan\\frac{L}{R-B_r/2},\\quad \\delta_{rr}=-\\arctan\\frac{L}{R+B_r/2}]]

各轮速度按其到 ICC 的转弯半径比例分配：

[[EQ:v_i=\\frac{R_i}{R}v,\\quad i\\in\\{fl,fr,rl,rr\\}]]

式中 [[SYM:R_i]] 为各轮转弯半径（前轮 [[SYM:sqrt((R-B_r/2)^2+L^2)]] 与 [[SYM:sqrt((R+B_r/2)^2+L^2)]]，后轮为 [[SYM:R-B_r/2]] 与 [[SYM:R+B_r/2]]）。导航控制帧（NAV2）下发的即为四轮目标转角与中心速度 [[SYM:v]]：车载固件将目标角经斜率限幅写入转向舵机，并按上式将中心速度映射为四轮目标转速，进入既有 PID 速度环。

松软地面的滑移使实际转弯半径偏离几何值，构成运动学参数不确定性，本文将其归入系统噪声由卡尔曼滤波吸收；同时固件利用转向角反馈实现转向失效检测（指令角与反馈角偏差超阈值持续超时即触发减速、提刀、停车），以覆盖舵机转向链路的特有故障面<待补充：转向阶跃响应标定数据>。

"""
t = t[:m.start()] + new_sec + t[m.end():]
t, npd = re.subn(r'横向控制采用 PD 控制律\[\[EQ:[^\]]*\]\]，经运动学映射为左右轮速对；',
    '横向控制采用 PD 控制律[[EQ:\\\\delta_c=K_p e+K_d \\\\dot{e}]]，PD 输出的中心等效转角 [[SYM:delta_c]] 经上节阿克曼几何分配为四轮目标转角与轮速；', t)
assert npd == 1, f'ch04 PD 句匹配 {npd} 次'
t = t.replace('本章建立了滑移转向运动学模型与横向偏差卡尔曼滤波估计方法',
              '本章建立了 4WS 阿克曼运动学模型与横向偏差卡尔曼滤波估计方法')
p.write_text(t, encoding='utf-8')
print('ch04 done')

# ---------- ch06 ----------
p = CH / 'ch06_draft.md'
t = p.read_text(encoding='utf-8')
reps = [
 ("完成四轮滑移转向移动平台的线控改造", "完成四轮独立驱动-独立转向（4WD-4WS）移动平台的线控改造"),
 ("建立滑移转向运动学模型与横向偏差卡尔曼滤波估计", "建立 4WS 阿克曼运动学模型与横向偏差卡尔曼滤波估计"),
 ("（2）滑移转向参数不确定性。松软地面滑移率变化影响运动学模型精度，后续可引入滑移率在线辨识或惯性测量单元融合。",
  "（2）转向执行链路品质约束。横向控制精度受转向舵机响应滞后与松软地面滑移的共同影响，后续将开展指令-反馈阶跃标定，并评估引入转向角反馈闭环与惯性测量单元融合的必要性。"),
]
for old, new in reps:
    assert old in t, 'ch06 NOT FOUND: ' + old[:30]
    t = t.replace(old, new)
p.write_text(t, encoding='utf-8')
print('ch06 done')

# ---------- 摘要（project_state） ----------
import json
sp = Path(__file__).resolve().parent.parent / '09_state' / 'project_state.json'
s = json.loads(sp.read_text(encoding='utf-8'))
s['thesis']['abstractZh'] = s['thesis']['abstractZh'].replace('四轮滑移转向底盘', '四轮独立驱动-独立转向（4WD-4WS）底盘')
s['thesis']['abstractEn'] = s['thesis']['abstractEn'].replace('four-wheel skid-steer chassis', 'four-wheel-drive, four-wheel-steer (4WD-4WS) chassis')
sp.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding='utf-8')
print('abstract updated')
