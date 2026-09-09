# 全 4WS 转向改造设计(固件 / 算法 / 协议 / 论文)

> 日期:2026-09-09
> 状态:设计稿,待作者复核
> 工作区:zcode(唯一开发区;论文改动同步至 chucao_prj 的 thesis_cau)
> 前置:v0.8/v0.9 方案 §3.1(已定论:按实车固件为准 → 真 4WD-4WS);作者已选定主工作模式 = **全 4WS**(四轮独立转角按 Ackermann 几何分配)
> 证据:`firmware/大车proj/大车/USER/main.c:519-532` 存在 `send_angle(1..4)` 四路转向舵机链路;AUTO 模式 `angle[]=0` 锁死走差速,即"有转向机构而不用"。

---

## 0. 问题定义

三层各错各的:

1. **硬件**:实车为 4WD-4WS(UART4 @19200 舵机总线,四轮独立偏转,有零位标定 `wheel_Angle_correct[]` 与转角限幅 `flag_steer_limit`)。无争议。
2. **代码**:固件 AUTO 把 `angle[0..3]` 强制清零(差速);PC 端 `network/nav_control.py` 的 `Ackermann4WS.compute()` 按 4WS 几何输出却无处可去;v0.7 曾要求算法改差速输出(理由"无转向执行器"系事实错误,撤回)。
3. **论文**:chucao_prj `thesis_cau` ch02"转向不设转向机构"、ch04 滑移转向运动学、D8"实车没有转向轮偏转执行器"——与开题承诺(四转向轮期望偏角)冲突,答辩裂缝。

## 1. 协议:新增 NAV2(type 0x11)

- 帧格式不变(`0xA5 0x5A | len | type | seq | payload | crc16`),新增 `TYPE_NAV2 = 0x11`。
- payload(21 字节):`δ_fl, δ_fr, δ_rl, δ_rr`(f32le,rad,+左)、`v`(f32le,m/s)、`flags`(u8)。
- **旧 NAV(0x01)保留**为差速兼容模式:固件收到旧帧按左右轮速对处理(v0.7 语义),回放/仿真可渐进迁移。
- 合法域:|δ| ≤ `max_steer`(取舵机机械限幅,台架标定后写入配置,初值 0.35 rad);|v| ≤ 1.0 m/s。超限值由固件钳位并置 flags 错误位回 STATUS。
- **桥接端(RDK X5)零改动**:`vehicle/bridge.py` 对帧类型透明(仅校验后转发),NAV2 直接通过。顺带修正 `bridge.py`/`stream_pi.py` 注释中"Raspberry Pi"→"RDK X5"。

## 2. PC 算法(network/nav_control.py)

- `KalmanLateral`、`PDController` 不动;`Ackermann4WS.compute(steer_center, v)` 恢复为唯一出口(此前按 v0.7 要求改差速的步骤不再执行)。
- 出口链:`PD 输出 steer → Ackermann4WS.compute → pack_nav2(δ×4, v, flags)`。
- E-STOP/视觉丢失行为不变(停发 NAV2 → 固件 500 ms 看门狗接管)。
- `common/protocol.py` 增加 `TYPE_NAV2`、`pack_nav2/unpack_nav2` 及已知向量 pytest;旧 `pack_nav` 保留并标注 deprecated。

## 3. 固件(大车工程 + retrofit.c)

- **撤锁**:删除 `main.c:519-521` 的 AUTO `angle[]=0` 强制清零。改为:MODE_AUTO 下每周期把 NAV2 目标角经 **slew-rate 限幅**(复用既有 safety gate 的限速路径)写入 `angle[]`,由原 `send_angle` 链路下发;四轮速度目标由 `v` 按 Ackermann 内外侧差分配(`Ackermann4WS.compute` 已输出该分配),进现有 PID 速度环。
- **旧 NAV 兼容**:收到 0x01 时保持现行差速逻辑(不写 `angle[]`)。
- **转向失效检测(新增,4WS 特有故障面)**:利用现有 `AD_angle[4]` 反馈,`|反馈角 − 指令角| > 阈值`(初值 5°,台架标定)持续 >300 ms → 判转向失效 → 减速 + 提刀 + 停车,走既有降级路径;事件写入日志帧。
- 看门狗/ESTOP/心跳语义全部不变。

## 4. 台架验证顺序(目标:2026 年 11–12 月完成,勿压到 2027 年 1 月)

1. 四轮零位重标(`wheel_Angle_correct`),台架;
2. **指令-反馈阶跃测试**:±5°/±10° 阶跃,记录响应滞后、稳态误差、超差率——这是"舵机品质能否支撑横向偏差 ≤±5 cm"的判据,亦是退路触发条件;
3. NAV2 帧回放驱动台架联动(含转向失效注入:人为断一路舵机反馈);
4. 通过后才进整车联调;不达标即触发退路:作业模式降为"小角度转向 + 差速纠偏",论文如实写"车具备 4WS,本作业模式选择小角度转向",**严禁再写"无转向机构"**。

## 5. 论文(chucao_prj / thesis_cau,不依赖春季试验,可先行)

- ch02 平台节:"无转向机构"→ 4WD-4WS 参数表(舵机路数、UART4、转角范围);
- ch04 运动学小节:滑移转向 → 4WS Ackermann + ICC 几何推导(`nav_control.py` 注释内推导可作底稿),时延补偿推导不受影响;
- D8 决策记录按"结论/被否备选/理由/证据/推翻条件"格式重写(v0.7 版的"理由"列含事实错误,整条作废);
- 增加与开题"四转向轮期望偏角"承诺的呼应句,与 v0.8 §3.2 的"林下→大田"显式调整声明同节出现。

## 6. 完成定义

- pytest:NAV2 pack/unpack 已知向量、钳位、旧 NAV 兼容路径通过;
- 固件:撤锁后 Keil 0 错误;slew 限幅与转向失效检测有台架记录(阶跃曲线 + 失效注入视频/日志);
- 论文:ch02/ch04/D8 三处改毕,grep 全库无"滑移转向/无转向机构"残留(除显式调整声明)。
