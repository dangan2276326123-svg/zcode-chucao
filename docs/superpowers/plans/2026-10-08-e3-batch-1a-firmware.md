# E3 批 1a（协议 + 固件）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 E3 契约的固件侧落地——权限只能由 `MODE` 帧申请、进无人五条件 fail-closed、刀的安全写成不变量、TOOL/NAV 只认当前持权者、STATUS 扩到 19 字节带回档案号/权限变迁原因/主循环计数/build 号/拒绝码，并把源文件编码统一成 GBK。

**Architecture:** 全部改动集中在 `firmware/大车proj/大车/HARDWARE/retrofit/`（我们自己的文件）加 `USER/main.c` 的**两处纯新增**（一句主循环计数、一条厂商 Modbus 分支锁零）。厂商那段 `:305` 死等结构**一个字符都不动**（A12）。权限判定收成一个函数 `owner_allows()`，四轮/刀/横移三个执行点都调它（spec §4.1：判定必须落在执行点，且不许各复制一份）。

**Tech Stack:** STM32F407 + SPL，Keil µVision（命令行 `UV4.exe -r`），C89 风格（变量声明在块首，沿用现有文件风格）。

## Global Constraints

- **前置**：批 1b 必须已合入并跑通（`pytest -q` = 207 passed）。顺序反了台架当天字段错位（spec §3.5）。
- **只改 `firmware/大车proj/大车/` 里那份**。`firmware/` 根下的四份是影子副本，本批 Task 6 直接删（A13）。
- **A12：不改厂商 `main.c` 的死等结构**（`:305` 那个 `while`、门限 800/1100、`:329` 握手块）。`main.c` 只允许两处**纯新增**：一句 `retrofit_notify_loop();`、一条 `regGroup[0]==1` 锁零分支。
- **A14：`retrofit.c`/`retrofit.h`/`protocol.h` 当前是 UTF-8，本批 Task 6 转成 GBK**。转换只动注释字节 ⇒ **重编译后 Code 必须仍是转换前那次的值**（当前基线 44848，若 Task 3–5 已让 Code 变化，则以"转换前后两次编译 Code 相同"为准）。
- **编码纪律**：Task 6 之前 `retrofit.*` 是 UTF-8、`main.c` 是 GBK；Task 6 之后全是 GBK。补丁脚本必须**逐文件试解码**（UTF-8 严格 → GBK 严格 → 都失败即停手报"混合编码"），改完用同一编码读回并确认"非 ASCII 变更行 = 0"（`main.c` 的新增行必须是纯 ASCII）。
- **fail-closed**：任何拿不到的量（现场拨档阈值、档案号）都不得"当作满足"。宁可进不了无人，不可带着未标定的判据进无人。
- 固件没有单元测试框架。**每个任务的验证 = 编译证据 + 符号证据 + 尺寸证据**（spec §10 步 1 的①–⑤），台架行为验证统一放到 Task 9。
- 提交纪律同批 1b：`git commit -F <文件> --cleanup=verbatim`，提交后看 `git log --oneline -1` 与 `git show --numstat --format=""`；**不提交** `OBJ/`、`*.map`、`*.hex`、`build_log.txt`、`PWM.uvguix.*`、`PWM.uvoptx`。
- ⚠️ 中文路径下 `git checkout`/`rebase` 可能静默 no-op：同步对侧之后必须做内容 diff 验证，必要时用文件系统 `cp` 兜底。

---

## File Structure

| 文件 | 责任 | 本批动作 |
|---|---|---|
| `firmware/大车proj/大车/HARDWARE/retrofit/protocol.h` | 帧类型常量 | 加 `TYPE_MODE 5`（Task 1）；Task 6 转 GBK（该文件只有 3 个非 ASCII 字节） |
| `firmware/大车proj/大车/HARDWARE/retrofit/retrofit.h` | 对外 API 与全部契约常量 | 加 MODE 请求码、档案号、许可位、authority/reject 码、现场拨档通道与阈值、新 API 声明（Task 2） |
| `firmware/大车proj/大车/HARDWARE/retrofit/retrofit.c` | 权限状态机与执行点 | dispatch 加 `case TYPE_MODE`；`owner`/五条件/拒绝码/刀不变量/TOOL 门/急停解除/拨档锁存/持续复查/19 字节 STATUS/`loop_alive`/`build_id`（Task 3–5）；Task 6 转 GBK |
| `firmware/大车proj/大车/USER/main.c` | 厂商主循环（GBK） | **两处纯新增**：`retrofit_notify_loop();`（Task 5）、`regGroup[0]==1` 锁零（Task 5） |
| `firmware/{retrofit.c,retrofit.h,protocol.c,protocol.h}` | 影子副本 | **删除**（Task 6，A13） |
| `README.md`、`firmware/集成说明.md` | 资产位置权威 | 标明固件源只在 `大车proj` 内；编码口径（Task 6） |
| `docs/参数差异台账.md`、`docs/缺口清单.md`、`AGENTS.md` | 状态权威 | F1/F2/F3/Fw-14/17/21/22/Pc-8 的状态就地改判；基线与"待重编译"标记（Task 8） |

---

### Task 1: 固件侧协议常量——`TYPE_MODE`

**Files:**
- Modify: `firmware/大车proj/大车/HARDWARE/retrofit/protocol.h`（`#define TYPE_STATUS 0x10` 之后）

**Interfaces:**
- Produces: `#define TYPE_MODE 5`（与 `common/protocol.py` 的 `TYPE_MODE = 5` 必须同值）

- [ ] **Step 1: 加常量**

在 `protocol.h` 的 `#define TYPE_STATUS  0x10` 之后插入（**纯 ASCII**）：

```c
#define TYPE_MODE    5   /* E3: authority request / release / estop-clear / profile handshake */
```

- [ ] **Step 2: 编译验证**

Run: `"D:\ruanjian\keil\KEIL32\UV4\UV4.exe" -r "D:\ai work\qoder\firmware\大车proj\大车\USER\PWM.uvprojx" -j0 -o "D:\ai work\qoder\firmware\大车proj\大车\USER\build_log.txt"`
Expected: 退出码 0 或 1（1 = 只有警告）；`build_log.txt` 尾部 `0 Error(s)`；`Program Size: Code=` 与改动前**相同**（只加了一个未被引用的宏，不该产生代码）

- [ ] **Step 3: 交叉核对 Python 侧同值**

Run: `python -c "from common import protocol as P; print(P.TYPE_MODE)"` → Expected: `5`

- [ ] **Step 4: 提交**

```bash
git add "firmware/大车proj/大车/HARDWARE/retrofit/protocol.h"
git commit -F- --cleanup=verbatim <<'EOF'
固件协议头加 TYPE_MODE=5，与 common/protocol.py 同值

E3 批 1a 第 1 步（spec §3.1/§3.4 五处同步之一）。只加一个宏，Code 尺寸不变
（build_log 已核）；此时还没有任何代码引用它，所以行为零变化 —— 这一步单独提交
是为了让"协议常量两侧同值"这件事在历史里可查。
EOF
```

---

### Task 2: `retrofit.h`——契约常量与新 API

**Files:**
- Modify: `firmware/大车proj/大车/HARDWARE/retrofit/retrofit.h`（在 `#define MODE_ESTOP 2` 之后、`retrofit_init` 声明之前）

**Interfaces:**
- Produces（全部供 Task 3–5 使用）：
  - `MODE_TELEOP 3`
  - `MODE_REQ_MANUAL/AUTO/TELEOP/CLEAR_ESTOP/PROFILE`（0x00/0x01/0x02/0x10/0x20）
  - `PROFILE_PREV 1`、`PROFILE_REAL 2`、`PROFILE_ID`（**编译期常量**，本批 = `PROFILE_PREV`）
  - `PERMIT_GATE_N 1`、`PERMIT_GATE_F 2`、`ENTRY_PERMIT`（**编译期常量**，本批 = `PERMIT_GATE_N`）
  - `OWNER_RC 0`、`OWNER_PC 1`、`OWNER_NONE 2`
  - `AUTH_BOOT 0` … `AUTH_HEARTBEAT_RELEASE 7`
  - `REJ_NONE 0` … `REJ_PERMIT 8`
  - `FIELD_CH 7`、`FIELD_SW_CALIBRATED 0`、`FIELD_ALLOW_HI`/`FIELD_MID_LO`/`FIELD_MID_HI`
  - `LOOP_STALL_FRAMES 5`
  - `void retrofit_on_mode_frame(const uint8_t *payload, uint16_t len);`
  - `void retrofit_notify_loop(void);`
  - `uint8_t retrofit_owner(void); uint8_t retrofit_reject(void); uint8_t retrofit_permit(void); uint8_t retrofit_profile(void);`

- [ ] **Step 1: 写头文件内容**

```c
#define MODE_TELEOP 3      /* E3 batch 2; firmware answers REJ_NOT_IMPL for now */

/* ---- MODE.request (must equal common/protocol.py) ---- */
#define MODE_REQ_MANUAL       0x00
#define MODE_REQ_AUTO         0x01
#define MODE_REQ_TELEOP       0x02
#define MODE_REQ_CLEAR_ESTOP  0x10
#define MODE_REQ_PROFILE      0x20

/* ---- vehicle profile: burned in, handshake compares against the PC yaml ---- */
#define PROFILE_PREV 1     /* 上代车 3.25 m */
#define PROFILE_REAL 2     /* 样机 2.15 m */
#define PROFILE_ID   PROFILE_PREV   /* 换车改这一行并重编译（运行中不热切） */

/* ---- entry permit (A5): compile-time, NEVER sent by the PC ---- */
#define PERMIT_GATE_N 1    /* 只许沿行空跑：刀强制提、横移禁 */
#define PERMIT_GATE_F 2    /* 允许落刀作业与横移（门 F） */
#define ENTRY_PERMIT  PERMIT_GATE_N

/* ---- who may drive right now (firmware-internal, not on the wire) ---- */
#define OWNER_RC   0
#define OWNER_PC   1
#define OWNER_NONE 2

/* ---- STATUS.authority = reason of the last authority transition ---- */
#define AUTH_BOOT              0
#define AUTH_PC_GRANTED        1
#define AUTH_FIELD_TAKEOVER    2
#define AUTH_RCS_LOST          3
#define AUTH_LINK_LOST_ESTOP   4
#define AUTH_PC_CLEAR_ESTOP    5
#define AUTH_PC_RELEASE        6
#define AUTH_HEARTBEAT_RELEASE 7

/* ---- STATUS.reject ---- */
#define REJ_NONE          0
#define REJ_PROFILE       1
#define REJ_RCS_STALE     2
#define REJ_FIELD_SWITCH  3
#define REJ_ESTOP_LATCHED 4
#define REJ_LOOP_STALLED  5
#define REJ_NOT_IMPL      6
#define REJ_FIELD_LATCHED 7
#define REJ_PERMIT        8

/* ---- field takeover switch (A4) ----
   FIELD_SW_CALIBRATED = 0 until B2 fills the three numbers below from the
   transmitter's own channel monitor. While it is 0 the gate FAILS CLOSED:
   unmanned mode cannot be entered at all. That is deliberate -- an
   uncalibrated threshold must never be treated as "condition satisfied". */
#define FIELD_CH            7
#define FIELD_SW_CALIBRATED 0
#define FIELD_ALLOW_HI   1600u   /* [B2] stick high end = allow unmanned */
#define FIELD_MID_LO     1200u   /* [B2] 3-position middle band, low edge  */
#define FIELD_MID_HI     1400u   /* [B2] 3-position middle band, high edge */
#define FIELD_LATCH_MS   1000u   /* must stay in "allow" this long to unlatch */

/* ---- execution-plane liveness (A12a / Fw-21) ---- */
#define LOOP_STALL_FRAMES 5   /* 5 STATUS periods (250 ms) without a change */

void retrofit_on_mode_frame(const uint8_t *payload, uint16_t len);
void retrofit_notify_loop(void);      /* call once per main-loop iteration */
uint8_t retrofit_owner(void);
uint8_t retrofit_reject(void);
uint8_t retrofit_permit(void);
uint8_t retrofit_profile(void);
```

- [ ] **Step 2: 编译验证**

Run: 同 Task 1 Step 2 的 `UV4.exe -r` 命令
Expected: `0 Error(s)`；Code 尺寸不变（全是宏与声明，无实现）

- [ ] **Step 3: 交叉核对与 Python 侧同值**

Run:
```bash
python -c "from common import protocol as P; print(P.MODE_REQ_AUTO, P.PROFILE_PREV, P.AUTH_HEARTBEAT_RELEASE, P.REJECT_PERMIT)"
```
Expected: `1 1 7 8` —— 与头文件里的 `MODE_REQ_AUTO`/`PROFILE_PREV`/`AUTH_HEARTBEAT_RELEASE`/`REJ_PERMIT` 逐个对上

- [ ] **Step 4: 提交**

```bash
git add "firmware/大车proj/大车/HARDWARE/retrofit/retrofit.h"
git commit -F- --cleanup=verbatim <<'EOF'
retrofit.h 落 E3 契约常量：档案号/许可位/持权者/authority/reject/拨档通道

E3 批 1a 第 2 步（spec §2/§3.2/§3.3/§4.3）。三个关键设计写进常量本身：

- PROFILE_ID 与 ENTRY_PERMIT 是**编译期常量，不由 PC 下发**（A5）：那样"上位机
  出错"就等于"可以落刀"。换车/换门 = 改一行 + 重编译，代价可接受。
- FIELD_SW_CALIBRATED = 0：B2 那张通道表没填之前，现场拨档这一条**恒不通过**
  （fail-closed）。未标定的阈值绝不能当成"条件满足"，代价是 B2 之前进不了无人。
- OWNER_* 是固件内部量（不上线），线上的 authority 是"最近一次变迁原因码"。
  两个概念分开，是 spec 自审时订正过的（初稿混用一个词）。

已逐个核对与 common/protocol.py 同值（MODE_REQ_AUTO=1、PROFILE_PREV=1、
AUTH_HEARTBEAT_RELEASE=7、REJ_PERMIT=8）。全是宏与声明，Code 尺寸不变。
EOF
```

---

### Task 3: `retrofit.c`——`MODE` 帧分派、五条件、拒绝码、owner 迁移

**Files:**
- Modify: `firmware/大车proj/大车/HARDWARE/retrofit/retrofit.c`（`:23` 附近的 static 变量区、`:60-75` dispatch、`:90-129` 帧处理函数区）

**Interfaces:**
- Consumes: Task 2 的全部常量；现有 `retrofit_sbus_ok()`（`:159`）、`estop_latched`（`:24`）、`mode`（`:23`）、`lift_bits`（`:33`）、`tick_ms`。
- Produces: `static uint8_t owner`、`static uint8_t auth_reason`、`static uint8_t reject_code`、`static uint8_t pc_profile`、`static uint8_t handshake_ok`、`static uint8_t field_latched`、`static uint32_t field_ok_since`、`static volatile uint8_t loop_counter`、`static uint8_t last_loop_seen`、`static uint8_t loop_stall_run`、`static uint32_t loop_check_ms`；函数 `retrofit_on_mode_frame()`、`retrofit_notify_loop()`、`retrofit_owner/reject/permit/profile()`、`static uint8_t owner_allows(void)`、`static uint8_t field_allows_unmanned(void)`、`static void set_owner(uint8_t who, uint8_t reason)`。

- [ ] **Step 1: 加状态变量**

在 `static uint8_t estop_latched = 0;`（`:24`）之后插入：

```c
/* ---- E3 control authority (spec 2026-10-08) ---- */
static uint8_t  owner = OWNER_RC;          /* who may drive right now */
static uint8_t  auth_reason = AUTH_BOOT;   /* last transition, reported in STATUS */
static uint8_t  reject_code = REJ_NONE;    /* last refusal, reported in STATUS */
static uint8_t  pc_profile = PROFILE_NONE_SAFE;  /* 0 until handshake */
static uint8_t  handshake_ok = 0;
static uint8_t  field_latched = 0;         /* field switch pulled to "manual" */
static uint32_t field_ok_since = 0;
static volatile uint8_t loop_counter = 0;  /* written by main loop, read in ISR */
static uint8_t  last_loop_seen = 0;
static uint8_t  loop_stall_run = 0;
static uint32_t loop_check_ms = 0;
```

并在常量区加 `#define PROFILE_NONE_SAFE 0`（若 Task 2 未定义 `PROFILE_NONE`，就用这个本地名，**不要引入与 Python 侧不同值的符号**；Python 侧 `PROFILE_NONE = 0`，两边同为 0）。

- [ ] **Step 2: 加三个判定函数**

放在 `retrofit_sbus_ok()`（`:159-167`）之后：

```c
uint8_t retrofit_owner(void)   { return owner; }
uint8_t retrofit_reject(void)  { return reject_code; }
uint8_t retrofit_permit(void)  { return ENTRY_PERMIT; }
uint8_t retrofit_profile(void) { return PROFILE_ID; }

void retrofit_notify_loop(void) { loop_counter++; }   /* A12a: one line in main.c */

static uint8_t field_allows_unmanned(void)
{
    /* FAIL CLOSED until B2 fills the thresholds (FIELD_SW_CALIBRATED == 0). */
#if FIELD_SW_CALIBRATED
    uint16_t v = sbus_channel_raw(FIELD_CH);   /* existing SBUS accessor */
    if (v >= FIELD_MID_LO && v <= FIELD_MID_HI) return 0;  /* middle = forbid */
    return v >= FIELD_ALLOW_HI;
#else
    return 0;
#endif
}

static void set_owner(uint8_t who, uint8_t reason)
{
    if (owner == who) { auth_reason = reason; return; }
    owner = who;
    auth_reason = reason;
    /* spec 4.4: on ANY handover the old targets are void -- a late frame
       from the previous owner must not be able to drop a knife. */
    cmd_vl = 0.0f; cmd_vr = 0.0f;
    tool_offset_mm = 0.0f;
    lift_bits = 0x07;          /* all beams up */
    last_tool_ms = 0;          /* forget the previous owner's TOOL freshness */
}

static uint8_t owner_allows(void) { return owner == OWNER_PC && !estop_latched; }
```

⚠️ `sbus_channel_raw(FIELD_CH)` 必须用工程里**已存在**的 SBUS 通道数组（`telecontrol.c` 导出的 `sbus_channel[]`，`main.c:305` 就在用它）。实施时先 `grep -n "sbus_channel" firmware/大车proj/大车/HARDWARE/telecontrol/*.h`确认外部声明，直接写 `extern uint16_t sbus_channel[16];` 或包含对应头文件——**不要新造一个访问器**。

- [ ] **Step 3: 加 `retrofit_on_mode_frame()`**

放在 `retrofit_clear_estop()`（`:124-129`）之后：

```c
/* E3 spec 4.2: five conditions, all must hold, and they are re-checked
   continuously (see retrofit_poll_1ms). Refusals are reported, not silent. */
static uint8_t enter_unmanned(uint8_t want_mode)
{
    if (!handshake_ok || pc_profile != PROFILE_ID) { reject_code = REJ_PROFILE;       return 0; }
    if (!retrofit_sbus_ok())                       { reject_code = REJ_RCS_STALE;    return 0; }
    if (!field_allows_unmanned())                  { reject_code = field_latched ? REJ_FIELD_LATCHED : REJ_FIELD_SWITCH; return 0; }
    if (estop_latched)                             { reject_code = REJ_ESTOP_LATCHED; return 0; }
    if (loop_stall_run >= LOOP_STALL_FRAMES)       { reject_code = REJ_LOOP_STALLED;  return 0; }
    if (want_mode == MODE_TELEOP)                  { reject_code = REJ_NOT_IMPL;     return 0; }

    /* Order matters (spec 4.2): safe the tools FIRST, then hand over. */
    lift_bits = 0x07;
    tool_offset_mm = 0.0f;
    cmd_vl = 0.0f; cmd_vr = 0.0f;
    last_tool_ms = 0;
    mode = want_mode;
    set_owner(OWNER_PC, AUTH_PC_GRANTED);
    reject_code = REJ_NONE;
    return 1;
}

void retrofit_on_mode_frame(const uint8_t *payload, uint16_t len)
{
    uint8_t req, prof;
    if (len < 2) return;
    req = payload[0];
    prof = payload[1];

    switch (req) {
    case MODE_REQ_PROFILE:
        pc_profile = prof;
        handshake_ok = (prof == PROFILE_ID);
        reject_code = handshake_ok ? REJ_NONE : REJ_PROFILE;
        break;
    case MODE_REQ_AUTO:
    case MODE_REQ_TELEOP:
        enter_unmanned(req == MODE_REQ_AUTO ? MODE_AUTO : MODE_TELEOP);
        break;
    case MODE_REQ_MANUAL:
        /* PC releases authority. Not allowed to clear an estop latch. */
        if (estop_latched) { reject_code = REJ_ESTOP_LATCHED; break; }
        mode = MODE_MANUAL;
        set_owner(OWNER_RC, AUTH_PC_RELEASE);
        reject_code = REJ_NONE;
        break;
    case MODE_REQ_CLEAR_ESTOP:
        /* A3: single confirmation from the whitelisted PC.
           Clearing the latch is NOT granting authority (spec 4.6). */
        estop_latched = 0;
        mode = MODE_MANUAL;
        set_owner(OWNER_RC, AUTH_PC_CLEAR_ESTOP);
        lift_bits = 0x07;            /* knives up -- fixes F2 */
        cmd_vl = 0.0f; cmd_vr = 0.0f;
        tool_offset_mm = 0.0f;
        last_tool_ms = 0;
        reject_code = REJ_NONE;
        break;
    default:
        reject_code = REJ_NOT_IMPL;
        break;
    }
}
```

- [ ] **Step 4: 接进 dispatch，并让 HEARTBEAT 也走 `set_owner`**

`USART6_IRQHandler` 的 `switch (rx_frame.type)`（`:60-75`）里加一个 case，并改写 HEARTBEAT 那个 case：

```c
            case TYPE_MODE:
                retrofit_on_mode_frame(rx_frame.payload, rx_frame.payload_len);
                break;
            case TYPE_HEARTBEAT:
                /* PC alive but not commanding -> release authority so the RC
                   operator regains control. E3: NAV no longer implies AUTO,
                   so this is now the ONLY implicit release path. */
                if (mode == MODE_AUTO || mode == MODE_TELEOP) {
                    mode = MODE_MANUAL;
                    set_owner(OWNER_RC, AUTH_HEARTBEAT_RELEASE);
                }
                break;
```

- [ ] **Step 5: 编译 + 符号 + 尺寸三证**

Run: `UV4.exe -r ...`（同 Task 1 Step 2）
Expected: `0 Error(s)`；Code 尺寸**相对 44848 增大**（新增了实际代码）

Run:
```bash
python - <<'PY'
import re
m = open(r"firmware/大车proj/大车/OBJ/PWM.map", encoding='utf-8', errors='replace').read()
for sym in ('retrofit_on_mode_frame', 'retrofit_notify_loop', 'enter_unmanned', 'set_owner'):
    hits = [l for l in m.split('\n') if sym in l]
    print(sym, len(hits), hits[0].strip()[:90] if hits else '')
PY
```
Expected: 四个符号**都能在 map 里找到**（`enter_unmanned`/`set_owner` 是 static，若被内联则允许 0 命中，但必须在 `PWM.map` 的 `retrofit.o` 段里能看到 `retrofit_on_mode_frame` 的地址）

- [ ] **Step 6: 提交**

```bash
git add "firmware/大车proj/大车/HARDWARE/retrofit/retrofit.c"
git commit -F- --cleanup=verbatim <<'EOF'
固件加 MODE 帧处理：进无人五条件 fail-closed，换主即作废旧目标

E3 批 1a 第 3 步（spec §4.2/§4.3/§4.4/§4.6）。

- owner（内部量，谁现在能动车）与 auth_reason（线上字段，最近一次变迁原因）分开。
- set_owner() 在任何一次换主时把 cmd_vl/cmd_vr/tool_offset 清零、lift_bits 置全提、
  last_tool_ms 清零 —— 这样现场夺权之后路上延迟到达的那条 TOOL 不可能再落刀（F3）。
- enter_unmanned() 五条件缺一不可，且**逐条给拒绝码**（档案/遥控/拨档/急停/执行面停摆），
  PC 侧能看出为什么被拒而不是"没反应"。
- 获批瞬间的动作顺序是"先把刀提到最高、再交权"，所以 Fw-17 那个"进 AUTO 落刀"
  在结构上不可能发生。
- MODE_REQ_CLEAR_ESTOP 给了 retrofit_clear_estop 一直缺的那个入口（Fw-14），
  并且把 lift_bits=0 改成 0x07（F2）；**清锁不等于授权**，解除后 owner 回 RC。
- HEARTBEAT 仍是唯一的隐式交权路径，现在也走 set_owner 并记 AUTH_HEARTBEAT_RELEASE。
- FIELD_SW_CALIBRATED=0 时 field_allows_unmanned() 恒返回 0（fail-closed）：
  B2 那张通道表填好之前**进不了无人**，这是刻意的。

编译 0 Error，Code 尺寸相对 44848 增大，map 里 retrofit_on_mode_frame 有地址。
待 Keil 重烧后才算生效；本提交不含 hex/map/build_log。
EOF
```

---

### Task 4: 刀不变量 + NAV/TOOL 只认持权者 + 持续复查

**Files:**
- Modify: `firmware/大车proj/大车/HARDWARE/retrofit/retrofit.c`（`:90-113` NAV/TOOL 处理、`:251-259` 刀输出、`:268-303` `stepper_update`、`:311-335` `retrofit_poll_1ms`）

**Interfaces:**
- Consumes: `owner_allows()`、`set_owner()`、Task 2 常量。
- Produces: 修改后的 `retrofit_on_nav_frame()`、`retrofit_on_tool_frame()`、刀输出段、横移闭锁段、`retrofit_poll_1ms()` 里的持续复查与 `loop_alive` 停摆检测。

- [ ] **Step 1: NAV 不再改 mode，且只认持权者（修 F1）**

把 `retrofit_on_nav_frame()`（`:90-103`）改成：

```c
void retrofit_on_nav_frame(const uint8_t *payload, uint16_t len, uint16_t seq)
{
    (void)seq;
    if (len < 9) return;
    /* E3 spec 4.4: NAV carries speed ONLY. It must never change authority --
       that was F1 ("PC presses a key, the car becomes unmanned with no field
       confirmation"). Authority comes from MODE frames only. */
    if (!owner_allows()) { reject_code = REJ_FIELD_LATCHED; return; }
    memcpy(&cmd_vl, &payload[0], 4);
    memcpy(&cmd_vr, &payload[4], 4);
    if (cmd_vl < -1.0f) cmd_vl = -1.0f;
    if (cmd_vl >  1.0f) cmd_vl =  1.0f;
    if (cmd_vr < -1.0f) cmd_vr = -1.0f;
    if (cmd_vr >  1.0f) cmd_vr =  1.0f;
}
```

⚠️ 原 `:93` 的 `if (len < 9 || estop_latched) return;` 里那半个急停判断由 `owner_allows()` 承担（急停时 `owner != OWNER_PC`）——**不要两处都留**，否则以后改一处漏一处。

- [ ] **Step 2: TOOL 同样只认持权者，且门 N 下忽略刀位与横移（修 F3 + Pc-8 固件侧）**

把 `retrofit_on_tool_frame()`（`:105-113`）改成：

```c
void retrofit_on_tool_frame(const uint8_t *payload, uint16_t len)
{
    if (len < 5) return;
    /* E3 spec 4.4: a TOOL frame from anyone but the current owner is void.
       This is the fix for F3 -- the old code only checked length and the
       estop latch, so a late TOOL frame still moved the lift after a field
       takeover. */
    if (!owner_allows()) { reject_code = REJ_FIELD_LATCHED; return; }
    if (ENTRY_PERMIT == PERMIT_GATE_N) {
        /* Gate N: knives locked up, no lateral travel. The PC is supposed to
           send lift=0x07 / offset=0 here; we ignore it either way so a PC bug
           cannot drop a knife (spec 4.5, both sides). */
        reject_code = ((payload[4] & 0x07) != 0x07) ? REJ_PERMIT : REJ_NONE;
        last_tool_ms = tick_ms;
        lift_bits = 0x07;
        tool_offset_mm = 0.0f;
        return;
    }
    last_tool_ms = tick_ms;
    memcpy(&tool_offset_mm, &payload[0], 4);
    lift_bits = payload[4];
    if (tool_offset_mm >  50.0f) tool_offset_mm =  50.0f;
    if (tool_offset_mm < -50.0f) tool_offset_mm = -50.0f;
}
```

- [ ] **Step 3: 刀输出改成不变量（修 Fw-17 + F2）**

把 `:253-259` 那个 `for` 循环体改成：

```c
    for (i = 0; i < 3; i++) {
        uint8_t up;
        /* E3 spec 4.5 invariant: unless the CURRENT owner asked for it within
           the last 500 ms, the beam stays UP. One rule, three holes closed
           (Fw-17 AUTO branch, F2 clear_estop, Pc-8 PC sending lift=0). */
        if (estop_latched)                  up = 1;
        else if (ENTRY_PERMIT == PERMIT_GATE_N) up = 1;
        else if (!tool_cmd_fresh)           up = 1;
        else if (!owner_allows())           up = 1;
        else                                up = (lift_bits >> i) & 1;
        gpio_out(GPIOD, (uint16_t)(GPIO_Pin_4 << i), up);
    }
```

（`tool_cmd_fresh` 的定义 `:251-252` 保留原样，含 `last_tool_ms != 0` 那个 P0-7 护栏。）

- [ ] **Step 4: 横移同样受许可位约束**

在 `stepper_update()`（`:268` 起）里，找到它读 `tool_offset_mm` 决定脉冲方向/数量的那一段，在函数开头加：

```c
    if (ENTRY_PERMIT == PERMIT_GATE_N || !owner_allows()) {
        /* Gate N: no lateral travel at all. Stop the pulse train and treat the
           applied position as the target so it does not resume on its own. */
        TIM_Cmd(TIM4, DISABLE);
        return;
    }
```

⚠️ 实施时**必须先读 `stepper_update()` 全文**（`:268-303`）确认 `TIM_Cmd(TIM4, DISABLE)` 与它既有的停转分支一致（`:300` 已有 `TIM_Cmd(TIM4, DISABLE);`），不要引入第二种停法。

- [ ] **Step 5: 持续复查 + 执行面停摆检测（`retrofit_poll_1ms`）**

在 `retrofit_poll_1ms()`（`:311-335`）的链路看门狗那段（`:315-319`）之后插入：

```c
    /* E3 spec 4.2: conditions are re-checked continuously, not only at entry. */
    if ((uint32_t)(tick_ms - loop_check_ms) >= 50u) {   /* once per STATUS period */
        loop_check_ms = tick_ms;
        if (loop_counter == last_loop_seen) {
            if (loop_stall_run < 250u) loop_stall_run++;
        } else {
            loop_stall_run = 0;
            last_loop_seen = loop_counter;
        }
    }

    if (owner == OWNER_PC && !estop_latched) {
        if (!field_allows_unmanned() || field_latched) {
            /* Field operator took over: immediate, latched, and it wins over
               everything (spec 4.3). */
            field_latched = 1;
            mode = MODE_MANUAL;
            set_owner(OWNER_RC, AUTH_FIELD_TAKEOVER);
            reject_code = REJ_FIELD_LATCHED;
        } else if (!retrofit_sbus_ok()) {
            /* RC link lost while the PC drives: lock the speed to zero and
               raise the knives, but DO NOT hand authority back -- handing it
               to a dead receiver is meaningless (spec 4.2). */
            cmd_vl = 0.0f; cmd_vr = 0.0f;
            lift_bits = 0x07;
            auth_reason = AUTH_RCS_LOST;
            reject_code = REJ_RCS_STALE;
        }
        if (loop_stall_run >= LOOP_STALL_FRAMES) {
            /* Execution plane is parked (Fw-21): the wheels are not listening,
               so do not pretend the PC is driving. */
            cmd_vl = 0.0f; cmd_vr = 0.0f;
            lift_bits = 0x07;
            reject_code = REJ_LOOP_STALLED;
        }
    }

    /* Unlatch the field override only after the switch has sat in "allow
       unmanned" for FIELD_LATCH_MS (debounce, spec 4.3). */
    if (field_latched && field_allows_unmanned()) {
        if (field_ok_since == 0u) field_ok_since = tick_ms;
        else if ((uint32_t)(tick_ms - field_ok_since) >= FIELD_LATCH_MS) {
            field_latched = 0;
            field_ok_since = 0u;
            if (reject_code == REJ_FIELD_LATCHED) reject_code = REJ_NONE;
        }
    } else if (field_latched) {
        field_ok_since = 0u;
    }
```

⚠️ `FIELD_SW_CALIBRATED == 0` 时 `field_allows_unmanned()` 恒为 0，所以上面第一段会**立刻把 owner 打回 RC 并锁存**——这正是 fail-closed 的表现（进不了无人，也留不住无人）。**在 B2 填数之前，台架只能验 ⑨⑪⑫ 这类"被拒"场景**，需要真进无人的 ②③⑧ 必须等 B2。这一条要在 Task 9 的清单里写清。

- [ ] **Step 6: 编译 + 尺寸 + 提交**

Run: `UV4.exe -r ...` → Expected: `0 Error(s)`，Code 尺寸再次增大

```bash
git add "firmware/大车proj/大车/HARDWARE/retrofit/retrofit.c"
git commit -F- --cleanup=verbatim <<'EOF'
刀写成不变量、NAV/TOOL 只认持权者、五条件持续复查

E3 批 1a 第 4 步（spec §4.2/§4.4/§4.5）。三个洞一起关：

- F1：retrofit_on_nav_frame 删掉 mode = MODE_AUTO，NAV 只给速度；急停判断收进
  owner_allows()，不留两份（改一处漏一处的经典来源）。
- F3：TOOL 帧现在只接受当前持权者的，换主之后迟到的那条作废。
- Fw-17 + F2 + Pc-8：刀输出改成一条不变量 —— 急停锁存 / 门 N / TOOL 不新鲜 /
  非当前持权者，四种情况一律提刀；只有"门 F + 持权者半秒内的明确指令"才允许落刀。
- 横移在门 N 下直接停 TIM4 脉冲，与既有停转分支同一种停法。
- poll_1ms 里加持续复查：现场拨档一扳回立刻交权并锁存（去抖 FIELD_LATCH_MS）；
  遥控失联时锁零速度+提刀但**不交权**（交给死掉的遥控没有意义）；
  loop_alive 连续 5 个 STATUS 周期不变即判执行面停摆（Fw-21 的探测手段）。

⚠️ FIELD_SW_CALIBRATED=0 时 fail-closed 会立刻把 owner 打回 RC，所以 B2 填表之前
台架只能验"被拒"类场景（⑨⑪⑫），需要真进无人的 ②③⑧ 必须等 B2。
编译 0 Error，Code 尺寸再次增大。待重烧。
EOF
```

---

### Task 5: STATUS 扩到 19 字节 + `main.c` 两处纯新增

**Files:**
- Modify: `firmware/大车proj/大车/HARDWARE/retrofit/retrofit.c`（`:220-235` `status_report`）
- Modify: `firmware/大车proj/大车/USER/main.c`（`:550` 附近、`:553-565` 门控块尾部）——**GBK 文件，新增行必须纯 ASCII**

**Interfaces:**
- Consumes: `owner`、`auth_reason`、`reject_code`、`loop_counter`、`PROFILE_ID`、`ENTRY_PERMIT`。
- Produces: 19 字节 STATUS 载荷；`build_id`（`__DATE__ __TIME__` 字节和 & 0xFF）；`main.c` 里的 `retrofit_notify_loop();` 与 `regGroup[0]==1` 锁零分支。

- [ ] **Step 1: `status_report()` 扩到 19 字节**

把 `:220-235` 整个函数替换为：

```c
static uint8_t build_id(void)
{
    /* Compile stamp checksum: changes on every rebuild without anyone having
       to remember to bump a number. Fixes the 09-23 incident where two hex
       files had identical Code size (44848) and only mtime told them apart.
       Full stamp goes to the HMI at boot (see main.c note in the spec). */
    static const char stamp[] = __DATE__ " " __TIME__;
    uint16_t sum = 0;
    uint8_t i;
    for (i = 0; stamp[i] != '\0'; i++) sum += (uint8_t)stamp[i];
    return (uint8_t)(sum & 0xFF);
}

static void status_report(void)
{
    uint8_t pl[19];
    uint8_t frame[2 + 5 + 19 + 2];
    float speed = retrofit_wheel_speed();
    float cur = adc_current_a();
    float bat = 48.0f;  /* TODO bench: ADC divider channel (Fw-5) */
    memcpy(&pl[0], &speed, 4);
    memcpy(&pl[4], &cur, 4);
    memcpy(&pl[8], &bat, 4);
    pl[12] = read_limits();
    pl[13] = mode;
    /* ---- E3 (spec 3.2): the five new bytes ---- */
    pl[14] = PROFILE_ID;
    pl[15] = auth_reason;
    pl[16] = loop_counter;
    pl[17] = build_id();
    pl[18] = reject_code;
    {
        uint16_t n = prot_build(TYPE_STATUS, tx_seq++, pl, sizeof(pl), frame);
        uart6_send(frame, n);
    }
}
```

⚠️ 载荷字段顺序必须与 `common/protocol.py` 的 `STATUS_V2_FMT = '<fffBBBBBBB'` 逐字节对齐：`speed, current, battery, limits, mode, profile, authority, loop_alive, build_id, reject`。

- [ ] **Step 2: `main.c` 第一处新增——主循环计数（A12a）**

在 `main.c:550` 那段我们自己的注释块（`/* RETROFIT safety gate: ... */`）**之前**插入一行（纯 ASCII）：

```c
	retrofit_notify_loop();   /* E3 A12a: prove the execution plane is alive (Fw-21) */
```

位置要求：**在 `while(1)` 循环体内、在 `:305` 那段死等之后、在 `:567-576` 的 `pwm_veloc()` 之前**。这样"计数在走"就等价于"这一轮真的走到了四轮输出"。⚠️ 不许放进 `if (retrofit_mode() == MODE_AUTO)` 里面，否则 MANUAL 下计数不涨、PC 会误判停摆。

- [ ] **Step 3: `main.c` 第二处新增——厂商 Modbus 接管分支锁零（A1）**

在 `:553-565` 那个 `if/else if` 链的**末尾**追加一个分支（纯 ASCII 注释）：

```c
	} else if (regGroup[0] == 1) {
		/* E3 A1: the vendor UART3/Modbus "upper computer" path is a
		   half-finished product and is OUT of the contract. It must not be
		   able to drive the wheels. regGroup[0] is written only by uart3.c:224. */
		veloc[0] = veloc[1] = veloc[2] = veloc[3] = 0.0;
	}
```

⚠️ `regGroup` 在 `main.c:123` 已有 `extern unsigned char regGroup[16];`，不需要新声明。**除这两处之外，`main.c` 一个字符都不许动**（A12）。

- [ ] **Step 4: 编码校验（GBK 文件的两处新增必须是纯 ASCII）**

Run:
```bash
python - <<'PY'
p = r"firmware/大车proj/大车/USER/main.c"
b = open(p, 'rb').read()
b.decode('gbk')            # 必须不抛
print("gbk ok, bytes =", len(b))
lines = b.decode('gbk').replace('\r\n', '\n').split('\n')
for i, l in enumerate(lines, 1):
    if 'retrofit_notify_loop' in l or ('regGroup[0] == 1' in l and 'veloc' in lines[i] if i < len(lines) else False):
        print(i, l.strip()[:100], "ascii_only=", all(ord(c) < 128 for c in l))
PY
```
Expected: `gbk ok`；两处新增行 `ascii_only= True`

- [ ] **Step 5: 编译 + 尺寸 + 符号**

Run: `UV4.exe -r ...` → Expected: `0 Error(s)`；Code 尺寸增大（19 字节 STATUS + build_id + main.c 两处）
Run: `python -c "m=open(r'firmware/大车proj/大车/OBJ/PWM.map',encoding='utf-8',errors='replace').read(); print('build_id' in m, 'retrofit_notify_loop' in m)"` → Expected: 至少 `retrofit_notify_loop` 为 `True`（`build_id` 是 static，可能被内联）

- [ ] **Step 6: 提交**

```bash
git add "firmware/大车proj/大车/HARDWARE/retrofit/retrofit.c" "firmware/大车proj/大车/USER/main.c"
git commit -F- --cleanup=verbatim <<'EOF'
STATUS 扩到 19 字节；main.c 两处纯新增（主循环计数 + Modbus 分支锁零）

E3 批 1a 第 5 步（spec §3.2/§4.7/§8）。

status_report 载荷 14 -> 19 字节，字段顺序与 common/protocol.py 的
'<fffBBBBBBB' 逐字节对齐：profile / authority(变迁原因) / loop_alive / build_id /
reject。build_id 是 __DATE__ " " __TIME__ 的字节和 &0xFF，每次重编译自动变，
不用人记 —— 这是 09-23 那次"两份 hex 的 Code 都是 44848、只有 mtime 能区分、
结果白跑一轮"的解药。

main.c 只动两处，都是纯新增、纯 ASCII、且都在我们自己已插入的代码旁边：
1. :550 注释块之前加 retrofit_notify_loop(); —— 位置必须在 while(1) 体内、
   :305 死等之后、pwm_veloc 之前，于是"计数在走"等价于"这一轮真的走到了四轮输出"。
   刻意不放进 if (MODE_AUTO) 里，否则 MANUAL 下计数不涨、PC 会误判停摆。
2. :553-565 门控链末尾加 else if (regGroup[0]==1) 锁零 —— A1 定案：厂商那条
   UART3/Modbus 接管通路退出契约，不允许动车轮。

A12 遵守情况：:305 那段死等、800/1100 两个门限、:329 握手块**一个字符未动**。
已用 GBK 严格解码校验 main.c 未被写坏，两处新增行 ascii_only=True。
编译 0 Error，Code 尺寸增大。待重烧。
EOF
```

---

### Task 6: A14 转 GBK + A13 删影子副本

**Files:**
- Modify（编码转换，内容不变）: `firmware/大车proj/大车/HARDWARE/retrofit/retrofit.c`、`retrofit.h`、`protocol.h`
- Delete: `firmware/retrofit.c`、`firmware/retrofit.h`、`firmware/protocol.c`、`firmware/protocol.h`
- Modify: `README.md`、`firmware/集成说明.md`（标明固件源只在 `大车proj` 内）

**Interfaces:** 无（不改任何代码语义）。

- [ ] **Step 1: 记录转换前的编译尺寸**

Run: `UV4.exe -r ...`，从 `build_log.txt` 抄下 `Program Size: Code=XXXXX`（**转换前基线**，Task 5 之后的值）

- [ ] **Step 2: 转换编码（只动注释字节）**

```bash
python - <<'PY'
import os
files = [
    r"firmware/大车proj/大车/HARDWARE/retrofit/retrofit.c",
    r"firmware/大车proj/大车/HARDWARE/retrofit/retrofit.h",
    r"firmware/大车proj/大车/HARDWARE/retrofit/protocol.h",
]
for p in files:
    b = open(p, 'rb').read()
    text = b.decode('utf-8')            # 必须严格成功，否则停手
    new = text.encode('gbk')            # 必须严格成功，否则停手
    assert new.decode('gbk') == text    # 往返一致
    open(p, 'wb').write(new)
    print(os.path.basename(p), len(b), '->', len(new),
          'nonascii', sum(1 for c in b if c > 127), '->', sum(1 for c in new if c > 127))
PY
```
Expected: 三个文件都打印出来且**没有异常**；`retrofit.c` 从 75 个非 ASCII 字节变成更多（GBK 双字节）；往返断言通过。
若任何一个文件 `decode('utf-8')` 或 `encode('gbk')` 抛异常 ⇒ **立刻停手**，说明该文件是混合编码（Fw-20 说的情况），先查清再动。

- [ ] **Step 3: 重编译，Code 必须与 Step 1 完全相同**

Run: `UV4.exe -r ...`
Expected: `0 Error(s)`，且 `Program Size: Code=` **与 Step 1 记录的数字一字不差**。
数字变了 ⇒ 转换伤到了代码（不只是注释），**立刻 `git checkout` 那三个文件回退**（⚠️ 中文路径下 checkout 可能静默 no-op，回退后必须再 `git diff --stat` 确认真的回去了，必要时用 `git show HEAD:<path> > <path>` 兜底）。

- [ ] **Step 4: 删影子副本并改文档**

```bash
git rm firmware/retrofit.c firmware/retrofit.h firmware/protocol.c firmware/protocol.h
```

在 `README.md` 的固件段与 `firmware/集成说明.md` 开头各加一句：

```
固件源**只在** `firmware/大车proj/大车/` 内（`HARDWARE/retrofit/` 与 `USER/`）。
`firmware/` 根下曾经放过四份同名副本，2026-10-08 已删除（A13）：它们不参与编译，
改了对车零影响，只会让人以为改了。git 历史里仍可取回。
编码：`retrofit.c/.h`、`protocol.h` 与厂商 `main.c` 现在**统一为 GBK**（A14）；
`protocol.c` 是纯 ASCII。改之前逐文件试解码，别假定全树一种编码（台账 Fw-20）。
```

- [ ] **Step 5: 提交**

```bash
git add -A firmware/ README.md
git commit -F- --cleanup=verbatim <<'EOF'
retrofit/protocol 三个文件统一转 GBK；删掉 firmware/ 根下四份影子副本

A14 + A13（spec §4.8）。作者要求保留中文注释，那就把编码统一到厂商那一边：
retrofit.c/retrofit.h/protocol.h 由 UTF-8 转 GBK，于是 Keil 里打开全是正常中文，
AGENTS 审查清单第 4 条"firmware/*.c 是 GBK"也重新成立，一个字不用改。

证据（注释不进代码，所以这是硬判据）：转换**前后各编译一次，Code 尺寸一字不差**；
三个文件都通过 decode('utf-8') -> encode('gbk') -> decode('gbk') 往返断言。
（转换前 retrofit.c 有 75 个非 ASCII 字节、GBK 严格解码在偏移 6407/11374/11409/
11447/14648 失败，即台账 Fw-20 记的那五处。）

同时删掉 firmware/ 根下的 retrofit.c/.h、protocol.c/.h：它们与编译树里那四份
逐字节相同（retrofit.c md5 1e15bd202d69003bde01ebdb051f6636），但 PWM.uvprojx
只列 HARDWARE/retrofit 那两份 ⇒ 改根下那份对构建与台架零影响，只会让人以为改了。
git 历史可取回。README 与集成说明已标明"固件源只在大车proj 内"。
EOF
```

---

### Task 7: 认版与交接（给作者的烧录包）

**Files:**
- Modify: `docs/参数差异台账.md`（§4 追加一行"认版"记录）

**Interfaces:** 无。

- [ ] **Step 1: 收集三条硬证据**

Run:
```bash
python - <<'PY'
import re, os, time
log = open(r"firmware/大车proj/大车/USER/build_log.txt", encoding='utf-8', errors='replace').read()
print([l for l in log.split('\n') if 'Error' in l or 'Program Size' in l][-3:])
for f in (r"firmware/大车proj/大车/OBJ/PWM.hex", r"firmware/大车proj/大车/OBJ/PWM.map"):
    print(f, os.path.getsize(f), time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(os.path.getmtime(f))))
m = open(r"firmware/大车proj/大车/OBJ/PWM.map", encoding='utf-8', errors='replace').read()
for sym in ('retrofit_on_mode_frame', 'retrofit_notify_loop', 'retrofit_sbus_ok'):
    print(sym, 'in map:', sym in m)
PY
```
Expected: `0 Error(s)`；`Program Size: Code=` 的具体数字；hex/map 的时间戳是刚才；三个符号都在 map 里（`retrofit_on_mode_frame` 必须在）。

- [ ] **Step 2: 把认版信息写进台账 §4**

追加一行（倒序，最新在上）：

```
| 2026-10-08 | E3 批 1a 认版 | Code=〔Step 1 实测数字〕，Warning=〔实测〕，hex/map mtime=〔实测〕，`retrofit_on_mode_frame`/`retrofit_notify_loop`/`retrofit_sbus_ok` 均在 `OBJ/PWM.map` | 台账 §4 + `firmware/大车proj/大车/OBJ/` | `UV4 -r` 退出码 + build_log 尾部 + map 符号三重证据；**STATUS 里 build_id 字段烧录后可在 PC 侧直接读出，从此不用靠 mtime 认版** | Qoder |
```

- [ ] **Step 3: 给作者的交接话术（写进提交信息，不单独建文件）**

```bash
git add "docs/参数差异台账.md"
git commit -F- --cleanup=verbatim <<'EOF'
批 1a 认版：Code/Warning/hex mtime/map 符号四条证据入台账 §4

给作者的操作口径仍然是一句话：**先 Rebuild 再 Download**（OBJ/ 被 gitignore，
hex 只活在构建它这台机器上）。烧完之后第一件事是在笔记本上看 STATUS 的
build_id 与 HMI 上屏的编译时间戳，跟台账这一行对上 —— 对上才算烧的是这一份。

⚠️ 烧完**不要立刻期待能进无人**：FIELD_SW_CALIBRATED 仍是 0（B2 那张通道表还没填），
现场拨档这一条 fail-closed，申请无人会被 reject=3 拒掉。这是刻意的安全默认。
台架先验 ⑨⑪⑫ 三条"被拒"场景，等 B2 填完数、把 FIELD_SW_CALIBRATED 改成 1 重编译，
再验需要真进无人的 ①②③④⑤⑥⑧⑩。
EOF
```

---

### Task 8: 台账/缺口清单/AGENTS 状态就地改判

**Files:**
- Modify: `docs/参数差异台账.md`（F1 相关的 Fw-14/Fw-17/Fw-21/Fw-22、Pc-8 的状态列**就地追加**改判，不删原文）
- Modify: `docs/缺口清单.md`（③-B 的 E3 行、②的 B1/B2 行、H2 关闭条件）
- Modify: `AGENTS.md`（"固件已重编译"那一段的数字与警告数、⑥ 的状态）

**Interfaces:** 无。

- [ ] **Step 1: 台账状态列就地追加**

按下表逐行**在原文之后追加**（保留原文，按"就地撤回/改判"的规矩）：

| 行 | 追加内容要点 |
|---|---|
| Fw-14 | `🟡 10-08 批 1a 已给唯一入口 = MODE(0x10) 单确认解除；lift_bits 由 0 改 0x07（F2 同批修掉）。**待台架 ⑫ 验证**才算关闭` |
| Fw-17 | `🟡 10-08 批 1a 已按不变量修（急停/门 N/TOOL 不新鲜/非持权者四种情况一律提刀）。**该台架 PD4/5/6 未接执行机构 ⇒ 只能验到信号级**，真实车上要重验` |
| Fw-21 | `🟡 10-08 批 1a 已加 loop_alive（main.c 一句 + STATUS 一个字节）与 reject=5，PC 侧 loop_stalled() 已就位。**待台架 B5（两分钟对照实验）验证**` |
| Fw-22 | `🔴 不改（A12）。10-08 已写进 spec §8 操作纪律；**X5 执行清单那一处待 Task 9 补**` |
| Pc-8 | `🟢 PC 侧（批 1b）+ 固件侧（批 1a）两半都已编码，**待台架信号级验证**；真实车接着电推杆时必须重验` |
| F1（在 v1.0 §4.3 与缺口清单里） | `🟡 10-08 已编码：NAV 不再改 mode，权限只能由 MODE 帧申请。**连带后果已落实**：link_probe 的旧判据作废并改写（批 1b Task 7）` |
| F3 | `🟡 10-08 已编码：TOOL 只认当前持权者 + 换主即作废旧目标 + 门 N 强制提刀禁横移。**⑧ 场景在台架无执行元件时是恒真命题，不算验过**` |

- [ ] **Step 2: 缺口清单与 AGENTS**

- 缺口清单 ③-B 第一条：`🟢 10-08 批 1b + 批 1a 均已编码；批 1a 已重编译（Code=〔实测〕）。**仍未台架** —— H2 关闭还差 B1 烧录 + B2 对拍（含 ①–⑥⑧–⑫）`
- 缺口清单 ② 的 B1 行加：`**新增判据**：拨杆后 STATUS 的 loop_alive 持续在变；HMI/STATUS 的 build_id 与台账认版行一致`
- 缺口清单 ② 的 B2 行加：`记录器已能发帧（--to + !nav/!tool/!beat/!auto/!manual/!clear），②③⑧ 这类"边发边记"现在做得了；**但 FIELD_SW_CALIBRATED=0 时 ②③⑧ 需要真进无人，必须等 B2 填表**`
- AGENTS "固件已重编译"那段：把 `09-21 UV4 -r：0 错误，60 警告，Code=44848` 之后**续写**（不删旧数字）：`→ 10-08 E3 批 1a：0 错误，〔实测〕警告，Code=〔实测〕，hex+map 已再生，map 内 retrofit_on_mode_frame@〔地址〕`
- AGENTS ⑥：`spec 已成文、待作者审阅` → `spec 已批准，批 1b（PC+工具，pytest 207）与批 1a（协议+固件，已重编译）均已编码，**未台架**`

- [ ] **Step 3: 跑检查器与全量测试**

Run: `python tools/check_doc_invariants.py` → Expected: 退出码 **0**（工具自己比对 AGENTS 写的基线，命中数以工具输出为准，**不要手抄数字进本计划**）。本任务不得新增任何"圈号 + 短横 + 圈号"的区间记法——要引用场景区间就写"①到⑥ 加 ⑧到⑫"这种逐号形式，或者直接把场景号列出来。
Run: `python -B -m pytest tests/ -q -p no:cacheprovider` → Expected: **207 passed**（批 1a 不改 Python）

- [ ] **Step 4: 提交**

```bash
git add docs/参数差异台账.md docs/缺口清单.md AGENTS.md
git commit -F- --cleanup=verbatim <<'EOF'
批 1a 编码完成后的状态改判：F1/F3/Fw-14/17/21、Pc-8 从"缺陷"改"已编码待台架"

七处状态列**就地追加**改判，原文一条不删（这个项目的规矩是撤回/改判都留痕）。
统一口径：批 1a 只到"已编码 + 已编译"，**没有一项到"已台架"**；两条硬禁令
（禁止实车 AUTO、禁止按现有接线文档直接带动力接线）继续生效。

同时把两个容易被读成"已经好了"的地方写明：
- Fw-17/Pc-8 在该台架上只能验到**信号级**（PD4/5/6 未接执行机构，作者 09-29 确认），
  真实车接着电推杆时必须重验；
- F3 的 ⑧ 场景在台架无执行元件时是**恒真命题**，不算验过（09-22 已定级）。

AGENTS 的编译数字续写不删历史；⑥ 的状态从"spec 待审"改为"两批均已编码、未台架"。
check_doc_invariants 退出码 0（未新增区间记法）；pytest 207 passed。
EOF
```

---

### Task 9: 台架验收（作者执行，qoder 出清单与判据）

**Files:**
- Modify: `docs/X5验机与接入执行清单.md`（追加"批 1a 烧录与对拍"一节，含 Fw-22 的操作纪律）

**Interfaces:** 无。**这一任务的执行者是作者**，qoder 只出清单、跑记录器、判读 CSV。

- [ ] **Step 1: 把操作纪律写进 X5 执行清单**

追加一节，内容必须包含：

```
## 批 1a 烧录与对拍（E3 门 N 步 2/步 3）

**上电前**
- 驱动轮**架空**（B2 全程；一旦离开 :305 那段死等，车会真的走）
- 确认 X5 的 bridge 在跑：`pgrep -af bridge`，没跑就 `bash vehicle/start_bridge.sh`
- 笔记本这侧：`python tools/bench_status.py --to 192.168.127.10:9000`（**--to 不填就是只收不发**）

**停车纪律（Fw-22，A12 的直接后果，必须遵守）**
- **不要用油门杆停车。** `main.c:305` 那段死等没有一次性闩锁，行驶中 ch[4] 一旦低于 800
  会再掉进去，而它既不写 PWM 也不喂狗 ⇒ 轮子保持上一次的占空比，直到约 3 秒后
  看门狗把整机咬复位才停。
- 停车用：遥控器那个停车/互锁档（ch[6]，低于 1400 即"停止工作"），或笔记本发 `!clear` 之前先发 `!manual`，或直接 `!estop`（急停会锁存，之后用 `!clear` 解除）。

**步 2（烧录 B1）通过标准**
1. 上电、遥控能正常开（MANUAL）
2. 不拨杆时板子仍会约 2.95 秒一轮重启 —— **这是 A12 的预期行为，不是故障**
3. 拨杆之后：STATUS 连续，且 `loop_alive` 列**持续在变**（不变 = 主循环没走到 = Fw-21）
4. `build_id` 与台账认版行一致（认版从此不靠文件时间）
5. `profile` 列 = 1（PREV），`permit` 在 PC 侧 = 1（门 N）

**步 3（对拍 B2）分两段**
- **B2 填表之前**（`FIELD_SW_CALIBRATED=0`，现场拨档 fail-closed）：只能验
  ⑨（不拨杆申请无人 → reject=5）、⑪（档案号故意填错 → reject=1）、
  ⑫（急停后 `!clear` → mode 回 MANUAL、刀位提、速度零、**不自动回无人**）
- **B2 填表并把 `FIELD_SW_CALIBRATED` 改 1 重编译之后**：验 ①②③④⑤⑥⑧⑩
  （清单见 spec §11；②③⑧ 涉及刀与横移，台架无执行元件 ⇒ **只到信号级，不许勾通过**）
```

- [ ] **Step 2: 作者执行，qoder 判读**

作者按上面跑；每跑完一段把 `results/bench_*/bench_log.csv` 路径发给 qoder。
qoder 判读要点：`loop_alive` 是否在变、`authority` 变迁序列是否与场景对得上、`reject` 是否是预期那一条、`tx_*` 行与 `frame` 行的时间差。

- [ ] **Step 3: 把结果回填台账与缺口清单**

每条场景一行：场景号 / CSV 路径 / 判定（通过 / 信号级 / 未过）/ 备注。**信号级就是信号级，不许写成通过**（09-22 定级）。

- [ ] **Step 4: 提交**

```bash
git add "docs/X5验机与接入执行清单.md"
git commit -F- --cleanup=verbatim <<'EOF'
X5 执行清单加"批 1a 烧录与对拍"一节：含 Fw-22 的停车纪律与 fail-closed 分段

三件事写死在清单里，因为它们是当场会出事的那种：
1. **不要用油门杆停车**（Fw-22）：:305 那段死等无闩锁，行驶中 ch[4]<800 会再掉进去，
   不写 PWM 也不喂狗 ⇒ 保持原速约 3 秒后整机重启。停车用 ch[6] 互锁档或急停帧。
2. **驱动轮全程架空**：离开死等之后车会真的走。
3. **B2 填表前只能验"被拒"类场景**（⑨⑪⑫）：FIELD_SW_CALIBRATED=0 时现场拨档
   fail-closed，需要真进无人的 ①②③④⑤⑥⑧⑩ 必须等通道表填好、改成 1 重编译。

另附步 2 的认版判据（loop_alive 在变 + build_id 与台账认版行一致），
从此"板上是哪一份镜像"不靠文件时间。
EOF
```

---

## Self-Review（本计划自查）

**1. spec 覆盖**：§2 许可位/档案号编译期常量 → Task 2；§3.1 MODE 帧 → Task 1/3；§3.2 五字段 → Task 5；§3.3 reject 码 → Task 2/3；§3.4 五处同步的固件两处（`protocol.c/h`）→ Task 1（`protocol.c` 无需改：它只按 `type` 透传，不认具体类型值——**这一点已在 Task 1 核对：`prot_parse_byte` 与 `prot_build` 都不 switch on type**）；§4.1 判定落在执行点 → Task 4 Step 3/4 + Task 5 Step 2（三个执行点都调 `owner_allows()` 或读 `loop_counter`）；§4.2 五条件 + 持续复查 → Task 3 Step 3 + Task 4 Step 5；§4.3 现场夺档与锁存 → Task 3 Step 2 + Task 4 Step 5；§4.4 NAV/TOOL 门 + 换主作废 → Task 3 Step 2（`set_owner`）+ Task 4 Step 1/2；§4.5 刀不变量 → Task 4 Step 3；§4.6 急停解除 → Task 3 Step 3；§4.7 loop_alive → Task 3 Step 2 + Task 5 Step 2；§4.8 编码统一 → Task 6；§8 厂商 Modbus 锁零 + 操作纪律 → Task 5 Step 3 + Task 9 Step 1；§10 步 1/2/3 → Task 7/9；§11 场景表 → Task 9；§13 R1/R2/R6/R10 → Task 5/6/7 的验证步骤。

**未覆盖（诚实列出，不在本批）**：§5.x 全部是批 1b（另一个计划文件）；§7.1 TELEOP 实现（批 2，固件现在回 `REJ_NOT_IMPL`）；§4.3 的 `FIELD_*` 三个阈值（等 B2 实测，本批 fail-closed）；HMI 上屏编译时间戳（spec §3.2 提到的 `build_id` 兜底）—— **这一条本批没做**，只有 STATUS 里的 `build_id`；要做需在 `main.c` 开机段加一句 `snprintf(tjcstr,...)`，属厂商文件的新增，留到 Task 7 之后单独一小批。

**2. 占位符扫描**：`〔待 B2 实测填入〕` 三处集中在 `FIELD_ALLOW_HI/FIELD_MID_LO/FIELD_MID_HI`，并且用 `FIELD_SW_CALIBRATED 0` 把它们**关成 fail-closed**——不是"先写个默认值以后再说"，是"没标定就进不了无人"。台账认版行里的 `〔实测数字〕` 是执行时当场抄的编译输出，Task 7 Step 1 给了取值命令。除此之外无 TBD/TODO/"类似 Task N"。

**3. 类型/符号一致性**：`owner_allows()` 在 Task 3 定义、Task 4 三处调用（NAV/TOOL/刀输出）与 Task 4 Step 4 的横移闭锁；`set_owner(who, reason)` 签名在 Task 3 定义、Task 3 Step 3/Step 4 与 Task 4 Step 5 调用一致（都是两个参数）；`field_allows_unmanned()` 在 Task 3 定义、Task 3/4 调用；`loop_counter` 声明为 `volatile uint8_t`（ISR 读、主循环写），`retrofit_notify_loop()` 只做 `loop_counter++`；`LOOP_STALL_FRAMES` 与 Python 侧 `STALL_FRAMES` **同为 5**（Task 2 与批 1b Task 4 各定义一次，值必须一致——已在两边写明）；STATUS 字段顺序与 `STATUS_V2_FMT = '<fffBBBBBBB'` 逐字节对齐（Task 5 Step 1 的 ⚠️）。

**4. 与批 1b 的接缝**：批 1b 的 `unpack_status_any` 按长度分派，所以**烧录前后 PC 都能跑**（旧固件 14 B → v1，新固件 19 B → v2）；批 1b 的 `link_probe` 已经会在收到 v1 帧时打印"板上是 E3 之前的固件"。⇒ 顺序错了不会静默错位，但仍要求 1b 先合（spec §3.5）。
