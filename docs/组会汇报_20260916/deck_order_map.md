# 组会汇报 deck 页面清单与溯源表（2026-09-16，第 3 版）

- 交付物：`组会汇报_纯视觉芍药行间除草机器人_20260916.pptx`（17 页，16:9，全可编辑）
- 生产路线：**Route C 务实回退**；本表由 `pragmatic_edit_plan.json` + `paper_analysis.json` 自动生成，不与 deck 脱钩
- 校验：`validate_paper_analysis.py` passed；`validate_pragmatic_fallback_pptx.py` passed（0 issues）；PowerPoint COM 导出 17 张 PNG 逐页目视
- 第 3 版变更：**按汇报人要求删除全部 13 处页底红字 takeaway**；原红字承担的两处限定词（纯函数复现、电流阈值须标定）折进 bullet 本体，口径边界只保留在本表『口径边界』列

## 展示图清单

**全 deck 无任何展示图**（17 页 `figure_count` 合计 0）。分割实际输出、导航线叠加、整机照片由汇报人现场展示。下表『溯源记录』不是展示图，是每个数字的出处登记。

| 页 | 导航段 | 版式 | 标题（结论式） | 证据链 | 关键数字的溯源记录 | 口径边界（口头也不可怕，但不可越） |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 立题与约束 | cover | 纯视觉芍药行间除草机器人 | — | — | — |
| 2 | 立题与约束 | text | 行间除草是芍药管理的劳力与成本瓶颈 | e_labor | f_labor: ch01_draft.md 第8行 人工除草成本；f_agron: ch02_draft.md 第14、18行；ch05:8 | 成本数字的文献出处尚未核验，汇报时按背景陈述不作定量论据 |
| 3 | 立题与约束 | summary | 农艺约束框定了样机的设计边界 | e_agron | f_agron: ch02_draft.md 第14、18行；ch05:8；f_frames: avi_frames/ 295 张 1920x1080 田间抽帧 + data/calib_params.npz | 三项均为设计目标值，未登记的项必须标待实测，不能补常识值 |
| 4 | 除草机构选型 | text | 八类除草机构逐个筛，六类被排除 | e_screen | f_table23: ch02_draft.md 第86-101行 表2-3 八类除草机构机理与适用性；f_decisions: 决策依据说明.md D2/D4/D6（第17-18、32-33、43-46行）；D8（第58行）已过时 | 商品机型与中文核心期刊机具文献缺失，筛选覆盖面有限，需说明为针对性检索 |
| 5 | 除草机构选型 | comparison | 入选两类：鸭掌铲主选，弹齿作对比 | e_pick | f_table23: ch02_draft.md 第86-101行 表2-3 八类除草机构机理与适用性；f_actuator: 参数差异台账.md Hw-9 第46行 电推杆规格 | 鸭掌铲幅宽尚未登记，与弹齿 250mm 对比条件不对等，须先补齐 |
| 6 | 设计与控制原理 | process | 技术路线：单一相机到刀具位移的四段链路 | e_route | f_ipm: tools/morph_process.py 第189-193行；camera_calib.py 第55-73行；f_drive: network/nav_control.py 第134-155行 Ackermann4WS；pc/control.py DifferentialDrive | IPM 参数仍为硬编码，链路在真实秋季域上尚未闭环验证 |
| 7 | 设计与控制原理 | text | 跨 4 行作业，3 条草带由 2 侧刀加 1 中间刀清除 | e_arch | f_actuator: 参数差异台账.md Hw-9 第46行 电推杆规格；f_slide: 参数差异台账.md Hw-7/Hw-12 第44、50行；ch02:117 滑台参数；f_board: docs/大板实物标注.jpg（1080x1920，13 处编号标注） | 整机装配照片缺失，本节结构关系以现场展示为准 |
| 8 | 设计与控制原理 | comparison | 底盘粗纠偏加刀具细对行，比只纠底盘更可行 | e_twolevel | f_slide: 参数差异台账.md Hw-7/Hw-12 第44、50行；ch02:117 滑台参数；f_pid: pc/control.py 第27行起 PID；pc/main.py 第209行调用 | 滑台未接线，刀具一级的实际带宽与精度尚无实测 |
| 9 | 设计与控制原理 | text | 分割选 DeepLabV3+ | e_seg | f_miou: network/train_metric_log.csv 第76行（epoch 76），共 202 行 | 该值是夏季域验证集结果，秋季域指标尚未产出；最终 checkpoint 与划分需冻结 |
| 10 | 设计与控制原理 | text | 分割分数不等于能导航，评价要分三层 | e_seg_limit | f_miou: network/train_metric_log.csv 第76行（epoch 76），共 202 行；f_ipm: tools/morph_process.py 第189-193行；camera_calib.py 第55-73行 | 导航线横向误差与失效分层的真值还未标，三层里只有第一层有数 |
| 11 | 设计与控制原理 | process | 行墙提取分远近两场，三条目标线要分开 | e_navline | f_ipm: tools/morph_process.py 第189-193行；camera_calib.py 第55-73行；f_frames: avi_frames/ 295 张 1920x1080 田间抽帧 + data/calib_params.npz | 单墙回退仍是粗偏移，低机位标定未做，秋季帧上的有效性未测 |
| 12 | 设计与控制原理 | text | 轨迹跟踪用 PD 加横向速率阻尼 | e_track | f_drive: network/nav_control.py 第134-155行 Ackermann4WS；pc/control.py DifferentialDrive | 未台架验证；阿克曼几何是实现细节不作创新点，不得称已实现四轮转向自主控制 |
| 13 | 设计与控制原理 | text | 中间刀还不能叫闭环：刀到位了，相机看不出来 | e_toolctrl | f_pid: pc/control.py 第27行起 PID；pc/main.py 第209行调用；f_proto_tool: common/protocol.py 第109-111行 pack_tool(offset_mm, lift) | 复现是纯函数结果，不证明整车行为；刀位反馈通路目前不存在 |
| 14 | 设计与控制原理 | summary | 升降管三梁、横移管中间刀，两套机构 | e_lift | f_actuator: 参数差异台账.md Hw-9 第46行 电推杆规格；f_slide: 参数差异台账.md Hw-7/Hw-12 第44、50行；ch02:117 滑台参数；f_board: docs/大板实物标注.jpg（1080x1920，13 处编号标注） | 电推杆接入方式仍待继电器板实物确认，滑台未接线 |
| 15 | 进土深度问题 | text | 开放问题：刀上发生了什么，机器不知道 | e_depth | f_lift_bits: retrofit.c 第12行与第244-258行 apply_outputs；f_proto_tool: common/protocol.py 第109-111行 pack_tool(offset_mm, lift)；f_limits: retrofit.c 第14行注释与第275-281行 stepper_update | 不得写成定深精度问题，也不得声称电流硬件已覆盖推杆回路 |
| 16 | 进土深度问题 | summary | 分两层解：先机械保机，再电流辨草 | e_depthfix | f_decisions: 决策依据说明.md D2/D4/D6（第17-18、32-33、43-46行）；D8（第58行）已过时；f_actuator: 参数差异台账.md Hw-9 第46行 电推杆规格 | 机械卸载结构未设计；电流判据在未标定前不得称可用 |
| 17 | 小结与讨论 | closing | 请各位老师同学批评指正 | — | — | — |

## 讲这页时要挡住的反问

- **第 3 页**：行距 30~40 cm、坡地 0~15° 为汇报人 09-16 现场确认值，与论文 `ch02:14` 的 30~60 cm、5~15° 冲突；按事实权威序以现场值为准，论文待改（台账 Hw-19）。
- **第 4-5 页**：为什么没有第三种刀 → 表 2-3 六种排除理由各自成立，ch05 组1 既定对比就是鸭掌铲 vs 弹齿；加第三种会同时改刀头与控制两个变量，归因不清。
- **第 8 页**：两级纠偏做了吗 → 没有，滑台未接线，本页是分工设计（proposed），实测排春季。
- **第 12 页**：你不是四轮转向吗 → 硬件具备该能力，当前 AUTO 只用轮速差；能力／拟用模式／已运行模式三者分开说。
- **第 13 页**：刀移过去图像偏差为什么不变 → 相机在车架上，量的是行相对车；这就是还不能叫闭环的原因。50 mm 限幅那组数字是**纯函数复现**，被问到必须说明不是整车实测。
- **第 15-16 页**：论文里不是写了深度监测？→ `ch04:50` 的摆角传感器无任何硬件登记，属过度声明，本次不采用。电流判据在标定前不得称可用；板上 ACS712 登记对象是**行走电机回路**，是否覆盖推杆未跟线。


## 交付声明

```text
Image2 backend used: no
Delivery mode: pragmatic editable fallback accepted by user
Visual style: sample-deck-derived white/red/black academic grammar
Scientific visuals: none displayed（数据图与整机照片由汇报人现场展示）
Structural QA completed: yes（17 页，0 issues）
Render/layout QA completed: yes（PowerPoint COM 导出 17 张 PNG + 目视复核）
Editable elements may exist: yes
```
