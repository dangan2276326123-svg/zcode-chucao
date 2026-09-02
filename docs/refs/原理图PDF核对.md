# 大板原理图 PDF 核对报告

来源：`D:\ai work\zcode\hardware_ref\大板\大板.pdf`（7 页，A4 横向，Altium 导出矢量图）。
方法：pymupdf 提取全部文字对象及坐标（逐页存于 `D:\ai work\tmp\page0~6.txt`），按坐标邻近区域匹配元件位号-网络关系；本报告所有结论均给出可复查的文字坐标证据。

## 页序确认（实际与任务假设不同）

| PDF 页(0基) | 内容 | 证据 |
|---|---|---|
| p0 | 4路485通讯 | "4路485通讯"、4×MAX13487 |
| p1 | CPU（STM32F407ZGT6） | "STM32F407ZGT6"×3 |
| p2 | IO/扩展（74HC245×N、DR25 J1/J2、LM393 轮速、T5/T4/LED_IN） | "74HC245D"×5、"DR25-公头"×2 |
| p3 | 传感器/AD（TJA1050、MP3、ADS1115、DS1、EEPROM） | "TJA1050"、"ADS1115"×2 |
| p4 | 电源+继电器（XT60、48_to_24/12、SL1/SRD1/SRD2、ACS712） | "XT60"、"48_to_24"、"SLA-05VDC-SL-A" |
| p5 | 外设连接器页（MPU/DTU/T6/T8/T11、SBUS/PWM，含 SL1/SRD/DS1 丝印） | "COMPU"、"COuart0sbus" |
| p6 | PCB 预览（几乎无矢量文字） | "Board" |

下文页码用 p0~p5（0 基）。

---

## 1. PA5 → R149 → SS8050 → SL1（大继电器）——驱动链证实，触点用途与 SchDoc 不同

- p4 坐标区 (460~570, 370~520)：`PA5_PWM1 → R149(1K) → NPN4(SS8050) → SL1 (SLA-05VDC-SL-A)`，线圈电源 5_B_V，续流 D9(SS14)/D25/D26(SS34)。
- **触点不是切换 XT60 T2**。SL1 触点两侧网络是 `MOTOR_1_1` 与 `MOTOR_1_2`（跨接 0R R4、SS210 D23）：`MOTOR_1_1` 来自 `VCCIN_24_A_1`（48_to_24 U24 输出，经 0R），`MOTOR_1_2` 接 DR25 **J2 引脚 12/13（MOTOR_1_2）与 24/25（MOTOR_1_1）** 引出。即 SL1 是串在电机控制器 24V 供电回路（MOTOR_1）上的大继电器；T1/T2 XT60 只是 48V VIN 输入（两者并联，无切换逻辑）。
- 另注意 p4 右侧同结构有 `NBREAK1 / CONBREAK1（CH3.96_2P，丝印"强制不刹车1"）+ SW_IN + SW2/SW3` 网络，属于刹车串入端子组（见第 2 条）。
- **与 SchDoc 差异**：SchDoc"SL1 切换 T2 电机电源"证伪；实际 SL1 切 MOTOR_1 的 24V 供电通断。

## 2. PF10 → NPN → SRD1 主继电器；NBREAK2——证实

- p4 (496~650, 216~300)：`PF10_OUT → R6(1K) → NPN2(SS8050) → SRD1 (SRD-05VDC-SL-C)`，线圈 5_B_V，线圈回路串 `CONBREAK2（NBREAK2，CH3.96_2P 端子）`。
- NBREAK2 是主继电器控制回路的外接断点（旁边 SW_IN/SW3、R1/R2 0R 只焊一个默认 R1、丝印"强制不刹车1"）——急停/刹车开关可串入此处。与 SchDoc 判断一致，更准确说是"刹车串入端子"。

## 3. PF8 → SRD2；PC0 → LED_1——证实

- p4：`PF8_OUT → R8(1K) → NPN3(SS8050) → SRD2 (SRD-05VDC-SL-C)`（触点侧 12V/5_B_V）。
- p4：`PC0 → R148(1K) → NPN1(SS8050) → LED_1 (3mm_led, 12V)`；旁边同结构还有 PG5 一路 LED 驱动。

## 4. 485 四路 MAX13487 映射——全部证实；U7 A_4/B_4 → T6 排针（无外设痕迹）

- p0：U10=PA2/PA3→A_1/B_1（T8）、U9=PC10/PC11→A_2/B_2（T8）、U8=PC12/PD2→A_3/B_3（T6）、**U7=PC7_485(RO)/PC6_485(DI)→A_4/B_4**（R15/R16 0K 串接、R71/R72 120R 端接、D21/D22 SMF6.0CA TVS、R79/R80 10K）。
- U7 的 A_4/B_4 走到 p0 右下 **T6（2.0_2*4P 排针，8 脚）**，T6 另两对脚为 A_3/B_3；p0 还有 T8（A_1/A_2/B_1/B_2）、T11（2.54_1*3P，UART4/PD12/PF5）、DTU Header-7、MPU 8P（PA0/PA1/PB8/PB9/PF0/PF1/RXD/TXD/WAK/RST/GPS/PG12/PG13/I2C2）。
- **PDF 中无任何 T6 外接设备型号痕迹**——只是预留 485 外接口。结论：USART6(PC6/PC7) 是否空闲取决于实车 T6 是否插线（另注意 485 第 1/2 路还并到了 DR25 J1/J2 的 A_1/B_1、A_2/B_2，见第 11 条）。

## 5. SW_reserv_CH1-8 → 74HC245 → T5——部分证实（网络名不同，T5 脚号已定位）

- p2 U6 (74HC245D) 区域 (470~620, 200~290)：输入 A0..A7 = **PD7,PD6,PD5,PD4,PD3,PE4,PE5,PE6**，输出 B0..B7 = PD7_OUT…PE6_OUT。**PDF 中不存在 "SW_reserv_CHx" 网络名**（该命名可能来自 Exp 板或 SchDoc 旧称）。
- T5（2.0_2*8P，16 脚，(690~790, 200~285)）：1/2=12V；左列（奇数）≈ **3=PE4_OUT、5=PD3_OUT、7=PD4_OUT、9=PD5_OUT、11=PD6_OUT**、13=PD7_OUT、15=GND 侧；右列（偶数）≈4=PE5_OUT、6=PE6_OUT、8/10=CANL/CANH、16=GND（脚号按行坐标推断，±1 行）。
- 即 PD4/PD5/PD6 对应 T5 的 **7/9/11 脚**（奇数列）。

## 6. 轮速 Hall→LM393→H_out→PB0/PB1/PA6/PA7——证实

- p2 (390~800, 60~140)：U20(LM393B)：Hall_1→H_out1→R7(0R)→**PB0**；Hall_2→H_out2→R5(0R)→**PB1**（2.5V 基准 R34 30k）。
- U21(LM393B)：H_out3→R10(0R)→**PA6**；H_out4→**PA7**（PA7/H_out4 同在 U21 区域 (740~800, 60~110)）。
- Hall_1-4 来自 DR25：J2 6/19 脚=Hall_1/Hall_2（丝印"左前/右前"），J1 6/19 脚=Hall_3/Hall_4（"左后/右后"）。

## 7. CAN 与 ADS1115——证实（U18 通道细节更正）

- p3 (330~520, 230~300)：U13 TJA1050：`PD1→TXD(pin1)`、`PD0→RXD(pin4)`（旁注 `PD0:CAN1_RX / PD1:CAN1_TX`），CANH/CANL + R136 120R，注释"去掉R107,R108"。
- U17 ADS1115：I2C1 = **PB8(SCL)/PB9(SDA)**，AIN0..AIN3 = AD1/AD2/AD3/AD4，ADDR→GND，5V_32 供电（C5 100nF）。✓
- U18 ADS1115：I2C2 = **PB10(SCL)/PB11(SDA)**，AIN0=**AD5**、AIN1=**AD6**、AIN3=**PWM_DC**（页注：AD6=刹车电流/电池电压、AD7(3.3V)=3.3V 电压、AD8(PWM_DC)=遥控电压）。SchDoc"AD5/AD6/PWM_DC"证实，PWM_DC 实为 AIN3（AD8 通道）。

## 8. ACS712 与 LM358——证实

- p4 (630~800, 420~520)：U22 (ACS712ELCTR-05B)：IP+/IP- 串 **MOTOR_2_2 回路**（R27/R28 0R），`VIOUT → AD5`（C15/D7/R11 10K/R12 1K 滤波，AD5 网络坐标 683,499）。✓
- U19 (LM358B, p4 (300~430, 420~470))：OUT1/OUT2 输出至 AD6 相关网络，+A3.3V 供电。✓

## 9. 拨码 DS1 / PD9-PD15 / MP3——部分证实，DS1 有更正

- p3 (630~760, 310~370)：DS1 = **DSIC03LS-P（3 位拨码）**，开关 1/2/3 = **PF12 / PF14 / PF13**，4/5/6=GND。SchDoc"PF14/PF13/PF11"中 **PF11 证伪，实为 PF12**。
- p2 (460~800, 415~500)：PD9/PD10/PD11/PF3 → U5 (74HC245) → PD9_IN/PD10_IN/PF3_IN…，另有 PD12_IN/PD13_IN/PD14_IN 去 **T4**（2.0 排针，含 LED_IN1/12V，p2 (698~800, 455~500)）；**T10** 在 p3 (690~740, 180~200) 一带。方向与 SchDoc"备用输入 PD9-PD15 → T4/T10"一致。
- MP3 模块 MP3（COMP3，18 脚，3.3_MP3 供电，SPK+/SPK- 经 R89 0K，DACL/DACR）：引脚为 **PG0,PG1,PG2,PG3,PG5,PG6,PG7,PG8**（p3 (30~180, 90~130)）。SchDoc"PG3-PG8"不完整（PG0/PG1/PG2 也在；未见 PG4）。

## 10. 电源树——证实

- p4：T1/T2 两个 XT60 输入 VIN（丝印 `VIN=46V~54V`，D3~D6 SS210）→ **U24/U23（48_to_24，R114/R115 6.8K 反馈，LED_24/LED_24_B）输出 VCCIN_24_A_1 / VCCIN_24_A_2** → 经 0R → **MOTOR_1_1 / MOTOR_2_1** → DR25 J2/J1 引出（外接电机控制器）。
- **U25（48_to_12）→12V** → **U26/U27（12V→5v_temp）** → **U14/U15 (LP5300B6F)** → 5_A_V / 5V_32；另有 5_A_V(1.5A)/5_B_V(1.5A) 分轨、3.3V。与 SchDoc 电源树一致（48_to_12 输出 12V，5v_temp 由 U26/U27 产生）。

## 11. XT60 T1/T2 与 DR25 J1/J2 引脚-网络表（实车接线用）

两个 XT60 均为 4 脚：+ = VIN(46~54V)、- = GND（另有 GND 焊点脚）；T1/T2 并联，无切换。

**DR25-公头 J2**（电机1/前轴侧，Hall_1=左前、Hall_2=右前）：

| 脚 | 网络 | 脚 | 网络 |
|---|---|---|---|
| 1 | B_1(485) | 14 | A_1(485) |
| 2 | B_2(485) | 15 | A_2(485) |
| 3 | PE2_OUT | 16 | PC8_OUT / PE11_OUT* |
| 4 | PC4_OUT / PF6_OUT* | 17 | PC3_OUT / PF7_OUT* |
| 5 | PE0_OUT / PE8_OUT* | 18 | PC6_OUT / PE9_OUT* |
| 6 | Hall_1 | 19 | Hall_2 |
| 7 | AD1 | 20 | AD3 |
| 8 | GND（旁 5_B_V） | 21 | GND |
| 9 | PF1_IN / PA4_IN* | 22 | PE13_IN / PC3_IN* |
| 10 | PE14_IN / PC2_IN* | 23 | PF2_IN / PC1_IN* |
| 11 | SW2 | 24 | MOTOR_1_1 |
| 12 | MOTOR_1_2 | 25 | MOTOR_1_1 |
| 13 | MOTOR_1_2 | 26/27 | GND |

**DR25-公头 J1**（电机2/后轴侧，Hall_3=左后、Hall_4=右后）：

| 脚 | 网络 | 脚 | 网络 |
|---|---|---|---|
| 1 | B_1(485) | 14 | A_1(485) |
| 2 | B_2(485) | 15 | A_2(485) |
| 3 | PE3_OUT / PA12_OUT* | 16 | PC9_OUT / PE14_OUT* |
| 4 | PC4_OUT / PF6_OUT* | 17 | PC3_OUT / PF7_OUT* |
| 5 | PE1_OUT / PA11_OUT* | 18 | PC7_OUT / PE13_OUT* |
| 6 | Hall_3 | 19 | Hall_4 |
| 7 | AD4 | 20 | AD2 |
| 8 | GND（旁 5_B_V） | 21 | GND |
| 9 | PE12_IN / PF15_IN* | 22 | PF0_IN / PF12_IN* |
| 10 | PE10_IN / PC5_IN* | 23 | PA5_IN / PC4_IN* |
| 11 | SW2 | 24 | MOTOR_2_1 |
| 12 | MOTOR_2_2 | 25 | MOTOR_2_1 |
| 13 | MOTOR_2_2 | 26/27 | GND |

（\* = 该脚旁出现两个网络标签，PDF 文字坐标无法唯一归属；MOTOR_x_1 为 48_to_24 供电进线，MOTOR_x_2 为经 SL1/SRD1 触点后的出线。J1 第 2 列另有一组不带 _IN/_OUT 的短名 PF0/PF1/PA4/PA5/PC1-PC5/PE10/PE12/PE13/PE14（坐标 x≈270-273 列），为 J1 第二排引脚网络。）
**注意**：485 第 1/2 路（A_1/B_1、A_2/B_2）直接引到了 J1/J2——DR25 电缆里含 485 总线。

## 12. CPU 丝印与 BOOT——F103 证伪、F407 证实；无 BOOT 跳线

- p1 三处丝印 **STM32F407ZGT6**（U1；引脚文本含 PA0-WKUP、PB8/SDIO_D4、PC6/I2S2_MCK 等 F407 命名）。SchDoc 的 "F103ZET6" 是旧符号误标，以 PDF 的 F407ZGT6 为准（这也意味着主频 168MHz、CCM RAM 等 F407 特性可用）。
- BOOT0(pin25) 仅 R113 10K 下拉 + RST/KEY（C45）复位电路；BOOT1=PB2。**未发现 BOOT0/BOOT1 选择跳线**——若需串口 ISP 需飞线，SWD 烧录不受影响。

---

## 对 B6 实物确认清单的影响

**可从实车清单划掉（PDF 已定）：**
- CPU 型号（STM32F407ZGT6，非 F103）；DS1 拨码位（PF12/PF14/PF13）；T5 上 PD4/PD5/PD6=7/9/11 脚；TJA1050=PD0/PD1；ADS1115 U17/U18 的 I2C 与通道分配；ACS712→AD5、LM358→AD6；SL1/SRD1/SRD2 完整驱动链；电源树结构。
- DR25 J1/J2 与 XT60 T1/T2 引脚-网络表已提齐（第 11 节），实车接线可直接照表，无需再抄板。

**仍需实物/实车确认：**
1. **T6（USART6 的 A_4/B_4）在实车是否插了外设**——决定 USART6 能否让给树莓派；同时确认 J1/J2 内 485 第 1/2 路总线（A_1/B_1、A_2/B_2）上实际挂了哪些设备，避免地址/负载冲突。
2. **NBREAK1/NBREAK2 的 CH3.96_2P 端子实车接法**：接的是刹车开关还是急停、常开/常闭、SW_IN 与 SRD1 触点的配合逻辑——PDF 只能看出"串入点"。
3. **SL1 断开的 MOTOR_1 回路实测**：确认 J2 12/13(MOTOR_1_2)、24/25(MOTOR_1_1) 与电机控制器 24V 进线的对应，以及电机控制器上电时序对 SL1 通断的依赖（PA5 断电是否导致控制器失电）。
4. **BOOT 无跳线** → 确认固件烧录走 SWD 即可，无影响；否则需飞线。
5. DR25 个别脚的双网络标签歧义（第 11 节带 \* 项）可用万用表通断 30 秒逐一敲定。
