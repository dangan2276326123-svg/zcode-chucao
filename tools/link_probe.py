# -*- coding: utf-8 -*-
"""PC -> 大板 的链路探针：往 X5 的 bridge 发一帧，看单片机认不认。

为什么需要它：证明链路要**双向**。写这句的时候 `bench_status.py` **只收不发**、
`pc/main.py --live` 会发但和记录器抢同一个 UDP 9100、还依赖相机流，车端没接相机
的时候反向根本没有办法单独验。**这句已过期**（E3 批 1b Task 8 给记录器加了 opt-in 的
`--to <桥IP>:9000` 发送面，不填时仍然一个字节都不发；`tools/latency_probe.py` 也发）——
所以"没有别的工具能发"不再是本工具存在的理由。仍然成立的是另一半：本工具**只发不收**
（不 bind 端口），不用先起记录器、不抢 9100、不依赖相机流，一条命令 + `EXPECTED` 判定表
就能单独验一次反向，所以可以和记录器同时开。（:86-89 那条注释记录的正是"这句留给 Task 10 改"。）

判据（Task 7 重写，spec §9 / A17；旧的那条"是否曾看到 AUTO"已废）：
每种命令**该看到什么**写在 `EXPECTED` 表里，`judge()` 按表给 PASS / FAIL / INCONCLUSIVE，
并且把"发送前基线"与"发送后变化"分开算——这两件事过去混在一句话里，评审的两个反例
（发 ESTOP 看到 MANUAL->ESTOP 被报成"检查接线"、第一帧本来就是 AUTO 被报成"收得进"）
都是这么来的。
  mode_auto / mode_manual / clear
         -> 发 MODE(0x01 / 0x00 / 0x10)，预期 mode 从**基线**跳到对应态；
            发送前就已经是那个态 => INCONCLUSIVE（不能证明是本次发送引发的）；
            连发送前基线都没采到（暖机期内一帧 STATUS 都没读到）=> 同样 INCONCLUSIVE——
            初始态证明不了因果，`judge()` 作为公开纯函数也不给这种入参印 PASS。
  mode_profile / mode_teleop
         -> 两条都**不以 mode 变化为判据**（握手的产物是 handshake_ok 那一位，不在 STATUS
            里；TELEOP 本批未实现）。能判的只有"链路活着 + 板子挂在哪条 reject 上"，
            文案各写各的，见 `_judge_new_mode`（T1，2026-10-12 加）。
  estop  -> 预期 MANUAL -> ESTOP（这是旧判据误报的那一条）。
  nav    -> A2 之后 NAV **不再改 mode**，判据反过来：收到 STATUS 且 mode 没变才算 PASS；
            mode 变了说明板上还是旧固件（F1 那个洞还没补）、另有东西在发帧、
            或者**旁边有人在动遥控器/按了急停**（最后这条在台架上最常见，是合法跳变，
            不是固件故障——三种可能都列出来，免得把 FAIL 一口读成固件坏了）。
  tool / beat -> 不以 mode 变化为判据（心跳把 AUTO 放回 MANUAL 本来就是预期，
            见 `retrofit.c:70-73`；单独发心跳观察不到转移属正常，不算失败）。
            这两条的 PASS 文案只说"链路收到 STATUS"，**不说权限有没有变化**——
            mode 到底变没变这两条根本没检查，写上去就是越过证据的话（AGENTS 清单第 5 条）。
一帧 STATUS 都没收到才说"查串口/桥接/接线"；`reject != 0` 是**正常响应**——链路明明通了、
只是权限没给，所以要报中文原因，不许写成"链路不通"。

注意：现在烧在板上的还是 **E3 之前的固件**（批 1a 未实施、未烧），三条后果必须知道：
  - 它的 switch 没有 TYPE_MODE 这一支（`retrofit.c:60-75`），`MODE_REQUEST_KINDS` 这一族
    的命令会被丢弃；
  - 它发的 STATUS 是 14 字节 v1，没有 reject/authority 字段 -> 探针打一行 v1 提示，
    并对这一族（`MODE_REQUEST_KINDS`）的命令直接给 INCONCLUSIVE，不给"接线有问题"的假结论；
  - 它仍然在 `retrofit.c:93/:102` 拿 NAV 当进 AUTO 的钥匙（F1 洞），所以**现在**跑 `nav`
    会判 FAIL（"NAV 之后 mode 变了"）——那是**预期**结果，读作"板上还是旧固件"，
    不是链路坏了。批 1a 烧进去之后这条 FAIL 才变成真问题。

**用法上必须连续发，别单发一条**（09-28 现场踩过，写在这是为了防止再踩）：
`vehicle/bridge.py:206` 传的是 `auto_on=True`，而 `decide_forward` 的条件是"PC 发过真帧后
60 秒内一旦 500ms 没有下一条就自己往串口注一条 ESTOP"。所以单发一条 NAV 的后果是
0.5 秒后板子被注入 ESTOP → `estop_latched=1` → 之后所有 NAV 都被 `:93` 忽略。
而 `retrofit_clear_estop()`（`retrofit.c:124`）**全工程没有调用点**（台账 Fw-14），
锁存只能靠**板子断电**清。正确姿势：

    python -B tools/link_probe.py nav 0 0 --every 0.2 --count 30 --host <X5>

这样 NAV 每 0.2 秒一条、空窗永远不到 500ms，注入不会触发；数发完停手时反过来**应该**
看到 mode 自己跳成 ESTOP——那正是失联注入这条安全路径在动的证据。
MODE 这一族（`MODE_REQUEST_KINDS`）不受这条影响（一条请求就够，之后的 reject/态从 STATUS
里读），但同一块板子上如果 NAV/TOOL 还在别处发着（`pc/main.py --live`），那条注入逻辑
照样会咬。

两种接法（09-28 加第二种，用来把"是板子收不进"和"是 X5 发不出"分开）：

    # A) 走 X5 + bridge（默认）
    python -B tools/link_probe.py nav 0 0 --every 0.2 --count 30 --host 192.168.127.10
    # B) 走 USB-TTL 直连大板：给了 --serial 就不发 UDP，并且**自己一边发一边读 STATUS**，
    #    不需要第二个窗口当显示器。接法：USB-TTL RXD ↔ 大板 PC6，TXD ↔ 大板 PC7，共地必接。
    python -B tools/link_probe.py nav 0 0 --every 0.2 --count 30 --serial COM6 --watch 10
    #    批 1a 烧进去以后，权限那条探针是：
    python -B tools/link_probe.py mode_auto --serial COM6 --watch 10

    ⚠️ 用 B 的时候**先把 X5 的 TX（Pin8）从那根网络上摘掉**：否则是 X5 与 USB-TTL 两个
    输出对顶同一根线，测出来什么都不能解释。3.3V 电平的 USB-TTL，别接 VCC 脚。

测试：UDP 那条路确实不含新逻辑（帧构造全走 `common/protocol.py` 的 `pack_*`，已被
`tests/test_protocol.py` 覆盖；剩下的只有 argparse 分支和一次 `socket.sendto`）。
但 `--serial` 那条有：`_read_status` 要自己拼帧、还要把"发送前基线 / 发送后变化 /
reject / 帧形态版本"分开收下来，判据 `judge()` 就建在这四样上，所以它配了
`tests/test_link_probe.py`（不需要硬件：假串口按脚本喂字节，钉"跨读边界拼帧"、
"模式跳变序列而不是最后一帧"、"序号回退的帧不计为好帧"、"评审那两个反例判对"四条）。
"""
import argparse
import math
import os
import socket
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(errors='replace')
except AttributeError:
    pass

from common import protocol as P          # noqa: E402
from pc import wire                                    # noqa: E402
# 台架 NAV 限速的唯一出处（09-30 复审 I-1：`bench_status --to` 与本文件是同一个
# bridge:9000 入口的两个发送器，一个有闸一个没闸就是不一致的安全不变量）。
# 这里只改 import 与下面那一处判定，不改第 4 行那句"只收不发"的旧口径——那是
# Task 10 的文档同步项（M-8），不属于本批。
from tools.bench_limits import (NAV_BENCH_LIMIT_MPS,          # noqa: E402
                                nav_exceeds_bench_limit,
                                tool_command_allowed, load_permit)

# 与固件 retrofit.h:11-13 及 spec §3.1 一致（TELEOP 是 E3 加的位，批 2 才实现）；
# 不在这四个值里的原样打印数字，不替它编名字。
MODE_NAME = {0: 'MANUAL', 1: 'AUTO', 2: 'ESTOP', 3: 'TELEOP'}
# 每种命令**应当**把 mode 推到哪一态；None = 不以 mode 变化为判据。
# 'nav': None 是 A2 的直接后果——NAV 不再隐含进 AUTO，判据反过来变成"mode 不许变"。
# 'beat': None 因为心跳在 MANUAL 下本来就不动 mode（AUTO 下放回 MANUAL 才是预期，:73），
# 单独发心跳观察不到转移属正常，不能算失败。
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

# 新加的提示行一律 ASCII：本机控制台是 cp936，中文靠 stdout reconfigure 兜，
# 但把"能不能读懂"押在编码上不如直接写英文（AGENTS 纪律）。
_V1_NOTE = ('note: STATUS payload is v1 (14 B) -> the board runs pre-E3 firmware. '
            'MODE frames are dropped (retrofit.c:60-75) and the reject/authority '
            'fields do not exist, so "refused by the authority gate" and "the frame '
            'never reached the MCU" cannot be told apart here; every command in '
            'MODE_REQUEST_KINDS is judged INCONCLUSIVE.')


def _name(mode):
    """态的显示名：None 说"未采到"，认得的给名字，认不出的原样给数字、不替它编名字。"""
    if mode is None:
        return '未采到'
    return MODE_NAME.get(mode, str(mode))


def _mode_text(modes):
    """把观察到的态序列印成 MANUAL->ESTOP；未知值原样给数字。"""
    return '->'.join(_name(m) for m in dict.fromkeys(modes))


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
                            '也可能是"这块板从没握过手"——两种 0x01 长得一样，'
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


def judge(kind, baseline_mode, seen_modes, reject_codes):
    """按命令定义预期响应，并区分"发送前基线"与"发送后变化"。

    评审指出的两个反例都必须判对：
      - 发 ESTOP 看到 MANUAL->ESTOP 是 PASS，不是"一直在 MANUAL，检查接线"；
      - 第一帧就已经是 AUTO 时，不能算这次发送的功劳 => INCONCLUSIVE。
    E3 之后新增：申请被拒（reject != 0）是**正常响应**，报出是哪一条原因——
    链路上收得到 STATUS 就说明收发都通，只是权限没给，别把它写成"接线问题"。

    前提（由 `_read_status` 保证）：seen_modes 是**发送开始之后**观察到的态，
    baseline_mode 是发送开始前最后一帧的态。二者混用就等于回到旧判据。

    两条契约（2026-10-08 收尾批）：
      - baseline_mode 为 None 时**不给 PASS**——没有基线就无从谈"这次发送引发了变化"，
        即使调用方漏传（`_run_serial` 当前不会漏）也只能得 INCONCLUSIVE。
      - detail 只写证据支持得到的话：tool/beat 不以 mode 变化为判据，也就没检查过
        mode 变没变，它们的 PASS 文案里不出现"权限"字样（口径，AGENTS 清单第 5 条）。
    """
    if not seen_modes:
        if baseline_mode is None:
            return 'INCONCLUSIVE', '一帧 STATUS 都没收到：查串口/桥接/接线，不是查权限'
        return 'INCONCLUSIVE', ('发送开始之后一帧 STATUS 都没有（发送前是 %s）：'
                                '收的方向在发送之后就断了，先查板子有没有重启、'
                                'USB-TTL 有没有松，不能对发送方向下结论'
                                % _name(baseline_mode))

    if kind not in EXPECTED:
        return 'INCONCLUSIVE', ('判据表里没有 %r 这条命令，不给结论'
                                '（拼错命令名不该印出一个 PASS）' % kind)

    if kind in ('mode_profile', 'mode_teleop'):
        return _judge_new_mode(kind, baseline_mode, seen_modes,
                               [c for c in reject_codes if c])

    want = EXPECTED[kind]
    rejects = [c for c in reject_codes if c]      # 0 = "没有拒绝"，不是拒绝码

    if want is None:
        # nav / tool / beat 的判据是"链路活着"；只有 nav 还**真的**比较了基线与观察态。
        # 文案必须跟着证据走（AGENTS 清单第 5 条）：没检查过的事不许写进结论里。
        if kind == 'nav':
            if baseline_mode is None:
                return 'INCONCLUSIVE', '没有发送前基线，"mode 有没有变"这条无从判断'
            if any(m != baseline_mode for m in seen_modes):
                return 'FAIL', ('NAV 之后 mode 变了（%s）——A2 之后 NAV 不许改权限，'
                                '三种可能都要查：板上还是旧固件（F1 洞还没补）、'
                                '有别的东西在发帧、或者旁边有人在动遥控器/按了急停'
                                '（最后那条是合法跳变，不是固件故障）'
                                % _mode_text(seen_modes))
            text = '收到 STATUS，且 mode 相对发送前基线没有变化'
        else:
            # tool / beat：不以 mode 变化为判据，mode 变没变本次**没有检查**，
            # 所以这里只说链路，不说权限。
            text = '收到 STATUS；本命令不以 mode 变化为判据（mode 变没变本次没有检查）'
        if rejects:
            text += ('；但板子挂着 reject=0x%02X（%s）——那是板子对某条请求的答复，'
                     '不是链路不通（reject 记的是"最近一次拒绝"，可能来自更早那条请求）'
                     % (rejects[-1], P.REJECT_TEXT.get(rejects[-1],
                                                       '未知拒绝码 %d' % rejects[-1])))
        return 'PASS', text

    if want in seen_modes:
        if baseline_mode is None:
            # 初始态证明不了因果（与"发送前就已经是 AUTO"同一个道理）：没有基线，
            # 观察到的期望态既可能是本次发送引发的，也可能一直就在。
            return 'INCONCLUSIVE', ('没有发送前基线（发送前那一段一帧 STATUS 都没读到），'
                                    '无法确认观察到的 %s 是本次发送引发的' % MODE_NAME[want])
        if baseline_mode == want:
            return 'INCONCLUSIVE', ('发送前就已经是 %s，不能证明是这次发送引发的'
                                    % MODE_NAME[want])
        return 'PASS', '基线 %s -> 观察到 %s' % (_name(baseline_mode), MODE_NAME[want])

    if kind in MODE_REQUEST_KINDS and rejects:
        code = rejects[-1]
        text = P.REJECT_TEXT.get(code, '未知拒绝码 %d' % code)
        return 'FAIL', ('请求被拒绝：%s（reject=0x%02X）——链路是通的，权限没给'
                        '（reject 记的是"最近一次拒绝"，也可能是更早那条请求留下的）'
                        % (text, code))

    return 'FAIL', ('期望看到 %s，实际只看到 %s，而且 reject 没挂：收的方向是通的，'
                    '发送没生效——先核对 STATUS 形态（v1 那块板没有 TYPE_MODE 这一支，'
                    'MODE 帧整条被丢），确认帧型之后才轮到谈接线'
                    % (MODE_NAME[want], _mode_text(seen_modes)))


def build(kind, args, seq, profile=P.PROFILE_NONE):
    """把命令行选择变成一条完整协议帧。未知 kind 必须抛，不能静默发空包。

    profile 只在 MODE 这一族（`MODE_REQUEST_KINDS`）里有意义（spec §3.1 / §6），而其中只有
    档案握手那条（`MODE_REQ_PROFILE`）让这个字段真的有效：默认 PROFILE_NONE。
    `main()` 从车辆档案取真值；取不到就带着 0 发出去，固件按 reject=0x01 拒——
    探针**不替板子猜一个"看起来合法"的档案号**，那样场景"用错档案号申请无人"
    就会被测成"档案握手一致"。
    """
    if kind == 'nav':
        return P.pack_frame(P.TYPE_NAV, P.pack_nav(float(args[0]), float(args[1])), seq)
    if kind == 'tool':
        return P.pack_frame(P.TYPE_TOOL, P.pack_tool(float(args[0]), int(args[1])), seq)
    if kind in ('beat', 'estop'):
        t = P.TYPE_HEARTBEAT if kind == 'beat' else P.TYPE_ESTOP
        return P.pack_frame(t, b'', seq)
    if kind in MODE_REQUEST_KINDS:
        req = {'mode_auto': P.MODE_REQ_AUTO, 'mode_manual': P.MODE_REQ_MANUAL,
               'clear': P.MODE_REQ_CLEAR_ESTOP,
               'mode_profile': P.MODE_REQ_PROFILE,
               'mode_teleop': P.MODE_REQ_TELEOP}[kind]
        return P.pack_frame(P.TYPE_MODE, P.pack_mode(req, profile), seq)
    raise ValueError('未知指令 %r：只有 nav / tool / beat / estop / mode_auto / '
                     'mode_manual / clear / mode_profile / mode_teleop' % kind)


def _load_profile_id():
    """车辆档案里的 profile_id；读不到退回 0（PROFILE_NONE）并打一行警告（spec §6）。

    退回 0 不是"假装成功"：0 一定被固件 reject=0x01 拒掉，判据会把那句原因说出来，
    operator 看得见"这台板子不认这个档案"，比不发或比猜一个号都诚实。
    """
    try:
        from pc import vehicle_profile
        return int(vehicle_profile.load()['profile_id'])
    except (ValueError, OSError) as exc:      # load() 把 OSError 也收进 ValueError
        print('warning: vehicle profile unavailable (%s) -> sending profile=0; '
              'the board will reject it with 0x01' % exc)
        return P.PROFILE_NONE


def _read_status(ser, stop, out, started=None):
    """后台读串口上的 STATUS，模式一跳就记下来。

    帧的切分复用 `vehicle.bridge.poll_serial_frames`（跨读边界不丢帧，那条有单测），
    新鲜度/乱序/重启重同步复用 `pc.status_rx.StatusReceiver`——**不另写一套解析**，
    否则"探针说通了、记录器说没通"这种分歧就没法解释。

    Task 7 起还要把判据用的四样东西分开收（`judge()` 的两个反例全靠这条时间线）：
      out['baseline']  第一帧的 mode（发送开始之前采到的）
      out['pre_send']  发送开始**之前**最后一帧的 mode —— judge 的 baseline_mode 用它
      out['seen']      发送开始**之后**观察到的 mode 序列（连续同态只记一次）
      out['rejects']   发送之后看到的非零 reject（0 = "没有拒绝"，不进账）
      out['versions']  收到的 STATUS 载荷形态 {1,2}；1 就是 E3 之前的固件
    started 为 None（老的调用方式与单测）＝没有"发送"这条线，所有帧都算观察到的。
    """
    from vehicle.bridge import poll_serial_frames
    from pc.status_rx import StatusReceiver
    rx = StatusReceiver()
    buf = b''
    prev = None
    while not stop.is_set():
        chunk = ser.read(64)
        if not chunk:
            time.sleep(0.005)
            continue
        frames, buf = poll_serial_frames(buf, chunk)
        for raw in frames:
            st = rx.handle(raw)
            if st is None:
                continue
            out['good'] += 1
            post_send = started is None or started.is_set()
            if 'baseline' not in out:
                out['baseline'] = st['mode']
            if not post_send:
                out['pre_send'] = st['mode']    # 一路覆盖到发送前的最后一帧
            else:
                seen = out.setdefault('seen', [])
                if not seen or seen[-1] != st['mode']:
                    seen.append(st['mode'])
                if st.get('reject'):          # v1 帧这里是 None，不进账（不猜 0）
                    out.setdefault('rejects', []).append(st['reject'])
            if st.get('v') is not None:
                out.setdefault('versions', set()).add(st['v'])
            if st['mode'] != prev:
                out['changes'].append((round(time.time() - out['t0'], 2),
                                       prev, st['mode']))
                prev = st['mode']


def _run_serial(a, frame_iter):
    """--serial：USB-TTL 直连大板时用它。发一条的同时还在读，所以不需要第二个显示器。"""
    import threading
    try:
        import serial
    except ImportError:
        sys.exit('需要 pyserial：pip install pyserial')
    try:
        ser = serial.Serial(a.serial, a.baud, timeout=0.05)
    except Exception as exc:
        sys.exit('打不开 %s（%s）。确认 COM 号、有没有被别的程序占用、以及是否 115200。'
                 % (a.serial, exc))
    out = {'good': 0, 'changes': [], 't0': time.time()}   # 其余四样由读线程填
    stop = threading.Event()
    started = threading.Event()    # 第一条帧写出去的时刻：之前的读数只当基线，不算战果
    th = threading.Thread(target=_read_status, args=(ser, stop, out, started), daemon=True)
    th.start()
    n = 0
    v1_noted = False
    try:
        time.sleep(0.6)                       # 先确认能听见板子说话，再开始发
        if out['good'] == 0:
            print('注意：前 0.6 秒一个 STATUS 都没读到。先别怪发送——'
                  'USB-TTL 的 RXD 有没有接到板子的 PC6、共地接了没、波特率对不对。')
        if out.get('versions') == {1}:        # 一上手就是 v1：当场就说，别等测完
            print(_V1_NOTE)
            v1_noted = True
        for frame in frame_iter:
            ser.write(frame)
            if not started.is_set():
                started.set()     # **先写后开闸**：路上本来就挂着的那一帧不算本次引起的
            n += 1
            print('#%-5d -> %s  %d B  %s' % (n, a.serial, len(frame), frame.hex(' ')))
    finally:
        end = time.time() + max(0.0, a.watch)
        while time.time() < end and not stop.is_set():
            time.sleep(0.05)
        stop.set()
        th.join(timeout=1.0)
        ser.close()
    print('\n读了 %d 帧 STATUS；模式跳变 %d 次：' % (out['good'], len(out['changes'])))
    for t, frm, to in out['changes']:
        print('  %6.2fs  %s -> %s' % (t, _name(frm), _name(to)))
    base = out.get('pre_send', out.get('baseline'))
    seen = out.get('seen', [])
    want = EXPECTED.get(a.kind)
    print('发送前基线 mode=%s；本次发的是 %s，预期=%s'
          % (_name(base), a.kind,
             MODE_NAME.get(want, '不以 mode 变化为判据')))
    if out.get('versions') == {1} and not v1_noted:
        print(_V1_NOTE)
    # 旧判据的毛病就出在"不管发什么都只问有没有出现过 AUTO"：发 ESTOP 看到
    # MANUAL->ESTOP（正确响应）被判成"去查接线"，发送前本来就是 AUTO 又误判"收得进"。
    # Task 7 把这句话拆成 judge()：按命令要的预期态 + 发送前基线 + reject 三个入参给结论。
    if a.kind in MODE_REQUEST_KINDS and out.get('versions') == {1}:
        print('判定：INCONCLUSIVE —— 板上是 E3 之前的固件（STATUS 14 字节 v1），'
              '它的 switch 没有 TYPE_MODE 这一支（retrofit.c:60-75），MODE 帧整条被丢弃 -> '
              '这一族（MODE_REQUEST_KINDS）这几条要等批 1a 烧进去才测得了。'
              '顺带：锁存清不掉是 Fw-14（`retrofit_clear_estop()` 全工程无调用点），'
              '在这块旧板上只能断电清。')
    else:
        verdict, detail = judge(a.kind, base, seen, out.get('rejects', []))
        print('判定：%s —— %s' % (verdict, detail))


def _permit_or_none():
    """车辆档案里的许可位（门 N/F）；**读不到返回 None = 一律拒**，不降级成门 F。

    与 `_load_profile_id()` 的对照是刻意的（最终审查 C-1 / 第 7 条"工具无视 permit"）：
    档案号取不到退回 0 是安全的（板子一定 reject=0x01，判据会说清）；许可位取不到若
    当成"允许落刀"，这条手动通道就把门 N 的语义绕过去了——而批 1a 之前固件不看 TOOL 的
    许可位，PC 这一关是唯一一关。取数用 `tools/bench_limits.load_permit()`（与
    `tools/bench_status.py` 同一个出处，AGENTS 清单第 6 条）。
    """
    try:
        return load_permit()
    except (ValueError, OSError) as exc:      # vehicle_profile 把 OSError 收进 ValueError
        print('warning: vehicle profile permit unavailable (%s) -> TOOL commands are '
              'refused (fail-closed, not treated as gate_f)' % exc)
        return None


def _nav_speeds_or_exit(args):
    """命令行的两个速度字面串 → 两个**有限** float；不是数/非有限就照实退出。

    共享谓词现在只认数字（C-1：非有限、装不进 f32、不是数字一律判为超限），所以转换
    放在这一层。报错文案要指着**真正的原因**说：对 `nav abc 0` 说"超出限速"是假话，
    对 `nav nan 0` 说"超出限速"也是假话——NaN 不是"太大"，是"比较不上、没法执行"。
    """
    out = []
    for tok in args:
        try:
            v = float(tok)
        except (TypeError, ValueError):
            sys.exit('nav 的速度参数不是数：%r（例如：nav 0.05 0.05）' % (tok,))
        if not math.isfinite(v):
            sys.exit('nav 的速度参数不是有限数：%r —— NaN/inf 装不进 f32，也没法当成'
                     '"一个不超限的速度"（共享闸按超限处理：它要的是能上线的数，'
                     '不是一个比较不上的值）' % (tok,))
        out.append(v)
    return out


def _tool_gate_or_exit(args):
    """TOOL 的两个参数 + 许可位 → 能不能发；不能就 sys.exit 说一句指着原因的话。"""
    try:
        mm, lift = float(args[0]), int(args[1])
    except (TypeError, ValueError):
        sys.exit('tool 的参数不是数：<横移mm> <lift位>（都写十进制整数，'
                 '例如 tool 0 7），收到 %r' % (args,))
    permit = _permit_or_none()
    if isinstance(permit, bool) or permit not in (wire.GATE_N, wire.GATE_F):
        sys.exit('tool 发不出去：许可位读不到或不是 gate_n/gate_f（收到 %r）。'
                 'fail-closed：拿不到不当作"允许落刀"。' % (permit,))
    if not tool_command_allowed(permit, mm, lift):
        sys.exit('tool mm=%r lift=%r 在 permit=%r 下不许发。门 N 只许 `tool 0 7`'
                 '（横移必须 0、三把刀必须全提），lift 还必须是 u8 里的整数——装不进'
                 '`pack_tool` 的数在这里就拒，不让它变成一句 struct.error。落刀与横移'
                 '属门 F：改 config/vehicle_profile.yaml 里的 permit，而那要先有'
                 'B5 全项 + 刀控接线。' % (mm, lift, permit))


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


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('kind', choices=['nav', 'tool', 'beat', 'estop']
                    + list(MODE_REQUEST_KINDS))
    ap.add_argument('args', nargs='*',
                    help='nav: vL vR (m/s)   tool: mm lift位   '
                         'the five MODE kinds: no arguments (profile comes from '
                         'config/vehicle_profile.yaml)')
    ap.add_argument('--host', default='192.168.127.10', help='X5 地址（网桥阶段改这里）')
    ap.add_argument('--port', type=int, default=9000, help='bridge 监听端口')
    ap.add_argument('--every', type=float, default=0.0,
                    help='>0 则周期发送（秒），用于模拟"PC 一直在发"')
    ap.add_argument('--count', type=int, default=0, help='周期发送的条数上限，0=不限')
    ap.add_argument('--serial', default=None,
                    help='给了就走 USB-TTL 直连（如 COM6 或 /dev/ttyUSB0），不发 UDP')
    ap.add_argument('--baud', type=int, default=115200)
    ap.add_argument('--watch', type=float, default=8.0,
                    help='--serial 时：发完之后再读多少秒，等 mode 跳变')
    a = ap.parse_args()

    if a.kind == 'nav' and len(a.args) != 2:
        sys.exit('nav 需要两个速度参数，例如：nav 0.05 0.05')
    if a.kind == 'tool' and len(a.args) != 2:
        sys.exit('tool 需要 <横移mm> <lift位>，例如：tool 0 7')
    # 两道闸都在**建 socket 之前**（与 bench_status 的 --to 同一条纪律：先拒、后碰资源）。
    if a.kind == 'nav':
        if nav_exceeds_bench_limit(*_nav_speeds_or_exit(a.args)):
            # 到这里的都是有限数了，所以这一句只对"真的超限"说真话。
            sys.exit('探针限速 %.2f m/s，别拿它当行车工具——要跑闭环请用 pc/main.py'
                     % NAV_BENCH_LIMIT_MPS)
    if a.kind == 'tool':
        _tool_gate_or_exit(a.args)
    # MODE 这一族的参数只有一个档案号，而它**必须**来自车辆档案：让用户在命令行
    # 上敲一个档案号，等于允许拿另一台车的权限去申请无人（spec §6）。
    check_mode_args(a.kind, a.args)
    profile = _load_profile_id() if a.kind in MODE_REQUEST_KINDS else P.PROFILE_NONE

    def frames():
        i = 0
        while True:
            yield build(a.kind, a.args, i & 0xFFFF, profile)
            i += 1
            if not a.every:
                break
            if a.count and i >= a.count:
                break
            time.sleep(a.every)

    if a.serial:
        _run_serial(a, frames())
        return

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)   # 不 bind：可与记录器共存
    n = 0
    try:
        for frame in frames():
            sock.sendto(frame, (a.host, a.port))
            n += 1
            print('#%-5d -> %s:%d  %d B  %s' % (n, a.host, a.port, len(frame),
                                                frame.hex(' ')))
    except KeyboardInterrupt:
        print('中断')
    finally:
        sock.close()
        print('共发 %d 条。现在去 bench_status 那个窗口看 mode / authority / reject。' % n)


if __name__ == '__main__':
    main()
