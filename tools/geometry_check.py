# -*- coding: utf-8 -*-
"""把"整车尺寸实测表"的判定变成算式，避免量完还是各人自己解释一遍。

背景：codex 09-21 复审 R3 指出 `ch02:14` 的"整机宽 ≤60 cm"与实际车宽矛盾；同日汇报人
确认样机 2.15 m、调试车 3.25 m（台账 Hw-20）。

**09-21 第二次修正（复审 §3）**：我第一版在这里写了一条**不成立的推论** ——
"轮距跨 N 个行距 ⇒ 轮下压过 N−1 行作物"。这是错的：两轮之间包含若干作物行，与轮胎
接地条带压住作物，是两件事。反例：行距 38.2、轮距 191 = 5×38.2，轮中心在 ±95.5 cm 时
正好落在 76.4 与 114.6 两行中间，跨 5 个行距却一行都不压。判压苗还需要轮迹横向对齐、
胎宽、作物保护带、行驶偏差 —— 这些没测，本工具**不下压苗结论**。
同时修掉 `slide_reach_verdict` 的单位错误（拿总行程去比单侧需求）。

用法：
    python tools/geometry_check.py                       # 用"文档口径"跑一遍
    python tools/geometry_check.py --row-pitch 38.2 --body-width 215 --track 191 \
           --knife-width 25 --slide-travel 30 --residual 8 --envelope 12 \
           --actuator-travel 20 --knife-lift 20 --clearance 10

只做几何与时间换算。没给的量一律报"未测→不下结论"，不补默认值。
"""
import argparse

# 文档口径（不是实测）：仅用于"跑一遍看矛盾在哪"，不作为结论
DOC_ROW_PITCH = 35.0         # Hw-19 现场确认 30~40 cm，取中值
DOC_BODY_WIDTH = 215.0       # 台账 Hw-20：样机（真实车）外廓宽
DOC_TRACK = 191.0            # 车宽 − 24（汇报人给的换算）
DOC_KNIFE_WIDTH = 25.0       # 弹齿 250 mm 五齿；鸭掌铲 25 cm（09-21 确认，幅宽对等）
ACTUATOR_SPEED_CM_S = 1.0    # 台账 Hw-9：电推杆 10 mm/s


def required_outer_span(row_pitch_cm, knife_width_cm, bands=3, side_clearance_cm=0.0):
    """n 条等距草带各放一把刀时，最外两把刀外缘之间的最小跨度（包络，不含通过性判断）。"""
    if row_pitch_cm <= 0 or bands < 1:
        raise ValueError('行距与带数必须为正')
    return (bands - 1) * row_pitch_cm + knife_width_cm + 2 * side_clearance_cm


def band_capacity(body_width_cm, row_pitch_cm, knife_width_cm):
    """这台宽度的车，包络上最多能同时把几把刀放进几条等距草带。"""
    if row_pitch_cm <= 0 or knife_width_cm <= 0:
        raise ValueError('行距与刀宽必须为正')
    return int((body_width_cm - knife_width_cm) // row_pitch_cm) + 1


def track_span(track_cm, row_pitch_cm):
    """**只报事实**：轮距相当于几个行距，以及"轮子落在行间沟里"在几何上是否可能。

    furrow_aligned_possible 只说明：存在一个横向对齐方式，使轮中心落在行间。
    它**不等于**实车就是这么对齐的 —— 那要测轮迹相对作物行的实际位置与胎宽。
    """
    n = track_cm / float(row_pitch_cm)
    nearest = round(n)
    off = abs(n - nearest) * row_pitch_cm
    return {'pitches': round(n, 2), 'furrow_aligned_possible': off <= 5.0,
            'residual_off_cm': round(off, 1)}


def slide_reach_verdict(residual_cm, envelope_cm, slide_travel_cm, safety_cm=0.0):
    """中间刀横移够不够：**单侧需求 ×2 才是总行程**（09-21 修正单位错误）。

    需求 = 要补偿的底盘残余偏差 + 刀具安全作业区 + 余量。
    **不是**"半个行距 + 保护带"：保护带限制可用空间，不能未经论证变成必须越过的行程。
    """
    one_side = abs(residual_cm) + abs(envelope_cm) + abs(safety_cm)
    need_total = 2.0 * one_side
    return {'need_one_side_cm': round(one_side, 1), 'need_total_cm': round(need_total, 1),
            'have_total_cm': slide_travel_cm, 'ok': slide_travel_cm >= need_total}


def knife_lift_rate(actuator_speed_cm_s, actuator_travel_cm, knife_lift_cm):
    """推杆位移 ≠ 刀尖位移：用实测传动比换算刀尖提升速度（R7）。"""
    if actuator_travel_cm <= 0 or knife_lift_cm <= 0:
        return None                     # 没测 M10 就不算，不给默认传动比
    return actuator_speed_cm_s * (knife_lift_cm / float(actuator_travel_cm))


def lift_time_s(target_clearance_cm, knife_rate_cm_s):
    if not knife_rate_cm_s:
        return None
    return target_clearance_cm / knife_rate_cm_s


def report(row_pitch, body_width, track, knife_width, slide_travel, residual,
           envelope, actuator_travel, knife_lift, clearance):
    L = ['行距 s=%.1f cm｜外廓宽 W=%.1f cm｜轮距 T=%.1f cm｜刀宽=%.1f cm'
         % (row_pitch, body_width, track, knife_width), '']
    cap = band_capacity(body_width, row_pitch, knife_width)
    L.append('【包络】这台车最多同时放 %d 把刀进 %d 条等距草带' % (cap, cap))
    L.append('        （只是包络够不够；能否通过田块另说）')
    L.append('')
    L.append('【判定 1】"清 N 条带"需要多宽：')
    for bands in (1, 2, 3, 4):
        need = required_outer_span(row_pitch, knife_width, bands)
        L.append('   %-8s 需 ≥ %5.1f cm  %s' % ('%d 条带' % bands, need,
               '够' if body_width >= need else '不够'))
    L.append('')
    t = track_span(track, row_pitch)
    L.append('【判定 2·只报事实，不判压苗】轮距 %.0f cm = %.2f 个行距；'
             % (track, t['pitches']))
    L.append('   若横向对齐到行间，最近整数对齐还差 %.1f cm → %s' % (
        t['residual_off_cm'],
        '几何上**可能**轮不压行' if t['furrow_aligned_possible'] else '整数对齐也差得多，需实测轮迹'))
    L.append('   ⚠️ 压不压苗还取决于：轮迹相对作物行的实际横向位置、胎宽、作物保护带、行驶偏差。'
             '这些未测 → **本工具不下压苗结论**（09-21 撤回旧推论）。')
    L.append('')
    L.append('【判定 3】中间刀横移（总行程 vs 单侧需求×2）：')
    if slide_travel is None or residual is None or envelope is None:
        L.append('   行程或"要补偿的残余偏差/作业区"未给 → 不下结论；'
                 'deck 第 8 页"300 mm 行程"是导轨长度，不是行程')
    else:
        v = slide_reach_verdict(residual, envelope, slide_travel)
        L.append('   单侧需 %.1f cm → 总行程需 %.1f cm，实有 %.1f cm → %s' % (
            v['need_one_side_cm'], v['need_total_cm'], v['have_total_cm'],
            '够' if v['ok'] else '不够'))
    L.append('')
    L.append('【判定 4】急停提刀时间（推杆位移 ≠ 刀尖位移）：')
    if not actuator_travel or not knife_lift:
        L.append('   传动比未实测（M10）→ 不给"抬刀几秒"这种数；10 mm/s 是推杆速度')
    else:
        rate = knife_lift_rate(ACTUATOR_SPEED_CM_S, actuator_travel, knife_lift)
        L.append('   刀尖提升速率 %.2f cm/s → 离土 %.1f cm 需 %.1f s'
                 % (rate, clearance, lift_time_s(clearance, rate)))
    return '\n'.join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--row-pitch', type=float, default=DOC_ROW_PITCH)
    ap.add_argument('--body-width', type=float, default=DOC_BODY_WIDTH)
    ap.add_argument('--track', type=float, default=DOC_TRACK)
    ap.add_argument('--knife-width', type=float, default=DOC_KNIFE_WIDTH)
    ap.add_argument('--slide-travel', type=float, default=None)
    ap.add_argument('--residual', type=float, default=None, help='要补偿的底盘残余偏差 cm')
    ap.add_argument('--envelope', type=float, default=None, help='刀具安全作业区 cm')
    ap.add_argument('--actuator-travel', type=float, default=None)
    ap.add_argument('--knife-lift', type=float, default=None)
    ap.add_argument('--clearance', type=float, default=10.0)
    a = ap.parse_args()
    print(report(a.row_pitch, a.body_width, a.track, a.knife_width, a.slide_travel,
                 a.residual, a.envelope, a.actuator_travel, a.knife_lift, a.clearance))


if __name__ == '__main__':
    main()
