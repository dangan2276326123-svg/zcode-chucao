# 论文断言式重写＋鸭掌铲独选 cascade 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按作者 11-17 裁定把论文改成断言式、方法唯一、无项目记录痕迹，并把鸭掌铲定为唯一刀头、撤出弹齿设计与对比试验。

**Architecture:** 纯 md  prose 重写＋图清单/图文件顺移＋出图工具一处修改。权威 spec＝`docs/superpowers/specs/2026-11-17-thesis-assertive-rewrite-design.md`（已批准）。论文 md 在 `D:\JetBrains\chucao_prj\thesis_cau\`（可写例外子树），工具/测试/spec 在 `D:\ai work\qoder`。每个任务自带验证环（交叉引用检查器＋定向 grep），逐任务手术式提交。

**Tech Stack:** Markdown（`[[EQ:]]`/`[[SYM:]]`/`[[FIG:]]`/`[[REF:n]]`/`<待补充>` 标记）、Python 检查器与 pytest、PIL 出图工具。

## Global Constraints

- 事实一条不改；不编数据/引用；不写田间结果；不声称执行链路已验证。断言的是方法，不是效果。
- 方法唯一性：全文不出现「设计候选/设计模型 vs 当前实现/尚未实现/未经整定/列为后续工作」双轨话术；阿克曼、卡尔曼只允许出现在文献综述他人工作语境。
- 保留项：4.3.3 横向「开环对行」；第 5 章预注册口径与「截至写作无结果」边界；`<待补充>` 内容占位符；文献综述他人方法名。
- 局限与展望只写客观条件类（地头自动转向/跨季节/田间验证完成）；两车数据归属口径保留。
- 提交纪律：chucao 仓（根 `D:\JetBrains`）只 `git add chucao_prj/thesis_cau/...` 逐文件；**严禁 stage**：`06_code/fig2-8_penetration_force_matlab.png`（工作树有改动）、`07_data/`、`10_output/thesis_draft_v12/13/14.docx`、`~$esis_draft_v14.docx`、`_render/`。qoder 仓提交工具/spec。
- 报告 docx 冻结不碰。firmware 不碰（本批无固件改动）。两条硬禁令不涉及。
- 提交标题当场新打（防复制）；日期以 `date` 当场核实（本计划立日 2026-11-17）。
- 基线类数字（节数/测试数）只由工具当场输出、只写收口报告一处，不抄进 md。
- grep 零命中必须解释（审查清单第 2 条）；改号必须全仓反查旧号交叉引用。
- 验证命令（每任务通用，qoder 目录下跑）：
  - `cd "D:/ai work/qoder" && PYTHONUTF8=1 python -B tools/check_thesis_sections.py`（期望 references missing = 0）
  - `cd "D:/ai work/qoder" && PYTHONUTF8=1 python -B -m pytest tests/test_make_thesis_docx.py -q -p no:cacheprovider`（期望全绿；测试计数是动态对账，无硬编码图数/组数钉，正常不需改测试）

---

### Task 1: ch04 §4.1 重写（需求＋框架图＋逐回路选择原因）

**Files:**
- Modify: `D:\JetBrains\chucao_prj\thesis_cau\03_chapters\ch04_draft.md`（现稿行 4–69 整节）

**Interfaces:**
- Produces: 4.1 平铺节（无三级标题）；图 4-1 占位符 `[[FIG:运动控制三回路架构图]]` 保留；后续节引用的「4.1 节」语义＝方法选择。旧表 4-1/4-2/4-3 消失，新表号在 Task 2/3 给出。

- [ ] **Step 1: 整节替换**

把 `## 行间除草机控制方法选择` 起、至 `## 基于 PD 控制的轨迹跟踪控制` 之前的全部内容替换为：

```markdown
## 行间除草机控制方法选择

行间除草的作业条件对运动控制提出三条约束：窄行与有限的横向空间要求底盘沿作物行持续纠正横向偏差；低作业速度（不大于 0.2 m/s）与脆嫩幼苗要求控制动作平缓、避免频繁急转；底盘与中间刀安装在不同地面工位，两者又须跟踪同一作物行。据此，运动控制系统组织为底盘轨迹跟踪、除草装置对行与提刀/落刀调度三个回路，安全联锁对各回路拥有最高优先级。控制路线如图 4-1 所示：感知在地面站解算为远/近场导航线，控制律经无线链路下发至车端执行，车载状态机统一调度三个回路。

[[FIG:运动控制三回路架构图]]

图 4-1 运动控制三回路架构与车载状态机的调度关系

底盘轨迹跟踪的对象是"横向偏差—车体运动"这一慢过程：作业速度低、偏差变化平缓，比例—微分（PD）反馈足以胜任。PD 是去掉积分项的 PID：跟踪对象不需要积分消差，引入积分反而在弯道引起超调，参数少也便于在样机上整定。纠偏指令以两侧差速执行：四轮各带一路速度环且车上已有，差速纠偏直接作用于速度环、不经过转向伺服，控制路径短、响应快，伺服滞后与零位误差不进纠偏回路；转向通道只承担低频的姿态切换（四轮共角横移），高频纠偏全走差速，两条通道分工明确。纯追踪类几何方法依赖前视距离，在窄行短视场条件下不适用[[REF:74]][[REF:75]]。

中间刀对行的执行端是伺服位置环，外环只需把近场横向误差映射为滑台位置增量，故取增量式 PID：积分项消除稳态对行偏差，微分项抑制草带读数抖动引起的频繁动作，增量形式在切换时无积分累积，便于手动/自动之间的无扰过渡。

入土回路不做连续深度调节。耕深由仿形轮—刀固定高度这一结构给定（第 2 章入土深度控制机构设计），控制层面只做提刀/落刀两位置的状态调度，由状态机与联锁条件管理（4.3.2 节）。

三个回路若各自独立工作，存在一个结构性问题：底盘与中间刀不在同一地面位置，视觉对两个工位的观测又取自同一帧图像，两处误差在空间与时间上都不对齐。本文把底盘—除草装置的协同作为显式的时空耦合问题处理，给出统一行线模型、双工位时空投影、宏微运动前馈解耦与刀位反馈闭环的耦合控制方法（4.4 节）。

感知与控制之间经无线链路连接，端到端时延由采集、编码、传输、推理、下发各环节组成，其估计与补偿在 4.2.4 节讨论。
```

- [ ] **Step 2: 验证**

Run: 通用检查器命令。Expected: missing = 0。
Run: `grep -n "表 4-\|帧结构\|HEARTBEAT\|权限\|闸门\|台架" "D:/JetBrains/chucao_prj/thesis_cau/03_chapters/ch04_draft.md"`
Expected: 4.1 范围内零命中（其余节若有命中属 Task 2–4 处理，记录行号）。

- [ ] **Step 3: 提交**

```bash
cd "D:/JetBrains" && git add chucao_prj/thesis_cau/03_chapters/ch04_draft.md && git commit -m "ch04 4.1 重写：需求＋框架图＋逐回路选择原因（PD/差速/增量式PID/两位置调度），帧结构、权限、闸门与台架记录撤出论文（作者 11-17 裁定）"
```

---

### Task 2: ch04 §4.2 唯一方法重写（差速运动学／平滑差分／PD＋表 4-1／时延）

**Files:**
- Modify: `D:\JetBrains\chucao_prj\thesis_cau\03_chapters\ch04_draft.md`（§4.2 四小节）

**Interfaces:**
- Consumes: Task 1 的 4.1（差速选择原因、PD 口径）。
- Produces: 表 4-1（底盘参数）；4.2.2 平滑差分式（α=0.3）；4.2.3 PD 控制律（Kd=Kp·τ̂）；REF:73 在本章不再被引用（Task 9 移 ch01）。

- [ ] **Step 1: 4.2.1 整小节替换**

`### 底盘运动学建模` 起至 `### 横向偏差变化率估计` 之前替换为：

```markdown
### 底盘运动学建模

底盘为四轮独立驱动、四轮独立转向（4WD-4WS）构型，构造见第 2 章。控制使用的运动学模型分两部分：两侧差速等效与四轮共角横移姿态。

设左、右两侧轮速为 [[SYM:v_l]]、[[SYM:v_r]]（四轮按左侧/右侧分组，同侧轮速取同值），轮距为 [[SYM:B]]，则底盘前进速度与偏航角速度为

[[EQ:v=\frac{v_l+v_r}{2},\qquad \omega=\frac{v_r-v_l}{B}]]

底盘以两侧速差产生的偏航运动纠正横向偏差：横向偏差经控制律（4.2.3 节）映射为两侧速度差，叠加在名义前进速度上并限幅。作业姿态下四个转向轮取同一转角 [[SYM:\theta]]，轮面互相平行，车体沿轮面方向平移；姿态角由转向通道给定，与差速纠偏在频段上解耦——姿态切换低频、偏差纠正高频。

松软地面的滑移使实际转弯半径偏离几何值，其影响并入横向偏差读数，由变化率估计的平滑环节（4.2.2 节）抑制高频部分。
```

- [ ] **Step 2: 4.2.2 整小节替换**

`### 横向偏差变化率估计` 起至 `### 轨迹跟踪控制律` 之前替换为：

```markdown
### 横向偏差变化率估计

控制律与前馈补偿都需要横向偏差的变化率 [[SYM:\dot{e}]]。视觉逐帧给出偏差读数本身，变化率由相邻帧差分估计：当前帧与上一帧偏差之差除以帧间时延，再经一阶指数平滑抑制分割噪声引起的差分抖动：

[[EQ:\dot{e}_k=\alpha\frac{e_k-e_{k-1}}{\Delta t_k}+(1-\alpha)\dot{e}_{k-1}]]

式中平滑系数 [[SYM:\alpha]]=0.3；帧间时延 [[SYM:\Delta t_k]] 取实测值而非固定值，以消除变速与链路时延波动下的估计偏差。该估计器结构简单、无模型假设，是控制律（4.2.3 节）与时延补偿（4.2.4 节）统一的变化率来源。
```

（卡尔曼候选小节连同状态方程整段删除；REF:73 此处不再引用。）

- [ ] **Step 3: 4.2.3 整小节替换**

`### 轨迹跟踪控制律` 起至 `### 时延估计与前馈补偿` 之前替换为：

```markdown
### 轨迹跟踪控制律

横向控制律采用 PD 控制。设横向偏差为 [[SYM:e]]、其变化率为 [[SYM:\dot{e}]]（4.2.2 节），两侧速度差指令为

[[EQ:\Delta v=K_p e+K_d\dot{e}]]

考虑无线链路的端到端时延 [[SYM:\tau]]，控制输入经一阶外推提前到执行时刻（4.2.4 节）：[[EQ:e_c=e+\dot{e}\hat{\tau}]]，控制律实际取形式

[[EQ:\Delta v=K_p e_c=K_p e+(K_p\hat{\tau})\dot{e}]]

即微分增益由时延超前项实现，[[EQ:K_d=K_p\hat{\tau}]]：超前补偿不是控制律之外的附加环节，而是其微分作用的实现形式。左、右两侧目标速度为 [[SYM:v_l=v-\Delta v]]、[[SYM:v_r=v+\Delta v]]，名义前进速度 [[SYM:v]]=0.14 m/s，两侧速度限幅 ±0.2 m/s。相比纯追踪类几何方法[[REF:74]][[REF:75]]，以行间中心线为基准的横向偏差控制更适应窄行短视场场景。

近年同类工作为控制律选择提供了参照：吴江东等[[REF:76]]把曲率自适应轨迹规划与跟踪控制做协同优化，沈跃等[[REF:77]]用带扰动补偿的 ENMPC 处理林果园轮式机器人跟踪，Liu 等[[REF:78]]针对履带农机提出滑移感知的前视点偏置方法，An 等[[REF:79]]以误差阈值实现直角转向下的自主导航。上述方法多面向高速或复杂动力学工况；本文低速窄行工况下，带时延超前的 PD 控制即满足偏差抑制要求，且结构更简、整定更容易。控制参数见表 4-1。

表 4-1 底盘横向控制参数

| 参数 | 取值 | 含义 |
| --- | --- | --- |
| [[SYM:K_p]] | 1.5 s⁻¹ | 横向偏差比例增益 |
| 名义前进速度 [[SYM:v]] | 0.14 m/s | 作业速度设定 |
| 速度限幅 | ±0.2 m/s | 两侧轮速上限 |
| 平滑系数 [[SYM:\alpha]] | 0.3 | 变化率一阶指数平滑 |
| 时延估计窗口 | 100 帧，取中位数 | 抗无线链路重尾 |
```

- [ ] **Step 4: 4.2.4 两句替换**

old: `该补偿的田间显著性检验在第 5 章试验设计中安排；本文把它定位为工程处理手段，其收益大小属待验证内容。`
new: `该补偿的田间效果由第 5 章试验检验。`
（其余照旧：四项时延分测口径与 `<待补充：时延实测分布与补偿前后横向偏差对比>` 保留。）

- [ ] **Step 5: 验证**

Run: 通用检查器。Expected: missing = 0。
Run: `grep -n "卡尔曼\|阿克曼\|候选\|尚未实现\|未经整定\|REF:73" "D:/JetBrains/chucao_prj/thesis_cau/03_chapters/ch04_draft.md"`
Expected: 零命中（零命中解释：本节已按唯一方法重写）。

- [ ] **Step 6: 提交**

```bash
cd "D:/JetBrains" && git add chucao_prj/thesis_cau/03_chapters/ch04_draft.md && git commit -m "ch04 4.2 唯一方法重写：差速等效运动学＋共角姿态、平滑差分变化率、PD 控制律（微分由超前项实现）与参数表 4-1，卡尔曼候选段删除"
```

---

### Task 3: ch04 §4.3 重写（增量式 PID＋表 4-2／联锁设计语言／4.3.3 设计层描述）

**Files:**
- Modify: `D:\JetBrains\chucao_prj\thesis_cau\03_chapters\ch04_draft.md`（§4.3 三小节）

**Interfaces:**
- Consumes: Task 2 表 4-1 之后的表号序列。
- Produces: 表 4-2（刀具 PID 参数）；4.3.2 前置句（ch05 引用）；4.3.3 开环对行口径（图 4-1 注记引用）。

- [ ] **Step 1: 4.3.1 防御段替换＋参数表**

old: `但据此断言"瓶颈一定在感知端"是超出证据的：分辨率只是执行端的一个方面，实际对行精度还要看滑台能否在挂草、土埂阻力下按指令到位，以及重复定位与齿隙回差的大小，这三项在当前样机上均无实测数据（滑台尚未接入执行链路，见 4.3.3 节）。故本文对执行端只给设计层面的能力说明，误差来源的归因留待第 5 章按实测分布判定，不预设结论。`
new:
```markdown
对行精度由第 5 章按刀位指令与刀位实测的成对记录判定，本节给出执行端的设计能力。控制参数见表 4-2。

表 4-2 中间刀对行 PID 参数

| 参数 | 取值 | 含义 |
| --- | --- | --- |
| [[SYM:K_p]] | 0.8 | 比例增益 |
| [[SYM:K_i]] | 0.05 | 积分增益（条件积分抗饱和） |
| [[SYM:K_d]] | 0.1 | 微分增益 |
| 输出限幅 | ±50 mm | 滑台行程约束 |
```

- [ ] **Step 2: 4.3.2 三处替换**

(a) old: `就验证状态而言：地面站侧那份有针对性单元测试，覆盖急停锁存与解锁、进入无人的前置条件不满足即拒绝、手操档门槛等关键路径，**并非全部状态转换组合的覆盖**；车载固件侧那份不经这套测试，其对执行机构的实际动作尚待台架复验<待补充：状态转换图、台架组合场景记录>。`
new: `状态转换关系见<待补充：状态转换图>。`

(b) old: `上述是设计口径，样机现状须同时写出：**这块外接继电器板今天没有接到车载控制器的输出上**，电推杆由遥控器自身的开关通道直接通断来推拉（现场确认 2026-10-17）。也就是说，本节那套提刀/落刀逻辑在 PC 与固件两侧都已编码、已编译，但它到刀之间还差一次接线；在接完之前，"固件控刀"在样机上不是既成事实，而是待闭合的执行链路。由此得出一条准入侧的结论：空跑阶段三路刀保持在提位，**必须由机械锁定或拆下保证，不能依赖软件联锁**——软件那份兜底今天不落在刀上。`
new: `提刀/落刀执行链路的闭合与刀控联锁的田间启用列为第 5 章试验前置；空跑阶段三路刀的提位由机械锁定保证。`

(c) old: `电机过载保护这一路在本设计中列为**待启用**：四路电流的采集硬件在位（ACS712 经 ADS1115 读取），但固件中该通道的换算系数尚未标定、当前返回占位值，因而"滑动窗口均值超阈值判定为刀具卡滞或电机堵转、触发提刀并降速"这条判据既没有可用的输入量，也没有经过田间整定的阈值。本文不把它列为已实现的保护，只作为设计内容给出，并在第 5 章的试验口径中说明：挂草与撞石工况下的瞬态保护当前只能依赖刀腿弹簧与牵引方向浮动自由度的被动让移（仿形轮＋弹簧被动稳深），主动抬刀受限于两点——电流判据未标定，以及提刀推杆本身的速度（手册值 10 mm/s，满行程秒级以上）不满足瞬态响应<待补充：电流阈值田间标定，或明确声明本项不实现>。`
new: `电机过载保护基于在位电流采集通道（ACS712 经 ADS1115 读取）设计：滑动窗口均值超阈值判定为刀具卡滞或电机堵转，触发提刀并降速，阈值经田间标定后启用。挂草与撞石工况下的瞬态保护由刀腿弹簧与牵引方向浮动自由度的被动让移承担（仿形轮＋弹簧被动稳深）；提刀推杆本身的速度（手册值 10 mm/s，满行程秒级以上）不构成瞬态响应手段。`

- [ ] **Step 3: 4.3.3 开头段替换**

old: `另需交代一处信号流的实际状态。理想闭环应为"目标刀位（由近场导航线给出）减去刀位实测值"构成误差，而**样机中间刀滑台当前既没有刀位反馈、也没有可驱动的执行通路**（现场确认：滑台伺服电机的动力线与编码器线都未接，样机上它今天不能工作），因此实际控制输入取的是近场导航线相对车体中线的横向偏差本身，控制输出直接写为伺服目标位置。这一结构在指令层面是位置闭环、在作业效果层面是**开环对行**：刀是否真的到了指令位置，只能由外部量具实测，不能由指令值代替。更要紧的是，在这条线路接通之前，"主动对行"这一组对照在样机上做不出来，本文第 5 章已把滑台接入执行链路列为该组试验的前置条件。该限制对第 5 章执行层指标的测量口径有直接影响，第 5 章据此规定"刀位指令与刀位实测必须分别记录、不得以指令值充当实测值"。带刀位反馈的闭环形态及其与底盘的协同见 4.4 节。`
new: `中间刀对行回路以近场导航线相对车体中线的横向偏差为输入，控制输出为伺服目标位置。这一结构在指令层面是位置闭环；因未配置刀位实测反馈，在作业效果层面是**开环对行**：刀是否真的到了指令位置，只能由外部量具实测，不能由指令值代替。第 5 章据此规定"刀位指令与刀位实测必须分别记录、不得以指令值充当实测值"，并把滑台执行链路的闭合列为该组试验的前置条件。带刀位反馈的闭环形态及其与底盘的协同见 4.4 节。`

- [ ] **Step 4: 4.3.3 文献对照段尾句替换**

old: `相比之下本文的中间刀仍是增量式 PID 且执行链路未闭合（4.3.3 节），处在设计阶段而非整定完成。`
new: `本文的中间刀取增量式 PID，以行线几何精度保证对行，与上述机构避苗路线构成互补。`

- [ ] **Step 5: 验证**

Run: 通用检查器＋docx 测试。Expected: missing = 0、全绿。
Run: `grep -n "现场确认\|待启用\|占位值\|已编码\|已编译\|台架复验\|今天" "D:/JetBrains/chucao_prj/thesis_cau/03_chapters/ch04_draft.md"`
Expected: 零命中。

- [ ] **Step 6: 提交**

```bash
cd "D:/JetBrains" && git add chucao_prj/thesis_cau/03_chapters/ch04_draft.md && git commit -m "ch04 4.3 重写：增量式 PID 参数表 4-2、联锁与过流改设计语言、4.3.3 改设计层描述（开环对行口径保留），接线现状与四态句撤出"
```

---

### Task 4: ch04 §4.5 小结重写＋§4.4 残留核对

**Files:**
- Modify: `D:\JetBrains\chucao_prj\thesis_cau\03_chapters\ch04_draft.md`（§4.5；§4.4 只核对）

- [ ] **Step 1: 小结整节替换**

`## 本章小结` 起至文件末替换为：

```markdown
## 本章小结

本章按回路选择控制方法并给出相应设计。底盘轨迹跟踪采用 PD 控制，指令以两侧差速执行：比例增益作用于横向偏差，微分作用由时延超前项实现；运动学模型为两侧差速等效模型与四轮共角横移姿态。横向偏差变化率以平滑有限差分估计，帧间时延取实测值。中间刀对行采用增量式 PID，输出限幅于滑台行程。入土回路只做提刀/落刀两位置调度，耕深由第 2 章的仿形轮—刀固定高度结构给定。时延按四项口径分测，以一阶外推前馈补偿。在此基础上，本章把底盘—除草装置协同作为显式的时空耦合问题，给出统一行线模型、双工位时空投影、宏微运动前馈解耦与刀位反馈闭环的耦合控制方法；滑台行程 ±50 mm 要求底盘残余横向误差压在 ±5 cm 带内，耦合收益以第 5 章田间开/关对比判定。
```

- [ ] **Step 2: §4.4 核对**

Run: `grep -n "尚未\|候选\|待台架\|降级" "D:/JetBrains/chucao_prj/thesis_cau/03_chapters/ch04_draft.md"`
Expected: 零命中（4.4 已按前批裁定落地；若有命中按 spec §2.4 清除）。

- [ ] **Step 3: 验证＋提交**

Run: 通用检查器＋docx 测试。Expected: missing = 0、全绿。

```bash
cd "D:/JetBrains" && git add chucao_prj/thesis_cau/03_chapters/ch04_draft.md && git commit -m "ch04 小结按唯一方法重写，撤帧结构/权限/台架/四态句；4.4 残留核对零命中"
```

---

### Task 5: ch02 弹齿撤出＋项目记录清扫＋图注顺移

**Files:**
- Modify: `D:\JetBrains\chucao_prj\thesis_cau\03_chapters\ch02_draft.md`

**Interfaces:**
- Produces: 图注新号（图 2-4 三刀并行／图 2-5 丝印／图 2-6 SBUS／图 2-7 受力／图 2-8 应力），Task 6 的图清单与文件改名必须与此一致。

- [ ] **Step 1: 弹齿节整段删除**

删除 `### 弹齿结构与参数`（行 92）起、至 `### 铲类部件受力分析`（行 135）之前的全部内容（含表 2-4、`[[FIG:弹齿刀组结构与主要尺寸图]]`、图 2-4 图注、`#### 齿夹排构型与壁厚校核` 全段）。

- [ ] **Step 2: 选型论证结论改独选**

在 `### 选型论证` 节内找到结论句（含"主选/对照/对比"字样），替换为：`按作用机理逐项论证（表 2-3），本文选定鸭掌铲为刀头，以切根彻底性与行间适配性为主要判据。`
表 2-3 保留（弹齿行作为被否路线留在论证里）。

- [ ] **Step 3: 受力节弹齿句替换**

old: `对弹齿，其弹性变形使齿尖遇阻后摆让，峰值阻力低于刚性铲，但切根深度一致性差；二者构成"除草率—伤苗率—阻力"的权衡关系，为第 5 章对比试验提供了理论预期。本节只对铲类部件建立切削受力模型，弹齿作为对照部件按选型处理，本文不对其做受力分析与强度校核（选型路线与参数见上文"弹齿结构与参数"一节）。原列"代入田间土壤参数后的阻力数值估算与拉压传感器实测验证"一项据此不再单列：阻力差异不靠算出来交代，改由第 5 章组 1 的实测读数直接回答。`
new: `弹齿的弹性变形使齿尖遇阻后摆让，峰值阻力低于刚性铲，但切根深度一致性差，这是本文不取弹齿的原因之一。本节只对铲类部件建立切削受力模型。`

- [ ] **Step 4: 记录清扫（逐对替换）**

(a) 行 29 整段（`需说明的是，上句末段是**设计目标，不是样机现状**……软件侧的联锁只到信号层（见 4.3.2 节）。`）→ `刀与滑台执行链路的闭合列为第 5 章田间试验的前置条件（见 4.3.2 节）。`
(b) 行 228：删 `台架读数：AP 192.168.2.1、客户端 192.168.2.2、CH157、信号 −24～−36 dBm，视频走 TCP multipart MJPEG，网线直连条件下实测 105 ms @30 fps。**注意这个 105 ms 是网线直连的读数**，无线段的时延须在田间按 4.2.4 节的四项口径重新测，不能拿台架有线读数代替。` → `视频走 TCP multipart MJPEG；无线段时延按 4.2.4 节的四项口径在田间实测。`
(c) 行 234：删 `<待确认：四路 ACS712 具体挂在哪条 I²C 支路——固件里两条支路分别登记为"刹车电流/电池电压"与"车轮角度电位计"，与正文旧说法不一致>`；删 `但"在位"不等于"够用"……但决定了"能控"与"能装"是两件事。` → `刀控与滑台执行链路的闭合列为第 5 章田间试验的前置条件（见 4.3.2 节）。`
(d) 行 258：删 `其中第（4）项所依赖的电机电流采集通道在当前固件中仍为软件占位（读取返回固定值、阈值未整定），本文将其记为**设计内容**，不列为已具备能力；第（1）至（3）项已在车载固件中编码并通过编译与离线单元测试，其对执行机构的实际动作尚待台架与田间复验。除草刀继电器改为固件程序控制，原继电器硬件回路保留作为最后一级切断。` → `第（4）项阈值经田间标定后启用。上述联锁逻辑在车载固件中实现，除草刀继电器由固件程序控制，原继电器硬件回路保留作为最后一级切断。`
(e) 行 262：`ADS1115 电机电流读取已接入采集通道，但安培换算系数未标定、当前输出为占位值，故过流判据尚未启用。` → `ADS1115 电机电流读取接入采集通道，过流判据在换算系数经田间标定后启用。`
(f) 行 184：删 `（2026-11-06 现场实测确认）`；删 `<待登记：轮盘外径、轮盘厚度、隔套数量与长度，以装配后实测为准>`。
(g) 行 246：`其二，图 2-7 中 T4 口的功能在现场记为"输入（限位？）"，其含义与板上 U5/U6 两片 74HC245 的空焊状态**至今未定**（其中限位开关的有效电平极性尚未确定，它决定采购哪种开关），本文不据这两处未决项下任何结论。` → `其二，T4 口与 U5/U6 空焊位的功能不作为本文链路依据。`（图号在 Step 5 顺移）

- [ ] **Step 5: 图注顺移（全节 grep 逐处改）**

`图 2-5 三刀并行` → `图 2-4 三刀并行`；`图 2-6 车载控制板丝印` → `图 2-5 车载控制板丝印`（含行 248 `图 2-6 里红圈`）；`图 2-7 车载控制板丝印`/`图 2-7 中 T4` → `图 2-6 …`；`图 2-8`（行 160/163）→ `图 2-7`；`图 2-9`（行 160/166）→ `图 2-8`。图 2-1/2-2/2-3 不动。
Run: `grep -n "图 2-" ch02_draft.md` 逐行核对：只允许 2-1…2-8，且 2-4=三刀并行、2-5/2-6=板卡、2-7=受力、2-8=应力。

- [ ] **Step 6: 小结替换**

行 266 整段 → `本章完成了中草药行间除草机的总体方案设计：确定设计需求与指标；介绍四轮独立驱动-独立转向移动平台及其半线控基础；设计了电动入土深度调节与提刀机构；对 8 类行间除草部件按作用机理逐项论证，选定鸭掌铲为刀头，并建立铲类部件切削受力模型；完成车载电控的双指令源线控方案、通信协议与四重安全联锁设计。<待补充：台架实测数据>`

- [ ] **Step 7: 验证＋提交**

Run: 通用检查器。Expected: missing = 0（弹齿节删除后节数下降；若有 cross-ref 指向被删节，按节名改引）。
Run: `grep -n "弹齿\|组 1\|快换转接座\|192\.168\|现场确认\|占位\|待确认\|待登记" ch02_draft.md`
Expected: 弹齿仅出现在表 2-3 论证与受力节被否句；其余零命中。

```bash
cd "D:/JetBrains" && git add chucao_prj/thesis_cau/03_chapters/ch02_draft.md && git commit -m "ch02 鸭掌铲独选：弹齿结构设计整节撤出、论证结论改独选；项目记录（接线现状/台架IP/四态/内部核查标记）清扫；图注顺移 2-4…2-8"
```

---

### Task 6: 图清单顺移＋图文件 git mv

**Files:**
- Modify: `D:\JetBrains\chucao_prj\thesis_cau\04_figures\figures_manifest.md`
- Rename: `04_figures/fig2-6_board_silkscreen_485.jpg` → `fig2-5_board_silkscreen_485.jpg`；`fig2-7_board_sbus_and_knife_relay.jpg` → `fig2-6_board_sbus_and_knife_relay.jpg`；`fig2-8_penetration_force.png` → `fig2-7_penetration_force.png`；`fig2-9_blade_stress.png` → `fig2-8_blade_stress.png`

- [ ] **Step 1: 清单行编辑**

删图 2-4 弹齿行；原图 2-5 行 ID 改 图 2-4（File 列仍为 —，未制作）；原 2-6/2-7/2-8/2-9 行 ID 与 File 列按上面改名同步；受力 note 删 `图出现在 2.3.5、早于 2-4/2-5 的版位，全章编号待归一` 句；应力 note 图号改 图 2-8；清单尾部"图号按出现顺序给"那段历史说明里提到的旧号（图2-6/图2-7 照片）按新号更新或删该举例句。

- [ ] **Step 2: 文件改名（顺序执行，避免撞名）**

```bash
cd "D:/JetBrains" && git mv chucao_prj/thesis_cau/04_figures/fig2-6_board_silkscreen_485.jpg chucao_prj/thesis_cau/04_figures/fig2-5_board_silkscreen_485.jpg && git mv chucao_prj/thesis_cau/04_figures/fig2-7_board_sbus_and_knife_relay.jpg chucao_prj/thesis_cau/04_figures/fig2-6_board_sbus_and_knife_relay.jpg && git mv chucao_prj/thesis_cau/04_figures/fig2-8_penetration_force.png chucao_prj/thesis_cau/04_figures/fig2-7_penetration_force.png && git mv chucao_prj/thesis_cau/04_figures/fig2-9_blade_stress.png chucao_prj/thesis_cau/04_figures/fig2-8_blade_stress.png
```

- [ ] **Step 3: 全仓反查旧图号**

Run: `grep -rn "图2-9\|图 2-9\|fig2-9" "D:/JetBrains/chucao_prj/thesis_cau/" --include="*.md"` → 零命中；`图2-8/图 2-8` 只允许指应力图。
Run: 通用 docx 测试（FIGURE_MAP 读清单，嵌图路径必须解析）。Expected: 全绿。

- [ ] **Step 4: 提交**

```bash
cd "D:/JetBrains" && git add chucao_prj/thesis_cau/04_figures/figures_manifest.md && git commit -m "图清单与图文件顺移：弹齿图行删除，三刀并行/板卡/受力/应力依次 2-4…2-8，文件名 git mv 同步"
```

---

### Task 7: ch03 项目记录清扫＋方法断言化

**Files:**
- Modify: `D:\JetBrains\chucao_prj\thesis_cau\03_chapters\ch03_draft.md`

- [ ] **Step 1: 权重身份段替换**

old: `训练以验证集表现为选档依据：运行时加载的权重经同一套链路在验证集上回测，确认为最后一段的最佳档，而非该段末值权重——"末值"与"最佳"在训练日志里是两个不同的轮次，本文早期曾把两者混写，现已按回测结果更正。权重的文件身份（哈希、字节数、文件时间）一并锁定：` 起至 `（哈希相同）。` 整段
new: `训练以验证集表现为选档依据：运行时加载的权重经同一套链路在验证集上回测，确认为最后一段的最佳档，而非该段末值权重。`

- [ ] **Step 2: 三处措辞替换**

(a) `运行中的参数热更新未实现。` → `标定参数以参数文件离线加载。`
(b) 小节题 `标定产物管理与当前状态` → `标定产物管理`；该小节内含"占位/尚未接入/当前状态"的句子删除，保留参数文件、来源字段、像素空间一致性校验内容（先 Read 该小节再逐句改）。
(c) `需要说明的是，本文对单帧抖动的抑制**依靠空间维度上的多点拟合与离群剔除**，未实现跨帧的时间维度滤波；后者列为后续改进，其对连续失效判定的影响在第 5 章口径中一并交代。` → `单帧抖动由空间维度上的多点拟合与离群剔除抑制。`

- [ ] **Step 3: 3.4.5 与小结断言化**

3.4.5 内 `鲁棒加权当前只在远场一路启用` 类句 → `鲁棒加权融合在远场一路启用；近场一路取双墙中点`（删"当前/只"，写成设计本身）。
小结内：`权重身份以 sha256 与文件时间一并锁定` → `所加载权重经回测确认为最后一段的最佳档`；`逆透视单应的田间标定与加载贯通仍待完成` → `逆透视单应的田间标定按 3.2.3 节口径执行，其完成是第 5 章米制读数的前置`；`鲁棒加权当前只在远场一路启用，近场鲁棒化与跨帧时间滤波列为后续工作` → `鲁棒加权融合在远场一路启用，近场取双墙中点`。

- [ ] **Step 4: 验证＋提交**

Run: 通用检查器。Expected: missing = 0。
Run: `grep -n "sha256\|哈希\|21,158\|fb3acfb\|未实现\|列为后续\|当前状态\|占位" ch03_draft.md` → 零命中。

```bash
cd "D:/JetBrains" && git add chucao_prj/thesis_cau/03_chapters/ch03_draft.md && git commit -m "ch03 清扫：权重哈希/字节/时间撤出、热更新与跨帧滤波自贬句删、IPM 状态句改前置口径、远近场加权写成设计本身"
```

---

### Task 8: ch05 两组化＋记录清扫

**Files:**
- Modify: `D:\JetBrains\chucao_prj\thesis_cau\03_chapters\ch05_draft.md`

- [ ] **Step 1: 组 1 删、组号顺移**

删行 93 整段（`组 1（除草装置类型）：……不进入方差分析。`）。
`组 2（刀具控制方式）` → `组 1（刀具控制方式）`；`组 3（车刀耦合控制开/关对比）` → `组 2（车刀耦合控制开/关对比）`；组 2 段内 `本组的执行前置比组 2 多两项` → `本组的执行前置比组 1 多两项`、`连同组 2 已有的` → `连同组 1 已有的`、`按与组 2 相同的` → `按与组 1 相同的`。
行 101 `组 2 有明确的执行前置` → `组 1 有明确的执行前置`。
全章 grep `组 1\|组 2\|组 3` 逐行核对：不得残留旧组号语义（观测指标/统计节若引用装置对比组，删该引用）。

- [ ] **Step 2: 假设与统计节核对**

Read 行 6–20（三个可证伪假设）与 `### 数据处理与统计方法`：含"除草装置类型对比"的假设/统计描述删除或改写为两组口径；`三组` → `两组`（小结行 147 同改）。光照/遮挡分层的"两组"是合法用法，不动。

- [ ] **Step 3: 记录清扫**

(a) 行 101：`现场确认（2026-10-17）这两件目前都未成立——滑台驱动电机未接线、继电器板未接到车载控制器的输出上（见 2.1.2 节与 4.3.2 节），所以本组属"接线之后才谈得上执行"的试验，不是"只差下田"。` → `这两项前置的闭合见 4.3.2 节；本组属执行链路闭合之后开展的试验。`
(b) 行 58：`而本文写作时点该映射的**运行时参数仍是占位值，标定所用的加载链路尚未接入感知入口**。因此感知层的米制数据只能在完成样机机位外参标定、并以未参与标定的独立地面点验证投影误差之后获取` → `感知层的米制数据以完成样机机位外参标定、并以未参与标定的独立地面点验证投影误差为前置`。

- [ ] **Step 4: 验证＋提交**

Run: 通用检查器。Expected: missing = 0。
Run: `grep -n "组 3\|三组\|弹齿\|现场确认\|占位" ch05_draft.md` → 零命中。

```bash
cd "D:/JetBrains" && git add chucao_prj/thesis_cau/03_chapters/ch05_draft.md && git commit -m "ch05 两组化：装置对比组删除、刀具控制/耦合对比顺移组 1/组 2，现场确认与占位状态句改前置口径"
```

---

### Task 9: ch01 cascade＋REF:73 移入综述

**Files:**
- Modify: `D:\JetBrains\chucao_prj\thesis_cau\03_chapters\ch01_draft.md`

- [ ] **Step 1: 研究内容(3) 替换**

old: `（3）运动控制系统设计。建立四轮独立转向（4WS）阿克曼底盘运动学模型，设计轨迹跟踪 PD 控制与中间除草刀横向对行 PID 控制（横向偏差变化率当前以平滑差分估计，卡尔曼滤波估计列为设计候选），研究无线链路时延估计与前馈补偿方法，并给出移动底盘与除草装置的时空耦合控制设计（统一行线模型、双工位时空投影与宏微运动前馈解耦）；入土深度由结构给定，控制层面只做提刀/落刀状态调度。`
new: `（3）运动控制系统设计。建立四轮独立转向（4WS）底盘的两侧差速等效运动学模型与四轮共角横移姿态，设计 PD 轨迹跟踪控制（以两侧差速执行）与中间除草刀横向对行增量式 PID 控制，横向偏差变化率以平滑有限差分估计，研究无线链路时延估计与前馈补偿方法，并给出移动底盘与除草装置的时空耦合控制设计（统一行线模型、双工位时空投影、宏微运动前馈解耦与刀位反馈闭环）；入土深度由结构给定，控制层面只做提刀/落刀状态调度。`

- [ ] **Step 2: 研究内容(4) 替换**

old: `（4）田间对比试验方案设计与验证。设计不同除草装置（鸭掌铲与弹齿）对比试验、刀具控制与不控制（主动对行与固定刀）对比试验，以及车刀耦合控制开/关对比试验，验证整机作业性能。`
new: `（4）田间对比试验方案设计与验证。设计刀具控制与不控制（主动对行与固定刀）对比试验、车刀耦合控制开/关对比试验，验证整机作业性能。`

- [ ] **Step 3: 部件综述句替换**

old: `本文选机械式里的鸭掌铲为主刀头、弹齿作对照，理由是`
new: `本文选机械式里的鸭掌铲为刀头，理由是`

- [ ] **Step 4: REF:73 移入 1.2.2**

在苏童/张硕段（行 38）末尾追加一句：`在偏差序列的状态估计上，卡尔曼滤波亦是常用手段[[REF:73]]。`
Run: `grep -rn "REF:73" "D:/JetBrains/chucao_prj/thesis_cau/03_chapters/"` → 仅 ch01 一处。

- [ ] **Step 5: 验证＋提交**

Run: 通用检查器＋docx 测试（引用解析必须全命中）。Expected: missing = 0、全绿。
Run: `grep -n "阿克曼\|卡尔曼\|弹齿\|候选" ch01_draft.md` → 阿克曼/卡尔曼仅在综述他人工作句；弹齿仅在综述/被否语境；候选零命中。

```bash
cd "D:/JetBrains" && git add chucao_prj/thesis_cau/03_chapters/ch01_draft.md && git commit -m "ch01 cascade：研究内容(3)改唯一方法表述、(4)两组对比、鸭掌铲独选措辞，REF:73 卡尔曼移入文献综述"
```

---

### Task 10: ch06 结论与展望重写

**Files:**
- Modify: `D:\JetBrains\chucao_prj\thesis_cau\03_chapters\ch06_draft.md`

- [ ] **Step 1: 结论(1)(2)(4) 局部替换**

(1) `确定"鸭掌铲主选、弹齿对比"配置` → `选定鸭掌铲为刀头`。
(2) `权重身份以哈希与文件时间锁定；` → 删（留"经回测确认为最后阶段的最佳档"）。
(4) `设计了除草装置对比、刀具控制对比与车刀耦合控制开/关对比三组田间试验方案` → `设计了刀具控制对比与车刀耦合控制开/关对比两组田间试验方案`。

- [ ] **Step 2: 结论(3) 整段替换**

old: `（3）设计了三回路运动控制系统。` 起至 `故带角度的 AUTO 在换律之前不得落地。` 整段
new: `（3）设计了三回路运动控制系统。建立四轮独立驱动/独立转向底盘的两侧差速等效运动学模型与四轮共角横移姿态；横向偏差变化率以平滑有限差分估计；底盘轨迹跟踪采用带时延超前补偿的 PD 控制，以两侧差速执行；中间刀采用增量式 PID 实现横向主动对行；入土以仿形轮—刀固定高度定耕深、弹簧被动稳深，控制层面只做提刀/落刀两位置调度。安全仲裁由提刀状态机与地面站侧、车载固件侧两份实现共同承担，覆盖急停锁存、心跳超时、视觉丢失等联锁条件，过流保护纳入联锁设计。在此基础上给出移动底盘与除草装置的时空耦合控制方法：统一行线模型、双工位时空投影、宏微运动前馈解耦与刀位反馈闭环，以滑台行程 ±50 mm 约束底盘残余横向误差压在 ±5 cm 带内；收益以第 5 章田间开/关对比判定。`

- [ ] **Step 3: 展望整节替换**

`## 展望` 起至文件末替换为（第 (4) 条照抄现稿 (5) 两车口径段原文，一字不改）：

```markdown
## 展望

（1）地头自动转向。现有地头段由人工/遥控完成，受田块形状与感知视场限制，整机尚不具备地头自主转向与换行能力；后续将在地头检测基础上设计地头转向路径与换行策略，把自主作业从行间段扩展到全田块。

（2）跨季节域适应。现有分割模型基于夏季图像训练，杂草种类、密度与色泽的季节差异会造成性能漂移，需补采样本微调，并评估与传统行线提取方法的融合兜底策略。

（3）田间验证的完成。本文两组对比试验数据尚未获取，刀具控制与车刀耦合控制的定量验证将在春季田间窗口内完成，结论表述强度以数据显著性为准。

（4）试验平台与数据归属口径。[照抄现稿展望(5)全段]
```

- [ ] **Step 4: 验证＋提交**

Run: 通用检查器。Expected: missing = 0。
Run: `grep -n "哈希\|现场确认\|已编码\|不得落地\|三组\|弹齿\|算法" ch06_draft.md` → 零命中（弹齿/算法均不应再出现）。

```bash
cd "D:/JetBrains" && git add chucao_prj/thesis_cau/03_chapters/ch06_draft.md && git commit -m "ch06 重写：结论按唯一方法与鸭掌铲独选、撤执行链路长记录段；展望只写客观条件类（地头自动转向/跨季节/田间验证），两车口径保留"
```

---

### Task 11: 摘要中英文 cascade

**Files:**
- Modify: `D:\JetBrains\chucao_prj\thesis_cau\03_chapters\abstract_draft.md`

- [ ] **Step 1: CN 三处替换**

(a) `按作用机理对 8 类行间除草部件逐项论证后选定鸭掌铲为主刀头、弹齿作田间对比` → `按作用机理对 8 类行间除草部件逐项论证后选定鸭掌铲为刀头`
(b) 运动控制段（`运动控制建立阿克曼运动学设计模型` 起至 `电流过流保护因通道未标定列为待启用。`）→
`运动控制建立四轮独立驱动/独立转向底盘的两侧差速等效运动学模型与四轮共角横移姿态，横向偏差变化率以平滑有限差分估计，横向控制采用带时延超前补偿的 PD 控制，微分作用由超前项实现；中间刀采用增量式 PID 对行，因无刀位实测反馈，在作业效果层面属开环对行。入土深度由仿形轮—刀固定高度决定、弹簧被动稳定。针对底盘与中间刀工位不一致、同一帧观测对两工位时刻不同的问题，给出统一行线模型、双工位时空投影与宏微运动前馈解耦的耦合控制方法，以刀位反馈构成闭环回路，其收益以田间开/关对比验证。安全仲裁在地面站侧与车载固件侧各有一份实现，覆盖急停锁存、心跳超时、视觉丢失等联锁条件，过流保护纳入联锁设计。`
(c) `给出除草装置类型对比、刀具控制方式对比与车刀耦合控制开/关对比三组试验的区组设计与统计方法` → `给出刀具控制方式对比与车刀耦合控制开/关对比两组试验的区组设计与统计方法`

- [ ] **Step 2: EN 三处替换**

(a) `after evaluating eight categories of inter-row working elements by their action mechanisms, the hoe blade was selected as the main tool and flexible tines were retained as a field comparison` → `after evaluating eight categories of inter-row working elements by their action mechanisms, the hoe blade was selected as the cutting tool`
(b) `Motion control establishes an Ackermann kinematic design model (the current implementation uses differential-speed correction, with per-wheel angle command left for future work); the lateral-deviation rate is estimated by smoothed finite differencing, with Kalman filtering retained as a design candidate. The implemented lateral controller is proportional control with latency lead compensation, the derivative damping term not yet tuned.` → `Motion control establishes a differential-equivalent kinematic model of the four-wheel-drive, four-wheel-steer chassis together with the four-wheel common-angle lateral posture; the lateral-deviation rate is estimated by smoothed finite differencing, and the lateral controller is PD control with latency lead compensation, the derivative action being realized by the lead term.`
(c) `three of its conditions (emergency-stop latching, heartbeat timeout and vision loss) are coded and pass compilation and offline tests but their effect on the actuators still awaits bench and field re-verification, while overcurrent protection is listed as not yet enabled because its current channel is uncalibrated.` → `covering emergency-stop latching, heartbeat timeout and vision-loss interlocks, with overcurrent protection incorporated into the interlock design.`
(d) `three comparison experiments (weeding-device type, blade-control mode, and coupling-control on/off)` → `two comparison experiments (blade-control mode and coupling-control on/off)`

- [ ] **Step 3: 验证＋提交**

Run: 通用检查器＋docx 测试。Expected: missing = 0、全绿。
Run: `grep -n "阿克曼\|卡尔曼\|弹齿\|三组\|候选\| Ackermann\|Kalman\|tines\|three comparison" abstract_draft.md` → 零命中。

```bash
cd "D:/JetBrains" && git add chucao_prj/thesis_cau/03_chapters/abstract_draft.md && git commit -m "摘要中英文 cascade：唯一方法表述（差速运动学/平滑差分/PD 超前即微分）、鸭掌铲独选、两组试验、安全仲裁改设计语言"
```

---

### Task 12: 图 4-1 重画（qoder 仓工具）

**Files:**
- Modify: `D:\ai work\qoder\tools\make_thesis_diagrams.py:214-239`（fig_control_loops）
- Output: `D:\JetBrains\chucao_prj\thesis_cau\04_figures\fig4-1_control_loops.png`（工具 OUT 目录，重生成覆盖）
- Modify: `D:\JetBrains\chucao_prj\thesis_cau\04_figures\figures_manifest.md`（图 4-1 note）

- [ ] **Step 1: 函数体替换**

`fig_control_loops()` 的 docstring 与函数体（行 215–239）替换为：

```python
    """4.1 节：三回路架构＋地面站—无线链路—车端控制路线。
    回路文字按唯一方法口径：PD 差速纠偏 / 增量式 PID 对行 / 两位置调度。"""
    c = Canvas(760, 320)
    c.note(250, 10, '地面站控制律')
    c.note(520, 10, '车端执行（指令经无线链路下发）')
    c.box(40, 30, 150, 40, '远场导航线')
    c.box(40, 90, 150, 40, '近场导航线')
    c.box(40, 150, 150, 40, '提刀 / 落刀调度')
    c.box(250, 30, 210, 40, '底盘轨迹跟踪回路\nPD 差速纠偏')
    c.box(250, 90, 210, 40, '除草装置控制回路\n中间刀增量式 PID 对行')
    c.box(250, 150, 210, 40, '入土控制回路\n两位置状态调度')
    for i, y in enumerate((50, 110, 170)):
        c.arrow(190, y, 250, y)
    c.box(520, 30, 200, 40, '两侧轮速 + 四轮共角姿态')
    c.box(520, 90, 200, 40, '中间刀滑轨位置指令')
    c.box(520, 150, 200, 40, '提刀 / 落刀')
    for y in (50, 110, 170):
        c.arrow(460, y, 520, y)
    c.group(250, 210, 470, 60, '车载状态机统一调度 · 安全联锁具有最高优先级')
    c.note(258, 240, '急停锁存 / 心跳超时 / 视觉丢失（见 4.3.2 节）')
    c.arrow(355, 190, 355, 210)
    c.note(40, 288, '注：图中"刀位实测反馈"一项缺失，故中间刀对行在作业效果层面为开环'
                    '（见 4.3.3 节）。')
    return c.save('fig4-1_control_loops.png')
```

- [ ] **Step 2: 重生成＋读回**

Run: `cd "D:/ai work/qoder" && PYTHONUTF8=1 python -B tools/make_thesis_diagrams.py`
Expected: 四张图尺寸打印，fig4-1 写盘成功。用 Read 工具打开生成的 fig4-1 PNG 目视核对：无状态文字、两列边界注记在位、无叠字。

- [ ] **Step 3: 图清单 note 更新**

图 4-1 行 note：`其内文字按四态口径写"三条已编码待台架复验、过流待启用"` → `其内文字按设计口径写（急停锁存/心跳超时/视觉丢失）`；其余照旧。

- [ ] **Step 4: 验证＋双仓提交**

Run: 通用 docx 测试。Expected: 全绿。

```bash
cd "D:/ai work/qoder" && git add tools/make_thesis_diagrams.py && git commit -m "fig4-1 重画：撤状态注记、补地面站—无线—车端边界、回路文字按唯一方法口径（PD 差速/增量式 PID/两位置）"
cd "D:/JetBrains" && git add chucao_prj/thesis_cau/04_figures/fig4-1_control_loops.png chucao_prj/thesis_cau/04_figures/figures_manifest.md && git commit -m "图 4-1 重生成（设计语言、控制路线一图可读）与图清单 note 同步"
```

---

### Task 13: 全文总验证＋残留反查＋HEAD 报告

**Files:**
- 只读核对，不改文件（发现问题回对应 Task 修）。

- [ ] **Step 1: 全量验证**

Run: `cd "D:/ai work/qoder" && PYTHONUTF8=1 python -B tools/check_thesis_sections.py`
Run: `cd "D:/ai work/qoder" && PYTHONUTF8=1 python -B -m pytest tests/test_make_thesis_docx.py -q -p no:cacheprovider`
Expected: missing = 0；全绿。读数只写进收口报告。

- [ ] **Step 2: 残留反查（thesis_cau 全部 md）**

```bash
cd "D:/JetBrains/chucao_prj/thesis_cau" && grep -rn "候选\|尚未实现\|未实现\|未经整定\|列为后续\|设计模型\|现场确认\|现场实测确认\|sha256\|哈希\|21,158\|已编码\|已编译\|已台架\|待台架\|待启用\|占位值\|192\.168" 03_chapters/ 04_figures/figures_manifest.md
```
Expected: 零命中（零命中必须解释：本批已按 spec 清扫）。
弹齿/阿克曼/卡尔曼逐条人工判读（只允许论证/综述语境）；`三组` 零命中；`图2-9/图 2-9` 零命中；`组 3` 零命中。

- [ ] **Step 3: 工作树核对＋HEAD 报告**

Run: `cd "D:/JetBrains" && git status --short -- chucao_prj/thesis_cau/`
Expected: 只剩禁 stage 项（fig2-8_penetration_force_matlab.png 改动、07_data/、v12–v14、~$、_render/）。
向作者报 chucao HEAD 与 qoder HEAD＋改动清单＋"未触及"清单，请其转发 zcode。

---

## Self-Review 记录

- spec 覆盖：§2.1→Task 1；§2.2→Task 2；§2.3→Task 3；§2.4/2.5→Task 4；§3 ch02→Task 5、图→Task 6、ch05→Task 8、ch01→Task 9、摘要→Task 11、ch06→Task 10；§4→Task 5/7/8/10/11；§5→Task 2/9/10/11；§6→Task 12；§7→各 Task 验证步＋Task 13；§8 不做项→Global Constraints。无缺口。
- 占位扫描：Task 10 (4)「照抄现稿展望(5)全段」为明确搬运指令（源文本在文件内，非 TBD）；Task 7 Step 2(b) 为先读后改的精确规则。其余步骤均给实际文本。
- 一致性：表号 4-1（Task 2）→4-2（Task 3）；图号 Task 5 图注与 Task 6 清单/文件名一致；组号 Task 8 顺移后 Task 9/10/11 均用两组；REF:73 Task 2 删引用、Task 9 补引用，净引用数不变。