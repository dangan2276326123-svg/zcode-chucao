# 项目：纯视觉芍药行间除草机器人（硕士论文样机）

本工作区是唯一开发区。`D:\JetBrains\chucao_prj` 等原仓库**只读，禁止修改**。

## 当前状态（2026-09-02）
- 方案 v0.7（docs/纯视觉芍药行间除草机器人_手把手实施方案_v0.7.docx）为最新执行版本
- 阶段：W1 基本完成——protocol.py（10 测试通过）+ pc/perception.py + pc/replay.py 离线回放均已交付；训练域测试图验证 status=dual 链路正确；avi 帧存在域差异（过分割 fg≈0.55），待秋季微调。待办：push（网络恢复后 git push）、STM32 串口测试向量、秋季采集清单
- 每完成一个模块：跑测试、更新本文件的"当前状态"、git commit（本工作区自己 init 了仓库）

## 关键事实（不要重新推导）
- 底盘：滑移转向，四轮独立驱动（TIM1 PWM：PE9/PE11/PE13/PE14，经 74HC245→DR25 外接控制器）
- 线控方案 A：固件内 SBUS/UDP 双指令源，SBUS=PA10（USART1+DMA），遥控优先无条件回手动
- 运动学：差速模型 vL/vR（Ackermann4WS 已弃用，nav_control.py 中仅参考）
- 感知：DeepLabV3+ MobileNetV2 二分类 → IPM → 双墙中心线（morph_process.py 的 peony_postprocess 可复用）
- 权重统一用 model_data/weights/best_model.pth（0.7428m 那套是旧目录，勿混用）
- 标定：calib_params.npz（keys: mtx, dist, newcameramtx, mapx, mapy），1920x1080 标定，IPM 参数需低机位重标

## STM32 引脚分配（新增功能，禁止改动既有占用）
| 用途 | 引脚 |
| --- | --- |
| 树莓派 UART | USART6: PC6(TX)/PC7(RX) |
| 刀继电器 ×3 | PD4 / PD5 / PD6 |
| 中间刀步进 PULSE/DIR/EN | PB6(TIM4_CH1) / PB5 / PB7 |
| 限位开关 ×3 | PD15 / PD10 / PD11 |
| 轮速捕获（恢复） | PB0/PB1/PA6/PA7（TIM3，代码在 pwm.c 已注释） |

既有占用（禁复用）：PA10 SBUS、PE9/11/13/14 四轮 PWM、PA5 刹车继电器、PF10 主继电器、PF8 示廓灯、PC0 LED1、PA2/PA3 USART2 编码器、PC10/PC11 UART4 伺服、PC12/PD2 UART5 串口屏、PD0/PD1 CAN、PB8/9+PB10/11 软 I2C（ADS1115）、PF14/13/11 拨码、PF3 EXTI。PG8 双重定义（MP3 vs uart2），二选一。

## 通信协议（v0.4 表 3）
帧：0xA5 0x5A | len u16 LE | type u8 (1导航/2急停/3心跳/4刀具/0x10状态) | seq u16 LE | payload | CRC16-CCITT-FALSE（覆盖帧头之后全部字节）
- MCU 500ms 无心跳 → 急停+提刀；ESTOP 锁存须人工复位
- 导航帧载荷：vL, vR (f32)；状态帧载荷：车速、电流 AD5/AD6、限位状态

## 已知坑（新代码必须规避）
- camera_calib.py:13 硬编码绝对路径且 import 时加载 → 重构为延迟加载+配置
- local_single_station.py:85 取帧元组嵌套 bug；frame=None 死循环
- train_m.py:822 test 模式 NameError
- KalmanLateral dt 固定 0.05s 不更新 → 重构时用实测 dt
- morph_process.py 单墙回退 ±200px 魔法数
- 路径含空格（"D:\ai work\zcode"），脚本引用必须加引号

## 测试与交付纪律
- 每个模块配 pytest（tests/），改完必跑：python -m pytest tests -v
- 算法侧验收标准见 v0.7 §3 交付矩阵
- 用户负责：机械装配、STM32 实物改造、田间采集（清单见 v0.7 §4.4）
