# -*- coding: utf-8 -*-
"""PC 侧发送工具共用的**台架安全限值**（单一事实源，AGENTS 审查清单第 6 条）。

为什么要有这个文件：现在能往大板发帧的 PC 侧入口是三个共用的调用点——`tools/link_probe.py`
（命令行探针）、`tools/bench_status.py --to`（记录器的 opt-in 发送面）与
`tools/latency_probe.py`（D2 的阶跃，`measure_d2()` 用同一个谓词判 `step_v`）。三者走的是
同一个 `bridge:9000`，同一块板子，所以限速这条安全不变量只能有一份：各写一个字面量，
下一次就是改了一份没改另一份，而"哪个闸生效"这种事没人会在台架上重新验一遍。

限速的理由（这些是**代码事实**，不是推测，出处都标着）：
  · 现在烧在板上的固件里，一条 NAV 就是进 AUTO 的钥匙（**10-10 批 1a Task 8 定身份**：
    下面那三个行号属**板上那一版**，写作 `f0ecf73:firmware/retrofit.c`——`firmware/` 根下那份
    影子副本已由批 1a Task 6 删除（`da053de`），裸路径今天**不可解析**；正身
    `firmware/大车proj/大车/HARDWARE/retrofit/retrofit.c` 的同一行号已落到 `TYPE_MODE` 分派上，
    把行号照抄过去会读到完全不同的语句）：
    `f0ecf73:firmware/retrofit.c:93` `if (len < 9 || estop_latched) return;` → `:98-101` 把
    `cmd_vl`/`cmd_vr` 钳到 **±1.0 m/s** → `:102` `mode = MODE_AUTO;`
    （批 1a 的 F1 修法正是把这一支拆掉：**10-10 已编码 + 已编译**——正身 `:131-151` 的 NAV 分支
    不再写 `mode`，那段注释自己写着 closes F1——但**未烧录** ⇒ 板上仍是上面这个语义）；
  · 行走侧有斜率限制 `SLEW_ACC = 0.2 m/s²`（`f0ecf73:firmware/retrofit.c:140`；正身里同一条
    `#define SLEW_ACC` 在 `:289`，值未变），所以
    "钳到 ±1.0"不等于安全——一条 0.9 的命令约 4.5 秒后**真的**把车推到 0.9 m/s。
    一台 2.15 m 宽、带着刀和滑台的机器在台架上跑 0.9 m/s，不需要更多形容词。

结论：这三个手动发送器都把 NAV 硬拦在 0.20 m/s，超限**拒发**（不是"发个 0 试试"），
并且当场把拒了这件事打在屏幕上。这几个工具不是行车工具——要跑闭环请用 `pc/main.py`；
但**别把它读成"走 `main.py` 就自动受这个闸保护"**：闭环每拍也发 NAV，它的限速来自
`pc/control.py:92` 的 `v_max=0.2`——**同一个数值、另一个出处**（控制律的限幅，不是这道闸）。
两条不合并是有理由的：`v_max` 是控制量，改了它会同时改掉控制律的整定与判据；这个数是
台架准入线，改了它只影响手动工具敢发多快。要真让它们共用一个源，属批 2 控制律的事，
现在先把关系写明（AGENTS 清单第 6 条：不许让"哪个数生效"靠猜）。
"""

import math

from pc import wire

# 台架 NAV 限速（m/s）：三个手动发送器共读这一个数（闭环的限速是另一个出处，见上面）。
NAV_BENCH_LIMIT_MPS = 0.20

# `struct.pack('<f', x)` 装不下的数会抛 `struct.error`/`OverflowError`——
# 上面那道闸把"装不上线的数"也算成超限，所以要知道上线值域的边界是多少。
_F32_MAX = 3.4028234663852886e38

# 门 N 的刀位（bit0-2 = beam 1-3 全提）。这里**不另立一份口径**：闭环那一头的强制
# 写在 `pc/wire.py:91-95`（GATE_N 下 `off=0.0, lift=0x07`），`tests/test_bench_status.py`
# 里那条一致性断言把两边钉在一起——`frames_for_state` 改了这里就得跟着红。
_GATE_N_LIFT = 0x07
_GATE_N_OFFSET_MM = 0.0


def _number_or_none(v):
    """收成**可上线的有限 float**；不是数字、非有限、装不进 f32 ⇒ None。

    只认 int/float（`bool` 也不算数）：把字面串递进来就该由入参层先转、转不了就报错，
    由这道闸替它猜意思等于替它决定能不能上线——`float('nan')` 是一次**合法**转换，
    而 `link_probe nav nan 0` 走的正是这条路（命令行字面串 → `float()` → 这里）。
    """
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    v = float(v)
    if not math.isfinite(v) or abs(v) > _F32_MAX:
        return None
    return v


def nav_exceeds_bench_limit(vl, vr):
    """True = 这条 NAV 不许发：要么超出台架限速，要么根本不是一个可上线的速度。

    **fail-closed**（最终整枝审查 C-1）：非有限值、超出 f32 值域、不是数字，一律按
    "超限"处理。旧写法 `max(abs(float(vl)), abs(float(vr))) > 0.20 + 1e-6` 在 NaN 上恒为
    False——而这条谓词是三个手动发送器共用的**唯一**硬闸，"比较不上"就等于"闸门开着"。
    后果按现烧固件算（`f0ecf73:firmware/retrofit.c:93` —— 10-10 批 1a Task 8 定身份：这个行号
    属板上那一版，正身里同一段已被批 1a 改掉）：它的早退只管长度与急停锁存，`:98-101` 那
    四次钳制对 NaN 一次都不触发（NaN 与任何数比较皆为假），而 `:102` 的
    `mode = MODE_AUTO;` 无条件执行 = 夺遥控的权，最后得到的是一台**既没停车也没跑**的车
    （B2 里最难归因的那一类症状）。

    超出 f32 范围也算超限，这是一条**设计选择**（审查 C-1 要求写清）：`pack_nav` 对
    `1e39` 抛的是 `struct.error`，而两个调用方的出口是 `sys.exit(一条中文理由)` 与
    `[TX REFUSED]`；台架上说得清"为什么不能发"比一个裸 traceback 有用。

    返回 bool、**不抛**：它是谓词不是校验器，报错文案由调用方各自决定。

    按 f32 的**线上值**比时要留一点余量：0.2 存成 f32 是 0.20000000298…，不留余量就会
    把"正好等于限值"这条边界拒掉。同一个闸在几个发送器上必须给同一个答案，所以判定
    逻辑也放进这个文件里，而不只是数字。
    """
    a, b = _number_or_none(vl), _number_or_none(vr)
    if a is None or b is None:
        return True
    return max(abs(a), abs(b)) > NAV_BENCH_LIMIT_MPS + 1e-6


def load_permit(path=None):
    """车辆档案里的许可位（`wire.GATE_N` / `wire.GATE_F`）。**读不到就抛**，不返回默认值。

    与 `tools/bench_status.py:load_profile_id()` 的降级语义是**两件事**，别照搬：
    档案号读不到退回 0 是安全的，因为 0 一定被板子按 `reject=0x01` 拒、而且看得见；
    许可位没有这个性质——"拿不到"若当成"门 F"，闸门就自己开了。所以这里只管取，
    **取不到的后果由调用方决定**（两个手动工具都把它映射成 None = TOOL 一律拒）。
    """
    from pc import vehicle_profile
    return vehicle_profile.load(path)['permit']


def tool_command_allowed(permit, tool_mm, lift_bits):
    """True = 门 N/F 许可位允许手动工具把这条 TOOL 发出去。fail-closed。

    为什么要有它（最终整枝审查 C-1 的另一半 + 审查第 7 条"工具无视 permit"）：
    闭环那一路在 GATE_N 下**没有选择**——`pc/wire.py:91-95` 把横移强制成 0.0、刀位强制
    成 0x07；而 `!tool mm lift` / `link_probe tool mm lift` 是人打的字，过去**一个字都不
    查**就上线。同一个桥上"闭环保了门 N、手动面不保"就是假的安全感：门 N 的字面含义是
    刀不许落，而按下一个键就能落。
      · GATE_F：载荷本身合法就放行（落刀与横移是门 F 的语义）；
      · GATE_N：只许 `wire.frames_for_state` 本来就会发的那一对 (0.0, 0x07)；
      · permit 拿不到 / 未知（None、0、没经 `wire.PERMIT_BY_NAME` 映射的名字串、bool）
        ⇒ 一律 False。"读不到档案"当作"允许落刀"就是这条闸门存在的理由。

    载荷本身要能上线（`pack_tool` 的 mm 是 f32、lift 是 u8）：装不下的数在这里给 False，
    调用方因此拿到的是拒发文案而不是 `struct.error`——与 `nav_exceeds_bench_limit` 同一
    个设计选择。返回 bool、**不抛**。
    """
    mm = _number_or_none(tool_mm)
    if mm is None:
        return False
    if isinstance(lift_bits, bool) or not isinstance(lift_bits, int):
        return False
    if not 0 <= lift_bits <= 0xFF:              # u8：越界 pack_tool 会抛 struct.error
        return False
    if permit is wire.GATE_F:                   # 身份比较：True == 1 不算 GATE_F
        return True
    if permit is wire.GATE_N:
        return mm == _GATE_N_OFFSET_MM and lift_bits == _GATE_N_LIFT
    return False
