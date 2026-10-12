# 台架就绪与状态文档同步 实施计划（2026-10-12）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把六处已经往回拉的状态文档改到与"批 1a／批 1b 均已编码、0 项台架"一致，并补上三条 PC 侧工具缺口（T1 档案握手与 TELEOP 的发送入口、T2 `run_log` 的帧型列、T3 急停锁存的开工提醒），让 `docs/X5验机与接入执行清单.md` §4B 那 17 格里今天只能"旁证"的格子在第一次上台架那晚有真判据。

**Architecture:** 改动只有两层。代码层是四个既有文件的**加法**——`pc/wire.py`（一列 + 一个纯函数）、`pc/main.py`（在 `send()` 里记一笔、每一拍清零、行末多一个关键字参数）、`tools/link_probe.py` 与 `tools/bench_status.py`（各加一条命令，都挂进已有的 `MODE_REQUEST_KINDS`／`TX_MODE_KINDS` 那一族，**不开新的参数通道**）、`tools/latency_probe.py`（`estop_caution()` 多打一行）；协议字节一个都没动（MODE 帧早就是 `<BB`），所以本批**不需要重编译、不需要烧录、不与批 1a 争任何文件**。文档层走本仓既有规矩：**就地追加／改判、原文不删**，六处同步 + §4B 的八格前置栏。

**Tech Stack:** Python 3（无新依赖）、pytest、`tools/check_doc_invariants.py`、Markdown。运行解释器与命令见 `README.md`「运行环境」。

**Spec:** `docs/superpowers/specs/2026-10-12-bench-readiness-sync-design.md`（作者 2026-10-12 批准；该文件自身的提交哈希以 `git log --oneline -1 -- docs/superpowers/specs/2026-10-12-bench-readiness-sync-design.md` 当场读数为准，本计划不抄）。判据冲突时以 spec 为准；spec §8 记了作者已经裁过的两处（顺序、以及 `--force-profile` **否决**）。

## Global Constraints

每一条对**每个任务**都生效。带"当场"字样的地方意思是：那个数只能由那条命令此刻的输出决定。

1. **不动 `firmware/`、不重编译、不烧录。** 也不改 `docs/参数差异台账.md` 的 §4 与 Fw-14／Fw-17／Fw-21／Fw-22／Pc-8 那五行——批 1a Task 8 已经就地改判过，本批再写一遍就是第二个事实源。
2. **不预勾任何一格台架结论。** 本计划全部改动的最高状态是「已编码 + 已单测」与「已文档化」。文档里凡写到台架，一律带"未台架"。
3. **两条硬禁令继续生效**：禁止实车 AUTO、禁止按现有接线文档直接带动力接线。本计划不需要板子；任何一步发现"要板子才能验"，就把它写成"未台架"，不许现场改成"顺手验了"。
4. **只 `git add <显式路径>`**，严禁 `git add -A`／`git add .`／`git add .`。作者的工作树里有这些脏项，一条都不许带进本批提交：`docs/组会汇报_20260916/**`（被作者删除）、`docs/组会汇报_20260923/`、`results/**`、`scan_result.txt`、`firmware/大车proj/大车/USER/PWM.uvguix.22763`、`firmware/大车proj/大车/USER/PWM.uvoptx`、`firmware/大车proj/大车/USER/build_log.txt`，以及 Keil 产物（`OBJ/`、`*.map`、`*.hex`）。每次提交前跑 `git diff --cached --numstat` 自查（注意：`git status --porcelain --cached` 不是合法旗标，会 exit 129）。
5. **提交形状固定**：`git commit -F- --cleanup=verbatim <<'EOF' … EOF`，标题**按本次改动当场写**。本仓有 6 次"复制上一条提交标题"的事故，所以写标题前先跑 `git show --stat --oneline HEAD` 看清上一条是什么、然后**不看它**打字。
6. **AGENTS 审查清单第 8 条（基线类数字）**：测试通过条数、测试文件数、`check_doc_invariants` 的圈号命中数、Keil 的 Code 尺寸与警告数、领先提交数——**只能由工具当场输出，不许抄进任何文档，包括本计划正文**。要引用就写"以某命令当场输出为准"并指向唯一权威处（现行测试基线在 `AGENTS.md`『当前状态』那一行，编译读数在台账 §4 那一行）。本计划正文里出现"基线"二字时指的都是**位置**，不是数值。
7. **`AGENTS.md` 本批只改 `:56` 那一行里的两个小片段**（③ 段的日期形状、② 段加一个指针）。同一个列表项的其余字符**一个都不动**；审查清单第 2 条所在的行块**不许碰**——那是 `tools/check_doc_invariants.py` 唯一摘除的扫描区，动它等于让规则自己击破自己。
8. **不得新增"圈号 + 短横 + 圈号"的区间记法。** 被禁记号与受保护基线记号的**具体形状不在本计划里写出**——写出来它就自己成了新命中，而 `tools/check_doc_invariants.py` 扫的是**全仓 md**（只剪 `.git`／`__pycache__`／`node_modules`，`.superpowers/` 的草稿一样进扫描）。全仓唯一被摘除的举例区是 `AGENTS.md` 审查清单第 2 条那个行块，别指望第二处豁免。判据只看工具输出：禁用语义恒 0 命中、受保护记号的命中数不许变。要引用场景号就写"①到⑥ 加 ⑧到⑫"这种逐号形式，或斜杠分隔（`⑨／⑪／⑫`）。
9. **含反引号或 `$()` 的文本一律走 Write 工具落成文件，再让命令读那个文件**——不许塞进 `bash -c "…"` 或双引号命令里。本仓为这件事写脏过一次台账（反引号被当命令替换执行，落进文件的是缺值的半句话）。规则：**文本先落文件，命令只读文件。**
10. **秋采时限 2026-10-15 优先于一切板载工作**（时限出处 = `docs/秋季图像采集清单.md` 自己写的那个日期）。本计划全部步骤 10-12 当晚做完且都不需要板子。
11. **两条检查命令固定**：
    - `python -B -m pytest tests/ -q -p no:cacheprovider` → 期望 0 failed / 0 error
    - `python -B tools/check_doc_invariants.py` → 期望退出码 **0**（2 = 基线漂移，必须解释"是加对了还是改错了"；**禁止为了让检查变绿而改基线数字**；1 = 禁用语义命中；3 = 有 md 读不进去，那"零命中"对它们不成立）
12. **`tools/latency_probe.py` 的打印面（含 `--help` 与 usage）必须纯 ASCII**——`tests/test_latency_probe.py` 里有静态断言扫这个；同一个测试文件还扫"已经进台账／已登记台账"那类没有落盘对应的措辞（对象是该文件本身与它的测试），所以新写的句子不许声称"台账里有了"。
13. **`.superpowers/` 只当草稿**：交接事实必须落到受版本控制的文件（执行清单／台账／契约／缺口清单）。收工前把该目录里的临时脚本删干净——`tools/check_doc_invariants.py` 的 `enumerate_ranges()` 扫**全仓 md**（只剪掉 `.git`／`__pycache__`／`node_modules`），草稿里的一句禁用语义会把检查弄红，而看上去像"文档出了问题"。
14. **表格行改动要带竖线对偶检查**：往 markdown 表格某一格追加句子时，先确认那一行的 `|` 数量与表头一致（§4B 的 C 表是 6 列 = 7 个竖线，§E 是 3 列 = 4 个），不一致就当场退出，不写半个字。

---

## 文件结构（本批改谁、各管什么）

| 文件 | 责任 | 本批动它的原因 |
|---|---|---|
| `pc/wire.py` | 线上语义的纯函数层：`frames_for_state()`、`RUN_LOG_COLUMNS`、`run_log_row()` | 新增 `tx_frames_text()` 与 `tx_frames` 列（T2） |
| `pc/main.py` | 采集/控制/发帧/落 CSV 的主循环 | 在真正的发送出口记一笔，把 T2 那一列填上 |
| `tools/link_probe.py` | 反向探针（唯一"不 bind 9100"的发帧器） | 新增 `mode_profile`／`mode_teleop`（T1） |
| `tools/bench_status.py` | B1/B2 台架记录器（收 + opt-in 发） | 新增 `!profile`（T1） |
| `tools/latency_probe.py` | D1／D2 往返时延测量 | `estop_caution()` 多一行（T3） |
| `tests/test_wire.py`、`tests/test_control.py` | 位置契约与主循环回归 | 钉住"追加在末尾、前面所有列下标不变"；解除两处写死的列数 |
| `tests/test_link_probe.py`、`tests/test_bench_status.py`、`tests/test_latency_probe.py` | 三条工具改动的字节级判据 | 各加一组测试 |
| `docs/X5验机与接入执行清单.md` | §4B 那 17 格的正文（格号／触发／看哪里／算过／不算过／前置） | 八格前置栏 + C21 + §E 三行改判 |
| `docs/缺口清单.md` | 唯一欠账台账 | 六处同步里的四处（标题、口径行、三处日期、③-B 新增三条） |
| `AGENTS.md` | 项目规矩与"当前状态" | `:56` 两个小片段 |
| `README.md` | 资产位置与工具说明的权威 | `bench_status.py` 那一行加指针 |

**执行顺序**：Task 1 → 2 → 3 → 4（代码，可并行但 1 与 2/3 有共享文件时按号做）→ Task 5（§4B，必须等 1/2/3 落地，否则"已补入口"是假话）→ Task 6（缺口清单／AGENTS／README，等 5 落地才指得到）→ Task 7（全量验证与交接）。

---

### Task 1: T2 —— `run_log` 的 `tx_frames` 列

**Files:**
- Modify: `pc/wire.py`（`RUN_LOG_COLUMNS` 在 `:22-32`、`run_log_row()` 在 `:106-140`）
- Modify: `pc/main.py`（`send()` 在 `:243-248`、每拍开头在 `:272-276`、发帧循环在 `:371-373`、行写在 `:541-548`）
- Modify: `tests/test_wire.py`（`:144-153` 两处写死的列位置/列数）
- Modify: `tests/test_control.py`（`:772-788` 测试名与两处写死的 25）
- Test: 同两个测试文件新增的断言

**Interfaces:**
- Consumes：`wire.frames_for_state()` 返回的 `[(frame_type, payload), …]`、`common/protocol.py` 的 `TYPE_*` 常量（`P`）。
- Produces：
  - `wire.TX_FRAME_NAMES: dict` — 帧型 → 短名
  - `wire.tx_frames_text(ftypes) -> str` — `'NAV+TOOL'` / `'HB'` / `'ESTOP'` / `'MODE'` / `'-'`
  - `wire.run_log_row(..., tx_frames='-')` — 新关键字参数，落**最后一列**
  - `pc/main.py` 的闭包变量 `tx_this_beat: list` — 每拍清零，只在真的 `sendto` 成功后 append

- [ ] **Step 1: 写失败的测试（`tests/test_wire.py`，追加到文件末尾）**

判据的核心是**位置**而不是数量，所以这里放一张"加列之前的列名快照"，断言写成"与快照逐个相等 + 只长一列"（AGENTS 审查清单第 8 条：列数一旦写死，下一批它就变成待检查内容——这个坑本仓已经踩过两次，Step 3 会顺手拆掉那两处）。

```python
# ---- T2（docs/superpowers/specs/2026-10-12-bench-readiness-sync-design.md §4）----
# `tx_frames` **追加之前**的列名快照。这张表是"位置契约"的锚：判据是
# "前 len(快照) 列与快照逐个相等、且总长恰好多 1"，而不是把列数写死在断言里。
# 为什么需要锚而不是靠人眼看 diff：`pc/wire.py` 的注释自己写着"前面各列的下标不变，
# 按位置读日志的旧消费者不受影响"，而这句话一旦被破坏，**没有任何一条既有测试会红**
# （既有测试全部按列名取数）。
_PRE_TX_FRAMES_COLUMNS = [
    't', 'frame_id', 'state', 'status', 'lat_m', 'lat_comp_m',
    'vL', 'vR', 'tool_mm', 'conf', 'latency_ms',
    'mcu_mode', 'batt_v', 'rx_good', 'rx_bad',
    'frame_age_s', 'recv_timeouts', 'link_drops',
    'profile', 'authority', 'reject', 'loop_alive', 'build_id', 'permit',
    'l1_events',
]


def test_tx_frames_is_appended_without_moving_earlier_columns():
    n = len(_PRE_TX_FRAMES_COLUMNS)
    assert wire.RUN_LOG_COLUMNS[:n] == _PRE_TX_FRAMES_COLUMNS
    assert len(wire.RUN_LOG_COLUMNS) == n + 1
    assert wire.RUN_LOG_COLUMNS[-1] == 'tx_frames'


def test_run_log_row_puts_tx_frames_last_and_defaults_to_the_silent_marker():
    """缺省 `'-'` 的含义是"这一拍线上确实一个字节都没走"，**不是缺数据**。

    ESTOP 稳态与回放模式都是这种。把它写成空串，读日志的人就会把"急停稳态的
    静默"当"日志坏了"；反过来把它写成 `NAV+TOOL`，回放模式就会声称发过东西。
    """
    res = {'status': 'dual', 'confidence': 0.9, 'lateral_px': 3.0}
    args = (1.0, 7, 'AUTO', res, 0.01, 0.02, 0.07, 0.07, 0.0, 12.0, None,
            ({}, 0, None), wire.GATE_N)
    row = wire.run_log_row(*args)
    assert len(row) == len(wire.RUN_LOG_COLUMNS)
    i = len(wire.RUN_LOG_COLUMNS) - 1
    assert row[i] == '-'
    assert wire.run_log_row(*args, tx_frames='NAV+TOOL')[i] == 'NAV+TOOL'


def test_tx_frames_text_names_each_frame_type():
    assert wire.tx_frames_text([]) == '-'
    assert wire.tx_frames_text([P.TYPE_HEARTBEAT]) == 'HB'
    assert wire.tx_frames_text([P.TYPE_NAV, P.TYPE_TOOL]) == 'NAV+TOOL'
    assert wire.tx_frames_text([P.TYPE_ESTOP]) == 'ESTOP'
    assert wire.tx_frames_text([P.TYPE_MODE]) == 'MODE'
    # 认不出的帧型原样给数字，不替它编名字（与 wire.REJECT_SHORT 同一口径）。
    assert wire.tx_frames_text([99]) == '99'
    assert wire.tx_frames_text([P.TYPE_TOOL, P.TYPE_NAV]) == 'TOOL+NAV'
```

- [ ] **Step 2: 跑测试，确认它是因为"东西不存在"而红**

Run: `python -B -m pytest tests/test_wire.py -q -p no:cacheprovider`
Expected: 三条新测试全红，且红法是 `AttributeError: module 'pc.wire' has no attribute 'tx_frames_text'` 与 `AssertionError`（列名/取值对不上），**不是** import 阶段收集错误。既有测试里 `:145` 与 `:150` 那两条**此刻仍该绿**（列还没加）——如果它们现在也红了，说明 Step 1 的改动跑到了实现之后，回头核对顺序。

- [ ] **Step 3: 实现（`pc/wire.py`）**

3a. `RUN_LOG_COLUMNS` 里 `'l1_events',` 之后、闭合 `]` 之前插入（保留 `'l1_events'` 上面那段"追加在末尾"的既有注释，不改写它）：

```python
    # ---- T2（2026-10-12 台架就绪）：这一拍 PC 真发上线的帧型 ----
    # 同样追加在**末尾**，跟着上面那条规矩走。§4B 的 C2 与 C18 要靠它把
    # "线上只有 HEARTBEAT""交回之后 PC 还在发"从旁证升成字节级证据，
    # 所以取值是帧型串而不是计数。列名快照与位置判据在 tests/test_wire.py。
    'tx_frames',
```

3b. 在 `frames_for_state()` 之后、`run_log_row()` 之前新增：

```python
# 帧型 → 本列用的短名。与 REJECT_SHORT 同一个理由：CSV 与 HUD 都要 ASCII，
# 而 `NAV+TOOL` 这种写法能直接对上 frames_for_state() 的返回顺序。
TX_FRAME_NAMES = {
    P.TYPE_NAV: 'NAV',
    P.TYPE_TOOL: 'TOOL',
    P.TYPE_HEARTBEAT: 'HB',
    P.TYPE_ESTOP: 'ESTOP',
    P.TYPE_MODE: 'MODE',
}


def tx_frames_text(ftypes):
    """把这一拍**真的写进 socket** 的帧型拼成一列文本：`NAV+TOOL` / `HB` / `-`。

    `'-'` 的意思是"这一拍线上确实一个字节都没有"——ESTOP 稳态是这种（E3 §5.1：
    稳态由 `frames_for_state('ESTOP', …)` 返回空列表，ESTOP 帧只在跳变那一拍发一次），
    回放模式也是这种（`pc/main.py` 的 `send()` 在 `sock is None` 时直接 return）。
    **它不是缺数据**：写成空串就会让人把"急停稳态的静默"当"日志坏了"，
    而把回放写成 `NAV+TOOL` 更糟——那是在给"这帧上线过"造一条假证据
    （spec §6.1 点名的就是这个形状：工具伪装成被测机制）。

    认不出的帧型原样给数字，不替它编名字。
    """
    if not ftypes:
        return '-'
    return '+'.join(TX_FRAME_NAMES.get(t, str(t)) for t in ftypes)
```

3c. `run_log_row()` 的签名末尾加关键字参数（`l1_events=0` 之后）：

```python
                l1_events=0, tx_frames='-'):
```

3d. `run_log_row()` 的文档串里 `l1_events` 那段之后补一句（原文不删）：

```
    `tx_frames` 是这一拍**真的写进 socket** 的帧型串（T2），由调用方从 `send()`
    的出口收集；缺省 `'-'` = "这一拍线上一个字节都没有"，含义与上面 `l1_events`
    那句一样：不能拿空串当"没接线"，也不能拿它当"发过了"。
```

3e. 返回列表末尾（`'%d' % l1_events,` 之后）加：

```python
        tx_frames,
```

- [ ] **Step 4: 接线（`pc/main.py`）**

四处，全部是加法。**注意闭包**：`tx_this_beat` 只用方法改动（`append` / `del xs[:]`），从不重新绑定，所以 `send()` 里不需要为它写 `nonlocal`——只有 `seq` 需要。

4a. `def send(ftype, payload):` 之前加一行声明，函数体里 `sock.sendto(...)` 之后、`seq += 1` 之前加一行记录：

```python
    tx_this_beat = []   # T2：这一拍**真的写进 socket** 的帧型，run_log 的 tx_frames 列用它

    def send(ftype, payload):
        nonlocal seq
        if sock is None:      # replay mode: no radio, no commands leave the PC
            return
        from common import protocol as P
        sock.sendto(P.pack_frame(ftype, payload, seq & 0xFFFF), pi)
        tx_this_beat.append(ftype)   # 在 sendto 之后：抛了就不算发过（与 bench_status 同纪律）
        seq += 1
```

4b. 每拍开头清零——插在 `prev_state = sm.state   # captured BEFORE any state event (P0-4)` 之后：

```python
            del tx_this_beat[:]      # T2：这一列只描述这一拍；上一拍的帧型不许漂过来
```

4c. 发帧循环不动（`frames_for_state()` 的返回值仍由 `send()` 逐条送出去，记录点在 `send()` 内部，所以按键那一路的 `MODE`/`ESTOP` 也自动进账——`[A]`/`[M]`/`[E]`/`[R]` 都发生在发帧循环之后、写行之前）。

4d. `:541` 那次 `wr.writerow(wire.run_log_row(...))` 的实参末尾，把
`l1_events=l1_events))          # I-6：降级事件落到时间轴上`
改成：

```python
                l1_events=l1_events,
                tx_frames=wire.tx_frames_text(tx_this_beat)))   # T2：这一拍线上真有什么
```

4e. `:269` 那行末尾的注释 `# 25 列；列定义与行构造都在 pc/wire.py` 改成（列数从注释里删掉，理由见 Step 1 的说明）：

```python
        wr.writerow(wire.RUN_LOG_COLUMNS)     # 列定义与行构造都在 pc/wire.py（列数不在这里写，AGENTS 清单第 8 条）
```

- [ ] **Step 5: 解除两处写死的列数（既有测试的反查，AGENTS 清单第 2 条）**

`grep -n "25" tests/test_wire.py tests/test_control.py pc/main.py` 会给出下面这三处的位置。逐条改，**取值断言一个字不动**（那些取值就是 spec §6.1 要的"旧数据复现旧结论"对照）：

5a. `tests/test_wire.py:145`：

```python
    assert wire.RUN_LOG_COLUMNS[-2] == 'l1_events'   # T2 之后 l1_events 让出末位，仍是"追加在末尾"的次序
```

5b. `tests/test_wire.py:150`：

```python
    assert len(row) == len(wire.RUN_LOG_COLUMNS)     # 列数由 test_tx_frames_is_appended_* 那条按快照钉
```

5c. `tests/test_control.py:772-788`：测试名里的 `25_columns` 在加列后就是假话，改名并把两处硬数换成对表头的比较（保留文档串里"原 24 + `l1_events`"那段历史，按"续写不抹历史"的规矩只补一句）：

```python
def test_main_run_log_writes_the_full_header_and_the_e3_fields(tmp_path, monkeypatch):
```
文档串里那段 `25 列（原 24 + l1_events）是控制器批准的偏差…24 是计划正文里的旧数。` 之后追加：

```
    10-12 又追加了一列 `tx_frames`（T2）。这一条**不再写死列数**——列名与位置由
    `tests/test_wire.py` 的 `_PRE_TX_FRAMES_COLUMNS` 快照钉，这里只比"表头 == 现场那张列表"
    与"每行与表头等长"。（AGENTS 清单第 8 条：抄进来的数字下一批就变成待检查内容。）
```
两条断言改成：

```python
    assert r['header'] == list(wire.RUN_LOG_COLUMNS)
    assert all(len(row) == len(r['header']) for row in r['rows']), \
        [len(x) for x in r['rows']]
```

- [ ] **Step 6: 跑全量，确认只有预期的绿**

Run: `python -B -m pytest tests/ -q -p no:cacheprovider`
Expected: **0 failed / 0 error**；条数以这条命令的当场输出为准，**不抄进任何文件**（AGENTS 清单第 8 条）。读数与 `AGENTS.md`『当前状态』那一行写的最近一次相比**只该多不少**（本任务净增 3 条）。
Run: `python -B -m pytest tests/test_control.py -q -p no:cacheprovider -k "run_log"`
Expected: 改名后的那条与相邻的 `l1_events` 取值断言全绿——它们证明新列没把前面任何一列的取值挪位。

- [ ] **Step 7: 提交**

先 `git diff --numstat` 眼看改动只落在 `pc/wire.py`、`pc/main.py`、`tests/test_wire.py`、`tests/test_control.py` 四个文件；然后：

```bash
git add pc/wire.py pc/main.py tests/test_wire.py tests/test_control.py
git commit -F- --cleanup=verbatim <<'EOF'
T2：run_log 加 tx_frames 一列，把 §4B 的 C2／C18 从旁证升成字节级证据

这一拍 PC 到底往线上放了什么，以前只能靠"MANUAL 态 frames_for_state() 只给心跳"
这个编码层事实旁证——§4B 的 C2 那一格原话就是"要真取证得去 USB-TTL 那侧抓字节"。
现在 run_log.csv 末尾有一列帧型（NAV+TOOL / HB / ESTOP / MODE / -），
记录点在 send() 的出口：只有真的 sendto 成功才算发过，回放模式一律记 '-'。

'-' 是"这一拍确实一个字节都没有"而不是缺数据，这条写进 docstring 也写进测试：
ESTOP 稳态与回放都长这个样子，混成空串就把静默读成日志坏了。

顺带拆掉两处写死的列数（tests/test_wire.py、tests/test_control.py 各一处 +
那条测试的名字）。位置契约改由 tests/test_wire.py 里的加列前列名快照钉：
"前面各列逐个相等、总长恰好多 1"。既有测试的**取值**断言一个字没动——
那才是 spec §6.1 要的"旧数据复现旧结论"对照。

检查：pytest 当场全量通过（条数以那条命令的输出为准，AGENTS 审查清单第 8 条）；
本任务不动 firmware/、不新增"圈号+短横+圈号"的区间记法。
EOF
```

---

### Task 2: T1（一）—— `link_probe` 的 `mode_profile` 与 `mode_teleop`

**Files:**
- Modify: `tools/link_probe.py`（`EXPECTED:106`、`MODE_REQUEST_KINDS:109`、`_V1_NOTE:113-117`、`build():213-233`、`judge():132-231`、`main():423-470`）
- Modify: `tests/test_link_probe.py`（`:289-315` 的参数化表 + 新增断言）

**Interfaces:**
- Consumes：`P.MODE_REQ_PROFILE`（0x20）、`P.MODE_REQ_TELEOP`（0x02）、`P.pack_mode(req, profile)`、既有 `_load_profile_id()`（档案号唯一出处 = `config/vehicle_profile.yaml`）。
- Produces：`link_probe.MODE_REQUEST_KINDS` 含 5 项、`EXPECTED` 含 `mode_profile`/`mode_teleop`（值都是 `None` = 不以 mode 变化为判据）、`link_probe._judge_new_mode(kind, baseline_mode, seen_modes, rejects)`、`link_probe.check_mode_args(kind, args)`（`main()` 调用它，测试也直接调它）。

- [ ] **Step 1: 写失败的测试**

1a. 把既有的那条参数化测试扩成五条（`tests/test_link_probe.py:289-293` 的列表末尾加两行）——**这是改号的反查重点**：既有测试的参数表就是"三种 MODE 命令"这个旧事实的载体：

```python
@pytest.mark.parametrize('kind, want', [
    ('mode_auto', P.MODE_REQ_AUTO),
    ('mode_manual', P.MODE_REQ_MANUAL),
    ('clear', P.MODE_REQ_CLEAR_ESTOP),
    ('mode_profile', P.MODE_REQ_PROFILE),
    ('mode_teleop', P.MODE_REQ_TELEOP),
])
def test_build_mode_frames_carry_the_request_and_profile(kind, want):
    frame = lp.build(kind, [], 7, profile=2)
    ftype, seq, payload = P.unpack_frame(frame)
    assert (ftype, seq) == (P.TYPE_MODE, 7)
    assert P.unpack_mode(payload) == (want, 2)
```

1b. 追加到文件末尾（三条，各管一件事：**上线字节**、**族归属**、**参数闸门不被绕过**）：

```python
# ---- T1（2026-10-12）：档案握手与 TELEOP 的入口 ----


def test_new_mode_kinds_belong_to_the_v1_inconclusive_gate():
    """两条新命令**必须**挂在 MODE_REQUEST_KINDS 上，而不是另开一条通道。

    这条归属决定的是"未烧批 1a 的板上会不会出现假 PASS"：`_run_serial()` 用
    `kind in MODE_REQUEST_KINDS and versions == {1}` 把结论压成 INCONCLUSIVE，
    因为 v1 那块板的 switch 里根本没有 TYPE_MODE 这一支、MODE 帧整条被丢。
    握手在那块板上从来没成功过，可"这轮没读到非零 reject"读起来**像**成功
    （spec §6.1 点名的形状就是它）。所以这不是代码组织问题，是判据问题。
    """
    for kind in ('mode_profile', 'mode_teleop'):
        assert kind in lp.MODE_REQUEST_KINDS
        assert kind in lp.EXPECTED          # 不在判据表里，judge() 只会给"没有这一条"
        assert lp.EXPECTED[kind] is None    # 两条都不以 mode 变化为判据


@pytest.mark.parametrize('kind', ['mode_auto', 'mode_manual', 'clear',
                                  'mode_profile', 'mode_teleop'])
def test_mode_commands_still_refuse_a_command_line_profile(kind):
    """T1 不许绕过那条老约束：档案号只能来自 config/vehicle_profile.yaml。

    闸门从 main() 里抽成 check_mode_args() 是为了能被直接钉住——测 main() 里那段
    顺序代码要构造 argv 并真的往发送那一步走，而这条闸门的意义恰恰是**不许走到发送**。
    """
    with pytest.raises(SystemExit):
        lp.check_mode_args(kind, ['2'])
    lp.check_mode_args(kind, [])            # 不传参数才是合法用法


def test_judge_mode_profile_and_teleop_say_different_things():
    """握手的 0x01 有两种成因，TELEOP 的 0x06 是**预期答复**——两句不能共用文案。"""
    # 握手：没读到非零 reject = 板子认了这个档案号
    assert lp.judge('mode_profile', 0, [0], [])[0] == 'PASS'
    # 握手：挂着 0x01 —— 要说清"这个号真的不匹配"与"从没握过手"分不开
    verdict, text = lp.judge('mode_profile', 0, [0], [P.REJECT_PROFILE])
    assert verdict == 'FAIL' and '从没' in text
    # 握手：板子回的是别的码 ⇒ 这条码不是握手产生的，不给结论
    assert lp.judge('mode_profile', 0, [0], [P.REJECT_RCS_STALE])[0] == 'INCONCLUSIVE'
    # TELEOP：0x06 就是这一格要的答复，且必须带上"不等于 TELEOP 可用"那句
    verdict, text = lp.judge('mode_teleop', 0, [0], [P.REJECT_NOT_IMPL])
    assert verdict == 'PASS' and 'TELEOP 可用' in text
    # TELEOP：读不到非零 reject ⇒ 与"帧整条被丢掉"分不开（v1 上就是这个长相）
    assert lp.judge('mode_teleop', 0, [0], [])[0] == 'INCONCLUSIVE'
    # 两条共同的最外层：一帧 STATUS 都没有，只能说不计结论
    assert lp.judge('mode_profile', 0, [], [])[0] == 'INCONCLUSIVE'
    assert lp.judge('mode_teleop', None, [0], [])[0] == 'INCONCLUSIVE'
```

- [ ] **Step 2: 跑测试，确认失败形状**

Run: `python -B -m pytest tests/test_link_probe.py -q -p no:cacheprovider`
Expected: 参数化那两条新用例红在 `ValueError: 未知指令` （`build()` 的抛错文案），另外三条红在 `assert 'mode_profile' in …` 与 `AttributeError: module 'tools.link_probe' has no attribute 'check_mode_args'`。

- [ ] **Step 3: 实现（`tools/link_probe.py`）**

3a. `EXPECTED` 与 `MODE_REQUEST_KINDS`（`:106-109`）：

```python
EXPECTED = {'nav': None, 'mode_auto': 1, 'mode_manual': 0,
            'estop': 2, 'clear': 0, 'tool': None, 'beat': None,
            # T1（2026-10-12）新增两条。都是 None：**握手与 TELEOP 都不该改 mode**——
            # 握手的产物是 handshake_ok 这一位（不在 STATUS 里），TELEOP 本批未实现。
            # 能判的只有"链路活着 + 板子挂在哪条 reject 上"，文案见 _judge_new_mode。
            'mode_profile': None, 'mode_teleop': None}
# 走 MODE 帧（TYPE_MODE）的命令都在这一族里。族本身是判据的一部分：
# _run_serial() 靠它 + STATUS 版本把未烧批 1a 的板压成 INCONCLUSIVE（见测试
# test_new_mode_kinds_belong_to_the_v1_inconclusive_gate）。
MODE_REQUEST_KINDS = ('mode_auto', 'mode_manual', 'clear',
                      'mode_profile', 'mode_teleop')
```

3b. `build()` 的 `if kind in MODE_REQUEST_KINDS:` 分支（请求码表补两项）与末尾 `ValueError` 文案补两条：

```python
    if kind in MODE_REQUEST_KINDS:
        req = {'mode_auto': P.MODE_REQ_AUTO, 'mode_manual': P.MODE_REQ_MANUAL,
               'clear': P.MODE_REQ_CLEAR_ESTOP,
               'mode_profile': P.MODE_REQ_PROFILE,
               'mode_teleop': P.MODE_REQ_TELEOP}[kind]
        return P.pack_frame(P.TYPE_MODE, P.pack_mode(req, profile), seq)
    raise ValueError('未知指令 %r：只有 nav / tool / beat / estop / mode_auto / '
                     'mode_manual / clear / mode_profile / mode_teleop' % kind)
```

3c. `_V1_NOTE`（`:113-117`）末尾那句枚举改成指向族本身，别再点名三条——**这是"改号必反查交叉引用"的那一处**，写死枚举的下一批必然漏：

```python
_V1_NOTE = ('note: STATUS payload is v1 (14 B) -> the board runs pre-E3 firmware. '
            'MODE frames are dropped (retrofit.c:60-75) and the reject/authority '
            'fields do not exist, so "refused by the authority gate" and "the frame '
            'never reached the MCU" cannot be told apart here; every command in '
            'MODE_REQUEST_KINDS is judged INCONCLUSIVE.')
```

3d. 在 `judge()` 之前新增 `_judge_new_mode()`（完整实现）：

```python
def _judge_new_mode(kind, baseline_mode, seen_modes, rejects):
    """T1 两条新命令的判据：都不以 mode 变化为判据，能判的只有链路 + reject。

    两条各说一句，不共用文案：
      · 握手（mode_profile）——固件的 `enter_unmanned()` 第一条件就是这一位，
        成功会写 reject=0、失败写 reject=0x01；而**"从没握过手"的板子读到 0x01
        是同一种长相**（§4B 读表须知第 3 句已经把这个坑登记过），所以这里
        不许把 0x01 直接写成"档案不符"就完事。
      · TELEOP（mode_teleop）——预期答复就是 0x06（该模式本批未实现）。
        它同时证明两件事：MODE 真的进了分派、未实现通路诚实。**不能写成
        "TELEOP 可用"**，那是批 2（spec §4 T1 的原话）。
    """
    if not seen_modes:
        if baseline_mode is None:
            return 'INCONCLUSIVE', '一帧 STATUS 都没收到：查串口/桥接/接线，不是查权限'
        return 'INCONCLUSIVE', ('发送开始之后一帧 STATUS 都没有（发送前是 %s）：'
                                '收的方向在发送之后就断了，不能对发送方向下结论'
                                % _name(baseline_mode))
    last = rejects[-1] if rejects else None
    name = P.REJECT_TEXT.get(last, '未知拒绝码 %s' % last)
    if kind == 'mode_profile':
        if last == P.REJECT_PROFILE:
            return 'FAIL', ('板子挂着 reject=0x01：可能是"这个档案号真的不匹配"，'
                            '也可能是"这块板从头到尾没握过手"——两种 0x01 长得一样，'
                            '分开要靠"是否先有过一次握手"这个流程前提（§4B 读表须知'
                            '第 3 句），不能只读这一个字节')
        if last is None:
            return 'PASS', ('握手帧已上线（MODE 0x20 + 档案号取自 '
                            'config/vehicle_profile.yaml），本轮没读到非零 reject。'
                            '这一格看的是 reject 不是态：它不改 mode。'
                            '⚠️ reject 记的是"最近一次"，成功会写回 0')
        return 'INCONCLUSIVE', ('握手之后板子挂的是 reject=0x%02X（%s），不是 0 也不是 '
                                '0x01：这一条不是握手本身产生的，别算成握手的结论'
                                % (last, name))
    if last == P.REJECT_NOT_IMPL:
        return 'PASS', ('reject=0x06（该模式本批未实现）正是预期答复：它同时证明 MODE '
                        '进了分派、TELEOP 的未实现通路诚实。**这不等于 TELEOP 可用**，'
                        '实现属批 2')
    if last is None:
        return 'INCONCLUSIVE', ('收到 STATUS 但没读到非零 reject：没烧批 1a 的板就是把 '
                                'MODE 整条丢掉、reject 字段根本不存在，这一格与'
                                '"什么都没发生"分不开')
    return 'FAIL', ('TELEOP 请求被排在它前面的判据挡了：reject=0x%02X（%s）——'
                    '四条判据的顺序是固件写死的，本格没测到未实现通路'
                    % (last, name))
```

3e. `judge()` 里，在 `if kind not in EXPECTED:` 那道守卫**之后**、`want = EXPECTED[kind]` **之前**插入分派：

```python
    if kind in ('mode_profile', 'mode_teleop'):
        return _judge_new_mode(kind, baseline_mode, seen_modes,
                               [c for c in reject_codes if c])
```

3f. 新增模块级闸门函数（放在 `_tool_gate_or_exit()` 附近，与它同一个族）：

```python
def check_mode_args(kind, args):
    """MODE 命令不接受命令行参数（spec §6：改档案号 = 改一台车的权限）。

    从 main() 抽出来有两个理由：① 它能被测试直接钉住（见
    tests/test_link_probe.py::test_mode_commands_still_refuse_a_command_line_profile）；
    ② 位置不许漂——它必须跑在**建 socket 之前**，与 bench_status 的 --to 同一条纪律：
    先拒、后碰资源。
    """
    if kind in MODE_REQUEST_KINDS and args:
        raise SystemExit('%s 不接受参数：档案号从 config/vehicle_profile.yaml 取，'
                         '不在命令行上给' % kind)
```

并把 `main()` 里 `:456-458` 那三行就地换成 `check_mode_args(a.kind, a.args)`（注释"MODE 三条的参数…"同步改成"MODE 这一族的参数只有一个档案号…"，其余不动）。

3g. `main()` 的 help 文案（`:427-429`）：

```python
    ap.add_argument('args', nargs='*',
                    help='nav: vL vR (m/s)   tool: mm lift位   '
                         'the five MODE kinds: no arguments (profile comes from '
                         'config/vehicle_profile.yaml)')
```

3h. `_run_serial()` 末尾那句中文 INCONCLUSIVE 打印（`:355-360`）里"mode_auto / mode_manual / clear 这三条"改成"这一族（`MODE_REQUEST_KINDS`）这几条"，别在第二处再枚举一遍——两处枚举就是两个事实源。

- [ ] **Step 4: 跑测试**

Run: `python -B -m pytest tests/test_link_probe.py -q -p no:cacheprovider`
Expected: 全绿。
Run: `python -B -m pytest tests/ -q -p no:cacheprovider`
Expected: 全量 0 failed / 0 error（条数以当场输出为准）。
Run: `python -B tools/link_probe.py mode_profile --help` 之后再跑 `python -B tools/link_probe.py mode_profile 2`
Expected: 前者正常打印用法（choices 里能看见 `mode_profile` 与 `mode_teleop`）；后者**立刻**退出并说明"不接受参数：档案号从 config/vehicle_profile.yaml 取"，且**不**留下任何 socket 相关报错——这一步同时验证 3f 的"位置不许漂"。

- [ ] **Step 5: 提交**

```bash
git add tools/link_probe.py tests/test_link_probe.py
git commit -F- --cleanup=verbatim <<'EOF'
T1：link_probe 能发档案握手与 TELEOP 了（mode_profile / mode_teleop）

§4B 的 C6 今天标着"待补工具"，C13/C14/C18/C19/C20/C21 全都要靠
"关掉这个程序、开那个程序"才补得回一次握手——因为 MODE(0x20) 与 MODE(0x02)
在 PC 侧一个合法入口都没有。

两条都挂进既有的 MODE_REQUEST_KINDS 那一族，不开新的参数通道：
档案号仍只从 config/vehicle_profile.yaml 取，命令行给参数当场拒
（闸门从 main() 抽成 check_mode_args()，抽出来的理由是能被钉住，
 而它的位置仍在建 socket 之前——先拒、后碰资源）。

挂进那一族不是为了整洁：_run_serial() 靠 kind in MODE_REQUEST_KINDS
加上 STATUS 版本把未烧批 1a 的板压成 INCONCLUSIVE。v1 那块板上握手
从来没成功过，可"这轮没读到非零 reject"读起来像成功——那正是本仓
反复出现的"工具伪装成被测机制"（Pc-9 同族）。

判据两条各写各的：握手的 0x01 有两种成因（真不匹配 / 从没握过手），
TELEOP 的 0x06 是预期答复，且明写"这不等于 TELEOP 可用"（实现属批 2）。
_V1_NOTE 与末尾那句中文原来都点名三条命令，改成指向族本身——
枚举写两处就是两个事实源。

检查：pytest 当场全量通过（条数以那条命令的输出为准，AGENTS 审查清单第 8 条）。
EOF
```

---

### Task 3: T1（二）—— `bench_status` 的 `!profile`

**Files:**
- Modify: `tools/bench_status.py`（`TX_MODE_KINDS:103`、`build_command():320-354`、`TxSender.send_line()` 的 `[TX SKIPPED]` 文案 `:449-450`、模块文档串 `:29` 附近那句命令枚举）
- Modify: `tests/test_bench_status.py`（`:307-312` 的元组表 + 新增断言）

**Interfaces:**
- Consumes：`P.MODE_REQ_PROFILE`、`P.pack_mode`、既有 `TxSender.send_line()` 的三类出口计数（`unparsed` / `refused` / `errors`）。
- Produces：`build_command('!profile', profile_id, seq)` → `('tx_profile', <TYPE_MODE 帧>)`；`'tx_profile' in TX_MODE_KINDS`（于是那一行的 `profile` 列有值）。

- [ ] **Step 1: 写失败的测试**

```python
# ---- T1（2026-10-12）：!profile —— 不重启 pc/main.py 也能重放档案握手 ----


def test_build_command_profile_is_a_mode_frame():
    kind, frame = bs.build_command('!profile', 2, 11)
    assert kind == 'tx_profile'
    t, seq, payload = P.unpack_frame(frame)
    assert (t, seq) == (P.TYPE_MODE, 11)
    assert P.unpack_mode(payload) == (P.MODE_REQ_PROFILE, 2)


@pytest.mark.parametrize('bad', ['!profile 2', '!profile x', '!profile '])
def test_build_command_profile_takes_no_argument(bad):
    """档案号不在输入行上给（与 `!auto` 同一条纪律：改档案号 = 改一台车的权限）。

    `'!profile '` 那条是分开的写法：cmd='profile'、args=[''] —— 有参数就等于拒。
    """
    assert bs.build_command(bad, 1, 1) is None


def test_tx_profile_row_fills_profile_and_stays_out_of_the_rx_side(tmp_path):
    """`tx_profile` 进 TX_MODE_KINDS：它是这一族里唯一"载荷真带档案号"的新命令。

    同时钉两条既有纪律：tx 行只算 `tx_rows`、**不碰 `rx_rows`**（verdict 的分母
    用后者，共用就等于给自己那套新鲜度/重同步判据喂假数据），
    且用的是发送侧那套独立序号。
    """
    assert 'tx_profile' in bs.TX_MODE_KINDS
    log = _mklog(tmp_path)
    sock = _FakeSock()
    s = bs.TxSender('192.168.127.10', 9000, sock=sock)
    kind, seq = s.send_line('!profile', 2, log)
    assert (kind, seq) == ('tx_profile', 0)
    assert s.seq == 1 and s.sent == 1
    assert (log.tx_rows, log.rx_rows) == (1, 0)
    row = _rows(log)[-1]
    assert row['kind'] == 'tx_profile' and row['profile'] == '2'
    # tx 行不许伪造收到的证据：mode/loop_alive 那几列留空
    assert row['mode'] == '' and row['loop_alive'] == ''
    log.close()
```

同时把既有 `test_build_command_parses_each_kind` 的元组表（`:307-312`）加一行 `('!profile', P.TYPE_MODE)`——那条表就是"记录器能发哪几条"的事实源，漏更新的话它会成为下一处过期枚举。

- [ ] **Step 2: 跑测试确认失败**

Run: `python -B -m pytest tests/test_bench_status.py -q -p no:cacheprovider`
Expected: 新用例红在 `assert None == 'tx_profile'` 之类（`build_command` 认不出 `!profile` 返回 None）。

- [ ] **Step 3: 实现（`tools/bench_status.py`）**

3a. `TX_MODE_KINDS`（`:103`）：

```python
# 只有这几条 ! 命令的载荷里带 profile（TYPE_MODE，spec §3.1）⇒ 只有它们的 tx 行该填
# profile 列。NAV/TOOL 填了就是给"线上根本没带的字段"造一条看起来像证据的数。
# 10-12 加 tx_profile（T1）：档案握手，用途是**不重启 pc/main.py 也能重放握手**。
TX_MODE_KINDS = ('tx_auto', 'tx_manual', 'tx_clear', 'tx_profile')
```

3b. `build_command()` 的 `cmd in ('auto', 'manual', 'clear')` 那一段（`:343-348`）改成一条查表 + 保留"不接受参数"的形状：

```python
        if cmd in ('auto', 'manual', 'clear', 'profile') and not args:
            req = {'auto': P.MODE_REQ_AUTO, 'manual': P.MODE_REQ_MANUAL,
                   'clear': P.MODE_REQ_CLEAR_ESTOP,
                   'profile': P.MODE_REQ_PROFILE}[cmd]
            return ('tx_' + cmd,
                    P.pack_frame(P.TYPE_MODE, P.pack_mode(req, profile_id), seq))
```
（`and not args` 那半句就是 Step 1 里 `!profile 2` 被拒的实现，位置在既有分支上，不新增通道。）

3c. `[TX SKIPPED]` 的用法串（`:449-450`）与模块文档串 `:29` 那句命令枚举各补 `!profile`。**两处都要补**：一处是操作员现场唯一会读的行，一处是 README／§4B 指向的说明——漏一处就又是两个事实源。最终形式（`%` 右侧只有一个占位符，所以 `% line` 原样保留，别顺手加元组）：

```python
            print('  [TX SKIPPED] cannot parse %r  (want: !nav vL vR | '
                  '!tool mm lift | !beat | !auto | !manual | !clear | !profile)'
                  % line)
```

- [ ] **Step 4: 跑测试**

Run: `python -B -m pytest tests/test_bench_status.py -q -p no:cacheprovider` → 全绿。
Run: `python -B -m pytest tests/ -q -p no:cacheprovider` → 全量 0 failed / 0 error。

- [ ] **Step 5: 提交**

```bash
git add tools/bench_status.py tests/test_bench_status.py
git commit -F- --cleanup=verbatim <<'EOF'
T1：bench_status 的 stdin 加 !profile（MODE 0x20 档案握手）

和 link_probe 的 mode_profile 是同一件事的两个入口，用途写死在名字里：
不重启 pc/main.py 也能重放一次握手。为什么需要：握手位是 RAM 位，
MCU 一复位就清零，而 enter_unmanned() 的第一条件就是它——§4B 因此把
"发不出 0x20"登记成一条工具缺口，凡是"申请无人"的格都被它拖着。

档案号仍只从 config/vehicle_profile.yaml 取：!profile 带参数 = 拒
（and not args 就挂在既有的 MODE 分支上，没开新通道）。
tx_profile 进 TX_MODE_KINDS，因为只有它的载荷真带档案号，profile 列才有值；
发送序号与 STATUS 接收序号照旧两套，tx 行不进 verdict 的分母。

命令枚举有两处（模块文档串与 [TX SKIPPED] 那行），两处都补——
枚举写一处漏一处是本仓第 2 条"改号必反查"的老形状。

检查：pytest 当场全量通过（条数以那条命令的输出为准，AGENTS 审查清单第 8 条）。
EOF
```

---

### Task 4: T3 —— `latency_probe` 的"清不掉锁存"那一行

**Files:**
- Modify: `tools/latency_probe.py`（`estop_caution():1046-1073`，只在那个 D1 会静默的分支里追加一行）
- Modify: `tests/test_latency_probe.py`（新增一条 + 把它塞进既有 ASCII 扫描的 `targets` 列表 `:1105-1116` 那片）

**Interfaces:**
- Consumes：`BRIDGE_ESTOP_AFTER_S`、既有 `estop_caution(timeout_d1_s, keepalive_s, settle_s)` 签名（**不改**）。
- Produces：`lines` 在 D1 分支里多一个元素，内容 ASCII，说明"三条软件补救都不存在"。

- [ ] **Step 1: 写失败的测试**

```python
def test_d1_silence_names_the_missing_remedies():
    """T3：D1 每轮的固有静默会锁存板子，而"救不了"这件事以前只在注释里。

    断言四件事：三条软件补救点名（[M] / !clear / link_probe clear）、
    说清为什么都不存在（都走 TYPE_MODE，未烧批 1a 的板整条丢掉）、
    只能断电、以及**烧了之后也不是"已知能清"**——那一手要 §4B 的 C11 真过
    （不许把待台架说成可用，AGENTS 清单第 5 条的四态口径）。

    反向那半是这条测试的重点：D1 不制造静默时**这两句都不许出现**。
    注意 `estop_caution()` 的 D2 分支里也有 'power cycle' 字样（既有文案），
    所以反向判据说的是本行独有的那两个特征串，不是笼统的 'power cycle'。
    """
    lines = LP.estop_caution(2.0)
    assert len(lines) >= 2
    text = '\n'.join(lines)
    for want in ('[M]', '!clear', 'link_probe clear', 'TYPE_MODE',
                 'power cycle', 'C11', 'is only proven after'):
        assert want in text, want
    quiet = LP.estop_caution(0.4, keepalive_s=LP.DEFAULT_KEEPALIVE_S)
    assert not any('link_probe clear' in ln for ln in quiet)
    assert not any('is only proven after' in ln for ln in quiet)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -B -m pytest tests/test_latency_probe.py -q -p no:cacheprovider`
Expected: 新用例红在 `assert len(lines) >= 2`（当前 D1 分支只 append 一行；`timeout_d1=2.0` 时 D2 那句因走 `elif` 而不出现）。

- [ ] **Step 3: 实现（`tools/latency_probe.py`）**

在 `estop_caution()` 的 `if timeout_d1_s is not None and timeout_d1_s > BRIDGE_ESTOP_AFTER_S:` 分支里，**既有 `lines.append(...)` 之后**追加（纯 ASCII；不含"台账里已有这一条"那类措辞；行号引用只写符号名不写行号——本仓的规矩是"以后指格子不指行号"）：

```python
        lines.append(
            'And the software remedies do not exist on that board: [M] in pc/main.py, '
            '!clear in bench_status stdin and "link_probe clear" all put a TYPE_MODE '
            'frame on the wire, which the pre-E3 firmware drops whole (the switch has '
            'no MODE_REQ branch) - a power cycle is the only way out. After batch 1a '
            'is flashed, MODE_REQ_CLEAR_ESTOP is *coded* to clear the latch, but it is '
            'only proven after bench cell C11 of the X5 checklist section 4B has '
            'passed; until then plan every D1 round as costing one power cycle, and '
            'keep the remedy column of your notes honest about that.')
```

- [ ] **Step 4: 把新行纳入既有 ASCII 静态扫描**

`tests/test_latency_probe.py` 那片 `targets`（列着若干 `'\n'.join(LP.estop_caution(...))` 的地方）里，在已有条目之后加一条同形状的：

```python
               '\n'.join(LP.estop_caution(2.0, keepalive_s=None, settle_s=0.0)),
```

- [ ] **Step 5: 跑测试**

Run: `python -B -m pytest tests/test_latency_probe.py -q -p no:cacheprovider` → 全绿（含 ASCII 扫描与"不许声称台账"那条 NEW-3 静态断言）。
Run: `python -B -m pytest tests/ -q -p no:cacheprovider` → 全量 0 failed / 0 error。
Run: `python -B tools/latency_probe.py --help` → 正常打印，且这条路径不报错（help 也在 ASCII 扫描面里）。

- [ ] **Step 6: 提交**

```bash
git add tools/latency_probe.py tests/test_latency_probe.py
git commit -F- --cleanup=verbatim <<'EOF'
T3：estop_caution 明写"未烧批 1a 时没有任何软件清锁存的路"

原来那段 D1 告警说的是"会锁存"，没说"你想清也清不掉"：
[M]、!clear、link_probe clear 三条发的是同一个 TYPE_MODE，
而未烧批 1a 的板把整条丢掉——现场真正需要的这句话以前只活在注释里，
而台架上没人翻源码，后果却是"这块板要断电"这种现场动作（模块文档串
自己就是这么写的，所以它该在打印面上）。

措辞留了一条不许越界：烧了批 1a 之后 MODE_REQ_CLEAR_ESTOP 只是
"coded to clear"，能不能清要等 §4B 的 C11 真过——本行不许把待台架
说成已知可用（AGENTS 审查清单第 5 条的四态口径）。

行号引用只写符号名，不写行号（本仓的"以后指格子不指行号"）。
新行同时进 tests/test_latency_probe.py 的 ASCII 静态扫描面。

检查：pytest 当场全量通过（条数以那条命令的输出为准，AGENTS 审查清单第 8 条）。
EOF
```

---

### Task 5: §4B 的八格前置栏 + C21 + §E 三行改判

**Files:**
- Modify: `docs/X5验机与接入执行清单.md`（§4B 在 `:169-317`；C 表行 `:239-275`，§E 表行 `:310-315`）
- Create（临时，收工删除）: `.superpowers/sdd/2026-10-12-bench-readiness-sync/append_cell.py`

**Interfaces:** 无代码接口。产出的是"§2 判据第 4 条能被机检"的形状：C2／C6／C10／C13／C14／C18／C19／C20 八格的最后一列里出现"已补入口（未台架）"或"两遍跑 + 人工对齐"，且这八格不再有"待补工具"。

- [ ] **Step 1: 写追加脚本（先落文件再执行，Global Constraint 9）**

判据：只改**唯一匹配**那一行；行的竖线数对不上就整文件不写；已经有这段文字就跳过（可重跑）。

⚠️ **一个当场查出来的坑（10-12 实测）**：`| C6 ` 与 `| C20 ` 这两个前缀各有 **2 行**匹配——§D 那张回填表里也有 `| C6 | | | |` 这样的短行（4 列 = 5 个竖线）。所以"匹配前缀 + 匹配竖线数"**两个条件都要有**，只按前缀匹配会撞上回填表那一行、把判据写进错的地方。前缀本身也故意保持短（`| C6 `），因为格号后面的说明文字在两处并不相同，用长前缀反而更脆。

```python
# -*- coding: utf-8 -*-
"""把一句话追加到 markdown 表格某一格（行末那个竖线之前）。

用法：python -B append_cell.py
只改**同时**满足"前缀匹配 + 竖线数等于表应有的数"的那一行；匹配到 0 行或 2 行
都整文件拒绝写入（宁可一行都不改，也不要把表格行拼成下一批读不出来的形状）。
竖线数这个条件是必须的：`| C6 ` 与 `| C20 ` 在 §D 回填表里各有一条同前缀的短行。
"""
import io

PATH = u'docs/X5验机与接入执行清单.md'
C_TABLE_PIPES = 7          # 6 列的 C 表行
E_TABLE_PIPES = 4          # 3 列的 §E 表行

# (行前缀, 该行应有的竖线数, 追加的文字, 幂等标记)
APPENDS = [
    (u'| C2 场景 ', C_TABLE_PIPES,
     u'🟢 **10-12 已补入口（未台架）**：`run_log.csv` 末尾新增 `tx_frames` 列，取值是'
     u'**真的写进 socket** 的帧型串（`HB`／`NAV+TOOL`／`ESTOP`／`MODE`／`-`）。'
     u"本格那句\u201c只能按编码层事实旁证\u201d作废（原文不删）：MANUAL 那一拍线上是不是只有心跳，"
     u'从今天起是**字节级证据**。`-` = 这一拍确实一个字节都没走（ESTOP 稳态、回放模式都是），'
     u'**不是缺数据**。判据本身一个字没改。',
     u'已补入口（未台架）'),
    (u'| C6 ', C_TABLE_PIPES,
     u'🟢 **10-12 已补入口（未台架）**：`python -B tools/link_probe.py mode_teleop` 发得出 '
     u'`MODE(0x02)` 了（档案号仍只从 yaml 取，命令行给参数当场拒）。本格那句"今天没有入口"'
     u'作废（原文不删）。**`reject=0x06` 只证明 MODE 进了分派 + 未实现通路诚实，'
     u'不等于 TELEOP 可用**（实现属批 2）；未烧批 1a 时探针会把这一格压成 INCONCLUSIVE，'
     u'不会给你一个假 PASS。',
     u'已补入口（未台架）'),
    (u'| C10 场景 ', C_TABLE_PIPES,
     u'🟢 **10-12 已补入口（未台架）**：握手现在有两个入口——`link_probe mode_profile`'
     u'（不 bind 9100，可与正在收 STATUS 的程序并存）与 `bench_status !profile`'
     u'（不能与 `pc/main.py` 同时开）；造"档案故意不一致"仍然靠**改 yaml 一行**，'
     u'本设计明确否决了 `--force-profile` 旗标（多一条只在这种场合用的路径 = 多一个'
     u'没上台架的怀疑点）。'
     u'🔴 **同一批把硬性收尾写进正文而不是注释**：本格做完必须**把 `profile_id` 改回 1**、'
     u'**再握手一次**确认 `reject` 回 0，并把改回后的 yaml 那一行**念出声**（现场最容易省的就是这步）。'
     u'忘改回的症状**长得完全不像人造成的**：之后每次开机握手都失败，而第一个怀疑方向是板子。',
     u'已补入口（未台架）'),
    (u'| C13 场景 ', C_TABLE_PIPES,
     u'🟢 **10-12 已补入口（未台架）**：档案握手不再需要"关掉这个程序、开那个程序"——'
     u'`link_probe mode_profile` 不 bind 9100，能与正在收 STATUS 的程序并存；'
     u'`bench_status` 也可用 `!profile` 自己发自己记。本格判据（NAV(0,0)+TOOL 提刀仍在发、'
     u'`mode` 仍是 AUTO、不得出现 HEARTBEAT）一个字没改。',
     u'已补入口（未台架）'),
    (u'| C14 场景 ', C_TABLE_PIPES,
     u'🟢 **10-12 已补入口（未台架）**：同 C13——握手有两个入口，不必为补一次握手来回开关程序。'
     u'本格的**信号级**限制不变（无执行元件时"横移不动"是恒真命题，不许勾通过）。',
     u'已补入口（未台架）'),
    (u'| C18 场景 ', C_TABLE_PIPES,
     u'🟢 **10-12 已补入口（未台架），判据改成两遍跑**：窗 2 那一路"还在发 NAV+TOOL"现在有两处证据——'
     u'`link_probe` 自己的 `#n -> …` 发送行，**以及** 窗 1 `run_log.csv` 的 `tx_frames` 列。'
     u'⚠️ 两半**不能同在一遍里取**：`pc/main.py` 与 `tools/bench_status.py` 都**独占绑 UDP 9100**'
     u'（09-22 实测 Windows 上 `SO_REUSEADDR` 会"bind 成功但包只给先绑上的那个"，所以这里故意不用它），'
     u'同一时刻只能开一个 ⇒ **跑两遍**：第一遍 `pc/main.py` 记 `state` + `tx_frames`，'
     u'第二遍 `bench_status` 记 STATUS 的 `mode`/`authority`/`reject`，**按两张表自己的绝对时间戳人工对齐**'
     u'（不做跨进程自动对齐：那会引入一个新的、没上台架的解释层）。'
     u'`link_probe` 不 bind，所以它是唯一能与窗 1 并存的那一路。',
     u'判据改成两遍跑'),
    (u'| C19 场景 ', C_TABLE_PIPES,
     u'🟢 **10-12 已补入口（未台架）**：进无人要的那次握手现在能就地补（`link_probe mode_profile`，'
     u'或 `bench_status !profile`），不必为它单开一次 `pc/main.py`。本格判据与"只能看轮子"那句照旧。',
     u'已补入口（未台架）'),
    (u'| C20 ', C_TABLE_PIPES,
     u'🟢 **10-12 已补入口（未台架）**：`run_log.csv` 的 `tx_frames` 列把本格最关键的那半句'
     u'"PC 确实发了 NAV(0,0)"从旁证升成**表里的记录**（按 `send()` 出口记账，回放模式记 `-`）。'
     u'另一半"板子不进 AUTO"仍读 `mcu_mode`/`authority`。判据一字未改。',
     u'已补入口（未台架）'),
    (u'| C21 按下 ', C_TABLE_PIPES,
     u'🔴 **10-12 把前置提到第 0 条：C11 必须先过**。C11 没真验过 `MODE(0x10)` 之前，'
     u'D1 每轮的固有静默一旦让桥注了 ESTOP 就**只能断电**——`[M]`、`!clear`、`link_probe clear` '
     u'三条都走 TYPE_MODE，在未烧批 1a 的板上整条丢掉（这条 10-12 起也进了 '
     u'`tools/latency_probe.py` 的开工打印，不再只在注释里）。'
     u'握手那半程的前置 ② 也松了：可用 `link_probe mode_profile` 就地补（它不 bind 9100，'
     u'能与 latency_probe 的监听并存），不必"先开 main.py 再关掉"。',
     u'C11 必须先过'),
    (u'| **没有能单发 ', E_TABLE_PIPES,
     u'🟢 **10-12 已补（未台架）**：`link_probe mode_profile` / `mode_teleop` 与 '
     u'`bench_status !profile`。本行那句"唯一发得出握手的是 `pc/main.py`"从此只在'
     u'"既要收 STATUS 又不肯开记录器"那一种场合成立。',
     u'10-12 已补（未台架）'),
    (u'| **`run_log` / `bench_log` 没有', E_TABLE_PIPES,
     u'🟢 **10-12 已补前半（未台架）**：`run_log.csv` 有 `tx_frames` 列了（发送侧、字节级）。'
     u'`bench_log.csv` 照旧不加列——它自己发的帧已经有 `kind=tx_*` 行，缺的只是"PC 做发送方"的'
     u'记录，那是 `run_log` 的职责。本行的"靠编码层语义旁证"对 C2/C18 已过期。',
     u'10-12 已补前半'),
    (u'| **C21 的 D1 测法', E_TABLE_PIPES,
     u'🟢 **10-12 已把这句话固化成开工打印**：`estop_caution()` 在 D1 会静默的那一跑多打一行，'
     u'明写"未烧批 1a 时 `[M]`／`!clear`／`link_probe clear` 三条都救不了、只能断电"。'
     u'本行的"要 C11 先过"不变，Pc-9 那个口子也不变。',
     u'10-12 已把这句话固化成开工打印'),
    (u'| C8 门 N 拒落刀', C_TABLE_PIPES,
     u'⚪ **10-12 登记裁定，本格仍未补**：本设计**明确不做** `--force-profile` 一类的注入旗标'
     u'（spec §1），合法入口仍是"临时把 yaml 的 `permit` 改 `gate_f`"那一条，'
     u'而那等于主动打开唯一那道 PC 闸门 ⇒ **待作者裁定**，不许因为"顺手就能加"就把它做完。',
     u'登记裁定'),
]


def main():
    lines = io.open(PATH, encoding='utf-8').read().split('\n')
    done, skipped = [], []
    for prefix, pipes, text, marker in APPENDS:
        hit = [i for i, ln in enumerate(lines)
               if ln.startswith(prefix) and ln.count(u'|') == pipes]
        if len(hit) != 1:
            raise SystemExit('%s matched %d rows with %d pipes, want exactly 1 '
                             '— nothing written' % (prefix, len(hit), pipes))
        i = hit[0]
        ln = lines[i]
        if not ln.endswith('|'):
            raise SystemExit('%s line %d does not end with a pipe — refusing'
                             % (prefix, i + 1))
        if marker in ln:
            skipped.append(prefix.strip())
            continue
        lines[i] = ln[:-1].rstrip() + u' ' + text + u' |'
        done.append('%s:%d' % (prefix.strip(), i + 1))
    with io.open(PATH, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines))
    print('appended %d, already-there %d' % (len(done), len(skipped)))


main()
```

- [ ] **Step 2: 跑脚本**

Run: `python -B .superpowers/sdd/2026-10-12-bench-readiness-sync/append_cell.py`
Expected: `appended 14, already-there 0`（C8 那格是"登记裁定"，不是补工具）。任何 `SystemExit` 都**不许绕过**——它说的是"这一行的形状我读不出来"，那就改用 Edit 工具按该行原文手工追加，并回头修正脚本里的前缀。
Run: `python -B .superpowers/sdd/2026-10-12-bench-readiness-sync/append_cell.py`（**再跑一次**）
Expected: `appended 0, already-there 14` —— 这条同时证明"重跑不会追加两遍"，因为现场真会重跑。

- [ ] **Step 3: 机检八格 + 不许留悬置**

Run（先 Write 成 `.py` 文件再执行，别把中文塞进 `bash -c`）：

```python
# -*- coding: utf-8 -*-
import io
import sys

PATH = u'docs/X5验机与接入执行清单.md'
WANT = [u'C2 场景 ', u'C6 ', u'C10 场景 ', u'C13 场景 ', u'C14 场景 ',
        u'C18 场景 ', u'C19 场景 ', u'C20 ']
lines = io.open(PATH, encoding='utf-8').read().split('\n')
bad = []
for w in WANT:
    # 前缀 + 竖线数两个条件都要：`| C6 ` 与 `| C20 ` 在 §D 回填表里各有一条同前缀短行
    hit = [ln for ln in lines
           if ln.startswith(u'| ' + w) and ln.count(u'|') == 7]
    if len(hit) != 1:
        # 匹配到 0 行**不是**通过。AGENTS 第 2 条 b) 项：先怀疑自己写错了。
        bad.append('%s -> 匹配 %d 行（要 1 行）' % (w, len(hit)))
        continue
    ln = hit[0]
    fresh = max(ln.rfind(u'已补入口（未台架）'), ln.rfind(u'两遍跑'))
    stale = ln.rfind(u'待补工具')
    if fresh < 0:
        bad.append('%s -> 最后一列没有 10-12 的那句' % w)
    elif stale > fresh:
        bad.append('%s -> "待补工具"还压在 10-12 那句后面（顺序反了）' % w)
print('cells checked=%d  violations=%d' % (len(WANT), len(bad)))
for b in bad:
    print('  ', b.encode('unicode_escape').decode())
sys.exit(1 if bad else 0)
```

**判据的形状要说清**：spec §2 第 4 条那句"不留'需补工具'这种已经过期或已完成的悬置"，按本仓"就地追加、原文不删"的规矩实现成**位置判据**——10-12 那句必须出现在旧的"待补工具"**之后**（同一格、同一列），旧原文照留。⚠️ 如果有人为了让这条变绿而把旧句子删掉，那是"为了让检查变绿而改内容"，本仓明令禁止（AGENTS 第 2 条的判读纪律 + 台账的撤回留痕规矩）。

Expected: `violations=0`、退出码 **0**。

- [ ] **Step 4: 表格与文档不变量**

Run: `python -B tools/check_doc_invariants.py` → 退出码 **0**（本任务不许新增任何"圈号+短横+圈号"的记法；脚本里的文案已按这条写）。
Run: `python -B -m pytest tests/ -q -p no:cacheprovider` → 全量 0 failed / 0 error（本任务只动 md，读数应与 Task 4 收尾那次一致）。

- [ ] **Step 5: 提交**

```bash
git add docs/X5验机与接入执行清单.md
git commit -F- --cleanup=verbatim <<'EOF'
§4B 八格前置栏就地改判 + C21 提到"C11 必须先过" + §E 三行登记已补

工具补上了，前置栏还写着"待补工具 / 今天没有入口"就是第二类债：
下一批人看不见它们已经不再是缺口，而把"未台架"读成"没做"。
八格（C2／C6／C10／C13／C14／C18／C19／C20）一律改成
"已补入口（未台架）"或"两遍跑 + 人工对齐"，原文一句不删。

两处刻意留在纸面上的东西：
- C10 的硬性收尾写进正文而不是注释：忘改回 profile_id 的症状长得完全
  不像人造成的（之后每次开机握手都失败，第一个怀疑方向是板子）。
- C18 写明"为什么两半不能同在一遍里取"：pc/main.py 与 bench_status 都
  独占绑 9100（09-22 实测 SO_REUSEADDR 会 bind 成功但包只给先绑上的那个），
  所以跑两遍、按各自绝对时间戳人工对齐；不做跨进程自动对齐——那会引入
  一个新的、没上台架的解释层。

C8 只登记裁定不做工具（--force-profile 已被否决）；§E 三行写明"已补"的
边界（tx_frames 只补了发送侧、bench_log 照旧不加列；Pc-9 的口子不变）。

检查：追加脚本重跑一次给 appended 0（幂等），八格机检 violations=0，
check_doc_invariants 退出码 0，pytest 当场全量通过（条数以那条命令的输出为准）。
EOF
```

---

### Task 6: 六处文档同步里剩下的四处（缺口清单 / AGENTS / README）

**Files:**
- Modify: `docs/缺口清单.md`（`:9` 标题 + `:12` 口径行、`:80`／`:225`／`:423` 三处日期、`③` 板 B 类末尾三条）
- Modify: `AGENTS.md`（`:56` 的 ③ 段日期形状、② 段加 §4B 指针——**同一段其余字符不动**）
- Modify: `README.md`（`bench_status.py` 那一行末尾加指针与 `!profile`）

**Interfaces:** 无。产出是 spec §2 第 3 条能被 grep 机检的形状。

- [ ] **Step 1: 逐锚点确认唯一性（动手之前）**

Run：把下面这个小检查 Write 成 `.py` 再执行（Global Constraint 9）。
Expected: 每条命中数都是 **1**。任何一条不是 1 就停下来改锚点，不许"就近改第一处"。

```python
# -*- coding: utf-8 -*-
import io

CHECKS = [
    (u'docs/缺口清单.md', u'## 📊 总览：做完的 / 没做的（2026-09-22 快照，qoder HEAD `1c9bdea`）'),
    (u'docs/缺口清单.md', u'> 测试通过条数、"Keil 0 错误"、159 这个数字本身'),
    (u'docs/缺口清单.md', u'- **C1 秋采（10 月中前，全局最紧）**'),
    (u'docs/缺口清单.md', u'### C1. 秋季图像采集（**时间最紧，10 月中前必须完成**）'),
    (u'docs/缺口清单.md', u'### H1. 🔴 数据资产安全（秋采 10 月中开拍前必修）'),
    (u'docs/缺口清单.md', u'**C. 等对侧（zcode）**'),
    (u'AGENTS.md', u'**③C1 秋采最紧（10 月中前）**'),
    (u'AGENTS.md', u'②**编译门槛已过 ⇒ B1 烧录 + B2 对拍（含 SBUS 失联两子情形）可做**'),
    (u'README.md', u'开机那行会把 permit 印出来。 |'),
]
ok = True
for path, needle in CHECKS:
    n = io.open(path, encoding='utf-8').read().count(needle)
    print('%d  %s  %s' % (n, path, needle[:40]))
    ok = ok and n == 1
print('ALL UNIQUE' if ok else 'FIX ANCHORS')
```

- [ ] **Step 2: 缺口清单的标题行与口径行（一次 Edit，两格连着改）**

`old_string`（`:9-12` 那四行原文，逐字）：

```
## 📊 总览：做完的 / 没做的（2026-09-22 快照，qoder HEAD `1c9bdea`）

> **口径**（AGENTS 审查清单第 5 条）：已设计 ≠ **已编码** ≠ **已编译** ≠ **已台架** ≠ **已田间**，逐态分列。
> 测试通过条数、"Keil 0 错误"、159 这个数字本身，**都只证明编码/编译层无回归**，不构成台架或田间证据。
```

`new_string`：

```
## 📊 总览：做完的 / 没做的（2026-10-12 逐格复核）

> **口径**（AGENTS 审查清单第 5 条）：已设计 ≠ **已编码** ≠ **已编译** ≠ **已台架** ≠ **已田间**，逐态分列。
> 当场输出的测试条数、警告数、Code 尺寸，**都只证明编码/编译层无回归**，不构成台架或田间证据。（AGENTS 审查清单第 8 条。这一句原先举着某个具体的测试条数——那个数抄进来那一刻就变成待检查内容了，10-12 摘掉；现行基线唯一一处写在 `AGENTS.md`『当前状态』，编译读数唯一一处写在台账 §4。）
> **标题里的日期只说明"这块板最后一次逐格复核是哪天"，不代表每一格都停在那一天**：每格现状以该格自己的续写日期为准，别拿本标题当全局状态。（原标题还带着一个 qoder HEAD 哈希，10-12 起删掉——哈希属基线类数字，抄进来就变成待检查内容。）
```

- [ ] **Step 3: 三处"10 月中"统一成硬时限 2026-10-15**

三处分别 Edit（`old_string` 用 Step 1 里验过的那三条原文)：

`:225`：
```
### C1. 秋季图像采集（**硬时限 2026-10-15；10-12 复核：剩 3 个白天**）
```
`:80`（只替换行首那半句，行内其余内容不动；注意**粗体不许嵌套**，所以括号里的日期不再另开一对 `**`）：
```
- **C1 秋采（硬时限 2026-10-15，全局最紧；10-12 复核剩 3 个白天，时限出处 = `docs/秋季图像采集清单.md` 自己写的那个日期）**：
```
`:423`：
```
### H1. 🔴 数据资产安全（秋采 2026-10-15 开拍前必修）
```

- [ ] **Step 4: 缺口清单 ③ 板 B 类新增 T1／T2／T3 三条**

插到 `**C. 等对侧（zcode）**` 之前（`old_string` 就是那一行，`new_string` = 三条 + 那一行）。每条四要素齐全：现状 / 卡住 §4B 哪几格 / 补法一句话 / 本设计后的状态。

```
- **T1（10-12 出设计并已编码）台架缺"档案握手／TELEOP 的发送入口"**：`tools/link_probe.py` 原来只有 `mode_auto`／`mode_manual`／`clear` 三条 MODE，`tools/bench_status.py` 的 stdin 同族也没有 `!profile` ⇒ `MODE(0x20)` 与 `MODE(0x02)` 在台架上**一个合法入口都没有**。卡住的是 §4B 的 C6（整格无法触发）与 C13／C14／C18／C19／C20／C21（凡"申请无人"都得先有握手，而握手位是 RAM 位、MCU 一复位就清零，唯一发送者是 `pc/main.py` 的开机那一拍 ⇒ 台架上要来回开关程序）。补法 = 两条命令进既有的 `MODE_REQUEST_KINDS` 那一族（**不开新的参数通道**：档案号仍只从 `config/vehicle_profile.yaml` 取，命令行给参数当场拒），记录器加 `!profile`。"档案故意不一致 ⇒ `reject=0x01`"那一格（C10）**不做旗标**——作者 10-12 裁定否决 `--force-profile`：改 yaml 一行 + 重启就造得出不一致，而多一条只在这种场合用的路径 = 多一个没上台架的怀疑点；作为交换，"改回 `profile_id: 1`"写成 §4B 正文里的硬性收尾。→ **已编码 + 已单测，未台架**。
- **T2（同上）`run_log.csv` 没有"这一拍 PC 发的是哪种帧"这一列**：§4B 的 C2 那句"线上只有 HEARTBEAT"、C18 那句"交回之后 PC 还在发"只能按 `wire.frames_for_state()` 的编码层语义**旁证**，不是字节级证据。补法 = 在 `send()` 的出口记账、`RUN_LOG_COLUMNS` **末尾**追加 `tx_frames`（帧型串 `NAV+TOOL`／`HB`／`ESTOP`／`MODE`／`-`；`-` = 这一拍确实一个字节都没走，不是缺数据）；`bench_log.csv` **不加列**（它自己发的帧已经有 `kind=tx_*` 行）。位置契约由 `tests/test_wire.py` 里"加列前的列名快照"钉死。→ **已编码 + 已单测，未台架**；C2／C18 取证要**跑两遍 + 人工对齐**（9100 独占绑定，理由见 §4B 的 C18）。
- **T3（同上）"D1 每轮自带 >500 ms 静默、而锁存清不掉"只活在注释里**：`tools/latency_probe.py` 的 `estop_caution()` 说清了"会锁存"，没说 `[M]`／`!clear`／`link_probe clear` 三条在**未烧批 1a 的板上都发的是同一个会被整条丢掉的 TYPE_MODE**，只能断电——而台架上没人翻源码，后果却是现场动作。补法 = 同一个分支里多打一行（纯 ASCII，进既有静态扫描）。措辞留一条边界：烧了批 1a 之后 `MODE_REQ_CLEAR_ESTOP` 只是"coded to clear"，**能不能清要等 §4B 的 C11 真过**。→ **已编码 + 已单测，未台架**。
```

- [ ] **Step 5: `AGENTS.md:56` 只改两个小片段**

5a. ③ 段：`**③C1 秋采最紧（10 月中前）**` → `**③C1 秋采最紧（硬时限 2026-10-15；10-12 复核剩 3 个白天）**`。
5b. ② 段：在 `这是 H2 从「已编码」到「已台架」的唯一途径；` 之后插入 `逐格清单见 `docs/X5验机与接入执行清单.md` §4B（17 格：格号／触发／看哪里／算过／不算过／前置）；`。
5c. **两处之外一个字符不动**：那一行里 ⑥ 段、四态口径、硬禁令、"警告数不是签名"那几段全部原样留着；审查清单第 2 条所在的行块不碰。

- [ ] **Step 6: `README.md` 的 `bench_status.py` 行**

`old_string` = `开机那行会把 permit 印出来。 |`（Step 1 已验唯一）
`new_string` =

```
开机那行会把 permit 印出来。**10-12 加**：stdin 另有一条 `!profile`（发 `MODE(0x20)` 档案握手，档案号仍只从 `config/vehicle_profile.yaml` 取、带参数就拒），用途是**不重启 `pc/main.py` 也能重放握手**。⚠️ 本工具与 `pc/main.py` **都独占绑 UDP 9100**（09-22 实测 Windows 上 `SO_REUSEADDR` 会"bind 成功但包只给先绑上的那个"，所以这里故意不用它），同一时刻只能开一个；`tools/link_probe.py` 的发送**不 bind**，是唯一能与本工具并存的那一路。台架那 17 格的逐格判据与这条互斥关系写在 `docs/X5验机与接入执行清单.md` **§4B**。 |
```

- [ ] **Step 7: grep 判据（spec §2 第 3 条）**

Write 成 `.py` 再跑：

```python
# -*- coding: utf-8 -*-
import io
import sys

PATHS = [u'docs/缺口清单.md', u'AGENTS.md', u'README.md',
         u'docs/X5验机与接入执行清单.md']
SHAPES = [u'10 月中', u'1c9bdea']
bad = []
for p in PATHS:
    t = io.open(p, encoding='utf-8').read()
    for s in SHAPES:
        if s in t:
            bad.append('%s 仍含 %r' % (p, s))
print('violations=%d' % len(bad))
for b in bad:
    print('  ', b)
sys.exit(1 if bad else 0)
```

Expected: `violations=0`、退出码 0。⚠️ 若 `docs/X5验机与接入执行清单.md` 里那处"10 月中"来自别的历史登记（不是时限），**不要为了变绿而删它**——那说明判据写宽了，按 AGENTS 第 2 条 b) 项的规矩先解释命中，再决定是改文档还是改判据（改判据必须附理由）。

- [ ] **Step 8: 跑两条检查**

Run: `python -B tools/check_doc_invariants.py` → 退出码 **0**。
Run: `python -B -m pytest tests/ -q -p no:cacheprovider` → 全量 0 failed / 0 error。

- [ ] **Step 9: 提交**

```bash
git add docs/缺口清单.md AGENTS.md README.md
git commit -F- --cleanup=verbatim <<'EOF'
状态文档同步：总览板摘掉哈希与抄来的测试数、三处"10 月中"落到 10-15、§4B 两处指针、③-B 登记 T1/T2/T3

这块板是"唯一欠账台账"，它往回拉的时候下一批人会把"未台架"读成"没做"，
而把秋采时限读成"10 月中前"这种没有日子、也没有剩几天的说法——今天 10-12，
时限是 10-15。

四处形状改动：
- 总览标题从"09-22 快照 + 一个 HEAD 哈希"改成"10-12 逐格复核"，并写明
  标题日期只管"这块板最后哪天逐格核过"，每格现状以它自己的续写日期为准；
  哈希删掉属基线类数字（AGENTS 审查清单第 8 条），口径行原来举着的那个
  测试数同样摘掉——现行基线唯一一处仍在 AGENTS『当前状态』，编译读数在台账 §4。
- 三处"10 月中"统一成 2026-10-15，并带"剩 3 个白天"这个当场判断。
- AGENTS 与 README 各加一个指向 §4B 的指针：人在板子边上先翻的是这两份，
  那张 17 格表此前只有缺口清单引到。AGENTS 只动 :56 里 ③／② 两个小片段，
  同一段其余字符一个没改。
- ③-B 补 T1／T2／T3 三条登记（现状／卡住哪几格／补法／本设计后状态），
  三条都写"已编码 + 已单测、未台架"。

本批不动 firmware/、不动台账、不预勾任何一格台架结论；两条硬禁令继续生效。

检查：九条锚点逐条唯一性先验后改；grep 判据 violations=0（10 月中与那个哈希
四份文档零命中）；check_doc_invariants 退出码 0；pytest 当场全量通过
（条数以那条命令的输出为准，AGENTS 审查清单第 8 条）。
EOF
```

---

### Task 7: 收口验证与交接（不新增功能）

**Files:**
- Modify: `docs/缺口清单.md`（只在 ③-B 的 T1/T2/T3 三条末尾把"未台架"补成"未台架（第一晚跑哪三格见 §5）"这类**已有形状**的指向；不新增数字）
- Delete: `.superpowers/sdd/2026-10-12-bench-readiness-sync/` 里的临时脚本与文案文件

**Interfaces:** 无。

- [ ] **Step 1: 逐条对 spec §2 的六条机检判据**

Write 成 `.py` 执行，**每条都要打印命中数**（零命中必须给出解释，AGENTS 第 2 条 b) 项）：

```python
# -*- coding: utf-8 -*-
import io
import re
import sys

def read(p):
    return io.open(p, encoding='utf-8').read()

w = read('pc/wire.py')
lp = read('tools/link_probe.py')
tw = read('tests/test_wire.py')
tp = read('tests/test_link_probe.py')
x5 = read(u'docs/X5验机与接入执行清单.md')

# 第 4 条判据的本体：八格各匹配 1 行，匹配不到就先报错、不许当成通过
# （AGENTS 第 2 条 b) 项："什么都没匹配到"是需要解释的结果，不是通过标志）。
EIGHT = [u'C2 场景 ', u'C6 ', u'C10 场景 ', u'C13 场景 ', u'C14 场景 ',
         u'C18 场景 ', u'C19 场景 ', u'C20 ']
rows = []
for w_ in EIGHT:
    hit = [ln for ln in x5.split('\n')
           if ln.startswith(u'| ' + w_) and ln.count(u'|') == 7]
    assert len(hit) == 1, (w_.encode('unicode_escape').decode(), len(hit))
    rows.append(hit[0])
eight_ok = all(max(ln.rfind(u'已补入口（未台架）'), ln.rfind(u'两遍跑'))
               > ln.rfind(u'待补工具') for ln in rows)

checks = [
    (u'1 判据：pytest 由 Step 2 那条命令给，不在这里判', True),
    (u'2 判据：check_doc_invariants 由 Step 3 那条命令给，不在这里判', True),
    (u'3 判据：三份文档不含"10 月中"与那个哈希形状（Task 6 Step 7 已跑）',
     (u'10 月中' not in read(u'docs/缺口清单.md')
      and u'10 月中' not in read('AGENTS.md')
      and u'10 月中' not in read('README.md'))),
    (u'4 判据：§4B 八格的最后一列不留"待补工具 / 今天没有入口"这种已完成或已过期的悬置',
     eight_ok),
    (u'5 判据：wire 有测试钉住 tx_frames 追加在末尾、前面各列下标不变',
     (u'tx_frames' in w and u'_PRE_TX_FRAMES_COLUMNS' in tw
      and u'RUN_LOG_COLUMNS[-1]' in tw)),
    (u'6 判据：link_probe 两条新命令有"上线字节"级断言（不是函数被调用级）',
     (u'mode_profile' in lp and u'mode_teleop' in lp
      and u'P.MODE_REQ_PROFILE' in tp and u'P.MODE_REQ_TELEOP' in tp
      and u'unpack_mode(payload) == (want, 2)' in tp)),
]
bad = [n for n, ok in checks if not ok]
print('judged=%d violations=%d' % (len(checks), len(bad)))
for n in checks:
    print('  %s %s' % ('OK ' if n[1] else 'BAD', n[0].encode('unicode_escape').decode()))
sys.exit(1 if bad else 0)
```

**这条脚本自己的两条使用边界**：① 第 1、2 条判据是"由那两条命令当场给"，所以在这里恒真——恒真的格子留在表里是为了让六条一眼看全，不许把它读成"已经验过"；② 第 6 条找的是 `unpack_mode(payload) == (want, 2)` 这一行，也就是 Task 2 Step 1a 那张参数化表里的**字节断言**，判据要的是"断言落在上线字节上"，不是"某个函数存在"。它红了先去看那张表是否被改坏，**不要**放宽这条判据。第 4 条若 `assert` 直接炸（某格匹配不到 1 行），那是 Task 5 的前缀写错了，同样按"零命中先怀疑自己"处置。

- [ ] **Step 2: 全量测试**

Run: `python -B -m pytest tests/ -q -p no:cacheprovider`
Expected: **0 failed / 0 error**；条数以这条命令的当场输出为准，**不抄进任何文档**（AGENTS 审查清单第 8 条）。与 Task 4 收尾那次相比只该多不该少；若**少了**，先怀疑测试被误删或被 skip，不要先怀疑计数。

- [ ] **Step 3: 文档不变量**

Run: `python -B tools/check_doc_invariants.py`
Expected: 退出码 **0**；受保护记号的命中数等于工具自己声明的基线（数值以这条命令的输出为准，本计划正文不抄——Global Constraints 第 6 条）。退出码 2 = 漂移，必须解释"是加对了还是改错了"，**禁止为变绿改基线**。退出码 3 = 有 md 读不进去——先清理 `.superpowers/` 草稿目录里可能存在的非 UTF-8 临时文件（Step 5）。

- [ ] **Step 4: 工作树自查**

Run: `git status --porcelain | head -40`
Expected: 只剩作者自己那些项（`docs/组会汇报_20260916/**` 删除、`docs/组会汇报_20260923/`、`results/**`、`scan_result.txt`、三个 Keil 脏项）。本批五个代码文件、四个测试文件、四份文档都应已提交、不出现在列表里。
Run: `git log --oneline -8`
Expected: 七条本批提交在顶部，标题各不相同且各自描述本次改动（本仓有 6 次复制标题的事故——扫一眼确认没重复）。

- [ ] **Step 5: 清草稿 + 交接口径**

```bash
rm -rf .superpowers/sdd/2026-10-12-bench-readiness-sync
git status --porcelain | head -5
```

向作者报告（正文形式，不建文件）：
- 本批 HEAD 与七条提交（`git log --oneline -8` 的当场输出）；
- **动过什么**：`pc/wire.py`、`pc/main.py`、`tools/{link_probe,bench_status,latency_probe}.py`、对应四个测试文件、`docs/{缺口清单,X5验机与接入执行清单}.md`、`AGENTS.md`、`README.md`；
- **没动什么**：`firmware/` 一行未动、Keil 未重编译、台账 §4 与 Fw-14／Fw-17／Fw-21／Fw-22／Pc-8 那五行原样（批 1a Task 8 已改判过）、两条硬禁令继续生效、**没有一格台架结论被预勾**；
- 四态口径：本批全部只到「已编码 + 已单测」与「已文档化」；
- 下一步归作者：10-13／10-14 白天秋采（10-15 硬时限），当晚哪一晚做第一次台架由他定，**只跑三格**（B1 烧录 + 认版四样一起看、档案握手成功、`loop_alive` 持续在变），并预期"卡在 X5 的 `start_bridge.sh`"（该脚本从未真跑过）——那是排障不是测试，不许写成机制结论；顺手两件：B3 油门三位置 `ch[4]` 读数、下田那趟带横断面 + M3／M14／M15 + 四轮方向重测（先拨一下杆）。

- [ ] **Step 6: 提交（若 Step 1/4 产生了文档侧的收尾改动）**

```bash
git add docs/缺口清单.md
git commit -F- --cleanup=verbatim <<'EOF'
收口：T1/T2/T3 三条登记各指一次第一晚的三格，不留"补完就完事"的读法

本批代码与文档都只到「已编码 + 已单测 / 已文档化」，三条登记的"未台架"
要把读者送到 §4B 的第一晚那三格上，否则"工具补好了"会被读成"台架就绪了"。

检查：spec §2 六条判据逐条实跑（含"零命中要先解释"的那一步）；
pytest 与 check_doc_invariants 的读数一律以当场命令输出为准，本仓现行
测试基线仍只写在 AGENTS『当前状态』那一行（AGENTS 审查清单第 8 条）。
EOF
```

若 Step 1/4 没有产生需要提交的改动，**不要造空提交**——跳过这一步并在报告里写明"收口未产生新改动"。

---

## 自检（写完后按 spec 反查一遍）

1. **spec 覆盖**：§3 六处 → Task 5（§4B 前置栏那条属 §1"做"的第三条）+ Task 6 的 Step 2/3/4/5/6；§4 T1 → Task 2 + Task 3 + Task 5 的 C6／C10／C13／C14／C19／C21；T2 → Task 1 + Task 5 的 C2／C18；T3 → Task 4 + Task 5 的 C21／§E 第三行；§2 六条判据 → Task 7 Step 1；§7 测试设计 → Task 1 Step 1、Task 2 Step 1、Task 3 Step 1、Task 4 Step 1；§1"明确不做"四条 → 分别落在 Global Constraints 1／2、Task 3 的接口（不加自动对齐）、Task 2 的 Step 3f（不改握手语义、闸门位置）、Task 5 的 C8（不做旗标）。
2. **占位符扫描**：全文没有 TBD／待补／"类似 Task N"；每个代码步都给完整片段与真实锚点行号。
3. **类型一致性**：`tx_frames_text(ftypes) -> str`（Task 1 Step 3b 定义 = Step 1 断言 = Step 4d 调用）；`check_mode_args(kind, args)`（Task 2 Step 3f 定义 = Step 1b 调用）；`_judge_new_mode(kind, baseline_mode, seen_modes, rejects)` 收**已过滤过的**非零 reject 列表（Step 3e 传 `[c for c in reject_codes if c]`，与 Step 1b 直接用 `[P.REJECT_PROFILE]` 一致）；`'tx_profile'` 既是 `build_command` 返回的 kind，也是 `TX_MODE_KINDS` 的成员（Task 3 Step 3a/3b）。
