# 纯视觉芍药行间除草机器人

本项目为纯视觉（单目相机，无 RTK/激光雷达）芍药行间除草机器人的完整工程：包括 DeepLabV3+ 语义分割训练、相机标定与 IPM 逆透视变换、导航控制、上位机（PC）主控循环、车端（树莓派）桥接与下位机（STM32）固件。

## 目录结构

```
zcode/
├── network/            # 深度学习与感知算法（Python）
│   ├── train_m.py      #   主分割模型训练入口（DeepLabV3+）
│   ├── train_h.py / train_r.py / train_x.py   # 其他实验训练脚本
│   ├── modeling.py / _deeplab.py / backbone/  # 网络结构定义
│   ├── camera_calib.py #   相机标定 + IPM（加载 data/calib_params.npz）
│   ├── nav_control.py  #   航向误差 → 控制量
│   ├── local_single_station.py  # 本地单工位端到端推理链路
│   └── predict_demo.py #   推理演示
├── pc/                 # 上位机主控（Python）
│   ├── main.py         #   完整控制循环入口（replay / live 模式，GUI 叠加，急停联锁）
│   ├── replay.py       #   视频回放推理
│   ├── perception.py   #   感知封装（分割 + IPM + 后处理）
│   ├── control.py      #   控制输出
│   └── state_machine.py#   作业状态机
├── vehicle/            # 车端（树莓派）
│   ├── stream_pi.py    #   图像回传
│   ├── bridge.py       #   PC ↔ 下位机桥接
│   └── config.yaml     #   车端配置（PI_IP 等）
├── firmware/           # 下位机固件（C / STM32）
│   ├── protocol.c/.h   #   串口协议
│   ├── retrofit.c/.h   #   改造车控制逻辑
│   ├── 大车 / 大车proj  #   Keil 工程与集成代码
│   └── 集成说明.md
├── tools/              # 数据处理脚本
│   ├── check_dataset.py    # 数据集检查
│   ├── json2mask.py        # 标注 JSON → mask
│   ├── morph_process.py    # 分割结果形态学后处理（被 pc/、network/ 引用）
│   └── split_dataset.py    # 训练/验证集划分
├── data/               # 数据（不入 git 的放 videos/）
│   ├── calib_params.npz    # 相机标定结果（1920x1080 原始参数）
│   └── videos/             # field_video1~3.avi 田间原始视频（已 gitignore）
├── avi_frames/         # 田间视频抽帧结果（已 gitignore）
├── calib_imgs/         # 标定棋盘格照片（已 gitignore）
├── model_data/weights/ # 训练权重 best_model.pth（已 gitignore）
├── hardware_ref/       # 硬件参考资料（原理图、大车固件等）
├── results/            # 推理/回放输出
├── tests/              # pytest 单元测试（协议、控制）
├── docs/               # 设计文档（实施方案 v0.4~v0.7 docx、秋季图像采集清单、缺口清单、refs、superpowers 设计稿）
└── AGENTS.md           # AI 协作约定
```

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

田间视频（`data/videos/`）→ 抽帧（`avi_frames/`）→ 标注（JSON）→ `tools/json2mask.py` 转 mask → `tools/split_dataset.py` 划分 → `network/train_m.py` 训练 → 权重（`model_data/weights/`）→ `pc/main.py` 感知（分割 `network/` + 标定/IPM + `tools/morph_process.py` 后处理）→ `pc/state_machine.py`/`pc/control.py` → 串口协议 → 树莓派桥接（`vehicle/`）→ STM32 固件（`firmware/`）驱动执行机构。
