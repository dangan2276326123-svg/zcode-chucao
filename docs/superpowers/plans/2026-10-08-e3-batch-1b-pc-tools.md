# E3 批 1b（PC + 工具）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 E3 控制权限契约的 PC 侧与工具侧全部落地——权限由显式 `MODE` 帧申请、STATUS 按载荷长度兼容 14/19 字节、PC 持权期间永不发心跳、门 N 下只发提刀，并让台架工具能边发边记。

**Architecture:** 新增一个纯函数模块 `pc/wire.py` 承载"这一拍该往线上发什么帧"的全部判定（可单测，不碰 GUI/串口）；`pc/state_machine.py` 只管状态与许可位；`pc/status_rx.py` 只管把 STATUS 解成字典并判执行面是否停摆；`pc/main.py` 退化成"取状态 → 问 wire → 发帧 → 记日志"。协议常量集中在 `common/protocol.py`，固件侧（批 1a）镜像同一套数值。

**Tech Stack:** Python 3.9（本机 `D:\ruanjian\anac`），pytest 7.1.2，无新依赖；串口/UDP 用标准库。

## Global Constraints

- **实施顺序不可换**：本批（1b）必须先合入并跑通，批 1a（协议+固件）才允许烧录。理由见 spec §3.5：反了台架当天就字段错位。
- 契约来源唯一：`docs/superpowers/specs/2026-10-08-e3-control-authority-design.md`（下称 spec）。数值与字段名以 spec §3 为准，**不得在本批自行改协议**。
- STATUS 载荷：v1 = 14 字节 `'<fffBB'`，v2 = **19 字节** `'<fffBBBBBBB'`（3 个 f32 + 7 个 u8）；线上字节 = 载荷 + 9（2 头 + 2 长 + 1 型 + 2 序 + 2 CRC）⇒ v1 = 23、v2 = **28**。
- `TYPE_MODE = 5`，载荷 `'<BB'` = request + profile，线上 11 字节。
- 测试基线：当前 `python -B -m pytest tests/ -q -p no:cacheprovider` = **159 passed**。本批只增不减；每个任务结束时跑全量。
- 只读仓禁区：不得触碰 `D:\JetBrains\chucao_prj`（唯一例外 `thesis_cau/`，本批不涉及）。
- 编码：本批全是 UTF-8 的 Python 与 YAML，**不要动 `firmware/` 下任何文件**（那是批 1a）。
- Windows 控制台是 cp936：脚本里**不要 `print` 中文/emoji**，要输出中文就写文件或加 `PYTHONIOENCODING=utf-8`。
- 提交纪律：一个任务一个提交；提交信息用 `git commit -F <文件> --cleanup=verbatim`（避免标题复制事故），提交后 `git log --oneline -1` 与 `git show --numstat --format=""` 各看一次，确认标题与改动范围。
- 不提交 Keil 构建产物（`firmware/**/OBJ/`、`*.map`、`build_log.txt`、`PWM.uvguix.*`、`PWM.uvoptx`）与 `results/` 下的新 CSV，除非任务明确要求。

---

## File Structure

| 文件 | 责任 | 本批动作 |
|---|---|---|
| `common/protocol.py` | 帧与载荷的唯一权威（打包/解包/常量） | 加 `TYPE_MODE`、MODE/profile/authority/reject 常量、`pack_mode`/`unpack_mode`、`pack_status_v2`、`unpack_status_any`（按长度分派） |
| `pc/wire.py` | **新**：一拍该发什么帧 + `run_log` 列定义与行构造 | 创建 |
| `pc/state_machine.py` | PC 侧状态与许可位 | 加 `permit`、`needs_confirm`、`holds_authority`、`confirm_continue()`；改 `tools_raised` |
| `pc/status_rx.py` | STATUS 接收、坏帧计数、执行面停摆判定 | 改用 `unpack_status_any`；加 `loop_stalled()`、`reject_text()` |
| `pc/vehicle_profile.py` | **新**：读 `config/vehicle_profile.yaml`，给出 `profile_id` 与 `permit` | 创建 |
| `config/vehicle_profile.yaml` | **新**：车辆档案（握手用） | 创建 |
| `pc/main.py` | 控制循环、HUD、CSV | 发帧改走 `wire.frames_for_state`；按键改发 MODE 帧；CSV/HUD 加新列 |
| `tools/link_probe.py` | 单命令探针 | 判据换成"按命令定义预期响应 + 区分发送前基线"，加 `mode` 命令 |
| `tools/bench_status.py` | 台架记录器 | 加 `--to` 发送能力（opt-in）、stdin 命令、新列、发出的帧也落 CSV |
| `tools/latency_probe.py` | **新**：D1/D2 延迟自测 | 创建 |
| `tests/test_protocol.py`、`tests/test_wire.py`(新)、`tests/test_control.py`、`tests/test_status_rx.py`、`tests/test_vehicle_profile.py`(新)、`tests/test_link_probe.py`、`tests/test_bench_status.py`、`tests/test_latency_probe.py`(新) | 回归 | 逐任务新增/修改 |

---

### Task 1: 协议层——`TYPE_MODE` 与 STATUS v2 的按长度分派

**Files:**
- Modify: `common/protocol.py`（在 `TYPE_STATUS` 之后加常量；在文件末尾加新函数）
- Test: `tests/test_protocol.py`（追加）

**Interfaces:**
- Consumes: 现有 `pack_frame(frame_type, payload, seq)`、`unpack_frame(data)`、`crc16_ccitt_false`。
- Produces:
  - `TYPE_MODE = 5`
  - `MODE_REQ_MANUAL = 0x00`、`MODE_REQ_AUTO = 0x01`、`MODE_REQ_TELEOP = 0x02`、`MODE_REQ_CLEAR_ESTOP = 0x10`、`MODE_REQ_PROFILE = 0x20`
  - `PROFILE_NONE = 0`、`PROFILE_PREV = 1`、`PROFILE_REAL = 2`
  - `AUTH_BOOT = 0`、`AUTH_PC_GRANTED = 1`、`AUTH_FIELD_TAKEOVER = 2`、`AUTH_RCS_LOST = 3`、`AUTH_LINK_LOST_ESTOP = 4`、`AUTH_PC_CLEAR_ESTOP = 5`、`AUTH_PC_RELEASE = 6`、`AUTH_HEARTBEAT_RELEASE = 7`
  - `REJECT_NONE = 0`、`REJECT_PROFILE = 1`、`REJECT_RCS_STALE = 2`、`REJECT_FIELD_SWITCH = 3`、`REJECT_ESTOP_LATCHED = 4`、`REJECT_LOOP_STALLED = 5`、`REJECT_NOT_IMPL = 6`、`REJECT_FIELD_LATCHED = 7`、`REJECT_PERMIT = 8`
  - `REJECT_TEXT = {code: 中文短句}`（HUD 用，spec §5.4 要求"人话不是十六进制"）
  - `STATUS_V1_LEN = 14`、`STATUS_V2_LEN = 19`、`STATUS_V2_FMT = '<fffBBBBBBB'`
  - `pack_mode(request: int, profile: int = 0) -> bytes`
  - `unpack_mode(payload: bytes) -> tuple[int, int]`
  - `pack_status_v2(speed, current_a, battery_v, limits, mode, profile, authority, loop_alive, build_id, reject) -> bytes`
  - `unpack_status_any(payload: bytes) -> dict`（键：`speed_mps, current_a, battery_v, limits, mode, profile, authority, loop_alive, build_id, reject, v`；v1 时后五个 E3 键为 `None`、`v=1`）
  - `wire_len(payload_len) -> int` = `payload_len + 9`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_protocol.py`：

```python
def test_mode_roundtrip():
    data = P.pack_frame(P.TYPE_MODE, P.pack_mode(P.MODE_REQ_AUTO, P.PROFILE_PREV), seq=11)
    t, seq, payload = P.unpack_frame(data)
    assert (t, seq) == (P.TYPE_MODE, 11)
    assert P.unpack_mode(payload) == (P.MODE_REQ_AUTO, P.PROFILE_PREV)
    assert len(data) == 11          # 2+2+1+2+2+2


def test_mode_payload_length_guard():
    with pytest.raises(ValueError):
        P.unpack_mode(b'\x01')


def test_status_v2_roundtrip_and_wire_size():
    payload = P.pack_status_v2(0.14, 0.0, 48.0, 0b101, 1,
                               P.PROFILE_REAL, P.AUTH_PC_GRANTED,
                               7, 0x3A, P.REJECT_NONE)
    assert len(payload) == P.STATUS_V2_LEN == 19
    data = P.pack_frame(P.TYPE_STATUS, payload, seq=5)
    assert len(data) == 28
    st = P.unpack_status_any(P.unpack_frame(data)[2])
    assert st['v'] == 2
    assert st['speed_mps'] == pytest.approx(0.14)
    assert (st['limits'], st['mode']) == (0b101, 1)
    assert (st['profile'], st['authority'], st['loop_alive'],
            st['build_id'], st['reject']) == (
        P.PROFILE_REAL, P.AUTH_PC_GRANTED, 7, 0x3A, P.REJECT_NONE)


def test_unpack_status_any_dispatches_v1_and_leaves_e3_keys_none():
    """A8 混跑用例一：旧固件帧 + 新 PC。不得崩，且不得把 limits 当成 profile。"""
    old = P.pack_status(0.1, 0.0, 48.0, 0b011, 0)     # 14 bytes
    st = P.unpack_status_any(old)
    assert st['v'] == 1 and st['mode'] == 0 and st['limits'] == 0b011
    assert st['profile'] is None and st['authority'] is None
    assert st['loop_alive'] is None and st['build_id'] is None
    assert st['reject'] is None


def test_unpack_status_any_rejects_other_lengths():
    for bad in (b'', b'\x00' * 13, b'\x00' * 15, b'\x00' * 18, b'\x00' * 20):
        with pytest.raises(ValueError):
            P.unpack_status_any(bad)


def test_wire_len_helper():
    assert P.wire_len(0) == 9 and P.wire_len(2) == 11
    assert P.wire_len(14) == 23 and P.wire_len(19) == 28


def test_reject_text_covers_every_code():
    codes = [P.REJECT_NONE, P.REJECT_PROFILE, P.REJECT_RCS_STALE,
             P.REJECT_FIELD_SWITCH, P.REJECT_ESTOP_LATCHED,
             P.REJECT_LOOP_STALLED, P.REJECT_NOT_IMPL,
             P.REJECT_FIELD_LATCHED, P.REJECT_PERMIT]
    assert set(P.REJECT_TEXT) == set(codes)
    assert all(isinstance(v, str) and v for v in P.REJECT_TEXT.values())
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -B -m pytest tests/test_protocol.py -q -p no:cacheprovider`
Expected: FAIL，`AttributeError: module 'common.protocol' has no attribute 'TYPE_MODE'`

- [ ] **Step 3: 写实现**

在 `common/protocol.py` 的 `TYPE_STATUS = 0x10` 之后插入：

```python
TYPE_MODE = 5           # E3: 权限申请/交回/解除急停/档案握手（spec §3.1）

# MODE.request（spec §3.1）
MODE_REQ_MANUAL = 0x00        # 交回人工
MODE_REQ_AUTO = 0x01          # 申请无人
MODE_REQ_TELEOP = 0x02        # 申请遥操作（批 2 实现；固件回 REJECT_NOT_IMPL）
MODE_REQ_CLEAR_ESTOP = 0x10   # 解除急停（A3 单确认）
MODE_REQ_PROFILE = 0x20       # 档案握手，profile 字段有效

# 车辆档案（spec §2 / §6）
PROFILE_NONE = 0
PROFILE_PREV = 1        # 上代车 3.25 m
PROFILE_REAL = 2        # 样机 2.15 m

# STATUS.authority = 最近一次权限变迁的原因（spec §3.2）
AUTH_BOOT = 0
AUTH_PC_GRANTED = 1
AUTH_FIELD_TAKEOVER = 2
AUTH_RCS_LOST = 3
AUTH_LINK_LOST_ESTOP = 4
AUTH_PC_CLEAR_ESTOP = 5
AUTH_PC_RELEASE = 6
AUTH_HEARTBEAT_RELEASE = 7

# STATUS.reject（spec §3.3）
REJECT_NONE = 0
REJECT_PROFILE = 1
REJECT_RCS_STALE = 2
REJECT_FIELD_SWITCH = 3
REJECT_ESTOP_LATCHED = 4
REJECT_LOOP_STALLED = 5
REJECT_NOT_IMPL = 6
REJECT_FIELD_LATCHED = 7
REJECT_PERMIT = 8

REJECT_TEXT = {
    REJECT_NONE: '',
    REJECT_PROFILE: '档案不符（PC 与固件不是同一台车）',
    REJECT_RCS_STALE: '遥控不新鲜（接收机断链或未同步）',
    REJECT_FIELD_SWITCH: '现场拨档不在"允许无人"位',
    REJECT_ESTOP_LATCHED: '急停仍锁存',
    REJECT_LOOP_STALLED: '执行面停摆（主循环计数不变，见 Fw-21）',
    REJECT_NOT_IMPL: '该模式本批未实现',
    REJECT_FIELD_LATCHED: '已被现场夺权，锁存中',
    REJECT_PERMIT: '许可位拒绝（门 N 下不许落刀/横移）',
}

STATUS_V1_LEN = 14
STATUS_V2_LEN = 19
STATUS_V1_FMT = '<fffBB'
STATUS_V2_FMT = '<fffBBBBBBB'   # + profile, authority, loop_alive, build_id, reject
```

在文件末尾追加：

```python
def wire_len(payload_len: int) -> int:
    """线上总字节 = 载荷 + 9（2 头 + 2 长 + 1 型 + 2 序 + 2 CRC）。"""
    return payload_len + HEADER_LEN + META_LEN + 2


def pack_mode(request: int, profile: int = 0) -> bytes:
    """MODE payload: request code + 档案号（只在 MODE_REQ_PROFILE 时有意义）。"""
    return struct.pack('<BB', request, profile)


def unpack_mode(payload: bytes):
    if len(payload) != 2:
        raise ValueError('mode payload must be 2 bytes')
    return struct.unpack('<BB', payload)


def pack_status_v2(speed: float, current_a: float, battery_v: float,
                   limits: int, mode: int, profile: int, authority: int,
                   loop_alive: int, build_id: int, reject: int) -> bytes:
    """STATUS v2 (19 B) — spec §3.2。loop_alive/build_id/reject 都是 u8。"""
    return struct.pack(STATUS_V2_FMT, speed, current_a, battery_v, limits, mode,
                       profile, authority, loop_alive & 0xFF,
                       build_id & 0xFF, reject)


def unpack_status_any(payload: bytes) -> dict:
    """按载荷长度分派（A8）：14 B = v1（E3 之前的固件），19 B = v2。

    v1 时 E3 那五个键返回 None，这样调用方能区分"旧固件"与"新固件报了 0"。
    其它长度一律 ValueError —— 字段错位必须炸，不能静默读歪。
    """
    if len(payload) == STATUS_V1_LEN:
        speed, cur, bat, limits, mode = struct.unpack(STATUS_V1_FMT, payload)
        return {'speed_mps': speed, 'current_a': cur, 'battery_v': bat,
                'limits': limits, 'mode': mode, 'profile': None,
                'authority': None, 'loop_alive': None, 'build_id': None,
                'reject': None, 'v': 1}
    if len(payload) == STATUS_V2_LEN:
        (speed, cur, bat, limits, mode, profile, authority,
         loop_alive, build_id, reject) = struct.unpack(STATUS_V2_FMT, payload)
        return {'speed_mps': speed, 'current_a': cur, 'battery_v': bat,
                'limits': limits, 'mode': mode, 'profile': profile,
                'authority': authority, 'loop_alive': loop_alive,
                'build_id': build_id, 'reject': reject, 'v': 2}
    raise ValueError('status payload must be %d or %d bytes, got %d'
                     % (STATUS_V1_LEN, STATUS_V2_LEN, len(payload)))
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -B -m pytest tests/test_protocol.py -q -p no:cacheprovider`
Expected: PASS（原有 5 条 + 新增 7 条）

- [ ] **Step 5: 全量回归 + 提交**

Run: `python -B -m pytest tests/ -q -p no:cacheprovider` → Expected: **166 passed**（159 + 7）

```bash
git add common/protocol.py tests/test_protocol.py
git commit -F- --cleanup=verbatim <<'EOF'
协议层加 TYPE_MODE 与 STATUS v2：按载荷长度分派 14/19 字节，旧固件帧不崩

E3 批 1b 第 1 步（spec §3）。新增 MODE 帧（申请无人/交回/解除急停/档案握手）、
档案号、authority 变迁原因码、reject 原因码及其人话文案、loop_alive/build_id 位。
unpack_status_any 按长度分派：14 B 走 v1 且 E3 五个键为 None（能区分"旧固件"与
"新固件报 0"），19 B 走 v2，其它长度一律 ValueError —— 字段错位必须炸。
wire_len() 把"载荷 + 9"这个换算收成一处。

pytest 159 -> 166 passed。本批不动 firmware/。
EOF
```

---

### Task 2: `pc/wire.py`——一拍该发什么帧（A9 状态优先 + A5/A6 许可位）

**Files:**
- Create: `pc/wire.py`
- Test: `tests/test_wire.py`（新建）

**Interfaces:**
- Consumes: `common.protocol`（`TYPE_NAV/TYPE_TOOL/TYPE_HEARTBEAT/TYPE_ESTOP`、`pack_nav`、`pack_tool`）。
- Produces:
  - `GATE_N = 1`、`GATE_F = 2`
  - `HOLDING = ('AUTO', 'LIFT')`（持权的 PC 状态）
  - `frames_for_state(state: str, usable: bool, vl: float, vr: float, tool_mm: float, permit: int = GATE_N) -> list[tuple[int, bytes]]`
  - `RUN_LOG_COLUMNS: list[str]`
  - `run_log_row(t_rel, fid, state, res, lat_m, lat_comp_m, vl, vr, tool_mm, latency_ms, st, feed_snapshot, permit) -> list`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_wire.py`：

```python
# -*- coding: utf-8 -*-
"""E3 §5.1/§5.3：线上语义由"是否持权"决定，不由视觉决定。"""
from common import protocol as P
from pc import wire


def _kinds(frames):
    return [f[0] for f in frames]


def test_manual_emits_only_heartbeat():
    frames = wire.frames_for_state('MANUAL', True, 0.2, 0.2, 5.0)
    assert _kinds(frames) == [P.TYPE_HEARTBEAT]


def test_auto_with_vision_emits_nav_and_tool():
    frames = wire.frames_for_state('AUTO', True, 0.14, 0.14, 3.0, wire.GATE_F)
    assert _kinds(frames) == [P.TYPE_NAV, P.TYPE_TOOL]
    assert P.unpack_nav(frames[0][1])[:2] == (0.14, 0.14)


def test_auto_without_vision_still_holds_authority():
    """codex 新发现一的正解：这一拍不许掉到 HEARTBEAT。"""
    frames = wire.frames_for_state('AUTO', False, 0.14, 0.14, 3.0)
    assert P.TYPE_HEARTBEAT not in _kinds(frames)
    assert _kinds(frames) == [P.TYPE_NAV, P.TYPE_TOOL]
    vl, vr, _flags = P.unpack_nav(frames[0][1])
    assert (vl, vr) == (0.0, 0.0)          # 速度锁零
    off, lift = P.unpack_tool(frames[1][1])
    assert off == 0.0 and lift == 0x07     # 提刀


def test_gate_n_forces_knives_up_and_no_lateral_even_in_auto():
    """Pc-8 的正解：门 N 下 AUTO 也只发提刀、横移恒 0。"""
    frames = wire.frames_for_state('AUTO', True, 0.14, 0.12, -8.0, wire.GATE_N)
    off, lift = P.unpack_tool(frames[1][1])
    assert off == 0.0 and lift == 0x07


def test_gate_f_allows_knives_down_only_when_auto_and_usable():
    down = wire.frames_for_state('AUTO', True, 0.1, 0.1, 2.0, wire.GATE_F)
    assert P.unpack_tool(down[1][1]) == (2.0, 0x00)
    # 同样 GATE_F，但视觉不可用 -> 仍然提刀、速度零
    up = wire.frames_for_state('AUTO', False, 0.1, 0.1, 2.0, wire.GATE_F)
    assert P.unpack_nav(up[0][1])[:2] == (0.0, 0.0)
    assert P.unpack_tool(up[1][1]) == (0.0, 0x07)


def test_lift_state_holds_authority_with_zero_speed():
    frames = wire.frames_for_state('LIFT', False, 0.0, 0.0, 0.0, wire.GATE_F)
    assert _kinds(frames) == [P.TYPE_NAV, P.TYPE_TOOL]
    assert P.unpack_tool(frames[1][1]) == (0.0, 0x07)


def test_estop_emits_nothing_every_beat():
    """ESTOP 帧只在状态跳变那一拍由 main.py 发一次，稳态不发帧。"""
    assert wire.frames_for_state('ESTOP', True, 0.0, 0.0, 0.0) == []


def test_run_log_columns_cover_the_e3_fields():
    for col in ('profile', 'mcu_mode', 'authority', 'reject',
                'loop_alive', 'build_id', 'permit'):
        assert col in wire.RUN_LOG_COLUMNS


def test_run_log_row_matches_column_count():
    st = {'seq': 3, 'speed_mps': 0.0, 'current_a': 0.0, 'battery_v': 48.0,
          'limits': 0, 'mode': 1, 'profile': 2, 'authority': 1,
          'loop_alive': 9, 'build_id': 0x3A, 'reject': 0, 'v': 2}
    res = {'status': 'dual', 'confidence': 0.5, 'lateral_px': 3.0}
    row = wire.run_log_row(1.0, 7, 'AUTO', res, 0.01, 0.02, 0.1, 0.1, 0.0,
                           12.0, st, ({}, 0, None), wire.GATE_N)
    assert len(row) == len(wire.RUN_LOG_COLUMNS)


def test_run_log_row_tolerates_v1_status_and_no_status():
    res = {'status': 'none', 'confidence': 0.0, 'lateral_px': None}
    row_none = wire.run_log_row(1.0, 1, 'MANUAL', res, 0.0, 0.0, 0.0, 0.0,
                                0.0, 5.0, None, ({}, 0, None), wire.GATE_N)
    row_v1 = wire.run_log_row(1.0, 2, 'MANUAL', res, 0.0, 0.0, 0.0, 0.0,
                              0.0, 5.0, {'seq': 1, 'mode': 0, 'v': 1},
                              ({}, 0, None), wire.GATE_N)
    assert len(row_none) == len(row_v1) == len(wire.RUN_LOG_COLUMNS)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -B -m pytest tests/test_wire.py -q -p no:cacheprovider`
Expected: FAIL，`ModuleNotFoundError: No module named 'pc.wire'`

- [ ] **Step 3: 写实现**

创建 `pc/wire.py`：

```python
# -*- coding: utf-8 -*-
"""E3 契约 §5.1/§5.3：这一拍往线上发什么帧，由"是否持权"决定，不由视觉决定。

抽成独立模块的理由：原来的判定散在 pc/main.py 的三个分支里
（:243 AUTO+usable / :253 LIFT / :261 else），"AUTO 但这一帧不可用且未满 2 秒"
会掉进 else 发 HEARTBEAT，固件收到心跳就把权限交回遥控（retrofit.c:70-73），
而 PC 状态与 run_log 仍写着 AUTO —— 这就是 codex 新发现一。
纯函数化之后这条规则可以被单测钉住。
"""
from common import protocol as P

# 执行许可位（spec §2 / A5）：编译期常量在固件侧，这里是 PC 侧镜像，
# 只决定"PC 该发什么"；两边不一致时以固件为准（固件会 reject=REJECT_PERMIT）。
GATE_N = 1     # 只许沿行空跑：刀强制提、横移强制禁
GATE_F = 2     # 允许落刀作业与横移

PERMIT_BY_NAME = {'gate_n': GATE_N, 'gate_f': GATE_F}

# 持权的 PC 状态。ESTOP 不持权（谁都不能动），MANUAL 是遥控持权。
HOLDING = ('AUTO', 'LIFT')

RUN_LOG_COLUMNS = [
    't', 'frame_id', 'state', 'status', 'lat_m', 'lat_comp_m',
    'vL', 'vR', 'tool_mm', 'conf', 'latency_ms',
    'mcu_mode', 'batt_v', 'rx_good', 'rx_bad',
    'frame_age_s', 'recv_timeouts', 'link_drops',
    # ---- E3 新增（spec §5.4）----
    'profile', 'authority', 'reject', 'loop_alive', 'build_id', 'permit',
]


def frames_for_state(state, usable, vl, vr, tool_mm, permit=GATE_N):
    """返回 [(frame_type, payload), ...]。

    规则（spec §5.1 表）：
      - 持权（AUTO/LIFT）→ 必须发 NAV+TOOL，**永不发 HEARTBEAT**；
        视觉不可用或处于 LIFT 时速度锁零、刀位提刀。
      - MANUAL → 只发 HEARTBEAT。
      - ESTOP → 稳态不发帧（跳变那一拍由调用方发一次 ESTOP 帧）。
    许可位（spec §5.3）：GATE_N 下横移恒 0、刀位恒 0x07；
      GATE_F 下只有 "AUTO 且视觉可用" 才允许落刀（lift=0）。
    """
    if state not in HOLDING:
        if state == 'ESTOP':
            return []
        return [(P.TYPE_HEARTBEAT, b'')]

    if not usable or state == 'LIFT':
        vl, vr, tool_mm = 0.0, 0.0, 0.0

    if permit == GATE_N:
        off, lift = 0.0, 0x07
    else:
        off = tool_mm
        lift = 0x00 if (state == 'AUTO' and usable) else 0x07

    return [(P.TYPE_NAV, P.pack_nav(vl, vr)),
            (P.TYPE_TOOL, P.pack_tool(off, lift))]


def run_log_row(t_rel, fid, state, res, lat_m, lat_comp_m, vl, vr, tool_mm,
                latency_ms, st, feed_snapshot, permit,
                rx_good='', rx_bad='', recv_timeouts='', link_drops=''):
    """按 RUN_LOG_COLUMNS 的顺序拼一行。st 可以是 None（无 STATUS）或 v1 字典。"""
    st = st or {}
    _feed, _seq, age = feed_snapshot if feed_snapshot else ({}, 0, None)

    def _e3(key):
        v = st.get(key)
        return '' if v is None else v

    return [
        '%.3f' % t_rel, fid, state,
        res.get('status', ''),
        '' if lat_m is None else '%.4f' % lat_m,
        '' if lat_comp_m is None else '%.4f' % lat_comp_m,
        '%.3f' % vl, '%.3f' % vr, '%.2f' % tool_mm,
        '%.3f' % res.get('confidence', 0.0),
        '%.1f' % latency_ms,
        st.get('mode', ''),
        '%.2f' % st['battery_v'] if 'battery_v' in st else '',
        rx_good, rx_bad,
        '' if age is None else '%.3f' % age,
        recv_timeouts, link_drops,
        _e3('profile'), _e3('authority'), _e3('reject'),
        _e3('loop_alive'), _e3('build_id'), permit,
    ]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -B -m pytest tests/test_wire.py -q -p no:cacheprovider`
Expected: PASS（10 条）

- [ ] **Step 5: 全量回归 + 提交**

Run: `python -B -m pytest tests/ -q -p no:cacheprovider` → Expected: **176 passed**

```bash
git add pc/wire.py tests/test_wire.py
git commit -F- --cleanup=verbatim <<'EOF'
新增 pc/wire.py：线上发什么帧由"是否持权"决定，不由视觉决定

E3 批 1b 第 2 步（spec §5.1/§5.3）。把原来散在 pc/main.py 三个分支里的判定
抽成纯函数 frames_for_state()，于是两条安全规则可以被单测钉住：

1. 持权（AUTO/LIFT）期间**永不发 HEARTBEAT** —— 修 codex 新发现一：
   "AUTO 但这一帧不可用且未满 2 秒"过去会掉进 else 发心跳，固件收到就把权限
   交回遥控（retrofit.c:70-73），而 PC 状态与 run_log 仍写着 AUTO。
2. 门 N（GATE_N）下横移恒 0、刀位恒 0x07 —— 修 Pc-8：pc/main.py:252 过去
   每周期发 lift=0（= 三路刀全落），门 N 的"刀锁提、禁横移"在 PC 侧零实现。

同时把 run_log 的列定义与行构造收进本模块（RUN_LOG_COLUMNS/run_log_row），
新增 profile/authority/reject/loop_alive/build_id/permit 六列；st 允许为
None 或 v1 字典（E3 字段为空串），列数恒定。

pytest 166 -> 176 passed。本批不动 firmware/，pc/main.py 的接线在 Task 6。
EOF
```

---

### Task 3: `pc/state_machine.py`——许可位、需要人确认、持权判定

**Files:**
- Modify: `pc/state_machine.py`
- Test: `tests/test_control.py`（改 1 条、追加 4 条）

**Interfaces:**
- Consumes: `pc.wire.GATE_N`/`GATE_F`。
- Produces:
  - `StateMachine(permit=wire.GATE_N)`，属性 `permit`、`needs_confirm`
  - `holds_authority -> bool`（`state in ('AUTO', 'LIFT')`）
  - `tools_raised -> bool`（改：`state != AUTO or permit == GATE_N`）
  - `vision_loss(no_boundary_evidence=True)`（新参数，默认 True ⇒ 置 `needs_confirm`）
  - `confirm_continue() -> bool`（LIFT 且 `needs_confirm` → 清标志并回 MANUAL）

- [ ] **Step 1: 改写会被契约变更打破的那条测试，并追加新测试**

`tests/test_control.py` 里现有的 `test_tools_raised_outside_auto`（约 120-126 行）断言 `go_auto()` 之后 `not sm.tools_raised`。**这条断言在 E3 之后不再成立**（默认许可位是门 N，AUTO 也必须提刀），按新契约改写：

```python
def test_tools_raised_depends_on_permit():
    """E3 §5.3：门 N 下 AUTO 也提刀；只有门 F 的 AUTO 才允许落刀。"""
    sm = StateMachine()                       # 默认 permit = GATE_N
    assert sm.tools_raised
    sm.go_auto()
    assert sm.tools_raised                    # <- 契约变更：过去这里是 False
    sm.estop()
    assert sm.tools_raised

    sm_f = StateMachine(permit=wire.GATE_F)
    assert sm_f.tools_raised
    sm_f.go_auto()
    assert not sm_f.tools_raised              # 门 F 的 AUTO 才落刀
```

（文件顶部加 `from pc import wire`。）

追加：

```python
def test_holds_authority_matches_wire_holding():
    sm = StateMachine()
    assert not sm.holds_authority             # MANUAL
    sm.go_auto()
    assert sm.holds_authority
    sm.vision_loss()
    assert sm.holds_authority                 # LIFT 仍持权
    assert sm.state == 'LIFT'
    sm.go_manual()
    assert not sm.holds_authority


def test_vision_loss_sets_needs_confirm_and_vision_ok_does_not_clear_it():
    """L2.5：无墙且无独立边界依据 -> 停车 + 必须人工确认，视觉回来也不自动放行。"""
    sm = StateMachine()
    sm.go_auto()
    sm.vision_loss()                          # 默认 no_boundary_evidence=True
    assert sm.needs_confirm
    sm.vision_ok()
    assert sm.state == 'MANUAL'
    assert sm.needs_confirm                   # 标志不被视觉恢复清掉
    assert not sm.go_auto()                   # 未确认前不许再进无人
    assert sm.confirm_continue()
    assert not sm.needs_confirm
    assert sm.go_auto() and sm.state == 'AUTO'


def test_vision_loss_with_boundary_evidence_does_not_need_confirm():
    sm = StateMachine()
    sm.go_auto()
    sm.vision_loss(no_boundary_evidence=False)
    assert sm.state == 'LIFT' and not sm.needs_confirm
    sm.vision_ok()
    assert sm.go_auto()                       # 有边界依据时允许直接恢复


def test_manual_vision_loss_still_does_not_change_state():
    """H2.1 旧契约保留：MANUAL 下失视觉不改状态（否则 NAV(0,0) 会被当成进 AUTO）。"""
    sm = StateMachine()
    sm.vision_loss()
    assert sm.state == 'MANUAL'
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -B -m pytest tests/test_control.py -q -p no:cacheprovider`
Expected: FAIL —— `TypeError: __init__() got an unexpected keyword argument 'permit'`、`AttributeError: 'StateMachine' object has no attribute 'holds_authority'`，以及改写后的 `test_tools_raised_depends_on_permit` 失败。

- [ ] **Step 3: 写实现**

`pc/state_machine.py` 改动（保留原有四态与 `go_auto/go_manual/estop/clear_estop` 的既有语义）：

```python
from pc import wire


class StateMachine:
    MANUAL = 'MANUAL'
    AUTO = 'AUTO'
    LIFT = 'LIFT'
    ESTOP = 'ESTOP'

    def __init__(self, permit=wire.GATE_N):
        self.state = self.MANUAL
        self.permit = permit          # E3 §2：门 N / 门 F 执行许可位
        self.needs_confirm = False    # E3 §5.2 L2.5：停车后必须人工确认
        self._events = []

    # ... 原有 _to / go_auto / go_manual / estop / clear_estop 不变 ...

    def vision_loss(self, no_boundary_evidence=True):
        """AUTO 下失视觉 -> LIFT（可恢复，线上发 NAV0 + TOOL 提刀）。

        E3 §5.2：无墙且**无独立边界依据**时置 needs_confirm（L2.5 保守档）——
        不声称能区分"到行尾"与"感知失败"，两类都交人判。
        H2.1 旧契约保留：MANUAL 下失视觉不改状态。
        """
        if self.state != self.AUTO:
            return
        if no_boundary_evidence:
            self.needs_confirm = True
        self._to(self.LIFT)

    def vision_ok(self):
        """只从 LIFT 恢复到 MANUAL；**不清 needs_confirm**，也不自动回 AUTO。"""
        if self.state == self.LIFT:
            self._to(self.MANUAL)
            return True
        return False

    def confirm_continue(self):
        """L2.5 的人工确认键：清标志。返回是否真的清掉了。"""
        if not self.needs_confirm:
            return False
        self.needs_confirm = False
        return True

    @property
    def holds_authority(self):
        """PC 是否持权 —— 与 wire.HOLDING 同源，别各写一份。"""
        return self.state in wire.HOLDING

    @property
    def wheels_enabled(self):
        return self.state == self.AUTO

    @property
    def tools_raised(self):
        """E3 §5.3：门 N 下 AUTO 也提刀；只有门 F 的 AUTO 才允许落刀。"""
        return self.state != self.AUTO or self.permit == wire.GATE_N
```

`go_auto()` 里加一条前置拒绝（在 `if self.state == self.ESTOP: return False` 之后）：

```python
        if self.needs_confirm:
            return False          # L2.5 未确认前不许再进无人
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -B -m pytest tests/test_control.py -q -p no:cacheprovider`
Expected: PASS

- [ ] **Step 5: 全量回归 + 提交**

Run: `python -B -m pytest tests/ -q -p no:cacheprovider` → Expected: **180 passed**

```bash
git add pc/state_machine.py tests/test_control.py
git commit -F- --cleanup=verbatim <<'EOF'
状态机加许可位与"需要人工确认"，tools_raised 按门 N/门 F 分别判定

E3 批 1b 第 3 步（spec §2/§5.2/§5.3）。

契约变更（原测试断言随之改写，不是把测试改绿）：test_tools_raised_outside_auto
断言 go_auto() 后 not tools_raised —— E3 之后默认许可位是门 N，AUTO 也必须提刀，
所以改写成 test_tools_raised_depends_on_permit，同时覆盖门 F 的 AUTO 才落刀。

新增：permit（门 N/门 F，与 wire 同源）、needs_confirm（L2.5：无墙且无独立边界
依据时置位，视觉恢复**不清**它，未确认前 go_auto() 直接拒绝）、confirm_continue()、
holds_authority（复用 wire.HOLDING，不各写一份）。
vision_loss() 加 no_boundary_evidence 参数；MANUAL 下失视觉不改状态这条 H2.1
旧契约原样保留。

pytest 176 -> 180 passed。
EOF
```

---

### Task 4: `pc/status_rx.py`——解 v2、判执行面停摆、拒绝原因给人话

**Files:**
- Modify: `pc/status_rx.py`
- Test: `tests/test_status_rx.py`（追加）

**Interfaces:**
- Consumes: `P.unpack_status_any`、`P.REJECT_TEXT`（Task 1）。
- Produces:
  - `STALL_FRAMES = 5`（模块常量）
  - `StatusReceiver.last` 现在含 E3 五个键（v1 时为 `None`）
  - `StatusReceiver.loop_stalled(frames=STALL_FRAMES) -> bool`
  - `StatusReceiver.reject_text() -> str`
  - `StatusReceiver.status_version -> int | None`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_status_rx.py`（沿用该文件现有的构造帧方式；若没有辅助函数就用下面这个）：

```python
def _v2(seq, loop_alive, reject=0, mode=1, profile=2, authority=1, build=0x3A):
    payload = P.pack_status_v2(0.0, 0.0, 48.0, 0, mode, profile,
                               authority, loop_alive, build, reject)
    return P.pack_frame(P.TYPE_STATUS, payload, seq=seq)


def test_v2_fields_land_in_last():
    rx = StatusReceiver()
    st = rx.handle(_v2(1, 7), now=100.0)
    assert st['v'] == 2 and st['profile'] == 2 and st['authority'] == 1
    assert st['loop_alive'] == 7 and st['build_id'] == 0x3A
    assert rx.status_version == 2


def test_v1_frame_keeps_e3_keys_none_and_does_not_crash():
    """A8 混跑用例：旧固件帧 + 新 PC。"""
    rx = StatusReceiver()
    payload = P.pack_status(0.1, 0.0, 48.0, 0, 0)
    st = rx.handle(P.pack_frame(P.TYPE_STATUS, payload, seq=1), now=100.0)
    assert st is not None and st['v'] == 1
    assert st['profile'] is None and st['loop_alive'] is None
    assert rx.status_version == 1
    assert not rx.loop_stalled()          # v1 无从判断，绝不谎报停摆


def test_loop_stalled_needs_five_identical_reads():
    rx = StatusReceiver()
    for i in range(4):
        rx.handle(_v2(10 + i, 3), now=100.0 + i * 0.05)
    assert not rx.loop_stalled()          # 4 帧还不够
    rx.handle(_v2(14, 3), now=100.2)
    assert rx.loop_stalled()              # 第 5 帧仍不变 -> 执行面停摆


def test_loop_stalled_false_when_counter_moves():
    rx = StatusReceiver()
    for i in range(6):
        rx.handle(_v2(20 + i, i), now=200.0 + i * 0.05)
    assert not rx.loop_stalled()


def test_loop_stalled_wraps_at_255():
    rx = StatusReceiver()
    for i, v in enumerate([253, 254, 255, 0, 1]):
        rx.handle(_v2(30 + i, v), now=300.0 + i * 0.05)
    assert not rx.loop_stalled()          # u8 回绕不算停摆


def test_reject_text_is_human_readable():
    rx = StatusReceiver()
    rx.handle(_v2(40, 1, reject=P.REJECT_FIELD_SWITCH), now=400.0)
    assert rx.reject_text() == P.REJECT_TEXT[P.REJECT_FIELD_SWITCH]
    rx.handle(_v2(41, 2, reject=P.REJECT_NONE), now=400.05)
    assert rx.reject_text() == ''
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -B -m pytest tests/test_status_rx.py -q -p no:cacheprovider`
Expected: FAIL，`AttributeError: 'StatusReceiver' object has no attribute 'loop_stalled'`（以及 `status_version`）

- [ ] **Step 3: 写实现**

`pc/status_rx.py`：把 `handle()` 里那一行 `speed, current_a, battery_v, limits, mode = P.unpack_status(payload)` 换成字典解包，并加停摆判定：

```python
STALL_FRAMES = 5    # 主循环约 80 ms 一圈、STATUS 20 Hz：250 ms 内应有约 3 次自增，
                    # 连续 5 帧读到同一个值 = 执行面停摆（spec §3.2 loop_alive）


class StatusReceiver:
    def __init__(self):
        # ... 原有字段不变 ...
        self._loop_hist = deque(maxlen=STALL_FRAMES)

    def handle(self, raw, now=None):
        now = time.monotonic() if now is None else now
        try:
            ftype, seq, payload = P.unpack_frame(raw)
            if ftype != P.TYPE_STATUS:
                raise ValueError('unexpected frame type %d on status port' % ftype)
            st = P.unpack_status_any(payload)      # 按长度分派 14/19（A8）
        except ValueError:
            self.bad += 1
            self._bad_times.append(now)
            return None
        # ... 原有 R5 序号新鲜度 / E1① 重同步逻辑不变 ...
        self._rej_run, self._rej_last = 0, None
        self._last_seq = seq
        self.good += 1
        self.last_good_time = now
        st['seq'] = seq
        self.last = st
        la = st.get('loop_alive')
        if la is None:
            self._loop_hist.clear()      # v1 固件：没有这个字段，不猜
        else:
            self._loop_hist.append(la)
        return dict(self.last)

    @property
    def status_version(self):
        return None if self.last is None else self.last.get('v')

    def loop_stalled(self, frames=STALL_FRAMES):
        """True = 执行面停摆（Fw-21 的探测手段）。v1 固件恒 False，绝不谎报。"""
        if len(self._loop_hist) < frames:
            return False
        vals = list(self._loop_hist)[-frames:]
        return len(set(vals)) == 1

    def reject_text(self):
        if not self.last or self.last.get('reject') is None:
            return ''
        return P.REJECT_TEXT.get(self.last['reject'], '未知拒绝码 %d' % self.last['reject'])
```

⚠️ `loop_stalled` 的 u8 回绕不会误报：回绕时 5 个值互不相同，`len(set(...)) == 1` 为假。

- [ ] **Step 4: 跑测试确认通过**

Run: `python -B -m pytest tests/test_status_rx.py -q -p no:cacheprovider`
Expected: PASS

- [ ] **Step 5: 全量回归 + 提交**

Run: `python -B -m pytest tests/ -q -p no:cacheprovider` → Expected: **186 passed**

```bash
git add pc/status_rx.py tests/test_status_rx.py
git commit -F- --cleanup=verbatim <<'EOF'
STATUS 接收按长度分派 14/19 字节，并加"执行面停摆"与拒绝原因人话

E3 批 1b 第 4 步（spec §3.2/§3.5）。handle() 改用 unpack_status_any，
v1 帧（E3 之前的固件）照旧能解、E3 五个键为 None，不崩也不把 limits 当 profile。

loop_stalled()：连续 5 帧读到同一个 loop_alive 即判执行面停摆 —— 这是 Fw-21
（权限在中断里、四轮在主循环里）唯一的探测手段，也是固件 reject=0x05 的 PC 侧对应物。
主循环约 80 ms 一圈、STATUS 20 Hz，250 ms 内应有约 3 次自增，所以 5 帧不变是真停摆；
u8 回绕时 5 个值互不相同，不会误报。**v1 固件恒返回 False，绝不谎报停摆。**

reject_text() 把原因码翻成人话（spec §5.4 要求 HUD 不显示十六进制）。

pytest 180 -> 186 passed。
EOF
```

---

### Task 5: `config/vehicle_profile.yaml` + `pc/vehicle_profile.py`

**Files:**
- Create: `config/vehicle_profile.yaml`
- Create: `pc/vehicle_profile.py`
- Test: `tests/test_vehicle_profile.py`（新建）

**Interfaces:**
- Consumes: `pc.wire.PERMIT_BY_NAME`、`P.PROFILE_*`。
- Produces:
  - `load(path=None) -> dict`（键 `profile_id: int`、`permit: int`、`path: str`）
  - `DEFAULT_PATH = 'config/vehicle_profile.yaml'`（相对仓库根）
  - `load()` 在文件缺失/键缺失/取值非法时 **raise `ValueError`**，不静默回默认值

- [ ] **Step 1: 写失败测试**

创建 `tests/test_vehicle_profile.py`：

```python
# -*- coding: utf-8 -*-
import os
import pytest
from pc import vehicle_profile as VP
from pc import wire
from common import protocol as P


def _write(tmp_path, text):
    p = tmp_path / 'vehicle_profile.yaml'
    p.write_text(text, encoding='utf-8')
    return str(p)


def test_load_repo_default():
    cfg = VP.load()
    assert cfg['profile_id'] in (P.PROFILE_PREV, P.PROFILE_REAL)
    assert cfg['permit'] in (wire.GATE_N, wire.GATE_F)


def test_load_parses_both_fields(tmp_path):
    p = _write(tmp_path, 'profile_id: 2\npermit: gate_f\n')
    cfg = VP.load(p)
    assert cfg['profile_id'] == P.PROFILE_REAL
    assert cfg['permit'] == wire.GATE_F


def test_missing_file_raises(tmp_path):
    with pytest.raises(ValueError):
        VP.load(str(tmp_path / 'nope.yaml'))


def test_unknown_permit_name_raises(tmp_path):
    with pytest.raises(ValueError):
        VP.load(_write(tmp_path, 'profile_id: 1\npermit: gate_x\n'))


def test_bad_profile_id_raises(tmp_path):
    for bad in ('profile_id: 0\npermit: gate_n\n',
                'profile_id: 3\npermit: gate_n\n',
                'permit: gate_n\n'):
        with pytest.raises(ValueError):
            VP.load(_write(tmp_path, bad))
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -B -m pytest tests/test_vehicle_profile.py -q -p no:cacheprovider`
Expected: FAIL，`ModuleNotFoundError: No module named 'pc.vehicle_profile'`

- [ ] **Step 3: 写实现**

创建 `config/vehicle_profile.yaml`：

```yaml
# E3 车辆档案（spec §6）。上电握手用：PC 发 MODE(MODE_REQ_PROFILE, profile_id)，
# 固件拿它跟自己烧进去的 PROFILE_ID 比；不一致 -> reject=REJECT_PROFILE 且拒绝进无人。
#
# profile_id: 1 = PREV 上代车（3.25 m，装控制栈试验用）
#             2 = REAL 样机（2.15 m，在地里）
# permit:     gate_n = 只许沿行空跑（刀强制提、横移禁）  <- 秋季门 N 用这个
#             gate_f = 允许落刀作业与横移（门 F，需 B5 全项 + 刀控 + 滑台接线）
#
# ⚠️ 运行中不热切（v1.0 §4.3）：档案装的是换算量，行驶中切换会让控制量跳变。
#    换车 = 重新上电 + 改这个文件 + 烧对应固件。
profile_id: 1
permit: gate_n
```

创建 `pc/vehicle_profile.py`：

```python
# -*- coding: utf-8 -*-
"""车辆档案加载（E3 spec §6）。

刻意不做"读不到就用默认值"：档案装的是换算量与安全许可位，
静默回默认等于让车带着错参数进无人。**读不到就报错停下。**
只用手写解析，不引 PyYAML 依赖（这个文件只有两个平铺的键）。
"""
import os

from common import protocol as P
from pc import wire

DEFAULT_PATH = os.path.join('config', 'vehicle_profile.yaml')
_VALID_PROFILE = (P.PROFILE_PREV, P.PROFILE_REAL)


def load(path=None):
    path = path or DEFAULT_PATH
    if not os.path.isabs(path):
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), path)
    if not os.path.exists(path):
        raise ValueError('车辆档案不存在：%s（spec §6：不许回默认值）' % path)

    kv = {}
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.split('#', 1)[0].strip()
            if not line or ':' not in line:
                continue
            k, v = line.split(':', 1)
            kv[k.strip()] = v.strip()

    try:
        profile_id = int(kv['profile_id'])
    except (KeyError, ValueError):
        raise ValueError('车辆档案缺 profile_id 或不是整数：%r' % kv.get('profile_id'))
    if profile_id not in _VALID_PROFILE:
        raise ValueError('profile_id 必须是 %s 之一，收到 %d' % (_VALID_PROFILE, profile_id))

    permit_name = kv.get('permit')
    if permit_name not in wire.PERMIT_BY_NAME:
        raise ValueError('permit 必须是 %s 之一，收到 %r'
                         % (sorted(wire.PERMIT_BY_NAME), permit_name))

    return {'profile_id': profile_id,
            'permit': wire.PERMIT_BY_NAME[permit_name],
            'path': path}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -B -m pytest tests/test_vehicle_profile.py -q -p no:cacheprovider`
Expected: PASS（5 条）

- [ ] **Step 5: 全量回归 + 提交**

Run: `python -B -m pytest tests/ -q -p no:cacheprovider` → Expected: **191 passed**

```bash
git add config/vehicle_profile.yaml pc/vehicle_profile.py tests/test_vehicle_profile.py
git commit -F- --cleanup=verbatim <<'EOF'
新增车辆档案 config/vehicle_profile.yaml 与加载器：读不到就报错，不回默认值

E3 批 1b 第 5 步（spec §6）。两个键：profile_id（1=上代车 3.25m / 2=样机 2.15m）
与 permit（gate_n / gate_f）。上电握手时 PC 用 MODE(0x20, profile_id) 报给固件，
固件跟自己烧进去的常量比，不一致就 reject=REJECT_PROFILE 并拒绝进无人。

刻意不做"读不到用默认"：档案装的是换算量与安全许可位，静默回默认等于让车带着
错参数进无人。也不引 PyYAML —— 这个文件只有两个平铺键，手写解析 20 行。

pytest 186 -> 191 passed。
EOF
```

---

### Task 6: `pc/main.py` 接线——按键发 MODE、发帧走 wire、CSV/HUD 带 E3 字段

**Files:**
- Modify: `pc/main.py`（按键处理、`send()` 调用点 `:243-261`、CSV 头 `:196-199` 与行 `:315-330`、HUD `:280-297`）
- Test: `tests/test_control.py`（追加 1 条纯函数级断言，不启 GUI）

**Interfaces:**
- Consumes: `wire.frames_for_state`、`wire.RUN_LOG_COLUMNS`、`wire.run_log_row`、`vehicle_profile.load`、`rx.reject_text()`、`rx.loop_stalled()`、`P.pack_mode`。
- Produces: `main()` 里 `permit`/`profile_id` 来自 `vehicle_profile.load()`；按键语义：`A` = 申请无人（发 `MODE(0x01)`，**不再靠 NAV 隐含进 AUTO**）、`M` = 交回（`MODE(0x00)`）、`R` = 解除急停（`MODE(0x10)`）、`C` = L2.5 人工确认（`sm.confirm_continue()`）。

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_control.py`（钉住"申请无人走 MODE 帧"这条新语义，避免以后有人把它改回 NAV）：

```python
def test_auto_request_goes_out_as_a_mode_frame_not_nav():
    """E3 §3.1：NAV 只给速度，权限只能用 MODE 帧申请。"""
    frames = wire.frames_for_state('MANUAL', True, 0.0, 0.0, 0.0)
    assert all(t != P.TYPE_NAV for t, _ in frames)      # MANUAL 不会顺带发 NAV
    req = P.pack_frame(P.TYPE_MODE, P.pack_mode(P.MODE_REQ_AUTO, 1), seq=1)
    t, _seq, payload = P.unpack_frame(req)
    assert t == P.TYPE_MODE
    assert P.unpack_mode(payload) == (P.MODE_REQ_AUTO, 1)
```

- [ ] **Step 2: 跑测试确认失败/通过基线**

Run: `python -B -m pytest tests/test_control.py -q -p no:cacheprovider`
Expected: 这条会 PASS（它只依赖 Task 1/2 的产物）——它的作用是**回归钉**，防止后面把语义改回去。真正的失败信号在 Step 3 之后的人工冒烟（Step 4）。

- [ ] **Step 3: 改 `pc/main.py`**

三处替换，逐处照抄：

**(a) 启动时加载档案**（在 `rx = StatusReceiver()` 附近，`:155` 一带）：

```python
        from pc import vehicle_profile as VP
        from pc import wire
        cfg_profile = VP.load()          # 读不到就抛，不许带错参数进无人
        permit = cfg_profile['permit']
        profile_id = cfg_profile['profile_id']
        sm = StateMachine(permit=permit)
```

**(b) 发帧改成走 wire**（把 `:243-261` 那个三分支整块换掉）：

```python
            # ---- control by state（E3 §5.1：状态优先，持权期间永不发心跳）----
            vl = vr = 0.0
            tool_mm = 0.0
            if sm.state == 'AUTO' and usable:
                tool_px = res.get('tool_offset_px')
                if tool_px is None:
                    tool_px = 0.0
                e_dot = rate.update(lat_m, dt)
                lat_c = comp.compensate(lat_m, e_dot)
                vl, vr = drive.wheel_speeds(lat_c, err_rate=e_dot)
                tool_mm = pid.update(tool_px * px_to_meters(1.0) * 1000.0, dt)
            elif sm.holds_authority:
                pid.reset()

            if sm.state == 'ESTOP' and prev_state != 'ESTOP':
                send(P.TYPE_ESTOP, b'')          # 只在跳变那一拍发一次
            for ftype, payload in wire.frames_for_state(
                    sm.state, usable, vl, vr, tool_mm, permit):
                send(ftype, payload)
```

（原 `if sm.state == 'ESTOP': send(P.TYPE_ESTOP, b'')` 那段跳变判断保留在状态事件区，不要重复发。）

**(c) 按键**（在原有按键分支里替换语义）：

```python
                if key == ord('a'):
                    # E3：申请无人 = 显式 MODE 帧，不再靠 NAV 隐含进 AUTO
                    send(P.TYPE_MODE, P.pack_mode(P.MODE_REQ_AUTO, profile_id))
                    sm.go_auto(confidence_ok=usable)
                elif key == ord('m'):
                    send(P.TYPE_MODE, P.pack_mode(P.MODE_REQ_MANUAL, profile_id))
                    sm.go_manual()
                elif key == ord('r'):
                    # A3 单确认解除急停；清锁≠授权，固件会回到 MANUAL
                    send(P.TYPE_MODE, P.pack_mode(P.MODE_REQ_CLEAR_ESTOP, profile_id))
                    sm.clear_estop()
                elif key == ord('c'):
                    sm.confirm_continue()        # L2.5 人工确认
```

**(d) CSV 头与行**：`:196-199` 的 `wr.writerow([...])` 换成 `wr.writerow(wire.RUN_LOG_COLUMNS)`；`:315-330` 的 `wr.writerow([...])` 换成

```python
                wr.writerow(wire.run_log_row(
                    t_rel, fid, sm.state, res, lat_m, lat_comp_m, vl, vr,
                    tool_mm, latency, rx.last if rx else None,
                    (_st, _seq, _age), permit,
                    rx_good=rx.good if rx else '', rx_bad=rx.bad if rx else '',
                    recv_timeouts=src.feed.timeouts if src.feed else '',
                    link_drops=src.feed.drops if src.feed else ''))
```

（`lat_comp_m`、`recv_timeouts`、`link_drops` 沿用原有变量名；若原变量名不同，以原文件为准，**不要新造名字**。）

**(e) HUD**（`:280-297` 那一段追加，不替换原有内容）：

```python
                        if rx.last and rx.last.get('v') == 2:
                            hud2 += '  prof:%d auth:%d loop:%d build:%02X' % (
                                rx.last['profile'], rx.last['authority'],
                                rx.last['loop_alive'], rx.last['build_id'])
                            if rx.loop_stalled():
                                hud2 += '  !!LOOP-STALLED!!'
                        _rj = rx.reject_text() if rx else ''
                        if _rj:
                            hud2 += '  reject:%s' % _rj
```

- [ ] **Step 4: 冒烟验证（回放模式，不接硬件）**

Run: `python -B -m pc.main --source data/videos --out results/_smoke_wire --no-gui`（按该文件实际参数名调整；`--no-gui` 若不存在则用现有等价开关）
Expected:
- 正常跑完并打印 `done: N frames -> .../run_log.csv`；
- `results/_smoke_wire/run_log.csv` 第一行**包含** `profile,authority,reject,loop_alive,build_id,permit` 六列；
- 所有行的 `permit` 列都是 `1`（门 N）。

Run: `python -c "import csv;r=list(csv.reader(open(r'results/_smoke_wire/run_log.csv',encoding='utf-8')));print(len(r[0]),len(r[1]));assert len(r[0])==len(r[1])"`
Expected: 两个数字相等（列数与行长一致），打印 `24 24`

- [ ] **Step 5: 全量回归 + 提交**

Run: `python -B -m pytest tests/ -q -p no:cacheprovider` → Expected: **192 passed**
清理：`rm -rf results/_smoke_wire`（**不要提交** `results/` 下的冒烟产物）

```bash
git add pc/main.py tests/test_control.py
git commit -F- --cleanup=verbatim <<'EOF'
main.py 接线：申请无人改发 MODE 帧、发帧走 wire、CSV/HUD 带 E3 字段

E3 批 1b 第 6 步（spec §5.1/§5.4）。四处改动：
- 启动时 vehicle_profile.load() 拿 profile_id 与 permit，读不到直接抛（不带错参数进无人）；
- 原来 :243-261 那个三分支换成 wire.frames_for_state()，"AUTO 但这一帧不可用且未满 2 秒"
  不再掉进 else 发心跳（codex 新发现一）；
- 按键语义：A=MODE(0x01) 申请无人、M=MODE(0x00) 交回、R=MODE(0x10) 解除急停、
  C=L2.5 人工确认。**NAV 不再承担权限语义**；
- run_log.csv 加 profile/authority/reject/loop_alive/build_id/permit 六列，
  HUD 显示档案/权限来源/主循环计数/build 号，并在 loop_stalled() 时打
  !!LOOP-STALLED!!、有拒绝码时打人话文案。

冒烟：回放模式跑通，CSV 列数与行长一致（24 列）。
pytest 191 -> 192 passed。固件未动 —— 现在 PC 会对旧固件发 MODE 帧，
旧固件按未知类型丢弃（dispatch 里没有 case 5），不影响既有行为；
真正生效要等批 1a 烧录。
EOF
```

---

### Task 7: `tools/link_probe.py`——废掉"是否曾看到 AUTO"，按命令定义预期响应

**Files:**
- Modify: `tools/link_probe.py`（`:62` `MODE_NAME`、`:66` `EXPECTED`、`:81` `_read_status`、`:112` `_run_serial`）
- Test: `tests/test_link_probe.py`（追加）

**Interfaces:**
- Consumes: `P.TYPE_MODE`/`pack_mode`（Task 1）。
- Produces:
  - `MODE_NAME = {0: 'MANUAL', 1: 'AUTO', 2: 'ESTOP', 3: 'TELEOP'}`
  - `EXPECTED = {'nav': None, 'mode_auto': 1, 'mode_manual': 0, 'estop': 2, 'clear': 0, 'tool': None, 'beat': None}`（值 = 期望的 `mode`，`None` = 不以 mode 变化为判据）
  - `judge(kind, baseline_mode, seen_modes, reject_codes) -> (verdict: str, detail: str)`，verdict ∈ `{'PASS', 'FAIL', 'INCONCLUSIVE'}`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_link_probe.py`（该文件已有 `_FakeSer`，复用它）：

```python
from tools import link_probe as LP


def test_judge_uses_baseline_not_ever_seen():
    """评审反例一：发送前就已经是 AUTO，不能算这次发送的功劳。"""
    v, _ = LP.judge('mode_auto', baseline_mode=1, seen_modes=[1], reject_codes=[])
    assert v == 'INCONCLUSIVE'


def test_judge_pass_on_real_transition():
    v, _ = LP.judge('mode_auto', baseline_mode=0, seen_modes=[0, 1], reject_codes=[])
    assert v == 'PASS'


def test_judge_estop_transition_is_pass_not_wiring_error():
    """评审反例二：发 estop 看到 MANUAL->ESTOP 过去被报成"一直在 MANUAL，检查接线"。"""
    v, _ = LP.judge('estop', baseline_mode=0, seen_modes=[0, 2], reject_codes=[])
    assert v == 'PASS'


def test_judge_reject_code_is_reported_as_rejected_not_failed():
    """E3：申请被拒是**正常响应**，要说清是哪一条，不是"链路不通"。"""
    v, detail = LP.judge('mode_auto', baseline_mode=0, seen_modes=[0],
                         reject_codes=[3])
    assert v == 'FAIL'
    assert '现场拨档' in detail


def test_judge_inconclusive_when_no_frame_at_all():
    v, _ = LP.judge('mode_auto', baseline_mode=None, seen_modes=[], reject_codes=[])
    assert v == 'INCONCLUSIVE'


def test_judge_nav_no_longer_expects_mode_change():
    """A2 之后 NAV 不改 mode：nav 命令的判据是"收到 STATUS 且 mode 未变"。"""
    v, _ = LP.judge('nav', baseline_mode=0, seen_modes=[0], reject_codes=[])
    assert v == 'PASS'
    v2, _ = LP.judge('nav', baseline_mode=0, seen_modes=[0, 1], reject_codes=[])
    assert v2 == 'FAIL'
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -B -m pytest tests/test_link_probe.py -q -p no:cacheprovider`
Expected: FAIL，`AttributeError: module 'tools.link_probe' has no attribute 'judge'`

- [ ] **Step 3: 写实现**

在 `tools/link_probe.py` 加：

```python
MODE_NAME = {0: 'MANUAL', 1: 'AUTO', 2: 'ESTOP', 3: 'TELEOP'}

# 值 = 期望的 mode；None = 不以 mode 变化为判据（A2 之后 NAV 不改 mode）
EXPECTED = {'nav': None, 'mode_auto': 1, 'mode_manual': 0,
            'estop': 2, 'clear': 0, 'tool': None, 'beat': None}


def judge(kind, baseline_mode, seen_modes, reject_codes):
    """按命令定义预期响应，并区分"发送前基线"与"发送后变化"。

    评审指出的两个反例都必须判对：
      - 发 ESTOP 看到 MANUAL->ESTOP 是 PASS，不是"一直在 MANUAL，检查接线"；
      - 第一帧就已经是 AUTO 时，不能算这次发送的功劳 => INCONCLUSIVE。
    E3 之后新增：申请被拒（reject != 0）是**正常响应**，报出是哪一条原因。
    """
    from common import protocol as P

    if not seen_modes and baseline_mode is None:
        return 'INCONCLUSIVE', '一帧 STATUS 都没收到：查串口/桥接/接线，不是查权限'

    want = EXPECTED.get(kind, None)

    if reject_codes:
        code = reject_codes[-1]
        text = P.REJECT_TEXT.get(code, '未知拒绝码 %d' % code)
        if kind in ('mode_auto', 'mode_manual', 'clear') and want is not None \
                and want not in seen_modes:
            return 'FAIL', '请求被拒绝：%s（reject=0x%02X）——链路是通的，权限没给' % (text, code)

    if want is None:
        # nav / tool / beat：判据是"链路活着且没有意外越权"
        if kind == 'nav' and any(m != baseline_mode for m in seen_modes):
            return 'FAIL', ('NAV 之后 mode 变了（%s）——A2 之后 NAV 不许改权限，'
                            '说明板上还是旧固件或有别的东西在发帧'
                            % '->'.join(MODE_NAME.get(m, str(m)) for m in seen_modes))
        return 'PASS', '收到 STATUS，且没有意外的权限变化'

    if want in seen_modes and baseline_mode != want:
        return 'PASS', '基线 %s -> 观察到 %s' % (
            MODE_NAME.get(baseline_mode, str(baseline_mode)), MODE_NAME[want])
    if want in seen_modes and baseline_mode == want:
        return 'INCONCLUSIVE', ('发送前就已经是 %s，不能证明是这次发送引发的'
                                % MODE_NAME[want])
    return 'FAIL', '期望看到 %s，实际只看到 %s' % (
        MODE_NAME[want],
        '->'.join(MODE_NAME.get(m, str(m)) for m in seen_modes) or '（无帧）')
```

`_run_serial()` 里把"是否曾看到 AUTO"那个判定换成调用 `judge()`，并在读取 STATUS 时额外收集 `reject`（v2 帧才有；v1 帧收到就打印一行"板上是 E3 之前的固件，mode_auto/clear 这两条测不了"）。`build()` 里加 `mode_auto`/`mode_manual`/`clear` 三种命令，分别打包 `P.pack_mode(P.MODE_REQ_AUTO, profile)` 等（`profile` 从 `pc.vehicle_profile.load()` 取，取不到就用 `P.PROFILE_NONE` 并打印警告）。

- [ ] **Step 4: 跑测试确认通过**

Run: `python -B -m pytest tests/test_link_probe.py -q -p no:cacheprovider`
Expected: PASS

- [ ] **Step 5: 全量回归 + 提交**

Run: `python -B -m pytest tests/ -q -p no:cacheprovider` → Expected: **198 passed**

```bash
git add tools/link_probe.py tests/test_link_probe.py
git commit -F- --cleanup=verbatim <<'EOF'
link_probe 判据重写：按命令定义预期响应，废掉"是否曾看到 AUTO"

E3 批 1b 第 7 步（spec §9）。旧判据把四种不同结果混成一句话，评审给了两个反例：
发 ESTOP 看到 MANUAL->ESTOP 被报成"一直在 MANUAL，检查接线"；第一帧本来就是
AUTO 被报成"收得进，问题在 X5 一侧"。

改成 judge(kind, baseline_mode, seen_modes, reject_codes) -> PASS/FAIL/INCONCLUSIVE：
区分发送前基线与发送后变化；一帧都没收到才说"查接线"；申请被拒（reject!=0）
是**正常响应**，报出中文原因而不是"链路不通"。

同时落实 A2 的连带后果：NAV 不再改 mode，所以 nav 命令的判据反过来变成
"收到 STATUS 且 mode 没变"——mode 变了就说明板上还是旧固件。
新增 mode_auto / mode_manual / clear 三个命令。

pytest 192 -> 198 passed。
EOF
```

---

### Task 8: `tools/bench_status.py`——能发、能记发出的帧、带 E3 列

**Files:**
- Modify: `tools/bench_status.py`（`:165` 列头、`:173` `_row`、`:294` `main`）
- Test: `tests/test_bench_status.py`（追加）

**Interfaces:**
- Produces:
  - `build_command(line: str, profile_id: int, seq: int) -> tuple[str, bytes] | None`（解析 stdin 的 `!nav vL vR` / `!tool mm lift` / `!beat` / `!auto` / `!manual` / `!clear`，返回 `(kind, frame_bytes)`；无法解析返回 `None`）
  - `BenchLog` 列头追加 `profile, authority, reject, loop_alive, build_id, profile_ack`，`kind` 新增 `tx_*`（发出的帧也落同一张 CSV）
  - `main()` 新增 `--to HOST:PORT`（**opt-in，不填即彻底禁用发送**）

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_bench_status.py`：

```python
def test_build_command_parses_each_kind():
    from tools import bench_status as BS
    from common import protocol as P
    kind, frame = BS.build_command('!nav 0.14 0.12', 1, 5)
    assert kind == 'tx_nav'
    t, seq, payload = P.unpack_frame(frame)
    assert (t, seq) == (P.TYPE_NAV, 5)
    assert P.unpack_nav(payload)[:2] == (0.14, 0.12)

    kind, frame = BS.build_command('!tool -3.5 7', 1, 6)
    assert kind == 'tx_tool'
    assert P.unpack_tool(P.unpack_frame(frame)[2]) == (-3.5, 7)

    for text, want_type in (('!beat', P.TYPE_HEARTBEAT),
                            ('!auto', P.TYPE_MODE),
                            ('!manual', P.TYPE_MODE),
                            ('!clear', P.TYPE_MODE)):
        kind, frame = BS.build_command(text, 1, 7)
        assert P.unpack_frame(frame)[0] == want_type
        assert kind.startswith('tx_')


def test_build_command_rejects_garbage():
    from tools import bench_status as BS
    for bad in ('', '!nav', '!nav x y', '!nope', 'nav 0.1 0.1'):
        assert BS.build_command(bad, 1, 1) is None


def test_auto_command_carries_profile_id():
    from tools import bench_status as BS
    from common import protocol as P
    _kind, frame = BS.build_command('!auto', 2, 9)
    assert P.unpack_mode(P.unpack_frame(frame)[2]) == (P.MODE_REQ_AUTO, 2)


def test_benchlog_header_has_e3_columns(tmp_path):
    from tools import bench_status as BS
    log = BS.BenchLog(str(tmp_path / 'b.csv'))
    log.tx('tx_nav', None)
    log.f.close()
    header = open(str(tmp_path / 'b.csv'), encoding='utf-8').readline().strip().split(',')
    for col in ('profile', 'authority', 'reject', 'loop_alive', 'build_id', 'kind'):
        assert col in header
    rows = open(str(tmp_path / 'b.csv'), encoding='utf-8').read().strip().split('\n')
    assert len(rows[1].split(',')) == len(header)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -B -m pytest tests/test_bench_status.py -q -p no:cacheprovider`
Expected: FAIL，`AttributeError: ... has no attribute 'build_command'` / `'BenchLog' object has no attribute 'tx'`

- [ ] **Step 3: 写实现**

在 `tools/bench_status.py` 加：

```python
def build_command(line, profile_id, seq):
    """把 stdin 的一行翻成一个待发帧。解析不了就返回 None（不猜、不默认）。"""
    from common import protocol as P
    parts = line.strip().split()
    if not parts or not parts[0].startswith('!'):
        return None
    cmd, args = parts[0][1:], parts[1:]
    try:
        if cmd == 'nav' and len(args) == 2:
            return 'tx_nav', P.pack_frame(P.TYPE_NAV, P.pack_nav(float(args[0]), float(args[1])), seq)
        if cmd == 'tool' and len(args) == 2:
            return 'tx_tool', P.pack_frame(P.TYPE_TOOL, P.pack_tool(float(args[0]), int(args[1], 0)), seq)
        if cmd == 'beat' and not args:
            return 'tx_beat', P.pack_frame(P.TYPE_HEARTBEAT, b'', seq)
        if cmd in ('auto', 'manual', 'clear') and not args:
            req = {'auto': P.MODE_REQ_AUTO, 'manual': P.MODE_REQ_MANUAL,
                   'clear': P.MODE_REQ_CLEAR_ESTOP}[cmd]
            return ('tx_' + cmd,
                    P.pack_frame(P.TYPE_MODE, P.pack_mode(req, profile_id), seq))
    except (ValueError, TypeError):
        return None
    return None
```

`BenchLog`：列头 `:165` 改成

```python
        self.w.writerow(['t_rel', 'iso', 'kind', 'seq', 'mode', 'speed',
                         'current_a', 'batt_v', 'limits', 'note', 'peer',
                         'profile', 'authority', 'reject', 'loop_alive',
                         'build_id'])
```

`_row()` 末尾追加五个字段（`st.get('profile', '')` 这类写法，v1 帧自然为空）；新增方法：

```python
    def tx(self, kind, note=''):
        """发出的帧也落同一张 CSV —— 否则"边发边记"的时间轴对不上。"""
        return self._row(kind, note=note)
```

`main()`：加 `--to`（`HOST:PORT`，默认 `None` = 彻底禁用发送），发送用独立的 `socket.socket(AF_INET, SOCK_DGRAM)`；stdin 用现有的 `_note_listener` 线程读，遇到 `!` 开头的行就 `build_command()` → `sendto` → `log.tx(kind)`，其它行仍当场景标记。发送序号用一个独立自增计数器，**不要和 STATUS 的接收序号混用**。

- [ ] **Step 4: 跑测试确认通过**

Run: `python -B -m pytest tests/test_bench_status.py -q -p no:cacheprovider`
Expected: PASS

- [ ] **Step 5: 全量回归 + 提交**

Run: `python -B -m pytest tests/ -q -p no:cacheprovider` → Expected: **202 passed**

```bash
git add tools/bench_status.py tests/test_bench_status.py
git commit -F- --cleanup=verbatim <<'EOF'
台架记录器加发送能力（opt-in）：边发边记，发出的帧落同一张 CSV

E3 批 1b 第 8 步（spec §9）。过去记录器只会收不会发，"PC 持续发 NAV/TOOL 的同时
看 STATUS"这类场景（验收表 ②③⑧）做不了 —— 只能关掉记录器改用 pc/main.py，
而两者抢 9100，于是模式跳变/静默 gap/场景标记那条时间轴就丢了。

- --to HOST:PORT，**不填即彻底禁用发送**（opt-in，免得误发动车）；
- stdin 支持 !nav vL vR / !tool mm lift / !beat / !auto / !manual / !clear，
  解析不了返回 None（不猜、不默认）；发送序号独立自增，不与接收序号混用；
- 发出的每一帧以 tx_* 落进同一张 CSV；列头加 profile/authority/reject/
  loop_alive/build_id 五列（v1 固件时自然为空）。

pytest 198 -> 202 passed。
EOF
```

---

### Task 9: `tools/latency_probe.py`——D1/D2 延迟自测

**Files:**
- Create: `tools/latency_probe.py`
- Test: `tests/test_latency_probe.py`（新建）

**Interfaces:**
- Produces:
  - `measure_d1(send_fn, recv_iter, repeats=30, timeout_s=2.0) -> dict`（键 `samples_ms`、`p50_ms`、`p95_ms`、`n`、`timeouts`）
  - `measure_d2(send_fn, recv_iter, step_v=0.14, threshold=0.05, timeout_s=5.0) -> dict`（同上 + `threshold_mps`）
  - `percentile(sorted_values, p) -> float`
  - `report(d1, d2) -> str`（**分开报**，并把 `SLEW_ACC` 掩盖效应写进文案）

- [ ] **Step 1: 写失败测试**

创建 `tests/test_latency_probe.py`：

```python
# -*- coding: utf-8 -*-
from tools import latency_probe as LP


def test_percentile():
    assert LP.percentile([1, 2, 3, 4], 50) == 2.5
    assert LP.percentile([1, 2, 3, 4], 95) == 4


def test_d1_measures_request_to_mode_echo():
    """D1 = 发 MODE(0x01) 到看见 mode/authority 变化。用假收发，不碰硬件。"""
    calls = []

    def send_fn(frame):
        calls.append(frame)

    # 第 3 帧才带来 mode 变化；时间戳由假 recv 提供
    events = [(0.010, {'mode': 0, 'authority': 0, 'speed_mps': 0.0}),
              (0.060, {'mode': 0, 'authority': 0, 'speed_mps': 0.0}),
              (0.110, {'mode': 1, 'authority': 1, 'speed_mps': 0.0})]

    def recv_iter(deadline):
        for t, st in events:
            if t > deadline:
                break
            yield t, st

    out = LP.measure_d1(send_fn, recv_iter, repeats=1, timeout_s=1.0)
    assert out['n'] == 1 and out['timeouts'] == 0
    assert abs(out['samples_ms'][0] - 110.0) < 1e-6


def test_d1_counts_timeout_when_no_change():
    out = LP.measure_d1(lambda f: None, lambda deadline: iter([]),
                        repeats=2, timeout_s=0.01)
    assert out['n'] == 0 and out['timeouts'] == 2
    assert out['p50_ms'] is None


def test_d2_waits_for_speed_to_cross_threshold():
    events = [(0.010, {'speed_mps': 0.0}),
              (0.400, {'speed_mps': 0.02}),      # 低于阈值，不算
              (0.900, {'speed_mps': 0.06})]      # 越过 0.05

    def recv_iter(deadline):
        for t, st in events:
            if t > deadline:
                break
            yield t, st

    out = LP.measure_d2(lambda f: None, recv_iter, step_v=0.14,
                        threshold=0.05, timeout_s=2.0, repeats=1)
    assert out['n'] == 1
    assert abs(out['samples_ms'][0] - 900.0) < 1e-6


def test_report_keeps_d1_and_d2_separate():
    """斜坡限幅会把链路延迟掩盖掉，两个数不许合成一个。"""
    d1 = {'samples_ms': [100.0], 'p50_ms': 100.0, 'p95_ms': 100.0,
          'n': 1, 'timeouts': 0}
    d2 = {'samples_ms': [900.0], 'p50_ms': 900.0, 'p95_ms': 900.0,
          'n': 1, 'timeouts': 0, 'threshold_mps': 0.05}
    text = LP.report(d1, d2)
    assert 'D1' in text and 'D2' in text
    assert '100.0' in text and '900.0' in text
    assert '0.2' in text            # SLEW_ACC 的说明必须在场
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -B -m pytest tests/test_latency_probe.py -q -p no:cacheprovider`
Expected: FAIL，`ModuleNotFoundError: No module named 'tools.latency_probe'`

- [ ] **Step 3: 写实现**

创建 `tools/latency_probe.py`：

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E3 spec §7.2：延迟自测两条，都不改固件。

D1 控制链路往返 = 发 MODE(0x01) 到 STATUS 里 mode/authority 变化。
   ⚠️ **不能用 NAV 测** —— A2 之后 NAV 不改 mode，发它看不到任何回显变化。
   对应 B8 的一票否决判据（控制帧往返 p95）。分辨率受 STATUS 20 Hz 限制（±50 ms）。
D2 指令到轮子真的转 = 发阶跃 NAV 到 STATUS 的 speed 首次越过阈值。
   含 D1 的全部 + 斜坡限幅 + PWM + 电机 + 传动 + 轮胎。
   ⚠️ SLEW_ACC = 0.2 m/s^2（retrofit.c:140）⇒ 0 -> 0.14 m/s 需要 0.7 秒，
      它会把百毫秒级的链路延迟完全掩盖，所以 D1 与 D2 **必须分开报**。
   ⚠️ TIM3 是 16 位计时，脉冲间隔 > 65.536 ms 会取模（0.005 m/s 被算成约
      0.01451 m/s）⇒ 低速段 speed 不可信，阈值必须 >= 0.05 m/s。

用法（台架，驱动轮架空）：
    python tools/latency_probe.py --to 192.168.127.10:9000 --listen 9100 --repeats 30
"""
import argparse
import socket
import time

from common import protocol as P

SLEW_ACC = 0.2          # m/s^2，与 retrofit.c:140 一致；只用于报告文案
MIN_THRESHOLD = 0.05    # m/s，低于此值 TIM3 混叠区不可信


def percentile(sorted_values, p):
    if not sorted_values:
        return None
    vals = sorted(sorted_values)
    k = (len(vals) - 1) * (p / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(vals) - 1)
    return vals[lo] + (vals[hi] - vals[lo]) * (k - lo)


def _summary(samples, timeouts):
    return {'samples_ms': list(samples), 'n': len(samples),
            'timeouts': timeouts,
            'p50_ms': percentile(samples, 50),
            'p95_ms': percentile(samples, 95)}


def measure_d1(send_fn, recv_iter, repeats=30, timeout_s=2.0,
               profile_id=0, clock=time.monotonic):
    samples, timeouts = [], 0
    for i in range(repeats):
        req = P.MODE_REQ_AUTO if i % 2 == 0 else P.MODE_REQ_MANUAL
        want = 1 if req == P.MODE_REQ_AUTO else 0
        send_fn(P.pack_frame(P.TYPE_MODE, P.pack_mode(req, profile_id), i))
        t0 = clock()
        got = False
        for t, st in recv_iter(t0 + timeout_s):
            if st.get('mode') == want:
                samples.append((t - t0) * 1000.0)
                got = True
                break
        if not got:
            timeouts += 1
    return _summary(samples, timeouts)


def measure_d2(send_fn, recv_iter, step_v=0.14, threshold=MIN_THRESHOLD,
               timeout_s=5.0, repeats=10, clock=time.monotonic):
    if threshold < MIN_THRESHOLD:
        raise ValueError('阈值 %.3f 低于 %.3f：TIM3 低速段混叠，测出来不可信'
                         % (threshold, MIN_THRESHOLD))
    samples, timeouts = [], 0
    for i in range(repeats):
        send_fn(P.pack_frame(P.TYPE_NAV, P.pack_nav(0.0, 0.0), 1000 + i * 2))
        send_fn(P.pack_frame(P.TYPE_NAV, P.pack_nav(step_v, step_v), 1001 + i * 2))
        t0 = clock()
        got = False
        for t, st in recv_iter(t0 + timeout_s):
            if (st.get('speed_mps') or 0.0) >= threshold:
                samples.append((t - t0) * 1000.0)
                got = True
                break
        if not got:
            timeouts += 1
    out = _summary(samples, timeouts)
    out['threshold_mps'] = threshold
    out['step_mps'] = step_v
    return out


def report(d1, d2):
    def fmt(d):
        if not d['n']:
            return 'n=0，超时 %d 次 —— 没有可用样本' % d['timeouts']
        return ('n=%d p50=%.1f ms p95=%.1f ms 超时 %d'
                % (d['n'], d['p50_ms'], d['p95_ms'], d['timeouts']))
    lines = [
        'D1 控制链路往返（发 MODE 到看见 mode 变化）：%s' % fmt(d1),
        '   分辨率 ±50 ms（STATUS 20 Hz）；这条对应 B8 的判据（控制帧往返 p95）。',
        'D2 指令到轮子转（阶跃到 speed>=%.2f m/s）：%s'
        % (d2.get('threshold_mps', MIN_THRESHOLD), fmt(d2)),
        '   含斜坡限幅：SLEW_ACC=%.1f m/s^2 ⇒ 0→0.14 m/s 需要约 0.7 s，' % SLEW_ACC,
        '   所以 D2 不是链路延迟。论文口径：链路延迟 = D1；机械响应 ≈ D2 − D1。',
        '   低速段（<%.2f m/s）speed 不可信：TIM3 16 位计时超过 65.536 ms 会取模。'
        % MIN_THRESHOLD,
    ]
    return '\n'.join(lines)
```

`main()` 用 `argparse` 收 `--to/--listen/--repeats/--profile`，发送用 UDP socket，接收侧起一个后台线程把 STATUS 解成 `(t, dict)` 塞进 `queue.Queue`，`recv_iter(deadline)` 从队列里取到 deadline 为止（**收帧必须走 `P.unpack_status_any`，坏帧计数不静默**）。

- [ ] **Step 4: 跑测试确认通过**

Run: `python -B -m pytest tests/test_latency_probe.py -q -p no:cacheprovider`
Expected: PASS（5 条）

- [ ] **Step 5: 全量回归 + 提交**

Run: `python -B -m pytest tests/ -q -p no:cacheprovider` → Expected: **207 passed**

```bash
git add tools/latency_probe.py tests/test_latency_probe.py
git commit -F- --cleanup=verbatim <<'EOF'
新增 tools/latency_probe.py：D1/D2 延迟自测，两个数分开报

E3 批 1b 第 9 步（spec §7.2）。作者要求"换个简单方法、能不能自己测"——两条都不改固件：
D1 发 MODE(0x01)/MODE(0x00) 交替，量到 STATUS 里 mode 变化为止（**不能用 NAV 测**，
A2 之后 NAV 不改 mode）；D2 发阶跃 NAV，量到 STATUS 的 speed 首次越过 0.05 m/s。

两个数必须分开报：SLEW_ACC=0.2 m/s^2 让 0→0.14 m/s 需要 0.7 秒，会把百毫秒级的
链路延迟完全掩盖。论文口径写成"链路延迟 = D1；机械响应 ≈ D2 − D1"。
阈值下限 0.05 m/s 是硬的（低于它 TIM3 16 位计时进入混叠区，0.005 m/s 会被算成
约 0.01451 m/s），measure_d2 直接拒绝更低的阈值。

手机 60fps 同框拍那条土办法只留作一次性交叉核对，不进这个脚本。
pytest 202 -> 207 passed。
EOF
```

---

### Task 10: 文档同步与批次收尾

**Files:**
- Modify: `README.md`（新增 `config/vehicle_profile.yaml`、`pc/wire.py`、`pc/vehicle_profile.py`、`tools/latency_probe.py`；`bench_status` 的 `--to` 与 stdin 命令）
- Modify: `docs/缺口清单.md`（③-B 的 E3 行改为"批 1b 已编码，等批 1a"；②的 B2 行加一句"记录器已能发帧"）
- Modify: `docs/参数差异台账.md`（§4 修改记录追加一行；Pc-8 状态列从"🔴 门 N 准入阻断项"改为"🟡 PC 侧已修，等批 1a 固件侧"）
- Modify: `AGENTS.md`（测试基线 159 → 207，并写清增长来源）

**Interfaces:** 无（纯文档）。

- [ ] **Step 1: 改 README**

在"运行环境/目录说明"处补 `config/vehicle_profile.yaml` 的用途与两个键；在工具表里加 `tools/latency_probe.py` 一行；把 `tools/bench_status.py` 那行补上 `--to` 与 `!nav/!tool/!beat/!auto/!manual/!clear`。

- [ ] **Step 2: 改台账与缺口清单**

台账 §4 追加（倒序，最新在上）：

```
| 2026-10-08 | E3 批 1b（PC+工具） | Pc-8 从"AUTO 每周期命令落刀"改为"PC 侧已修：门 N 下 wire 只发 lift=0x07、tool_mm=0"；新增 `pc/wire.py` 承载线上语义 | `pc/wire.py`、`pc/state_machine.py`、`pc/main.py`、`pc/status_rx.py`、`common/protocol.py`、`tools/{link_probe,bench_status,latency_probe}.py` | `pytest -q` = 207 passed；回放模式冒烟：run_log.csv 24 列、列数与行长一致 | 用户+Qoder |
```

Pc-8 状态列**就地改写**（不删原文，按"就地撤回"的规矩加一段）：在原有 🔴 文案后面追加 `🟡 **10-08 PC 侧已修**（批 1b）：门 N 许可位下 wire 只发 lift=0x07、tool_mm=0，且有单测钉住；**固件侧那半（permit==GATE_N 强制提刀并忽略矛盾的 TOOL 位）要等批 1a**，两侧都到位才算关闭本行。`

缺口清单 ③-B 第一条追加：`🟡 **10-08 批 1b 已编码**（PC+工具，pytest 207 passed）；**批 1a（协议+固件）未开工**，顺序不可换。`

- [ ] **Step 3: 改 AGENTS 基线**

把 `**当前测试基线：09-28 pytest -q = 159 collected / 159 passed**` 那句里的数字与链条更新为 `10-08 pytest -q = 207 passed`，并在链条里加一段 `→ 10-08 E3 批 1b（协议 MODE/STATUS v2 +7、wire +10、状态机 +4、status_rx +6、档案 +5、link_probe +6、bench_status +4、latency_probe +5）= 207`。**保留原有链条文字，只在末尾续写**（这块板的历史不删）。

- [ ] **Step 4: 跑检查器与全量测试**

Run: `python tools/check_doc_invariants.py` → Expected: 退出码 **0**，`①–⑧` 命中 **6** 次（基线），其余区分类符号 0
Run: `python -B -m pytest tests/ -q -p no:cacheprovider` → Expected: **207 passed**

- [ ] **Step 5: 提交**

```bash
git add README.md docs/缺口清单.md docs/参数差异台账.md AGENTS.md
git commit -F- --cleanup=verbatim <<'EOF'
批 1b 收尾：README/台账/缺口清单/AGENTS 同步，Pc-8 的 PC 侧那半就地改判

- README 补 config/vehicle_profile.yaml、pc/wire.py、pc/vehicle_profile.py、
  tools/latency_probe.py，以及 bench_status 的 --to 与 stdin 命令。
- 台账 §4 追加一行；Pc-8 状态列**就地追加**改判（不删原文）：PC 侧已修且有单测，
  固件侧那半等批 1a，两侧都到位才关闭本行。
- 缺口清单 ③-B 标明"批 1b 已编码、批 1a 未开工、顺序不可换"。
- AGENTS 测试基线 159 -> 207，链条续写不删历史。

check_doc_invariants 退出码 0（①–⑧ 命中 6 = 基线）；pytest 207 passed。
EOF
```

---

## Self-Review（本计划自查，已就地修正）

**1. spec 覆盖**：§3.1 MODE 帧 → Task 1；§3.2 STATUS v2 五字段 → Task 1/4；§3.3 reject 码与人话 → Task 1/4/6；§3.4 五处同步的 PC 三处（`protocol.py`/`uart_vectors.py`/`status_rx.py`）→ Task 1/4 + **Task 1 Step 5 之后需补 `common/uart_vectors.py` 的 MODE 向量**（见下方补漏）；§3.5 按长度分派 + 两条混跑用例 → Task 1（旧固件帧 + 新 PC）与 Task 4；§5.1 状态优先 → Task 2/6；§5.2 感知分级 L1/L2.5 → Task 3（`needs_confirm`）+ Task 6（按键 C）；§5.3 门 N 只发提刀 → Task 2/3；§5.4 日志与 HUD → Task 2/6；§6 档案 → Task 5；§7.2 D1/D2 → Task 9；§9 工具三处 → Task 7/8/9；§12 提交拆分 → 本文件即批 1b。

**补漏（自查发现，已并入）**：`common/uart_vectors.py` 是 spec §3.4 点名的五处之一，本批必须加 MODE 向量与 19 字节 STATUS 期望，否则批 1a 的对拍没有基准。→ 追加为 **Task 1 的 Step 6**：在 `build_vectors()` 里加 `('mode_auto', P.pack_frame(P.TYPE_MODE, P.pack_mode(P.MODE_REQ_AUTO, P.PROFILE_PREV), 9))`、`('mode_clear', ...MODE_REQ_CLEAR_ESTOP..., 10)`、`('status_v2', P.pack_frame(P.TYPE_STATUS, P.pack_status_v2(0.0, 0.0, 48.0, 0, 1, P.PROFILE_PREV, P.AUTH_PC_GRANTED, 1, 0x3A, P.REJECT_NONE), 11))`，并把该文件的提交并入 Task 1。

**未纳入本批（属批 1a 或批 2/3，不要在这里做）**：§5.2 的 L1 降速系数落到 `pc/control.py`（需要台架整定，批 1a 之后）；§4.x 全部固件侧；`pc/perception.py` 的 L1/L2.5 判据来源（依赖 M3 行距实测，B7）；TELEOP 实现（批 2）。

**2. 占位符扫描**：无 TBD/TODO/"类似 Task N"。Task 6 Step 3 里对 `lat_comp_m`/`recv_timeouts`/`link_drops` 三个变量名写了"以原文件为准，不要新造名字"——这是**显式的就地核对指令**，不是占位符。

**3. 类型一致性**：`frames_for_state(state, usable, vl, vr, tool_mm, permit)` 在 Task 2 定义、Task 6 调用，参数顺序一致；`GATE_N/GATE_F/PERMIT_BY_NAME/HOLDING` 只在 `pc/wire.py` 定义，Task 3/5 引用；`unpack_status_any` 返回的键名（`speed_mps/current_a/battery_v/limits/mode/profile/authority/loop_alive/build_id/reject/v`）与 `status_rx.last` 既有键名兼容（Task 4 直接整体替换 `self.last`，原有消费者用的 `mode`/`battery_v`/`speed_mps` 都在）；`judge()` 与 `build_command()` 的签名在 Task 7/8 的测试与实现中一致；`percentile`/`measure_d1`/`measure_d2`/`report` 在 Task 9 内自洽。

**4. 数字一致性**：159 → 166（+7）→ 176（+10）→ 180（+4）→ 186（+6）→ 191（+5）→ 192（+1）→ 198（+6）→ 202（+4）→ 207（+5）。每个任务的全量期望值都按此链条给出；**执行时以实测数为准，若不符必须停下来查，不许改期望值让它变绿**。
