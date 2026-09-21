# -*- coding: utf-8 -*-
"""把"整车尺寸实测表"的判定变成算式，避免量完还是各人自己解释一遍。

背景（2026-09-21 codex 复审 R3）：`ch02:14` 要求整机宽 ≤60 cm，而 deck 第 7 页与
`计划:11` 说"跨 4 行、清 3 条草带"；按行距 30~40 cm，3 条带中心跨 2s=60~80 cm，
加刀宽必超 60 cm。两个数不可能同时对——谁对取决于卷尺（见 docs/整车尺寸实测表_20260921.md）。

用法：
    python tools/geometry_check.py                      # 用"文档口径"跑一遍，看矛盾在哪
    python tools/geometry_check.py --row-pitch 35 --body-width 58 --knife-width 25 \
           --slide-travel 30 --actuator-travel 20 --knife-lift 20 --clearance 10

只做几何与时间换算，不猜任何未实测的值：没给的量一律按"未测"报，不补默认数。
"""
import argparse

# 文档口径（不是实测）：仅用于"跑一遍看矛盾"，不作为结论
DOC_ROW_PITCH = 35.0        # Hw-19 现场确认 30~40 cm，取中值
DOC_BODY_WIDTH_LIMIT = 60.0  # ch02:14 整机宽度不大于 60 cm
DOC_KNIFE_WIDTH = 25.0       # 弹齿刀组登记 250 mm 五齿；鸭掌铲未登记
DOC_SLIDE_TRAVEL = 30.0      # ch02:117 是 300 mm 导轨，行程未实测（deck 第 8 页把它当行程用）
ACTUATOR_SPEED_CM_S = 1.0    # 台账 Hw-9：电推杆 10 mm/s


def required_outer_span(row_pitch_cm, knife_width_cm, bands=3, side_clearance_cm=0.0):
    """n 条等距草带要各放一把刀时，最外两把刀外缘之间的最小跨度。"""
    if row_pitch_cm <= 0 or bands < 1:
        raise ValueError('行距与带数必须为正')
    return (bands - 1) * row_pitch_cm + knife_width_cm + 2 * side_clearance_cm


def band_capacity(body_width_cm, row_pitch_cm, knife_width_cm):
    """这台宽度的车，最多能同时把几把刀放进几条等距草带。"""
    if row_pitch_cm <= 0 or knife_width_cm <= 0:
        raise ValueError('行距与刀宽必须为正')
    return int((body_width_cm - knife_width_cm) // row_pitch_cm) + 1


def traffic_mode(body_width_cm, row_pitch_cm):
    """行走约束（与"够不够宽去作业"是两件事）：车宽超过行距就意味着要跨着作物行走。"""
    if body_width_cm <= row_pitch_cm:
        return ('in_band', 0)
    return ('straddle_rows', int(round(body_width_cm / row_pitch_cm)) - 1)


def candidate_configs(row_pitch_cm, body_width_cm, knife_width_cm, max_bands=4):
    """列出"清 N 条带"每种口径需要多宽，以及当前车宽够不够。

    判据只有一条：要 N 把刀各落进一条等距带，最外两把刀中心相距 (N-1)s，
    所以车宽至少要 (N-1)s + 刀宽。够不够是几何问题，不解释成"能不能通过"。
    """
    out = []
    for bands in range(1, max_bands + 1):
        need = required_outer_span(row_pitch_cm, knife_width_cm, bands)
        mode, rows = traffic_mode(need, row_pitch_cm)
        note = '车体走在带内' if mode == 'in_band' else '需跨 %d 行（轮/车体压在作物行上）' % rows
        out.append(('%d 条带' % bands, need, body_width_cm >= need, note))
    return out


def slide_reach_verdict(row_pitch_cm, slide_travel_cm, guard_band_cm=0.0, safety_cm=0.0):
    """中间刀横移够不够：要能从带中心偏到保护带边缘之外。"""
    need = row_pitch_cm / 2.0 + guard_band_cm + safety_cm
    return {'need_cm': round(need, 1), 'have_cm': slide_travel_cm,
            'ok': slide_travel_cm >= need}


def knife_lift_rate(actuator_speed_cm_s, actuator_travel_cm, knife_lift_cm):
    """推杆位移 ≠ 刀尖位移：用实测传动比换算刀尖提升速度（R7）。"""
    if actuator_travel_cm <= 0 or knife_lift_cm <= 0:
        return None                     # 没测 M10 就不算，不给默认传动比
    ratio = knife_lift_cm / float(actuator_travel_cm)
    return actuator_speed_cm_s * ratio


def lift_time_s(target_clearance_cm, knife_rate_cm_s):
    if not knife_rate_cm_s:
        return None
    return target_clearance_cm / knife_rate_cm_s


def report(row_pitch, body_width, knife_width, slide_travel, guard_band,
           actuator_travel, knife_lift, clearance):
    L = []
    L.append('行距 s=%.1f cm｜整机外廓宽 W=%.1f cm｜刀宽=%.1f cm' % (
        row_pitch, body_width, knife_width))
    L.append('')
    cap = band_capacity(body_width, row_pitch, knife_width)
    mode, rows = traffic_mode(body_width, row_pitch)
    L.append('【这台车】最多同时把 %d 把刀放进 %d 条等距草带；行走方式：%s' % (
        cap, cap, '车体走在带内' if mode == 'in_band' else '需跨 %d 行（压在作物行上）' % rows))
    L.append('')
    L.append('【判定 1】"清 N 条带"每种口径需要的最小车宽：')
    for name, need, ok, note in candidate_configs(row_pitch, body_width, knife_width):
        L.append('   %-8s 需 ≥ %5.1f cm  %s  —— %s' % (name, need, '够' if ok else '不够', note))
    L.append('')
    L.append('【判定 2】中间刀滑台横移够不够：')
    if slide_travel is None:
        L.append('   行程未实测（M8）→ 不下结论；deck 第 8 页"300 mm 行程"是导轨长度，不是行程')
    else:
        v = slide_reach_verdict(row_pitch, slide_travel, guard_band)
        L.append('   需 %.1f cm，实有 %.1f cm → %s' % (
            v['need_cm'], v['have_cm'], '够' if v['ok'] else '不够，主动对行覆盖不到'))
    L.append('')
    L.append('【判定 3】急停提刀时间（推杆位移 ≠ 刀尖位移）：')
    if not actuator_travel or not knife_lift:
        L.append('   传动比未实测（M10）→ 不给"抬刀几秒"这种数；10 mm/s 是推杆速度，不是刀具离地速度')
    else:
        rate = knife_lift_rate(ACTUATOR_SPEED_CM_S, actuator_travel, knife_lift)
        L.append('   刀尖提升速率 %.2f cm/s → 离土 %.1f cm 需 %.1f s' % (
            rate, clearance, lift_time_s(clearance, rate)))
    return '\n'.join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--row-pitch', type=float, default=DOC_ROW_PITCH)
    ap.add_argument('--body-width', type=float, default=DOC_BODY_WIDTH_LIMIT)
    ap.add_argument('--knife-width', type=float, default=DOC_KNIFE_WIDTH)
    ap.add_argument('--slide-travel', type=float, default=None)
    ap.add_argument('--guard-band', type=float, default=0.0)
    ap.add_argument('--actuator-travel', type=float, default=None)
    ap.add_argument('--knife-lift', type=float, default=None)
    ap.add_argument('--clearance', type=float, default=10.0)
    a = ap.parse_args()
    print(report(a.row_pitch, a.body_width, a.knife_width, a.slide_travel, a.guard_band,
                 a.actuator_travel, a.knife_lift, a.clearance))


if __name__ == '__main__':
    main()
