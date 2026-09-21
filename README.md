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
| `protocol.py` | 串口通信协议（帧格式、CRC、命令字），与下位机 `firmware/protocol.c` 一一对应 |
| `uart_vectors.py` | 控制量/状态量的串口向量编解码 |

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
| `status_rx.py` | MCU STATUS 接收（live 模式，UDP 9100）：坏帧捕获计数绝不裸抛（D7 约束），滚动 1 秒 ≥5 坏帧报警（多半是固件/Python 协议字段失同步）；纯逻辑类，socket 留在 main |
| `ipm_io.py` | **IPM 外参加载器（带来源校验）**：拒绝无来源字段、`points_source != field`、源图近乎纯色/全黑、重投影超 2 cm、点数 <4、**车辆档案不匹配**的标定文件。存在的原因：仓库里那份 `results/smoke_ipm/ipm_params.json` 看着像标定，其实源图全黑（mean=0/std=0），只是求解器的冒烟测试 |

### `vehicle/` — 车端（树莓派）

| 文件 | 说明 |
|---|---|
| `stream_pi.py` | 树莓派上抓取相机图像并回传给上位机 |
| `bridge.py` | PC ↔ 下位机桥接：把上位机控制量经串口转给 STM32，回传状态 |
| `config.yaml` | 车端配置（PI_IP、串口号等） |

### `tools/` — 数据处理脚本

| 文件 | 说明 |
|---|---|
| `check_dataset.py` | 数据集完整性检查（图/mask 对齐、类别统计） |
| `json2mask.py` | 标注 JSON → 训练用灰度 mask |
| `morph_process.py` | 分割结果后处理 + **导航线拟合**（被 `pc/perception.py` 和 `network/local_single_station.py` 导入）：`extract_dual_walls` 从 IPM 鸟瞰掩膜提取左右垄墙 → `fit_centerline_lsq` 对双墙各拟合 x=a·y+b 取中点 → `fit_centerline_lsq_weighted` 裁剪最小二乘 + 按内点率加权融合（遮挡鲁棒，单墙退化时门控回退）→ 输出 lookahead 行的横向偏差 `center_x` |
| `split_dataset.py` | **数据集划分（分组模式）**：按 视频/地块/日期 前缀整组划分，杜绝邻帧跨集合（H1.3）；冻结 `split_manifest.json`；硬性保证 train/val/test 各≥1 组，组数 <3 直接拒绝而非静默退回逐图；源目录先校验后清空，`--force` 才清目标 |
| `geometry_check.py` | **整车空间口径判据（只报事实，不报结论）**：要 N 把刀各进一条等距草带，车宽至少 `(N−1)·s + 刀宽`。`track_span` 给"轮距等于几个行距／离整行距还差多少／几何上是否可能对得上行"，**不输出压苗结论**——旧版那句"车宽>行距即压在作物行上"是 09-21 复审撤回的过度推论（行距 38.2 时轮距 191 恰为 5 个行距，两轮正落在行间）；判压苗要另量胎宽（M14）与轮迹对行线偏差（M15）。`slide_reach_verdict` 按"总行程 = 2 × 单侧需求"判够不够（旧实现拿总行程跟单侧比，会把 30 cm 报成够）。未实测的量返回"不下结论"，不补默认值。配合 `docs/整车尺寸实测表_20260921.md` |
| `pre_annotate.py` | **半自动预标注**（DeepLabV3+ → labelme JSON + 叠加目检图）：qoder 工作区版，缺依赖时打人话提示、输出默认锁在工作区内、打印权重 md5/mtime 与解释器路径。原脚本在只读仓 `chucao_prj/annotation_tools/`，不改它 |
| `启动预标注.bat` | 预标注启动入口（写死可用解释器）。**故意只写 ASCII**：.bat 里的中文必须 GBK 编码，否则 cmd 显示乱码 |

### 运行环境 — 用哪个解释器（09-21 实测，别再猜）

| 用途 | 解释器 | 已验证 |
|---|---|---|
| 训练 / 预标注 / 感知推理 | `D:\ruanjian\anac\envs\deeplab\python.exe`（conda env `deeplab`，Python 3.9.23） | numpy 2.0.2、cv2 5.0.0、torch 2.6.0+cu124、torchvision 0.21.0、albumentations 2.0.8；`pre_annotate.py` 跑通，设备 cuda |
| 同上（备用，`python` 在本机 PATH 里就是它） | `D:\ruanjian\anac\python.exe` | 352 张预标注全过，rc=0 |
| **只**用于打开 labelme 图形界面 | `chucao_prj\annotation_tools\labelme_env\Scripts\python.exe` | ⚠️ 该 venv **只有 labelme 5.10.1 + numpy**，没有 torch/albumentations/cv2 —— 拿它跑 `.py` 必然 `ModuleNotFoundError: No module named 'cv2'` |
| matplotlib 绑图 | ❌ 两个环境都不可用 | numpy 2.0.2 与已编译的 1.x 冲突（ImportError）。曲线改用 python-pptx 原生图表或 CSV |

**PyCharm 里"点运行没反应"的原因（09-21 实例）**：工程开成了父目录 `D:\JetBrains`。`D:\JetBrains\.idea\workspace.xml` 里运行配置数为 **0**，而 `pre_annotate` 那条配置存在 `chucao_prj\.idea\workspace.xml` 里并绑定 `<module name="chucao_prj"/>` —— **PyCharm 不加载嵌套子目录的 `.idea`**。正确做法：以 `D:\JetBrains\chucao_prj` 为工程打开（它自带 4 条配置与 deeplab SDK）。另：设置窗口未关闭时主窗口 ▶ 不响应。

### `firmware/` — 下位机固件（STM32F407，Keil）

| 文件/目录 | 说明 |
|---|---|
| `protocol.c/.h` | 串口协议实现（帧解析、CRC），与 `common/protocol.py` 对应 |
| `retrofit.c/.h` | 改造车控制逻辑（接收上位机指令驱动执行机构） |
| `集成说明.md` | 固件集成与烧录说明 |
| `大车/HARDWARE/retrofit/` | 上述 retrofit 模块在 Keil 工程内的副本 |
| `大车proj/大车/` | 完整 Keil uVision 工程：`USER/main.c` 主程序与中断；`HARDWARE/` 各外设驱动（PWM、电机 `bujin_motor`、`car_control`、`path_plan`、`sensor`、多路 `uart*`、`iic`、`CAN`、`ADC`、`LCD` 等）；`FWLIB/` STM32 标准外设库（官方库文件，不改动）；`OBJ/` 编译产物（.hex/.axf/.o，含可烧录的 `PWM.hex`）；`SYSTEM/` 延时/串口基础库；`keilkilll.bat` 清理编译产物脚本 |

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
| `tests/` | **11 个测试文件，`python -B -m pytest tests/ -q` = **120 passed（09-21 复审批次后实测）**。逐个：`test_protocol.py` 协议编解码/CRC 向量（**不含** C 对拍，那要台架 B2）；`test_control.py` 控制量与跨边界拆帧；`test_status_rx.py` STATUS 坏帧/新鲜度/MCU 重启重新同步；`test_nav_geometry.py` 前轮 Ackermann 几何（直行极限/后轮零角/共 ICC/刚体速度/镜像）；`test_mjpeg.py` TCP 流解析；`test_adaptive_walls.py` 自适应双墙；`test_perception_norm.py` 感知归一化；`test_data_tools.py` 资产安全 + 分组划分；`test_geometry_check.py` 空间口径判据（**只测事实与单位，不测物理结论**）；`test_ipm_io.py` 标定来源校验＋跑真实 solve() 的闭环；`test_pre_annotate.py` 预标注护栏（含"人工改过后重跑仍保留"） |
| `docs/缺口清单.md` | **项目"欠账台账"**：顶部『📊 总览：做完的/没做的』板为进度权威，逐项含做法/验收/耗时/依赖 |
| `docs/参数差异台账.md` | **硬件/参数事实的唯一权威**（Hw/Fw/Pc 项 + 改一笔记一笔）。当前到 Hw-19 |
| `docs/决策依据说明.md` | 设计决策记录（D1–D8）。⚠️ D8"实车无转向执行器"已作废未标，见台账 Hw-13 |
| `docs/接线图_v1.md` | 大板接线图 v1（含 §4A 待改项） |
| `docs/车上供电与接线清单.md` | **供电与接线权威版**（方案 B 定稿 v4，198 行，采购详版，09-12） |
| `docs/车上供电与接线清单_v1.md` | 同上早期版（119 行，09-12 16:49），**已存档**，以 v4 为准 |
| `docs/X5验机与接入执行清单.md` | RDK X5 到货验机四项与接入步骤 |
| `docs/秋季图像采集清单.md` | 秋季采集执行文档（矩阵、命名、标注规范、IPM 顺带标定） |
| `docs/整车尺寸实测表_20260921.md` | **M1–M12 量车型**：每项给测法、照片留档与"这个数用来判什么"；判据在 `tools/geometry_check.py` |
| `docs/thesis_text_fixes_R7_H4.md` | 论文正文修改单（R7/H4 对应项） |
| `docs/大板实物标注.jpg`、`近照A/B/C标注.jpg` | 主控板实物照（13 处编号标注）。**全仓无整机/刀架/电推杆照片**——见量车型 |
| `docs/组会汇报_20260907/`、`docs/组会汇报_20260916/` | 组会 deck（Route C 可编辑 pptx + plan JSON + 证据合同 `paper_analysis.json` + `gen_map.py` 生成的溯源表 + 渲染 QA 图） |
| `docs/纯视觉…实施方案_v0.4~v0.7.docx` | 历史总体方案 docx（**已被 md 版方案取代**，见下） |
| `docs/refs/` | 调研原始记录（访谈 raw、原理图核对、参考资料调研、方法章理论材料） |
| `docs/superpowers/specs/2026-09-16-v1.0-system-validation-design.md` | **现行方案**（整机设计与田间系统验证；V1–V4 真值、P/E 修复区、两道准入门） |
| `docs/superpowers/specs/2026-09-08-v0.9-defense-first-design.md` | 已被 v1.0 取代（顶部有横幅），保留作决策史 |
| `docs/superpowers/specs/2026-09-09-4ws-steering-design.md` | 4WS 转向设计稿 |
| `docs/superpowers/specs/2026-08-14-peony-interrow-weeder-design.md` | 最早的系统设计稿 |
| 外部评审件 | 在 **`D:\ai work\codex\docs\reviews\`**（不在本仓）：09-09 整体审查、09-14 复审、09-15 论文聚焦复审、09-21 增量复审 |

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

# 0) 采集原图放这里；文件名首段就是分组键（默认按 _ 切），例 A3_000123.jpg → 组 A3
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
python -B -m pytest tests/ -q   # 09-21 复审批次后基线：120 passed
```

## 数据流

田间视频（`data/videos/`）→ 抽帧（`avi_frames/`）→ **`tools/pre_annotate.py` 半自动预标注**（labelme JSON + 叠加目检图）→ **在 `pre_annotated/labelme/` 里用 labelme 人工复核修正**（重跑预标注默认跳过已有 JSON，不覆盖人工成果）→ `tools/split_dataset.py` **分组划分 + 冻结 `split_manifest.json`**（`--source` 指人工定稿目录，不是 `raw/`）→ `tools/json2mask.py` 按集合转 mask → `network/train_m.py` 训练 → 权重（`model_data/weights/`）→ `pc/main.py` 感知（去畸变/标定 → 分割 `network/` → IPM 鸟瞰（⚠️ 现在仍是 `perception.py` 里的**占位几何**；`pc/ipm_io.py` 这个带来源校验的加载器**还没有调用方**，接线属 E2③ 未完项）→ **`tools/morph_process.py` 双墙提取 + 最小二乘导航线拟合**：远场线给底盘、近场线给中间刀）→ `pc/state_machine.py`/`pc/control.py` → 串口协议（`common/protocol.py` ↔ `firmware/protocol.c`）→ 车端网关（RDK X5，`vehicle/`）→ STM32 固件（`firmware/`）驱动执行机构。
