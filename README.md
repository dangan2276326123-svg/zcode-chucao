# 纯视觉芍药行间除草机器人

本项目为纯视觉（单目相机，无 RTK/激光雷达）芍药行间除草机器人的完整工程：包括 DeepLabV3+ 语义分割训练、相机标定与 IPM 逆透视变换、导航控制、上位机（PC）主控循环、车端（树莓派）桥接与下位机（STM32）固件。

## 逐文件说明

### 根目录

| 文件 | 说明 |
|---|---|
| `README.md` | 本文件：目录/文件说明 + 快速上手 |
| `AGENTS.md` | AI 协作（ZCode/Agent）工作约定 |
| `.gitignore` | git 忽略规则（视频、抽帧、标定图、权重、抽帧、标定图、权重等（Keil OBJ 编译产物已另行清理出库）） |

### `common/` — PC/车端共用的 Python 模块

| 文件 | 说明 |
|---|---|
| `protocol.py` | 串口通信协议（帧格式、CRC、命令字），与下位机 `firmware/大车proj/大车/HARDWARE/retrofit/protocol.c` 一一对应。**E3 批 1b 加**：`TYPE_MODE=5` 与 `pack_mode()`（申请/退出无人、解除急停、档案握手——A2 之后 NAV 不再承担权限语义）、STATUS 两形态 `pack_status_v2()`（19 B）与 `unpack_status_any()`（**按载荷长度分派 14/19**，A8）、`REJECT_*` 原因码与 `REJECT_TEXT` 中文长文案、`PROFILE_*`/`AUTH_*` 常量。⚠️ 这些是 **PC 侧的一半**：现固件的 switch 没有 `TYPE_MODE` 分支（`retrofit.c:60-75`，行号按**现烧在板上的那版** = `f0ecf73`；批 1a 已加该分支但尚未烧，工程内正身 `firmware/大车proj/大车/HARDWARE/retrofit/retrofit.c`），STATUS 仍是 14 B——两侧都要生效必须等批 1a 烧录 |
| `uart_vectors.py` | **B2 台架对拍向量表 + USB-TTL 手发 sender**（`python common/uart_vectors.py --dump` 打印，`<COM>` 真发）。**组数以 `--dump` 当场输出为准**（E3 批 1b 加了 `mode_auto`/`mode_clear` 两条 MODE 与一条 19 B 的 `status_v2`，批 1a 的对拍基准就是这张表）；含两条**必须被丢弃**的坏帧（坏 CRC、截断）。`repack()` 按帧自身的类型重打包——早期是按向量名字前缀猜（`nav*`→NAV、其余→HEARTBEAT），E3 的 `mode_*`/`status_v2` 不匹配任何前缀会被当心跳发出去，而固件见心跳是"AUTO 交回 MANUAL"，语义正好相反 |

### `network/` — 深度学习与感知算法

| 文件 | 说明 |
|---|---|
| `train_m.py` | **主分割模型训练入口**（DeepLabV3+ MobileNetV2，960×720，二分类：背景/杂草） |
| `train_h.py` / `train_r.py` / `train_x.py` | 其他骨干/配置的实验训练脚本（h/r/x 变体） |
| `train_metric_log.csv`（及 `_backup`） | 训练过程指标日志 |
| `modeling.py` | DeepLabV3+ 模型组装（选 backbone、ASPP、解码器） |
| `_deeplab.py` | DeepLabV3+ 核心结构实现（ASPP、Decoder） |
| `backbone/mobilenetv2.py` | MobileNetV2 骨干（主用） |
| `backbone/resnet.py` | ResNet 骨干（备选） |
| `backbone/xception.py` | Xception 骨干（备选） |
| `backbone/hrnetv2.py` | HRNetV2 骨干（备选） |
| `camera_calib.py` | 相机标定适配器：加载 `data/calib_params.npz`，去畸变 + IPM 逆透视（输出 960×720 物理坐标掩码） |
| `nav_control.py` | 导航控制：行中心线偏差/航向误差 → 差速控制量 |
| `local_single_station.py` | 本地单工位端到端链路：标定→分割→后处理→IPM→控制，用于整链自测 |
| `predict_demo.py` | 单张/文件夹推理演示（可视化叠加） |
| `utils.py` | 数据集加载、指标（mIoU）、损失等训练辅助 |

### `pc/` — 上位机（笔记本电脑）主控

| 文件 | 说明 |
|---|---|
| `main.py` | **完整控制循环入口**：`--source` replay 模式 / `--live` 实车模式，GUI 叠加显示，ESTOP 急停联锁 |
| `replay.py` | 对视频/图片目录逐帧回放推理并保存结果（离线验证） |
| `perception.py` | 感知封装：加载权重与标定 → 去畸变 → 分割 → IPM 鸟瞰 → **导航线拟合**（远场 `peony_postprocess` + `fit_centerline_lsq_weighted` 给底盘导航；近场 `peony_postprocess` 给中间刀 PID） |
| `control.py` | 控制层 4 个纯 Python 类（无 torch/cv2 依赖，各带单元测试）：`MiddleToolPID` 近场横向误差 → 中间刀滑台偏移（条件积分抗饱和，输出限幅 ±50mm）；`LatencyCompensator` 链路时延估计（滚动 p50/p95）+ 误差前移补偿 err+rate·delay；`LatErrorRate` 横向误差变化率估计（有限差分 + 平滑，供上者）；`DifferentialDrive` 底盘差速：远场横向误差+航向阻尼 → 左右轮速 v∓dv（标称 0.14 m/s，限幅 ±0.2）。⚠️ 过渡态：实车有四轮转向伺服但固件在 AUTO 锁直，按纯差速走；四轮转向+差速混合重写未做（缺口清单 P0-1），电流前馈也未实现（F4） |
| `state_machine.py` | 作业状态机（待机/作业/掉头/急停等状态切换） |
| `wire.py` | **E3 §5.1/§5.3「这一拍往线上发什么」的唯一出处**（10-08 批 1b 加）：纯函数 `frames_for_state(state, usable, vl, vr, tool_mm, permit)`——持权（AUTO/LIFT）必发 NAV+TOOL 且**永不发 HEARTBEAT**，MANUAL 只发心跳，ESTOP **稳态返回 `[]`**（跳变那一拍的 ESTOP 帧由调用方发）；`permit` 非 `GATE_N`/`GATE_F` 一律 `ValueError`（fail-closed，四个状态都校验）。同文件另有 `RUN_LOG_COLUMNS`（**run_log 列名的权威**）与 `run_log_row()`、门 N 语义（`GATE_N` 下横移恒 0、刀位恒 `0x07`）、HUD 用的 `REJECT_SHORT` ASCII 短码表与 `reject_short()`（`cv2.putText` 画不出 CJK；CSV 的 reject 列存**数字码**，中文全文在 `common/protocol.py:REJECT_TEXT`——`tools/link_probe.py` 的 stdout 打整句，而 `pc/main.py` 一侧的 `status_rx.reject_text()` **还没有生产调用点**，spec §5.4 的"人话"到批 1b 是「已编码 + 待联调」）。抽出来的理由：这三条判定原先散在 `main.py` 三个分支里，"AUTO 但这一帧不可用"会掉进 else 发心跳 |
| `vehicle_profile.py` | **车辆档案加载（E3 §6）**：读 `config/vehicle_profile.yaml` 的 `profile_id` 与 `permit` 两个平铺键（手写解析，不引 PyYAML）。**读不到就报错停下，绝不回默认值**——档案装的是换算量与安全许可位，静默回默认等于让车带着错参数进无人；`exists()` 为真但读不进去（目录/被占用/权限）也算"读不到"，统一抛 `ValueError` 给 `pc/main.py` 决定"能不能进无人" |
| `status_rx.py` | MCU STATUS 接收（live 模式，UDP 9100）：坏帧捕获计数绝不裸抛（D7 约束），滚动 1 秒 ≥5 坏帧报警（多半是固件/Python 协议字段失同步）；纯逻辑类，socket 留在 main。**E3 批 1b 加**：`handle()` 改用 `protocol.unpack_status_any()` **按载荷长度分派**（14 B = E3 之前的 v1，19 B = E3 的 v2，其它长度计坏帧）——这就是"批 1b 必须先合、批 1a 才能烧"的理由：旧解析器见到 19 B 会把每一帧计成坏帧，报警会喊成自家解析器；`status_version` 属性给出 1/2/None；`loop_stalled()` 由连续 `STALL_FRAMES` 帧读到同一个 `loop_alive` 判**执行面停摆**（Fw-21 的探测手段，固件 `reject=0x05` 的 PC 侧对应物）——⚠️ **它返回 False 不等于执行面活着**，v1 固件没有这个字段时历史被清空、恒 False，"绝不谎报停摆"；`reject_text()` 把拒绝码翻成中文长文案（HUD 不用它，见 `pc/wire.py`） |
| `ipm_io.py` | **IPM 外参加载器（带来源校验）**：拒绝无来源字段、`points_source != field`、源图近乎纯色/全黑、重投影超 2 cm、点数 <4、**车辆档案不匹配**的标定文件。存在的原因：仓库里那份 `results/smoke_ipm/ipm_params.json` 看着像标定，其实源图全黑（mean=0/std=0），只是求解器的冒烟测试 |

### `config/` — PC 侧配置

| 文件 | 说明 |
|---|---|
| `vehicle_profile.yaml` | **E3 车辆档案（spec §6）**，上电握手用，只有两个平铺键：`profile_id`（1 = PREV 上代车 3.25 m / 2 = REAL 样机 2.15 m）与 `permit`（`gate_n` = 只许沿行空跑、刀强制提且横移禁；`gate_f` = 允许落刀与横移）。PC 发 `MODE(0x20, profile_id)`，固件拿它跟自己烧进去的 `PROFILE_ID` 比，不一致 ⇒ `reject=0x01` 且拒绝进无人。**运行中不热切**（v1.0 §4.3）：档案装的是换算量，行驶中切换会让控制量跳变；换车 = 重新上电 + 改这个文件 + 烧对应固件。⚠️ 固件侧那份是**编译期常量**，与本文件不一致时**以固件为准**（固件回 `reject=0x08`），本文件只决定"PC 该发什么"。读取方：`pc/vehicle_profile.py`（读不到就抛，不回默认值）；`tools/bench_status.py --to` 与 `tools/latency_probe.py` 的档案号也**只从这里取**，不在命令行或输入行上给（spec §6：改档案号 = 改一台车的权限） |

### `vehicle/` — 车端（现在是 RDK X5，目录名与部分注释沿用"树莓派"，未全量改名）

| 文件 | 说明 |
|---|---|
| `start_bridge.sh` | **X5 侧一条命令起桥**（09-28 加）：先 `pkill -f "cat /dev/ttyS"` 把抢串口的人清掉，再 `sudo python3 bridge.py`。用法 `sh ~/qoder/vehicle/start_bridge.sh`。**必须 LF 换行**——`.gitattributes` 里钉了 `*.sh text eol=lf`，因为本机 `core.autocrlf=true`，带 CRLF 的 shebang 到了 X5 会以 `bad interpreter: /bin/sh^M` 失败，那种在车边上会被误读成串口有问题 |
| `bridge.py` | PC ↔ 下位机桥接：把上位机控制量经串口转给 STM32，回传状态 |
| `stream_pi.py` | 树莓派上抓取相机图像并回传给上位机 |
| `config.yaml` | 车端配置，字段是 `serial_dev` / `baud` / `udp_port` / `pc_ip` / `pc_port` / `stream.{port,width,height,fps}` / `watchdog_ms`（可选 `allowed_sources`）。**没有 `PI_IP` 这个字段**，旧说法作废 |

### `tools/` — 数据处理脚本

| 文件 | 说明 |
|---|---|
| `bench_status.py` | **B1/B2 台架验收记录器**：收 MCU 的 STATUS 帧（UDP 9100，复用 `pc/status_rx.StatusReceiver`，与生产同一套新鲜度/乱序/重启重同步判据），按绝对时间戳把每帧、每次**模式跳变**、每段**静默 gap**（成对 gap_start/gap_end ＋ 时长）和**你敲的场景标记**写进同一张 CSV。用途是把"失联几秒停车、夺权后刀具动不动"这类几秒内的瞬时行为变成可回看的证据。⚠️ 它**不测**横向偏差的米制数值（感知侧占位几何未接线）；CSV 里的 `current_a`/`batt_v` 两列固件是占位值（`retrofit.c:226` 写死 48.0f；行号按现烧那版 `f0ecf73`，HEAD 里这一行已移到 `retrofit.c:431`），只能看趋势不能当实测。X5 侧 `vehicle/config.yaml` 的 `pc_ip` 必须指到本机，否则收不到帧——那不是 MCU 的错。**E3 批 1b（Task 8）加发送面**：`--to <桥IP>:9000` 是 **opt-in**（不填时一个字节都不往外发，`!nav` 之类只打一行"没启用"），填了才另开一个不 bind 的 socket 发；stdin 命令 `!nav vL vR` / `!tool mm lift` / `!beat` / `!auto` / `!manual` / `!clear`，档案号只从 `config/vehicle_profile.yaml` 取；**发出的每一帧同样落进那张 CSV**（`kind=tx_*`，自带发送序号），发送序号与 STATUS 的接收序号是两套计数（共用就等于给自己的新鲜度/重同步判据喂假数据）。有了它，"PC 持续发 NAV/TOOL 的同时看 STATUS"那一类场景才不用关掉记录器改开 `pc/main.py`。⚠️ **发 NAV 前必读**：现在板上的固件里一条 NAV 就是进 AUTO 的钥匙（`retrofit.c:93→:102`，行号按现烧在板上的那版 = `f0ecf73`，正身在 `firmware/大车proj/大车/HARDWARE/retrofit/`、根目录影子副本已删；批 1a 的 F1 拆掉它但**尚未烧**），且本工具对 NAV 有 **0.20 m/s 硬闸**（与 `tools/link_probe.py` 共用 `tools/bench_limits.py` 那一个数），超限 `[TX REFUSED]`：不发、不消耗序号、不落 CSV；**用法前提是驱动轮离地**，跑行车闭环请用 `pc/main.py`。**E3 批 1b 收口（C-1）加**：`!tool` 另有一道**许可位闸**（`tools/bench_limits.tool_command_allowed()`）——门 N 只许 `!tool 0 7`（与闭环 `wire.frames_for_state` 同一对字节），门 F 放行合法载荷，**档案读不到/许可位未知 = 一律拒**（不降级成门 F），拒发同样不发、不消耗序号、不落 CSV；NAV 那道闸也扩成 fail-closed（非有限 / 装不进 f32 / 不是数字一律判为超限）。开机那行会把 permit 印出来。**10-12 加**：stdin 另有一条 `!profile`（发 `MODE(0x20)` 档案握手，档案号仍只从 `config/vehicle_profile.yaml` 取、带参数就拒），用途是**不重启 `pc/main.py` 也能重放握手**。⚠️ 本工具与 `pc/main.py` **都独占绑 UDP 9100**（09-22 实测 Windows 上 `SO_REUSEADDR` 会"bind 成功但包只给先绑上的那个"，所以这里故意不用它），同一时刻只能开一个；`tools/link_probe.py` 的发送**不 bind**，是唯一能与本工具并存的那一路。台架逐格判据与这条互斥关系写在 `docs/X5验机与接入执行清单.md` **§4B**（那张待执行清单；格数不写在这里，AGENTS 审查清单第 8 条）。 |
| `check_citations.py` | **坐标式引用审计**（2026-10-12 立）：扫全仓 md 里 `路径:行号`／`§节号` 这类引用，解析目标文件后分三档报——HARD（路径不存在或行号越界）、CHECK（读得到但对不上被引内容，需人工看）、SOFT（目录大小写与磁盘不符，Windows 看不出、Linux 克隆即断）。**退出码恒为 0，这是报告不是闸**：把坐标数字写成硬判据，下一批就会有为了变绿去改数字的人（同 AGENTS 审查清单第 8 条的理由）。`--strict` 看 CHECK 全量、`--fail-on-hard` 才非零。跑法 `python -B tools/check_citations.py`。历史文档（specs／plans／台账 §4）里的行号是当时的记录，按"续写不抹历史"不追改 |
| `bench_limits.py` | **台架限速的唯一出处**（AGENTS 审查清单第 6 条"单一事实源"）：`NAV_BENCH_LIMIT_MPS = 0.20` + 谓词 `nav_exceeds_bench_limit(vl, vr)`。现在能往大板发帧的三个 PC 入口——`tools/link_probe.py`、`tools/bench_status.py --to`、`tools/latency_probe.py`——走的是同一个 `bridge:9000`、同一块板子，所以这条安全不变量**只能有一份**：各写一个字面量，下一次就是改了一份没改另一份，而"哪个闸生效"没人会在台架上重新验。判定逻辑（不只是数字）也在这里，同一个闸在三个入口必须给同一个答案；比较留了 f32 余量（0.2 存成 f32 是 0.20000000298…，不留余量会把"正好等于限值"这条边界拒掉）。**E3 批 1b 收口（C-1）**：`nav_exceeds_bench_limit()` 改成 **fail-closed**——非有限值（NaN/±inf）、装不进 f32 的数、以及不是数字的入参一律判为超限（NaN 与任何数比较皆为假，旧写法等于"比较不上就放行"）；同文件另加 `tool_command_allowed(permit, tool_mm, lift_bits)`（门 N 只许 (0.0, 0x07)、门 F 放行合法载荷、未知/取不到的 permit 一律拒）与 `load_permit()`（读不到就抛，**不返回默认值**——两个手动工具共用这一个取数出处）。理由与出处写在该文件文档串里：`retrofit.c:93` 早退只管长度与急停锁存、`:98-101` 把速度钳到 ±1.0、`:102` 一条 NAV 即 `mode = MODE_AUTO`，而斜率 `SLEW_ACC=0.2 m/s²`（`:140`）意味着一条 0.9 的命令约 4.5 秒后**真的**把 2.15 m 宽、带着刀和滑台的机器推到 0.9 m/s。**这几个行号一律按"现在实际烧在板上"的那版固件**（`f0ecf73`，`git show f0ecf73:firmware/大车proj/大车/HARDWARE/retrofit/retrofit.c` 可取回）：批 1a 的 F1 已经把 `:102` 那条改写掉但**尚未烧录**，根目录那份同名的影子副本 2026-10-10 已删除（A13），别按 HEAD 的行号去对 |
| `link_probe.py` | **PC → 大板的反向探针**（只发不收，不 bind 端口，可与记录器同时开）：往 `bridge:9000` 发一帧，看单片机认不认。**E3 批 1b（Task 7）重写判据**：废掉"是否曾看到 AUTO"这个统一判据，改成 `EXPECTED` 表按命令定义预期响应 + `judge()` 把"发送前基线"与"发送后变化"分开算，并保留 INCONCLUSIVE（发送前基线没采到、或本来就是那个态 ⇒ 证明不了因果）；A2 之后 NAV 不再改 `mode`，所以 nav 的判据反过来是"**mode 不许变**"，变了要列三种可能（旧固件 F1 洞 / 有别的东西在发帧 / 旁边有人动遥控器）；`reject != 0` 是**正常响应**（链路通了、权限没给），报中文原因不写"链路不通"。NAV 同受 `tools/bench_limits.py` 的 0.20 m/s 闸，**E3 批 1b 收口（C-1）**后这条闸是 fail-closed 的：命令行先自己把两个速度转成**有限** float（"不是数"与"不是有限数"各有各的报错，`nav nan 0` 从此 rc≠0 且一帧不发），转出来的数再交给共享谓词判超限；`tool mm lift` 同受许可位闸（门 N 只许 `tool 0 7`，档案读不到 = 拒，不降级成门 F） |
| `latency_probe.py` | **E3 spec §7.2 的延迟自测两条，都不改固件**：`D1` = 交替发 `MODE(0x01)`/`MODE(0x00)`，量到 STATUS 里 `mode` 变成这条请求所要的那个值（⚠️ **不能用 NAV 测**——A2 之后 NAV 不改 `mode`，发它看不到任何回显变化，会被读成"链路超时"；分辨率受 STATUS 20 Hz 限制 ±50 ms）；`D2` = 每轮先把 NAV(0,0) **持停到看见轮子确实停了**再发阶跃，量到 `speed` 首次越过阈值（含 D1 全部 + 斜坡 + PWM + 电机 + 传动 + 轮胎）。**两个数必须分开报**：`SLEW_ACC=0.2 m/s²` 让 0→0.14 m/s 要约 0.7 秒，完全掩盖百毫秒级链路延迟，论文口径是"链路延迟 = D1；机械响应 ≈ D2 − D1"。硬约束写在该文件文档串里并各有出处：阈值下限 0.05 m/s 是硬的（TIM3 16 位，脉冲间隔 >65.536 ms 取模 ⇒ 低速段 `speed` 不可信）；阶跃速度共用 `tools/bench_limits.py`；续发/持停是因为桥在最后一条 PC 帧 500 ms 后自注 ESTOP 而锁存只能断电清（Fw-14），`--keepalive 0` 在命令行上直接拒。⚠️ 已知未修：**续发节奏由到达的 STATUS 驱动，STATUS 断流 ⇒ 续发停摆 ⇒ 又静默**（审查发现 M-3，登记处 = `docs/参数差异台账.md` 的 Pc-9 行） |
| `check_dataset.py` | 数据集完整性检查（图/mask 对齐、类别统计） |
| `json2mask.py` | 标注 JSON → 训练用灰度 mask |
| `morph_process.py` | 分割结果后处理 + **导航线拟合**（被 `pc/perception.py` 和 `network/local_single_station.py` 导入）：`extract_dual_walls` 从 IPM 鸟瞰掩膜提取左右垄墙 → `fit_centerline_lsq` 对双墙各拟合 x=a·y+b 取中点 → `fit_centerline_lsq_weighted` 裁剪最小二乘 + 按内点率加权融合（遮挡鲁棒，单墙退化时门控回退）→ 输出 lookahead 行的横向偏差 `center_x` |
| `split_dataset.py` | **数据集划分（分组模式）**：按 视频/地块/日期 前缀整组划分，杜绝邻帧跨集合（H1.3）；冻结 `split_manifest.json`；硬性保证 train/val/test 各≥1 组，组数 <3 直接拒绝而非静默退回逐图；源目录先校验后清空，`--force` 才清目标 |
| `check_doc_invariants.py` | **文档不变量检查器**：执行 AGENTS 审查清单第 2 条 b) 项的"全仓枚举圈号区间并打印命中数"。扫描范围按 09-22 定案**摘除审查清单第 2 条所在行块**（规则自己的反例举例不计入，否则它永远红）。退出码 0=干净／1=禁用语义命中／2=基线漂移需解释／3=有 md 读不进去（**读不到就不算零命中**，防止假通过）。数法按**出现次数**、不按行数，两者都印。 |
| `geometry_check.py` | **整车空间口径判据（只报事实，不报结论）**：要 N 把刀各进一条等距草带，车宽至少 `(N−1)·s + 刀宽`。`track_span` 给"轮距等于几个行距／离整行距还差多少／几何上是否可能对得上行"，**不输出压苗结论**——旧版那句"车宽>行距即压在作物行上"是 09-21 复审撤回的过度推论（行距 38.2 时轮距 191 恰为 5 个行距，两轮正落在行间）；判压苗要另量胎宽（M14）与轮迹对行线偏差（M15）。`slide_reach_verdict` 按"总行程 = 2 × 单侧需求"判够不够（旧实现拿总行程跟单侧比，会把 30 cm 报成够）。未实测的量返回"不下结论"，不补默认值。配合 `docs/整车尺寸实测表_20260921.md` |
| `capture_field.py` | **秋采落盘入口**（10-14 加）：连 X5 的 TCP MJPEG，`空格` 按 `raw/{光照}_{视角}_{行况}/t{NN}_{MMDD}_{序号}.jpg` 落 JPG、`1/2/3`/`4/5/6`/`7/8/9` 切行况/光照/视角、`v` 录 30 秒验证视频、退出留 `capture_log_*.csv`。**在此之前采集清单要求的命名没有任何工具能产出**（`stream_view.py` 的 `s` 存的是 `results/stream_view_HHMMSS.png`，名字/格式/目录三样全不对）。配套：`vehicle/stream_pi.py` 加了 `--width/--height`（默认仍 720p，采集要 1080p） |
| `pre_annotate.py` | **半自动预标注**（DeepLabV3+ → labelme JSON + 叠加目检图）：qoder 工作区版，缺依赖时打人话提示、输出默认锁在工作区内、打印权重 md5/mtime 与解释器路径。原脚本在只读仓 `chucao_prj/annotation_tools/`，不改它 |
| `启动预标注.bat` | 预标注启动入口（写死可用解释器）。**故意只写 ASCII**：.bat 里的中文必须 GBK 编码，否则 cmd 显示乱码 |
| `make_thesis_docx.py` | **论文 Word 生成器（P1）**：从只读仓的论文开发区 `chucao_prj/thesis_cau/03_chapters/*.md` 渲染出一份**正文零域**的 docx，产物写回 `thesis_cau/10_output/thesis_draft_v15_clean.docx`。存在理由是当场数到的症状：v14 是在校模板自己的 `document.xml` 上打补丁得到的，继承 `w:fldChar` 818／`w:instrText` 348／`MACROBUTTON` 47／`PAGEREF` 28／`SEQ` 7——那就是"打开慢、不好改"的来源。本工具反过来做：**取模板包（样式、字体、主题、页面设置留下）但把正文整块删掉重写**，标题走 Heading 样式、表格走三线表、目录走死文本（页码等版式定稿后由 Word 一次性生成，不留 PAGEREF）。**封面走另一条路**：`--cover academic` 把模板的封面/书脊/独创性声明/授权说明**按 XML 块搬过来再拆域**（`_strip_field_machinery`），因为重打一遍只会做出一张假封面；当场搬 62 块、拆 109 个域节点、删 1 条**已失效的外链图片引用**（模板 `INCLUDEPICTURE` 指 `news.cau.edu.cn/upload/2005/…jpg`，`curl -sL` 读数 307 → `https://www.cau.edu.cn/`、0 字节，留着就是封面红叉；真正渲染的是本地 `media/image1.jpeg` 校名图，所以只删 `r:link`、不删图）、并在封面与书脊的接缝处**补 1 个分页符**（模板全前言只有一个显式分页符，恰在被删掉的附件2 段末尾，不补书脊就并到封面上去）。三个模式：`--check` 只解析不写、默认写出、`--verify` 重新解开产物数域（判据是那一串计数全为 0；页眉页脚的 `PAGE`/`STYLEREF` 单独一层报，不含在"正文零域"这句话里）。⚠️ 三条不许糊过去的约定：**19 处公式按原样 LaTeX 落纸并标 〔公式待录〕**（公式由作者手录，工具不猜语义）；**行内符号只有在"没有残留反斜杠／花括号／脱字符"时才算转码成功**，否则灰底标出——错得看起来很干净比标出来更糟；`<待补充>`、`[[REF:]]`、`[[FIG:]]` 一律保留可见。源码哈希、字数与全部校验读数**只写在产物旁边那份 `10_output/word_版本清单.md` 一处**（AGENTS 审查清单第 8 条），本行不抄数。依赖 `python-docx`，输出目录由环境变量 `THESIS_DIR` 覆盖；测试 `tests/test_make_thesis_docx.py`（15 条，另做 6 处变异验证它们咬得住） |

### 运行环境 — 用哪个解释器（09-21 实测，别再猜）

| 用途 | 解释器 | 已验证 |
|---|---|---|
| 训练 / 预标注 / 感知推理 | `D:\ruanjian\anac\envs\deeplab\python.exe`（conda env `deeplab`，Python 3.9.23） | numpy 2.0.2、cv2 5.0.0、torch 2.6.0+cu124、torchvision 0.21.0、albumentations 2.0.8；`pre_annotate.py` 跑通，设备 cuda |
| 同上（备用，`python` 在本机 PATH 里就是它） | `D:\ruanjian\anac\python.exe` | 352 张预标注全过，rc=0 |
| **只**用于打开 labelme 图形界面 | `chucao_prj\annotation_tools\labelme_env\Scripts\python.exe` | ⚠️ 该 venv **只有 labelme 5.10.1 + numpy**，没有 torch/albumentations/cv2 —— 拿它跑 `.py` 必然 `ModuleNotFoundError: No module named 'cv2'` |
| matplotlib 绑图 | ❌ 两个环境都不可用 | numpy 2.0.2 与已编译的 1.x 冲突（ImportError）。曲线改用 python-pptx 原生图表或 CSV |

**`cv2.imshow` 能不能开窗（10-13 傍晚实测，09-21 那张表没覆盖这件事）**：上面那行的判据是
"预标注跑通"，而预标注不开窗，所以 GUI 能力一直没被记过——代价是手操档当天现场炸的：
键盘输入长在 `imshow`/`waitKey` 上，`python -B pc/main.py --live` 第一拍就抛
`OpenCV ... The function is not implemented. Rebuild the library with Windows, GTK+ 2.x or Cocoa support`。

- 成因（当场 `pip list` 读到的）：同一个解释器里**同时装着** `opencv-python 4.13.0.90` 和
  `opencv-python-headless 5.0.0.93`。两个包都往 `site-packages\cv2\` 落文件，`import cv2` 拿到
  谁取决于安装顺序，而 headless 那份的 `imshow` **必抛**。
- 修 = 两个都卸、只留 GUI 那一份（版本号不变，所以 HUD 那个每行 85 字符预算的实测前提不动）：
  `python -m pip uninstall -y opencv-python-headless opencv-python` 然后
  `python -m pip install opencv-python==5.0.0.93`。
- 判据 = **窗口真开出来**，不是 `getBuildInformation()` 里找 `WIN32:`——这两个 wheel 的
  Video I/O 段根本没有那一行，只有 `imshow` + `waitKey(30)` + `getWindowProperty(name,
  WND_PROP_VISIBLE)` 返回可见才算过（10-13 当场：base 与 `envs\deeplab` 两个解释器都过，
  `window visible=1.0`）。
- 影响面不止手操：`pc/calib_ipm.py`（IPM 外参标定——门 N 那个横向指标卡的正是它）、
  `tools/stream_view.py`、`tools/udp_view.py`、`network/local_single_station.py` 都调
  `imshow`。田里那两天要用它们之前，先照上面三行测一遍。

**PyCharm 里"点运行没反应"的原因（09-21 实例）**：工程开成了父目录 `D:\JetBrains`。`D:\JetBrains\.idea\workspace.xml` 里运行配置数为 **0**，而 `pre_annotate` 那条配置存在 `chucao_prj\.idea\workspace.xml` 里并绑定 `<module name="chucao_prj"/>` —— **PyCharm 不加载嵌套子目录的 `.idea`**。正确做法：以 `D:\JetBrains\chucao_prj` 为工程打开（它自带 4 条配置与 deeplab SDK）。另：设置窗口未关闭时主窗口 ▶ 不响应。

### `firmware/` — 下位机固件（STM32F407，Keil）

| 文件/目录 | 说明 |
|---|---|
| `大车proj/大车/HARDWARE/retrofit/` | **retrofit 模块与串口协议的唯一正身**：`retrofit.c/.h`（改造车控制逻辑，接收上位机指令驱动执行机构）、`protocol.c/.h`（帧解析 + CRC16，与 `common/protocol.py` 一一对应）。Keil 工程 `USER/PWM.uvprojx` 的 `<FilePath>` 只列这里的 `retrofit.c` 与 `protocol.c`，`<IncludePath>` 只到 `..\HARDWARE\retrofit` |
| `集成说明.md` | 固件集成与烧录说明 |
| ~~`retrofit.c/.h`、`protocol.c/.h`（本目录根下）~~ | **已于 2026-10-10 删除（A13，台账 Fw-20）**：那是四份不参与编译的影子副本，改了构建产物与台架表现都不变，只会让人以为改了。删除前它们的内容与 `f0ecf73` 时工程内那版一致（仅行尾 CRLF 差异），git 历史可取回：`git show f0ecf73:firmware/大车proj/大车/HARDWARE/retrofit/retrofit.c` |
| `大车proj/大车/` | 完整 Keil uVision 工程：`USER/main.c` 主程序与中断；`HARDWARE/` 各外设驱动（PWM、电机 `bujin_motor`、`car_control`、`path_plan`、`sensor`、多路 `uart*`、`iic`、`CAN`、`ADC`、`LCD` 等）；`FWLIB/` STM32 标准外设库（官方库文件，不改动）；`OBJ/` 编译产物（.hex/.axf/.o，含可烧录的 `PWM.hex`）；`SYSTEM/` 延时/串口基础库；`keilkilll.bat` 清理编译产物脚本 |

**固件源的位置与编码（2026-10-10，A13 + A14，台账 Fw-20）**

- 固件源**只在** `firmware/大车proj/大车/` 内（`HARDWARE/retrofit/` 与 `USER/`）。`firmware/` 根下曾放过四份同名副本，已删除——它们不在构建清单里，改了对车零影响，只会造成"两份真相"。
- 编码：`HARDWARE/retrofit/retrofit.c`、`retrofit.h`、`protocol.h` 与厂商 `USER/main.c` 现在**统一为 GBK**（A14，作者要中文注释自己能读，Keil 编辑器按本地码页打开）；`protocol.c` 是纯 ASCII（非 ASCII 字节数 = 0，两种编码都能写）。
- 改之前**逐文件试解码**（UTF-8 严格 → GBK 严格 → 都失败就报"混合编码"并停手），别假定全树一种编码；编辑后用同一编码读回并统计"非 ASCII 的变更行"，必须为 0。
- A14 的硬判据：转码**前后各编译一次，`Code`/`RO-data`/`RW-data`/`ZI-data` 逐项一字不差**（注释字节变化不该产生代码）；两次都必须是当场同一条 `UV4 -r` 的读数，不沿用文档里的旧数字。

### `hardware_ref/` — 硬件参考资料



| 文件/目录 | 说明 |
|---|---|
| `大板/` | 主控板 Altium 原理图（`407-cpu/io/power/exp/485.schdoc` 分图 + `大板.pdf` 合图 + `tianjin.PrjPcb` 工程） |
| `大车firmware/` | 改造前原车固件（参考用，勿改动） |

### `data/` — 数据

| 文件/目录 | 说明 |
|---|---|
| `calib_params.npz` | 相机标定结果（1920×1080 原始内参/畸变系数），被 `network/camera_calib.py` 和 `pc/perception.py` 加载 |
| `videos/field_video1~3.avi` | 田间原始视频（共 2.8 GB，已 gitignore，仅存本地） |

### 其他目录

| 目录 | 说明 |
|---|---|
| `avi_frames/` | 田间视频抽帧结果 `img_XXXXXX.jpg`（295 张 1920×1080，已 gitignore） |
| `calib_imgs/` | 标定棋盘格照片 `IMG_XXXX.jpg`（已 gitignore） |
| `model_data/weights/` | 训练权重 `best_model.pth`（已 gitignore）。⚠️ 与只读仓 `chucao_prj/model_data/0.7428m/best_model.pth` **同大小不同 md5**（`32da179c…` vs `cdd22733…`），不是同一个 checkpoint，引用前必须点名 |
| `results/smoke*` | 冒烟测试输出：标定/去畸变/推理样例图与 `run_log.csv` |
| `tests/` | **测试文件数与通过条数以 `python -B -m pytest tests/ -q -p no:cacheprovider` 当场实测为准**——本行不写死数字（抄进文档的那一刻它就变成待检查内容，上一批正是"把检查器的符号抄进计划"害它长红一次）；增长链与最近一次读数记在 AGENTS「当前状态」那一条，那里同样写着"后续每批以实测数为准"。逐个：`test_protocol.py` 协议编解码/CRC 向量 + **E3 的 MODE 载荷、STATUS 14/19 两形态、reject 码与中文文案全覆盖**（**不含** C 对拍，那要台架 B2）；`test_control.py` 控制量与跨边界拆帧 + **E3 主循环组合场景**（持权期间的发帧序列、`run_log` 列名与列位、档案实读值进每一行、按键发 `TYPE_MODE` 而不是靠 NAV 隐含、HUD 每行 ≤85 字符且纯 ASCII）；`test_status_rx.py` STATUS 坏帧/新鲜度/MCU 重启重新同步 + **E3 的按载荷长度分派与 `loop_stalled()`**（v1 固件没这字段 ⇒ 恒 False，不许谎报停摆）；`test_nav_geometry.py` 前轮 Ackermann 几何（直行极限/后轮零角/共 ICC/刚体速度/镜像）；`test_mjpeg.py` TCP 流解析 + 有界读流 `StreamFeed`（含"connect 卡住也不拖住控制循环"）；`test_adaptive_walls.py` 自适应双墙；`test_perception_norm.py` 感知归一化；`test_data_tools.py` 资产安全 + 分组划分（含"文件名没带批次号 → 整批塌成一组"的命名陷阱）；`test_geometry_check.py` 空间口径判据（**只测事实与单位，不测物理结论**）；`test_ipm_io.py` 标定来源校验＋跑真实 solve() 的闭环；`test_pre_annotate.py` 预标注护栏（含"人工改过后重跑仍保留"）；`test_link_probe.py` 反向探针（`--serial` 读数路：跨读边界拼帧、模式跳变序列、序号回退不计好帧）+ **E3 重写后的 `judge()`**（发送前基线与发送后变化分开算、无基线给 INCONCLUSIVE、NAV 的判据是"mode 不许变"、reject 非零算正常响应）——**不需要硬件**；`test_bench_status.py` 台架状态记录器（字段名必须与生产解析器一致、模式跳变单独成行、静默段成对落账；含 09-28 那条盲点回归——**报文一直到达但全被拒收时也必须记 gap**，因为 MCU 重启后序号回退正好就是这个样子）+ **E3 的 `--to` 发送面**（不填即一个字节都不发、`tx_*` 落同一张 CSV、发送序号与接收序号两套计数、NAV 超限拒发且不消耗序号）；`test_wire.py` **E3 的持权发帧纯函数**（AUTO 瞎了那一拍仍发 NAV+TOOL 不发心跳、ESTOP 稳态返回空、未知 permit 一律抛、门 N 下刀恒 `0x07` 横移恒 0、`RUN_LOG_COLUMNS` 与行长一致）；`test_vehicle_profile.py` **E3 的档案加载**（读不到就抛、空串 `''` 不回默认路径、`OSError` 也收口成 `ValueError`、`permit` 只认名字表）；`test_latency_probe.py` **E3 的 D1/D2 假世界**（桥的 500 ms 静默窗口建模、re-arm 门、阈值 0.05 硬下限、打印面随实参走、以及"不许对现场说台账里已有条目"的静态断言）；`test_doc_invariants.py` 文档不变量检查器本身（钉住两条容易做错的语义：规则自己举的反例不计入扫描、基线按出现次数而非行数）。⚠️ 全绿只说明**编码层无回归**，不是任何台架/田间准入（AGENTS 审查清单第 5 条） |
| `docs/缺口清单.md` | **项目"欠账台账"**：顶部『📊 总览：做完的/没做的』板为进度权威，逐项含做法/验收/耗时/依赖 |
| `docs/参数差异台账.md` | **硬件/参数事实的唯一权威**（Hw/Fw/Pc 项 + 改一笔记一笔）。最新编号只增不复用，**以该文件表格当场读到的为准**（本行不写死编号，写死必然落后于包含本行的那次提交） |
| `docs/决策依据说明.md` | 设计决策记录（D1–D8）。⚠️ D8"实车无转向执行器"已作废未标，见台账 Hw-13 |
| `docs/接线图_v1.md` | **整车接线图 v2**（RDK X5 版，全车元件）。⚠️ 文件名仍叫 `_v1` 而内容是 v2——10-12 作者定：**不改名**，版本以文件内标题与文末变更记录为准，引用它的地方一律写"v2 整车版"。章节：§0 全车总览／§1 电源／§2 行走／§3 转向／§4 作业／§5 控制链路／§5A 实物近照核对／§6 人机与辅助／§7 接线顺序与上电前检查单。**上电前先过 §7 那张检查单** |
| `docs/车上供电与接线清单.md` | **供电与接线权威版**（方案 B 定稿 v4，198 行，采购详版，09-12） |
| ~~`docs/车上供电与接线清单_v1.md`~~ | 同上早期版（119 行，09-12 16:49），**已存档**，以 v4 为准 → **2026-10-12 起本地不留**（该文件自己第 3 行就写着"已被取代、仅存档，不要再据此采购或接线"）。取回见本节末『旧版归档说明』 |
| `docs/X5验机与接入执行清单.md` | RDK X5 到货验机四项与接入步骤 |
| `docs/秋季图像采集清单.md` | 秋季采集执行文档（矩阵、命名、标注规范、IPM 顺带标定） |
| `docs/整车尺寸实测表_20260921.md` | **M1–M12 量车型**：每项给测法、照片留档与"这个数用来判什么"；判据在 `tools/geometry_check.py` |
| `docs/thesis_text_fixes_R7_H4.md` | 论文正文修改单（R7/H4 对应项） |
| `docs/大板实物标注.jpg`、`近照A/B/C标注.jpg` | 主控板实物照（13 处编号标注）。**全仓无整机/刀架/电推杆照片**——见量车型 |
| ~~`docs/组会汇报_20260907/`、`docs/组会汇报_20260916/`~~ | 组会 deck（Route C 可编辑 pptx + plan JSON + 证据合同 `paper_analysis.json` + `gen_map.py` 生成的溯源表 + 渲染 QA 图）→ **2026-10-12 起两版都本地不留**：0907 那目录里 5.4 MB 是逐页 png 与单页 pptx 的渲染 QA 中间产物（`export_png.ps1` 可再生），0916 那版是**作者自己先从工作树删掉的**，本次只是把那个删除落进提交。**现行 deck 是下一行的 0923** |
| `docs/组会汇报_20260923/` | **现行组会 deck**：`组会汇报.pptx` + `deck_order_map.md`（逐页溯源表）+ `paper_analysis.json`／`paper_analysis_validation.json`（证据合同）+ `pragmatic_edit_plan.json` + `gen_map.py`／`export_png.ps1`。⚠️ 同目录的 `render_qa/`（逐页 `幻灯片N.PNG` + montage，2.3 MB）属可再生中间产物，**已写进 `.gitignore`、不进仓**——要重出图就跑 `export_png.ps1` |
| `results/` | **台架与冒烟证据，必须进仓**：`bench_YYYYMMDD_HHMM/bench_log.csv` 是 `tools/bench_status.py` 的输出（§4B 的规矩是一格一个目录），`smoke*` 是 IPM／主入口的冒烟产物。台账、缺口清单、E3 spec、§4B 回填表引用的就是这些路径——**不进仓则对侧（zcode）读不到证据**，而 AGENTS"交接事实必须落到受版本控制的文件"这条正是上一批踩过的坑。⚠️ `results/smoke_ipm/ipm_params.json` **不是标定**（源图全黑，见 v1.0 spec 与本仓台账 H5.2 那行），别当外参用 |
| ~~`docs/纯视觉…实施方案_v0.4~v0.7.docx`~~ | 历史总体方案 docx（**已被 md 版方案取代**，见下）→ **2026-10-12 起四份都只留在 git 历史**，本地不再占位。缺口清单 §G 那条针对 v0.7 旧路径的勘误**照旧有效**，只是要先按下面『旧版归档说明』把 docx 取出来再看 |
| `docs/refs/` | 调研原始记录（访谈 raw、原理图核对、参考资料调研、方法章理论材料） |
| `docs/superpowers/specs/2026-09-16-v1.0-system-validation-design.md` | **现行方案**（整机设计与田间系统验证；V1–V4 真值、P/E 修复区、两道准入门） |
| `docs/superpowers/specs/2026-09-08-v0.9-defense-first-design.md` | 已被 v1.0 取代（顶部有横幅），保留作决策史 |
| `docs/superpowers/specs/2026-09-09-4ws-steering-design.md` | 4WS 转向设计稿 |
| `docs/superpowers/specs/2026-08-14-peony-interrow-weeder-design.md` | 最早的系统设计稿 |
| 外部评审件 | 在 **`D:\ai work\codex\docs\reviews\`**（不在本仓）：逐份文件名**以该目录当场 `ls` 为准**，本行不列清单（10-12 起：原先手列的四份早已少于目录实际内容，而没人会回来补这一行） |

### 这几份 md 各管什么（2026-10-12 加：权威分工）

> 用途：回答"这事以哪份文件为准"。下表"管什么"那一列**是每份文件自己写的口径**，不是归类。
> 一句话版：**规矩看 `AGENTS.md`，东西在哪看本文件，数值的唯一出口是台账，还差什么看缺口清单，人站在板子边上时看 X5 清单，为什么这么设计看 specs，当初具体怎么做的看 plans。**

| 层 | 文件 | 管什么 | 不该拿它当什么 |
|---|---|---|---|
| 规矩 | `AGENTS.md` | 工作区边界与只读仓的唯一例外、角色分工（qoder 主写／zcode 审查后合主线）、审查清单、两条硬禁令（禁止实车 AUTO、禁止按现有接线文档直接带动力接线）、**现行测试基线唯一一处写在它的『当前状态』** | 不是进度表，也不写硬件数值 |
| 资产位置 | `README.md`（本文件） | 每个文件与工具在哪、干什么、运行环境与解释器、『旧版归档说明』 | 不定义协议字段，不判准入 |
| 事实 | `docs/参数差异台账.md` | **硬件与参数事实的唯一权威**（Hw／Fw／Pc，改一笔记一笔；AI 只能引用不得自行推测覆盖）、**Keil 编译读数唯一一处**（§4） | 不记待办；实测表填完才是它的输入 |
| 进度／欠账 | `docs/缺口清单.md` | 唯一欠账台账：顶部『📊 总览』是进度权威，正文按 ①做完／②已编码未台架／③明确没做（A 只能作者、B 能写代码但被前置卡、C 等对侧）／④本批没碰／⑤等作者决策 分块 | **不是现场手册**——"按哪个键、看哪一列"要去看 X5 清单 |
| 现场执行 | `docs/X5验机与接入执行清单.md` | §0A 每次开机那两条命令、§4A E3 台架纪律（§4B 自己写着"本表假设 §4A 已读过"）、§4B 批 1a 烧录与对拍的逐格待执行清单（内含 D 段回填表与 E 段"今天办不了／未验边界"） | 不重定义协议字段（指向 E3 契约）；它的格数别抄来抄去，用命令当场数 |
| 设计契约 | `docs/superpowers/specs/2026-09-16-v1.0-system-validation-design.md` | **现行方案**：V1–V4 真值口径、门 N 与门 F 两道准入门、里程碑 | 更早那几份 spec 挂着"已被取代"横幅，只作决策史 |
| 设计契约 | `docs/superpowers/specs/2026-10-08-e3-control-authority-design.md` | **E3 控制权限契约**：`MODE`／`STATUS` 字段、进无人的四条判据、验收场景号、A1–A18 决策原话 | **协议字段以它为准，不以工具注释为准** |
| 设计契约 | `docs/superpowers/specs/2026-10-12-bench-readiness-sync-design.md` | 台架就绪与状态文档同步这一层的设计、范围与可机检判据 | 不新增准入主张 |
| 设计契约 | `docs/superpowers/specs/2026-10-13-pc-manual-channel-design.md` | **手操档（TELEOP）与无人拆档**：三道门 vs 四道门、0.1 m/s 两层钳位、键盘按住语义、带动力前置那两格的判据 | 不是"豁免"文书：两条硬禁令它一条都没撤；`mode=3` 的日志属调试档，**不进论文任何表与结论** |
| 施工图 | `docs/superpowers/plans/*.md` | 每一步具体怎么做、勾选注、**计划自己的勘误**与变异测试证据 | **不是待办清单**；里面写过的当场读数也别当现状用（要重取就用命令重取） |
| 要你手填的实测表 | `docs/整车尺寸实测表_20260921.md`、`docs/四轮行走方向实测表_20260923.md`、`docs/遥控器键位通道映射表_20260923.md` | 现场量车／看发射机才能填的三张表；填完才把数进台账 | **没填完之前不许据此改判据或改固件**（四轮方向那张表就是这么被停住的） |
| 硬件实物 | `docs/车上供电与接线清单.md`（方案 B 定稿 v4）、`docs/接线图_v1.md`（内容是 v2 整车版） | 采购、供电与带动力接线之前必读；接线图那张 §7 检查单是上电前的闸门 | ⚠️ 引用接线图的小节号一律核对是不是 v2 的编号（10-12 已订正台账三条旧指针）；两份文档各有一个 §4A，必须带文件名 |
| 秋采 | `docs/秋季图像采集清单.md` | C1 执行文档（矩阵、命名契约、标注规范），**2026-10-15 那个时限的出处** | 台账与缺口清单只引用它，不复述采集矩阵 |
| 论文 | `docs/thesis_text_fixes_R7_H4.md` ＋只读仓 `chucao_prj/thesis_cau/` | 论文正文改动清单（**待授权**）与论文本体所在 | 本仓不含论文正文 |
| 汇报材料 | `docs/组会汇报_20260923/`（现行 deck + `deck_order_map.md` 逐页溯源） | 对外汇报用什么、每页主张的出处 | **里面的数字不是准入证据**：要引用参数一律回台账取（AGENTS 事实权威序） |
| 原始依据 | `docs/refs/` | 调研记录、大板原理图 PDF 核对、访谈原文、方法章理论材料 | 结论进了台账才算被采用 |

**不在本仓的两处**：外部评审件在 `D:\ai work\codex\docs\reviews\`（**这一行不列文件名**：引用它们的台账／缺口清单各自写了全路径，README 再列一份就是第二张会过期的清单——09-14 复审那条曾在 `docs/缺口清单.md` 里被写成 `docs/reviews/…` 这种本仓不存在的相对路径，10-12 已就地订正，见该节开头）；论文正文在 `D:\JetBrains\chucao_prj\thesis_cau\`（只读仓里唯一被授权可写的子树，提交要走手术式 `git add thesis_cau/...`）。

**一条计数口径**：本节**不写"有几条／有几格／有几份"这类数**（AGENTS 审查清单第 8 条：孤立存在的计数下一批就变成待检查内容）。要数就用命令当场拿，比如台架清单的格数用 `grep -c '^| C' docs/X5验机与接入执行清单.md`。

**一处已当场核实并处理的不一致（10-12 作者定：不改文件名）**：`docs/接线图_v1.md` 的文件名写 v1，而它第一行标题是"整车接线图 v2(RDK X5 版,全车元件)"，本 README 之前还把它描述成"大板接线图 v1"（范围与版本都小了）。处理：**文件名保留**（`README.md`、`docs/缺口清单.md`、`docs/参数差异台账.md` 都按这个路径引用它，改名要全文反查还得给历史留指针，不值），版本以文件内标题与变更记录为准；README 与本节表格改成"整车 v2"；文件顶部加了一条命名说明。**顺带查出更要紧的一条并一起改了**：台账 Hw-2／Hw-3／Hw-4 三条的"出处"列按 v1 时代的章节号引，而该文件 v1→v2 时章节重排过——三条分别被引到"人机与辅助(原车,不动)"、"行走系统"、"转向系统(原车)"，而那三节里根本没有 SL1／刀继电器极性／PB5-PB6-PB7（按 `## N.` 切节后在每节正文里搜关键词当场核到）。台账是唯一事实权威，出处指针领人到错的章节比版本号严重，所以这三条已就地订正、原引用一字不删。同表 Hw-10 引 §2 是**对的**（那节确实是行走电机与霍尔），没顺手改。

### 旧版归档说明（2026-10-12）

作者 10-12 定的口径：**本地只留最新版，旧版全部退到 git 历史里**。下面这些文件**此刻已在那条 GitHub 主线上**（逐条对 `zcode/master` 反查过），所以从工作树移除它们不丢东西——只是要取回得用哈希。

| 从工作树移除的 | 取回办法（10-12 实测：`git log -1 --format='%h %ad' --date=short -- <路径>`，最后一次含该内容的提交） |
|---|---|
| 实施方案 docx **v0.4／v0.5_详细版／v0.6／v0.7** | `git show b6b369d:"docs/纯视觉芍药行间除草机器人_手把手实施方案_v0.7.docx" > 落地路径`（其余三份换路径同理；各自的哈希用上面那条命令现查） |
| `docs/车上供电与接线清单_v1.md` | `git show 975450a:docs/车上供电与接线清单_v1.md > 落地路径` |
| `docs/组会汇报_20260907/`（整目录，其中 5.4 MB 是逐页渲染 QA 的中间产物） | 单文件 `git show 1ca4f72:docs/组会汇报_20260907/组会进展汇报_纯视觉芍药行间除草机器人.pptx > x.pptx`；**整目录**可以用 `git checkout 1ca4f72 -- docs/组会汇报_20260907`，但要知道这条会**顺手把它们暂存**——取回不是为了提交就 `git restore --staged docs/组会汇报_20260907` 退回去 |
| `docs/组会汇报_20260916/`（**作者自己先从工作树删掉的**，本次只是把那个删除落进提交） | 单文件如 `git show 7605995:docs/组会汇报_20260916/deck_order_map.md > x.md` |

表里那四个哈希是**历史里的固定地址**，不是"当前 HEAD／测试条数"那一类每批都会变的读数——AGENTS 审查清单第 8 条管的是后者，所以这里可以写死。要查任何一份文件的全史：`git log --follow --format='%h %ad %s' --date=short -- <路径>`。

**没有一起清掉的两类，以及为什么**：`docs/superpowers/specs/` 与 `docs/superpowers/plans/` 里那些带横幅的旧版设计稿（v0.9、4WS、08-14）**留盘**。它们是**被按路径引用的决策链**——AGENTS『当前状态』的 ⑥ 指 v0.9 那批批准口径，缺口清单与台账逐条指 spec/plan 的具体小节，删掉会把"为什么这么决定"变成只能翻历史；而 docx 与 deck 属**交付物**，新版存在即旧版无用。要一并清也做得，代价是上面那几处指针得同时改成指向哈希。

## 快速上手

> 解释器见上面「运行环境」表：训练与预标注用 `D:\ruanjian\anac\envs\deeplab\python.exe`（或 PATH 里的 `D:\ruanjian\anac\python.exe`）；**别用 `labelme_env`**。
> 权重默认 `model_data/weights/best_model.pth`，标定文件 `data/calib_params.npz`。

### 标注 → 划分 → 训练（C1/C2 链路，**逐步可执行版**）

> 这一段 09-21 复审指出两处会真出事的接口错配，已改：① 旧示例从 `raw/` 划分，
> 但人工修正后的 JSON 在 `pre_annotated/labelme/`，从 `raw/` 划分等于**把人工成果丢掉**；
> ② `split_dataset.scan_pairs()` 只按 `.jpg` 配对，而 `pre_annotate` 接受 PNG/BMP，
> 非 `.jpg` 的图**不会进训练集**（预标注脚本现在会打这句警告）。

```bash
PY=D:/ruanjian/anac/envs/deeplab/python.exe     # 见上面「运行环境」表，别用 labelme_env

# 0) 采集原图放这里。**文件名首段就是分组键**（默认按 _ 切）：
#    t01_0928_0001.jpg → 组 t01。一组 = 一段连续拍摄/一块田/一天。
#    ⚠️ 别用 IMG_0001.jpg 这种全局序号名——每张都切出 IMG，整批塌成 1 组，
#       独立测试集直接不存在（脚本会拒绝，但那是白跑一趟）。见采集清单 §6
#    分组决定 train/val/test 的边界，同一组绝不跨集合（H1.3）
ls data/autumn_data/raw | head

# 1) 半自动预标注：先 --limit 3 小批试跑
$PY tools/pre_annotate.py --input data/autumn_data/raw \
    --output data/autumn_data/pre_annotated --limit 3
#    产物：pre_annotated/labelme/{同名 .jpg + 同名 .json}   ← labelme 要求图与 JSON 同目录
#          pre_annotated/check/check_*.jpg                ← 机器草稿叠加图，仅目检用
#          pre_annotated/重点检查清单.txt                  ← 前景占比异常/无多边形，优先人工复核
#    ⚠️ 重跑同一目录**默认跳过已存在的 JSON**（里面可能有人工修正）。
#       确实要推倒重做才加 --overwrite；同名不同扩展（a.jpg + a.png）直接拒绝。

# 2) 人工复核：labelme 打开 pre_annotated/labelme/（不是 raw/，也不是 check/）
#    labelme 只用于**打开图形界面**时才用 labelme_env 的解释器。
#    标签必须落在冻结字典内（默认写 shaoyao），否则第 5 步严格模式报错。

# 3) 划分：--source 指人工定稿所在的 labelme 目录，不是 raw
$PY tools/split_dataset.py --source data/autumn_data/pre_annotated/labelme \
    --out-root model_data --dry-run        # 先看组数与三集合分配
$PY tools/split_dataset.py --source data/autumn_data/pre_annotated/labelme \
    --out-root model_data --force          # 分组不足 3 组会直接拒绝，不再静默退回逐图
#    产物：model_data/{train,val,test}/images/{.jpg,.json} + 空的 masks/
#          model_data/split_manifest.json   ← 分组已冻结，训练与复核都以它为准
#    ⚠️ --force 会清空目标目录；源目录与输出目录重叠时脚本会拒绝（R2 修复）

# 4) 生成 mask：split 只建空 masks/ 目录，要自己跑 json2mask（三个集合各一次）
for s in train val test; do
  $PY tools/json2mask.py --input model_data/$s/images --output model_data/$s/masks
done
#    全背景掩码会单独点名（多半是标签名不在冻结字典里或该图未标注）

# 5) 训练
$PY network/train_m.py                     # 读 model_data/{train,val,test}/{images,masks}
```

**口径提醒（复审 §6）**：训练集可以用模型预标注再人工修正，但**评价用的真值要独立制作并复核**。
看过算法输出、只纠正了几处明显错处的草稿，不能当无偏真值；
S0 用来调阈值的数据也要与最终留出评价分开记用途。

### 回放推理（离线验证整条链路）

```bash
python pc/main.py --source data/videos/field_video1.avi          # 完整控制循环（replay 模式）
python pc/replay.py data/videos/field_video1.avi --step 15       # 仅回放推理并保存结果
```

### 实车运行

```bash
python pc/main.py --live --pi-ip 192.168.127.10 --stream-host 192.168.127.10 --stream-port 5000
```

> ⚠️ 两条硬禁令仍然有效：**禁止实车 AUTO、禁止按现有接线文档带动力接线**（解除条件见 `docs/缺口清单.md` 门 N／门 F）。

### 测试

```bash
python -B -m pytest tests/ -q        # 通过条数以本命令当场输出为准；这里不写死数字（理由见上面 tests/ 那一行）
python -B tools/check_doc_invariants.py   # 圈编号/交叉引用全仓枚举；exit 0 才算干净
```

## 数据流

田间视频（`data/videos/`）→ 抽帧（`avi_frames/`）→ **`tools/pre_annotate.py` 半自动预标注**（labelme JSON + 叠加目检图）→ **在 `pre_annotated/labelme/` 里用 labelme 人工复核修正**（重跑预标注默认跳过已有 JSON，不覆盖人工成果）→ `tools/split_dataset.py` **分组划分 + 冻结 `split_manifest.json`**（`--source` 指人工定稿目录，不是 `raw/`）→ `tools/json2mask.py` 按集合转 mask → `network/train_m.py` 训练 → 权重（`model_data/weights/`）→ `pc/main.py` 感知（去畸变/标定 → 分割 `network/` → IPM 鸟瞰（⚠️ 现在仍是 `perception.py` 里的**占位几何**；`pc/ipm_io.py` 这个带来源校验的加载器**还没有调用方**，接线属 E2③ 未完项）→ **`tools/morph_process.py` 双墙提取 + 最小二乘导航线拟合**：远场线给底盘、近场线给中间刀）→ `pc/state_machine.py`/`pc/control.py` → 串口协议（`common/protocol.py` ↔ `firmware/大车proj/大车/HARDWARE/retrofit/protocol.c`）→ 车端网关（RDK X5，`vehicle/`）→ STM32 固件（`firmware/`）驱动执行机构。
