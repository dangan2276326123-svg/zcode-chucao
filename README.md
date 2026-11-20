# 纯视觉芍药行间除草机器人

本项目为纯视觉（单目相机，无 RTK/激光雷达）芍药行间除草机器人的完整工程：DeepLabV3+ 语义分割训练、相机标定与 IPM 逆透视变换、导航控制、上位机（PC）主控循环、车端（RDK X5）桥接与下位机（STM32）固件。

> **本文件只回答三件事：东西在哪、干什么、怎么跑。**
> 进度看 `docs/缺口清单.md` 顶部总览；硬件数值看 `docs/参数差异台账.md`；人站在板子边上时看 `docs/X5验机与接入执行清单.md`；规矩看 `AGENTS.md`。
> 旧版 README 给每个文件写了长注（批次历史、踩坑细节、设计理由），2026-11-13 已一字不动搬进 [`docs/README_详注存档_20261113.md`](docs/README_详注存档_20261113.md)。本文件只留结论与指针，要查"为什么"去存档或对应的台账／spec。

## 这事以哪份文件为准（权威分工）

> 一句话版：**规矩看 `AGENTS.md`，东西在哪看本文件，数值的唯一出口是台账，还差什么看缺口清单，人站在板子边上时看 X5 清单，为什么这么设计看 specs，当初具体怎么做的看 plans。**

| 层 | 文件 | 管什么 | 不该拿它当什么 |
|---|---|---|---|
| 规矩 | `AGENTS.md` | 工作区边界与只读仓唯一例外、qoder 主写／zcode 审查的分工、审查清单、两条硬禁令（禁止实车 AUTO、禁止按现有接线文档直接带动力接线）、现行测试基线唯一落点（它的『当前状态』） | 不是进度表，也不写硬件数值 |
| 资产位置 | `README.md`（本文件） | 每个文件与工具在哪、干什么、运行环境、旧版归档说明 | 不定义协议字段，不判准入 |
| 事实 | `docs/参数差异台账.md` | 硬件与参数事实的唯一权威（Hw／Fw／Pc，改一笔记一笔）、Keil 编译读数唯一落点（§4） | 不记待办；实测表填完才是它的输入 |
| 进度／欠账 | `docs/缺口清单.md` | 唯一欠账台账，顶部『📊 总览』是进度权威 | 不是现场手册——"按哪个键、看哪一列"去看 X5 清单 |
| 现场执行 | `docs/X5验机与接入执行清单.md` | 每次开机两条命令（§0A）、E3 台架纪律（§4A）、烧录与对拍逐格清单（§4B） | 不重定义协议字段（指向 E3 契约）；格数用命令当场数 |
| 设计契约 | `docs/superpowers/specs/2026-09-16-v1.0-system-validation-design.md` | **现行方案**：V1–V4 真值口径、门 N／门 F 两道准入门、里程碑 | 更早的 spec 挂"已被取代"横幅，只作决策史 |
| 设计契约 | `docs/superpowers/specs/2026-10-08-e3-control-authority-design.md` | E3 控制权限契约：MODE／STATUS 字段、进无人判据、验收场景、决策原话 | 协议字段以它为准，不以工具注释为准 |
| 设计契约 | `docs/superpowers/specs/2026-10-12-bench-readiness-sync-design.md` | 台架就绪与状态文档同步的设计与可机检判据 | 不新增准入主张 |
| 设计契约 | `docs/superpowers/specs/2026-10-13-pc-manual-channel-design.md` | 手操档（TELEOP）与无人拆档：三道门 vs 四道门、限速两层钳位、带动力前置判据 | 不是"豁免"文书，两条硬禁令一条没撤；手操日志属调试档，不进论文 |
| 施工图 | `docs/superpowers/plans/*.md` | 每一步具体怎么做、勾选注、计划自己的勘误与变异测试证据 | 不是待办清单；里面的当场读数别当现状用 |
| 要你手填的实测表 | `docs/整车尺寸实测表_20260921.md`、`docs/四轮行走方向实测表_20260923.md`、`docs/遥控器键位通道映射表_20260923.md` | 现场量车／看发射机才能填的三张表，填完才把数进台账 | 没填完之前不许据此改判据或改固件 |
| 硬件实物 | `docs/车上供电与接线清单.md`（方案 B 定稿 v4）、`docs/接线图_v1.md`（内容是 v2 整车版） | 采购、供电与带动力接线前必读；接线图 §7 检查单是上电前闸门 | 引用接线图小节号先核对是不是 v2 编号；两份文档各有一个 §4A，必须带文件名 |
| 采集 | `docs/秋季图像采集清单.md` ＋ `docs/秋采一天执行表_20261103.md` | 采集矩阵、命名契约、标注规范；一天测完的顺序表与填空栏 | 秋采已取消并入春测（2026-11-05），两份保留作春测模板 |
| 论文 | `docs/thesis_text_fixes_R7_H4.md` ＋ 只读仓 `chucao_prj/thesis_cau/` | 论文正文改动清单与论文本体所在 | 本仓不含论文正文 |
| 汇报材料 | `docs/组会汇报_20260923/`（现行 deck + 逐页溯源表） | 对外汇报用什么、每页主张的出处 | 里面的数字不是准入证据，引用参数一律回台账取 |
| 原始依据 | `docs/refs/` | 调研记录、原理图核对、访谈原文、方法章理论材料 | 结论进了台账才算被采用 |
| 证据边界 | 本表＋下方"三个感知模型"表 | **调车证据 ≠ 论文证据**：画线＋漏沙是春测前的工程调通，不进论文；论文实验只有春季田间一处。协同创新方法（设计）见 `docs/决策依据说明.md` D19 | 不许拿调车偏差当田间指标；也不许因"调车不算论文"就跳过它 |

**不在本仓的两处**：外部评审件在 `D:\ai work\codex\docs\reviews\`（文件名以当场 `ls` 为准，本行不列清单）；论文正文在 `D:\JetBrains\chucao_prj\thesis_cau\`（只读仓唯一可写子树，提交走手术式 `git add thesis_cau/...`）。

**计数口径**：本文件不写"有几条／几格／几份"这类数（AGENTS 审查清单第 8 条），要数就用命令当场拿。

## 快速上手

> 解释器见下方「运行环境」表：训练与预标注用 `D:\ruanjian\anac\envs\deeplab\python.exe`（或 PATH 里的 `D:\ruanjian\anac\python.exe`）；**别用 `labelme_env`**（它只有 labelme，没有 torch/cv2）。
> 权重默认 `model_data/weights/best_model.pth`，标定文件 `data/calib_params.npz`。

### 标注 → 划分 → 训练

```bash
PY=D:/ruanjian/anac/envs/deeplab/python.exe

# 0) 原图放 data/autumn_data/raw/。文件名首段是分组键（按 _ 切）：
#    t01_0928_0001.jpg → 组 t01。别用 IMG_0001.jpg 这种全局序号名——整批塌成 1 组，
#    独立测试集直接不存在。同一组绝不跨 train/val/test（H1.3）

# 1) 半自动预标注（先 --limit 3 小批试跑）
$PY tools/pre_annotate.py --input data/autumn_data/raw \
    --output data/autumn_data/pre_annotated --limit 3
#    重跑默认跳过已有 JSON（里面可能有人工修正），推倒重做才加 --overwrite

# 2) 人工复核：labelme 打开 pre_annotated/labelme/（不是 raw/，也不是 check/）
#    标签必须落在冻结字典内（默认 shaoyao）

# 3) 划分：--source 指人工定稿的 labelme 目录，不是 raw/
$PY tools/split_dataset.py --source data/autumn_data/pre_annotated/labelme \
    --out-root model_data --dry-run        # 先看组数与分配
$PY tools/split_dataset.py --source data/autumn_data/pre_annotated/labelme \
    --out-root model_data --force          # 分组不足 3 组直接拒绝；--force 会清空目标目录

# 4) 生成 mask（split 只建空目录，三个集合各跑一次）
for s in train val test; do
  $PY tools/json2mask.py --input model_data/$s/images --output model_data/$s/masks
done

# 5) 训练
$PY network/train_m.py
```

**口径提醒**：训练集可以预标注再人工修正，但**评价用的真值要独立制作并复核**；看过算法输出只纠了几处的草稿不能当无偏真值。

### 回放与实车

```bash
python pc/main.py --source data/videos/field_video1.avi    # 离线回放（完整控制循环）
python pc/replay.py data/videos/field_video1.avi --step 15 # 仅回放推理并保存结果
python pc/main.py --live --pi-ip 192.168.127.10 --stream-host 192.168.127.10 --stream-port 5000
```

> ⚠️ 两条硬禁令仍然有效：**禁止实车 AUTO、禁止按现有接线文档带动力接线**（解除条件见 `docs/缺口清单.md` 门 N／门 F）。

### 测试与文档检查

```bash
python -B -m pytest tests/ -q             # 通过条数以当场输出为准，不写死数字
python -B tools/check_doc_invariants.py   # 圈编号/交叉引用全仓枚举；exit 0 才算干净
python -B tools/check_citations.py        # 坐标式引用审计（报告不是闸，退出码恒 0）
```

## 目录地图

### 根目录

| 文件 | 说明 |
|---|---|
| `README.md` | 本文件：目录/文件说明 + 快速上手 |
| `AGENTS.md` | AI 协作工作约定（规矩与审查清单） |
| `.gitignore` | 忽略规则（视频、抽帧、标定图、权重等；Keil OBJ 编译产物已另行清理出库） |
| `thesis_latest.docx` | 论文最新产物的覆盖式副本（每次生成重写，已 gitignore）；权威产物与版本清单在 `chucao_prj/thesis_cau/10_output/` |

### `common/` — PC/车端共用模块

| 文件 | 说明 |
|---|---|
| `protocol.py` | 串口协议（帧格式、CRC、命令字），与固件 `protocol.c` 一一对应；含 MODE、STATUS 14/19 两形态、拒绝码。⚠️ PC 侧与固件侧要同步烧录才两侧生效（E3 spec） |
| `uart_vectors.py` | B2 台架对拍向量表 + USB-TTL 手发 sender；组数以 `--dump` 当场输出为准，含两条必须被丢弃的坏帧 |
| `capture_naming.py` | 采集落盘命名契约（段名与段号规则），`capture_field` 与 `record_local` 共用。只准依赖标准库（板子上没 cv2 也得能 import） |

### `network/` — 深度学习与感知算法

| 文件 | 说明 |
|---|---|
| `train_m.py` | 主分割模型训练入口（DeepLabV3+ MobileNetV2，960×720，二分类） |
| `train_h.py` / `train_r.py` / `train_x.py` | 其他骨干/配置的实验训练脚本 |
| `train_metric_log.csv`（及 `_backup`） | 训练过程指标日志（内部证据；论文/报告/PPT 不写其中的张数与指标数值，2026-11-12 作者裁定） |
| `modeling.py` / `_deeplab.py` | DeepLabV3+ 模型组装与核心结构（ASPP、Decoder） |
| `backbone/` | MobileNetV2（主用）、ResNet、Xception、HRNetV2（备选） |
| `camera_calib.py` | 标定适配器：加载 `data/calib_params.npz`，去畸变 + IPM |
| `nav_control.py` | 行中心线偏差/航向误差 → 差速控制量 |
| `local_single_station.py` | 本地单工位端到端链路自测 |
| `predict_demo.py` | 单张/文件夹推理演示（可视化叠加） |
| `utils.py` | 数据集加载、指标、损失等训练辅助 |

### `pc/` — 上位机（笔记本）主控

| 文件 | 说明 |
|---|---|
| `main.py` | 完整控制循环入口：`--source` 回放 / `--live` 实车，GUI 叠加，急停联锁 |
| `replay.py` | 视频/图片目录逐帧回放推理并保存结果 |
| `perception.py` | 感知封装：权重+标定 → 去畸变 → 分割 → IPM → 导航线拟合（远场线给底盘、近场线给中间刀）。⚠️ IPM 目前仍是占位几何，真外参接线未完（E2③） |
| `control.py` | 4 个纯 Python 控制类（无 torch/cv2 依赖）：中间刀 PID（限幅 ±50 mm）、时延估计与超前补偿、误差变化率、底盘差速。⚠️ 四轮转向+差速混合重写未做（P0-1） |
| `state_machine.py` | 作业状态机（待机/作业/掉头/急停） |
| `perception_worker.py` | 感知后台线程：单槽信箱、新帧顶旧帧，主拍不阻塞；给出"画面最后一字节 → 本拍下命令"的管道延迟，供超前补偿用 |
| `wire.py` | "这一拍往线上发什么"的唯一出处（持权必发 NAV+TOOL、MANUAL 只发心跳、ESTOP 稳态空）；也是 `run_log.csv` 列名权威——新列只往末尾挂 |
| `vehicle_profile.py` | 车辆档案加载：读不到就报错停下，绝不回默认值 |
| `status_rx.py` | STATUS 接收（UDP 9100）：按载荷长度分派 14/19，坏帧计数不裸抛，1 秒 ≥5 坏帧报警 |
| `ipm_io.py` | IPM 外参加载器（带来源校验）：拒绝无来源、非田间源图、重投影超限、档案不匹配的标定文件 |

### `config/` — PC 侧配置

| 文件 | 说明 |
|---|---|
| `vehicle_profile.yaml` | 三个平铺键：`profile_id`（1=上代车 / 2=样机，只作记录）、`permit`（gate_n 空跑 / gate_f 允许落刀）、`log_tag`（写进 run_log 每行的车型标记）。⚠️ 上电握手用途已取消（作者 10-15 裁定，台账 §4）；`log_tag` 与 `permit` 都是 fail-closed，缺失/非法直接开不起来；运行中不热切 |

### `vehicle/` — 车端（RDK X5；目录名与部分注释沿用"树莓派"）

| 文件 | 说明 |
|---|---|
| `start_bridge.sh` | 一条命令起桥：`sh ~/qoder/vehicle/start_bridge.sh`。必须 LF 换行（.gitattributes 已钉） |
| `start_bench.sh` | 一条命令起台架（桥+推流）：`sh ~/qoder/vehicle/start_bench.sh [1080p|stop]`。判据是进程在/TCP 连得上，链路通不通另看 `tools/bench_status.py` |
| `bridge.py` | PC ↔ STM32 桥接：控制量经串口转发，状态回传 |
| `stream_pi.py` | 相机抓取并回传上位机（`--width/--height` 可切 1080p） |
| `record_local.py` | X5 本地录像：行进段画面唯一留得住的路（相机直录板子自己的盘，回来 scp 再抽帧）。`--check`/`--probe` 先验相机/avimux/盘。`--session-min` 按总时长到点自停（人在遥控上够不着键盘），日志每段落一行、`started` 是该段开始时刻。⚠️ 四态只到"已编码+已本机单测"，板上三处未验——到田里第一件事就是验它，不通退回"停车+网线+逐张拍"。停录用 Ctrl-C 或 `kill -INT`，不许 kill -9 |
| `collect_demo.sh` | **画线漏沙采集一键入口（2026-11-20）**：`sh vehicle/collect_demo.sh [批次] [分钟] [每段秒] [MMDD]`。先跑 `--check --probe`（有 🔴 就停手），再 `nohup` 后台开录到点自停——车开走、SSH 断开也不影响；提前停用 `kill -INT <PID>`。落 `data/paint_data/video/t{NN}_{MMDD}_v{NN}.avi`，现场步骤见 `docs/画线漏沙采集_20261120.md`。⚠️ 只在本机单测过，X5 上首次跑仍按"到田里第一件事"验 |
| `config.yaml` | 车端配置（serial_dev/baud/udp_port/pc_ip/pc_port/stream/watchdog_ms）。没有 `PI_IP` 字段，旧说法作废 |

### `tools/` — 工具脚本

| 文件 | 说明 |
|---|---|
| `bench_status.py` | 台架验收记录器：STATUS 帧、模式跳变、静默 gap、场景标记写同一张 CSV；`--to` 可选发送面。⚠️ 与 `pc/main.py` 独占 UDP 9100，同时只能开一个；NAV 有 0.20 m/s 硬闸 + 门 N 许可闸；用法前提是驱动轮离地 |
| `bench_limits.py` | 台架限速的唯一出处（0.20 m/s，fail-closed）+ 刀指令许可判定；三个发帧入口共用这一个闸 |
| `link_probe.py` | PC → 大板反向探针（只发不收、不 bind，可与记录器并存）；按命令定义预期响应，reject 非零是正常响应不是链路不通 |
| `latency_probe.py` | 延迟自测：D1=链路延迟、D2=含机械响应，两个数必须分开报（论文口径：链路=D1，机械≈D2−D1） |
| `check_dataset.py` | 数据集完整性检查（图/mask 对齐、类别统计） |
| `json2mask.py` | 标注 JSON → 训练用灰度 mask |
| `morph_process.py` | 分割后处理 + 双墙提取 + 最小二乘导航线拟合（被 perception 与单工位链路导入） |
| `split_dataset.py` | 分组划分（按视频/地块/日期前缀整组，杜绝邻帧跨集合），冻结 split_manifest；组数 <3 直接拒绝 |
| `check_doc_invariants.py` | 文档不变量检查器（圈号区间全仓枚举；exit 0 干净 / 1 禁用命中 / 2 基线漂移 / 3 有文件读不进） |
| `check_citations.py` | 坐标式引用审计（路径:行号／§节号），分 HARD/CHECK/SOFT 三档报告；退出码恒 0，是报告不是闸 |
| `geometry_check.py` | 整车空间口径判据，只报事实不报结论（压苗与否必须实测横断面）；现行设计输入行距 60 cm／刃宽 50 cm（台账 Hw-38） |
| `capture_field.py` | 停车特写 + IPM 素材逐张拍（连 X5 的 TCP MJPEG）；行进段录像已改走 `record_local.py` |
| `extract_frames.py` | 采集视频抽帧：间隔按位移算（≥0.5 m），同视频默认拒绝重抽；工具不做任何筛选（筛验证/测试集等于让判卷老师进考场） |
| `fake_cam.py` | 合成相机推流：没相机没下田时把整条链跑完。⚠️ 只能证明通路——跟踪精度、伤苗率、时延一个都不许从这条路取 |
| `bench_run.py` | 台架一键（起桥+合成流+主控三窗）；只替"怎么开"，不替任何判据与安全前置；`--out` 目录已有 run_log 就停手 |
| `pre_annotate.py` | 半自动预标注（DeepLabV3+ → labelme JSON + 目检图），默认不覆盖已有人工标注 |
| `启动预标注.bat` / `台架一键.bat` | 双击入口（写死解释器；.bat 正文只写 ASCII，中文由 python 侧打印） |
| `md_to_docx_sheet.py` | docs/ 的 md 执行表 → A4 Word 打印件（同名 docx 落 md 旁，不进仓可再生） |
| `make_thesis_docx.py` | 论文 Word 生成器：正文零域，插图按 `figures_manifest.md`（唯一事实源），公式原样落纸待作者手录；全部校验读数只写 `10_output/word_版本清单.md` 一处 |
| `make_thesis_diagrams.py` | 论文框图绘制（技术路线/架构/感知链/三回路）；每格每箭头必须来自正文原文，不许多加部件 |
| `check_thesis_sections.py` | 论文章节号引用检查：论文源码没有节号（编号由 Word 大纲位置决定），改结构后必须跑它 |
| `eval_test_set.py` | 独立测试集评测：指标函数 import 不自写、权重哈希随结果出、`--input-size` 必须显式给定、`--split val` 对照跑不出已知值则 test 的数不能当真 |

### `firmware/` — 下位机固件（STM32F407，Keil）

| 文件/目录 | 说明 |
|---|---|
| `大车proj/大车/` | 上代车（3.25 m）完整 Keil 工程；retrofit 模块与协议在 `HARDWARE/retrofit/`。**11-05 起保持逐字节不动**（作者裁定） |
| `样机proj/样机/` | 新实车（样机 2.15 m）工程，从上代整份复制；只允许两处不同：`USER/main.c` 轮 4 转向符号（W4_A/W4_B 两宏）与 `retrofit.h` 的 PROFILE_ID。可烧录件 `OBJ/PWM.hex` |
| `集成说明.md` | 固件集成与烧录说明 |

三条硬规矩（细节与教训见存档）：

- **两棵工程树除白名单外逐字节相同**，由 `tests/test_firmware_projects.py` 当场执行；改共用模块（retrofit、protocol、path_plan…）必须同一次提交改两份。
- **`firmware/` 下源文件一律字节级改**：retrofit.c 是混合编码，整文件"读成文本再写回"会静默写坏中文行；改前逐文件试解码，改后按原编码读回核对。
- 根目录曾有四份不参与编译的影子副本，2026-10-10 已删（台账 Fw-20）；固件源只在两棵工程树内。

### `hardware_ref/` — 硬件参考资料

| 文件/目录 | 说明 |
|---|---|
| `大板/` | 主控板 Altium 原理图（分图 + 合图 PDF + 工程） |
| `大车firmware/` | 改造前原车固件（参考用，勿改动） |

### `data/` — 数据

| 文件/目录 | 说明 |
|---|---|
| `calib_params.npz` | 相机标定结果（1920×1080 内参/畸变），被 camera_calib 与 perception 加载 |
| `videos/field_video1~3.avi` | 田间原始视频（共 2.8 GB，gitignore，仅存本地） |

**三个感知模型，不许混（2026-11-12 加）**：

| 模型 | 数据域 | 用途 | 能不能进论文 |
|---|---|---|---|
| A 夏季芍药 | 夏季田间真芍药（`avi_frames/` 那批） | **论文模型**：现权重 `model_data/weights/best_model.pth`，验证/测试指标以 `network/train_metric_log.csv` 与台账为准 | ✅ 论文感知指标只从它出 |
| B 画线替身 | 地面画线模拟芍药带（**未采集、未训练**，2026-11-12 作者计划的调车方案） | **调车专用**：春测前先把导航与刀控调通，配漏沙 tracer 看走线偏差 | ❌ 它的一切读数都是工程调试，不进论文任何表与结论 |
| C 春测真芍药 | 春季田间真芍药（3 月底 4 月初采集） | 届时**换数据集重训**，直接进田间试验 | ✅ 论文田间试验（ch05）的感知与效果数据从它出 |

换模型 = 换数据集重训，不是拿 B 的权重冒充 A/C；B 存在的全部意义是"把车调好等春天"，调车证据与论文证据的边界见上方权威分工表末行。

### 其他目录与文档

| 目录/文件 | 说明 |
|---|---|
| `avi_frames/` | 田间视频抽帧（295 张 1920×1080，gitignore） |
| `calib_imgs/` | 标定棋盘格照片（gitignore） |
| `model_data/weights/` | 训练权重（gitignore）。⚠️ 与只读仓 `chucao_prj/model_data/0.7428m/best_model.pth` 同大小不同 md5，不是同一个 checkpoint，引用前必须点名 |
| `results/` | **台架与冒烟证据，必须进仓**（台账/spec/回填表引用的就是这些路径，不进仓对侧读不到）。⚠️ `results/smoke_ipm/ipm_params.json` 不是标定（源图全黑），别当外参用 |
| `tests/` | 测试文件数与通过条数以 `python -B -m pytest tests/ -q -p no:cacheprovider` 当场实测为准；增长链记在 AGENTS『当前状态』。⚠️ 全绿只说明编码层无回归，不是任何台架/田间准入 |
| `docs/缺口清单.md` | 项目欠账台账，顶部『📊 总览』为进度权威 |
| `docs/参数差异台账.md` | 硬件/参数事实唯一权威；最新编号只增不复用，以文件当场读到的为准 |
| `docs/决策依据说明.md` | 设计决策记录 D1–D19（编号以当场读到的为准；D19=底盘—中间刀协同方法，只到已设计）。⚠️ D8"实车无转向执行器"已作废未标，见台账 Hw-13 |
| `docs/接线图_v1.md` | **整车接线图 v2**（RDK X5 版）。⚠️ 文件名仍叫 _v1 是作者定的不改名，版本以文件内标题为准；上电前先过 §7 检查单 |
| `docs/车上供电与接线清单.md` | 供电与接线权威版（方案 B 定稿 v4）；_v1 早期版已退 git 历史（见下方归档说明） |
| `docs/X5验机与接入执行清单.md` | X5 验机四项与接入步骤、台架逐格清单 |
| `docs/秋季图像采集清单.md` / `docs/秋采一天执行表_20261103.md` | 采集执行文档与一天顺序表；秋采已取消，保留作春测模板 |
| `docs/整车尺寸实测表_20260921.md` | M1–M12 量车型：测法、照片留档、这个数用来判什么 |
| `docs/方位与轮序编号约定_20261024.md` | 沟通用两套编号（方向 1=刀面=作业方向；轮 1 左前/2 右前/3 右后/4 左后）及与固件下标的对照。**描述方位只用这张表，别自造编号** |
| `docs/thesis_text_fixes_R7_H4.md` | 论文正文修改单（R7/H4 对应项） |
| `docs/大板实物标注.jpg`、`近照A/B/C标注.jpg` | 主控板实物照（13 处编号标注）。全仓无整机/刀架/电推杆照片 |
| `docs/组会汇报_20260923/` | 现行组会 deck + 逐页溯源表 + 证据合同；render_qa/ 是可再生中间产物（gitignore）。0907/0916 两版已退 git 历史 |
| `docs/refs/` | 调研原始记录（访谈、原理图核对、方法章理论材料） |
| `docs/superpowers/specs/` | 现行方案 v1.0 与 E3 等契约；v0.9、4WS、08-14 旧稿挂横幅留盘作决策链（被按路径引用，不删） |
| `docs/README_详注存档_20261113.md` | 本文件旧版全文（逐文件长注：批次历史、踩坑细节、设计理由），2026-11-13 搬入 |

## 运行环境 — 用哪个解释器（09-21 实测，别再猜）

| 用途 | 解释器 | 已验证 |
|---|---|---|
| 训练 / 预标注 / 感知推理 | `D:\ruanjian\anac\envs\deeplab\python.exe`（conda env `deeplab`，Python 3.9.23） | numpy 2.0.2、cv2 5.0.0、torch 2.6.0+cu124；预标注跑通，设备 cuda |
| 同上（备用，`python` 在 PATH 里就是它） | `D:\ruanjian\anac\python.exe` | 352 张预标注全过 |
| **只**用于打开 labelme 图形界面 | `chucao_prj\annotation_tools\labelme_env\Scripts\python.exe` | ⚠️ 只有 labelme + numpy，拿它跑 .py 必然缺 cv2 |
| matplotlib 绑图 | ❌ 两个环境都不可用 | numpy 2.0.2 与编译期 1.x 冲突；曲线改用 CSV 或其他画法 |

**cv2.imshow 开窗（10-13 实测）**：opencv-python 与 opencv-python-headless 不能共存（headless 的 imshow 必抛）。修 = 两个都卸、只装 `opencv-python==5.0.0.93`；判据 = 窗口真开出来（`getWindowProperty` 可见），不是看 build info。凡要用 imshow 的工具（main.py 手操、calib_ipm、stream_view 等）下田前先照此测一遍。细节见存档。

**PyCharm"点运行没反应"**：工程要以 `D:\JetBrains\chucao_prj` 打开（运行配置在它的 .idea 里），开父目录 `D:\JetBrains` 加载不到嵌套配置；另设置窗口未关时 ▶ 不响应。

## 旧版归档说明（2026-10-12）

作者定的口径：**本地只留最新版，旧版全部退到 git 历史里**。下面这些文件已在 GitHub 主线上（逐条对 `zcode/master` 反查过），取回用哈希：

| 从工作树移除的 | 取回办法 |
|---|---|
| 实施方案 docx v0.4／v0.5_详细版／v0.6／v0.7 | `git show b6b369d:"docs/纯视觉芍药行间除草机器人_手把手实施方案_v0.7.docx" > 落地路径`（其余换路径同理） |
| `docs/车上供电与接线清单_v1.md` | `git show 975450a:docs/车上供电与接线清单_v1.md > 落地路径` |
| `docs/组会汇报_20260907/`（整目录） | 单文件 `git show 1ca4f72:docs/组会汇报_20260907/组会进展汇报_纯视觉芍药行间除草机器人.pptx > x.pptx`；整目录 `git checkout 1ca4f72 -- <目录>` 会顺手暂存，取回不提交就 `git restore --staged` 退回 |
| `docs/组会汇报_20260916/`（作者自己先删的，提交只是落账） | 单文件如 `git show 7605995:docs/组会汇报_20260916/deck_order_map.md > x.md` |

这四个哈希是历史里的固定地址，不是每批会变的读数，可以写死。查任何文件全史：`git log --follow --format='%h %ad %s' --date=short -- <路径>`。

**没有一起清掉的**：specs/ 与 plans/ 里带横幅的旧设计稿留盘——它们是被按路径引用的决策链，删掉"为什么这么决定"就只能翻历史；docx 与 deck 属交付物，新版存在即旧版无用。

## 数据流

1. 田间视频（`data/videos/`）→ 抽帧（`avi_frames/`）
2. `tools/pre_annotate.py` 半自动预标注 → 在 `pre_annotated/labelme/` 用 labelme 人工复核（重跑不覆盖人工成果）
3. `tools/split_dataset.py` 分组划分 + 冻结 manifest → `tools/json2mask.py` 转 mask → `network/train_m.py` 训练 → 权重（`model_data/weights/`）
4. `pc/main.py` 感知：去畸变/标定 → 分割 → IPM 鸟瞰（⚠️ 仍是占位几何，`pc/ipm_io.py` 加载器还没有调用方，接线属 E2③ 未完项）→ `tools/morph_process.py` 双墙提取 + 最小二乘拟合（远场线给底盘、近场线给中间刀）
5. `pc/state_machine.py` / `pc/control.py` → 串口协议（`common/protocol.py` ↔ 固件 `protocol.c`）→ 车端网关（RDK X5，`vehicle/`）→ STM32 固件驱动执行机构