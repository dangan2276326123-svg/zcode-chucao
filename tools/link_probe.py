# -*- coding: utf-8 -*-
"""PC -> 大板 的链路探针：往 X5 的 bridge 发一帧，看单片机认不认。

为什么需要它：证明链路要**双向**，而现有工具里 `bench_status.py` 只收不发、
`pc/main.py --live` 会发但和记录器抢同一个 UDP 9100、还依赖相机流。车端没接相机
的时候，反向根本没有办法单独验。本工具只发不收（不 bind 端口），所以可以和
记录器同时开。

判据（Task 7 重写，spec §9 / A17；旧的那条"是否曾看到 AUTO"已废）：
每种命令**该看到什么**写在 `EXPECTED` 表里，`judge()` 按表给 PASS / FAIL / INCONCLUSIVE，
并且把"发送前基线"与"发送后变化"分开算——这两件事过去混在一句话里，评审的两个反例
（发 ESTOP 看到 MANUAL->ESTOP 被报成"检查接线"、第一帧本来就是 AUTO 被报成"收得进"）
都是这么来的。
  mode_auto / mode_manual / clear
         -> 发 MODE(0x01 / 0x00 / 0x10)，预期 mode 从**基线**跳到对应态；
            发送前就已经是那个态 => INCONCLUSIVE（不能证明是本次发送引发的）。
  estop  -> 预期 MANUAL -> ESTOP（这是旧判据误报的那一条）。
  nav    -> A2 之后 NAV **不再改 mode**，判据反过来：收到 STATUS 且 mode 没变才算 PASS；
            mode 变了说明板上还是旧固件（F1 那个洞还没补）或另有东西在发帧。
  tool / beat -> 不以 mode 变化为判据（心跳把 AUTO 放回 MANUAL 本来就是预期，
            见 `retrofit.c:70-73`；单独发心跳观察不到转移属正常，不算失败）。
一帧 STATUS 都没收到才说"查串口/桥接/接线"；`reject != 0` 是**正常响应**——链路明明通了、
只是权限没给，所以要报中文原因，不许写成"链路不通"。

注意：现在烧在板上的还是 **E3 之前的固件**（批 1a 未实施、未烧），三条后果必须知道：
  - 它的 switch 没有 TYPE_MODE 这一支（`retrofit.c:60-75`），三条 MODE 命令会被丢弃；
  - 它发的 STATUS 是 14 字节 v1，没有 reject/authority 字段 -> 探针打一行 v1 提示，
    并对三条 MODE 命令直接给 INCONCLUSIVE，不给"接线有问题"的假结论；
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
MODE 三条不受这条影响（一条请求就够，之后的 reject/态从 STATUS 里读），但同一块板子上
如果 NAV/TOOL 还在别处发着（`pc/main.py --live`），那条注入逻辑照样会咬。

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

# 与固件 retrofit.h:11-13 及 spec §3.1 一致（TELEOP 是 E3 加的位，批 2 才实现）；
# 不在这四个值里的原样打印数字，不替它编名字。
MODE_NAME = {0: 'MANUAL', 1: 'AUTO', 2: 'ESTOP', 3: 'TELEOP'}
# 每种命令**应当**把 mode 推到哪一态；None = 不以 mode 变化为判据。
# 'nav': None 是 A2 的直接后果——NAV 不再隐含进 AUTO，判据反过来变成"mode 不许变"。
# 'beat': None 因为心跳在 MANUAL 下本来就不动 mode（AUTO 下放回 MANUAL 才是预期，:73），
# 单独发心跳观察不到转移属正常，不能算失败。
EXPECTED = {'nav': None, 'mode_auto': 1, 'mode_manual': 0,
            'estop': 2, 'clear': 0, 'tool': None, 'beat': None}
# 这三条走 MODE 帧（TYPE_MODE），是"会被权限拒绝"的命令；reject 码只对它们给结论。
MODE_REQUEST_KINDS = ('mode_auto', 'mode_manual', 'clear')

# 新加的提示行一律 ASCII：本机控制台是 cp936，中文靠 stdout reconfigure 兜，
# 但把"能不能读懂"押在编码上不如直接写英文（AGENTS 纪律）。
_V1_NOTE = ('note: STATUS payload is v1 (14 B) -> the board runs pre-E3 firmware. '
            'MODE frames are dropped (retrofit.c:60-75) and the reject/authority '
            'fields do not exist, so "refused by the authority gate" and "the frame '
            'never reached the MCU" cannot be told apart here; mode_auto / '
            'mode_manual / clear are judged INCONCLUSIVE.')


def _name(mode):
    """态的显示名：None 说"未采到"，认得的给名字，认不出的原样给数字、不替它编名字。"""
    if mode is None:
        return '未采到'
    return MODE_NAME.get(mode, str(mode))


def _mode_text(modes):
    """把观察到的态序列印成 MANUAL->ESTOP；未知值原样给数字。"""
    return '->'.join(_name(m) for m in dict.fromkeys(modes))


def judge(kind, baseline_mode, seen_modes, reject_codes):
    """按命令定义预期响应，并区分"发送前基线"与"发送后变化"。

    评审指出的两个反例都必须判对：
      - 发 ESTOP 看到 MANUAL->ESTOP 是 PASS，不是"一直在 MANUAL，检查接线"；
      - 第一帧就已经是 AUTO 时，不能算这次发送的功劳 => INCONCLUSIVE。
    E3 之后新增：申请被拒（reject != 0）是**正常响应**，报出是哪一条原因——
    链路上收得到 STATUS 就说明收发都通，只是权限没给，别把它写成"接线问题"。

    前提（由 `_read_status` 保证）：seen_modes 是**发送开始之后**观察到的态，
    baseline_mode 是发送开始前最后一帧的态。二者混用就等于回到旧判据。
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

    want = EXPECTED[kind]
    rejects = [c for c in reject_codes if c]      # 0 = "没有拒绝"，不是拒绝码

    if want is None:
        # nav / tool / beat：判据是"链路活着且没有意外越权"
        if kind == 'nav':
            if baseline_mode is None:
                return 'INCONCLUSIVE', '没有发送前基线，"mode 有没有变"这条无从判断'
            if any(m != baseline_mode for m in seen_modes):
                return 'FAIL', ('NAV 之后 mode 变了（%s）——A2 之后 NAV 不许改权限，'
                                '说明板上还是旧固件（F1 洞还没补）或有别的东西在发帧'
                                % _mode_text(seen_modes))
        text = '收到 STATUS，且没有意外的权限变化'
        if rejects:
            text += ('；但板子挂着 reject=0x%02X（%s）——那是权限的事，不是链路的事'
                     % (rejects[-1], P.REJECT_TEXT.get(rejects[-1],
                                                       '未知拒绝码 %d' % rejects[-1])))
        return 'PASS', text

    if want in seen_modes:
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

    profile 只在三条 MODE 命令里有意义（spec §3.1 / §6）：默认 PROFILE_NONE。
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
               'clear': P.MODE_REQ_CLEAR_ESTOP}[kind]
        return P.pack_frame(P.TYPE_MODE, P.pack_mode(req, profile), seq)
    raise ValueError('未知指令 %r：只有 nav / tool / beat / estop / mode_auto / '
                     'mode_manual / clear' % kind)


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
              'mode_auto / mode_manual / clear 这三条要等批 1a 烧进去才测得了。'
              '顺带：锁存清不掉是 Fw-14（`retrofit_clear_estop()` 全工程无调用点），'
              '在这块旧板上只能断电清。')
    else:
        verdict, detail = judge(a.kind, base, seen, out.get('rejects', []))
        print('判定：%s —— %s' % (verdict, detail))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('kind', choices=['nav', 'tool', 'beat', 'estop']
                    + list(MODE_REQUEST_KINDS))
    ap.add_argument('args', nargs='*',
                    help='nav: vL vR (m/s)   tool: mm lift位   '
                         'mode_auto/mode_manual/clear: 不需要参数')
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
    if a.kind == 'nav' and max(abs(float(x)) for x in a.args) > 0.20:
        sys.exit('探针限速 0.20 m/s，别拿它当行车工具——要跑闭环请用 pc/main.py')
    # MODE 三条的参数只有一个 profile 号，而它**必须**来自车辆档案：让用户在命令行
    # 上敲一个档案号，等于允许拿另一台车的权限去申请无人（spec §6）。
    if a.kind in MODE_REQUEST_KINDS and a.args:
        sys.exit('%s 不接受参数：档案号从 config/vehicle_profile.yaml 取，'
                 '不在命令行上给' % a.kind)
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
