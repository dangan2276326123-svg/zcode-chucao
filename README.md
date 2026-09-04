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
| `perception.py` | 感知封装：加载权重与标定 → 去畸变 → 分割 → 形态学后处理 → IPM |
| `control.py` | 控制量计算与下发（转向/速度） |
| `state_machine.py` | 作业状态机（待机/作业/掉头/急停等状态切换） |

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
| `morph_process.py` | 分割结果形态学后处理（开闭运算、小连通域剔除），被 `pc/perception.py` 和 `network/local_single_station.py` 导入 |
| `split_dataset.py` | 训练/验证集划分 |

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
| `avi_frames/` | 田间视频抽帧结果 `img_XXXXXX.jpg`（已 gitignore） |
| `calib_imgs/` | 标定棋盘格照片 `IMG_XXXX.jpg`（已 gitignore） |
| `model_data/weights/` | 训练权重 `best_model.pth`（已 gitignore） |
| `results/smoke*` | 冒烟测试输出：标定/去畸变/推理样例图与 `run_log.csv` |
| `tests/test_protocol.py` | 串口协议单元测试（Python↔C 一致性） |
| `tests/test_control.py` | 控制量计算单元测试 |
| `docs/秋季图像采集清单.md` | 秋季田间采集执行文档（矩阵、命名、标注规范、IPM 标定顺带采集） |
| `docs/缺口清单.md` | 项目"欠账台账"：每项含做法/验收标准/耗时/依赖，完成打 ✅ |
| `docs/纯视觉芍药行间除草机器人_手把手实施方案_v0.4~v0.7.docx` | 项目总体实施方案（v0.7 为最新） |
| `docs/refs/` | 调研原始记录（`_lijun_raw.txt`、`_wangshuo_raw.txt` 访谈记录；原理图 PDF 核对、参考资料调研、方法章理论材料） |
| `docs/superpowers/specs/2026-08-14-peony-interrow-weeder-design.md` | 系统设计稿（brainstorming 产物） |

## 快速上手

### 环境

Python 3 + PyTorch + OpenCV（`pip install torch opencv-python numpy pyyaml`）。权重路径默认 `model_data/weights/best_model.pth`，标定文件 `data/calib_params.npz`。

### 训练

```bash
python network/train_m.py
```

### 回放推理（离线验证整条链路）

```bash
python pc/main.py --source data/videos/field_video1.avi          # 完整控制循环（replay 模式）
python pc/replay.py data/videos/field_video1.avi --step 15       # 仅回放推理并保存结果
```

### 实车运行

```bash
python pc/main.py --live --pi-ip <树莓派IP>
```

### 测试

```bash
python -m pytest tests/ -q
```

## 数据流

田间视频（`data/videos/`）→ 抽帧（`avi_frames/`）→ 标注（JSON）→ `tools/json2mask.py` 转 mask → `tools/split_dataset.py` 划分 → `network/train_m.py` 训练 → 权重（`model_data/weights/`）→ `pc/main.py` 感知（分割 `network/` + 标定/IPM + `tools/morph_process.py` 后处理）→ `pc/state_machine.py`/`pc/control.py` → 串口协议（`common/protocol.py` ↔ `firmware/protocol.c`）→ 树莓派桥接（`vehicle/`）→ STM32 固件（`firmware/`）驱动执行机构。
