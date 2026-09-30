# -*- coding: utf-8 -*-
"""PC -> 大板 的链路探针：往 X5 的 bridge 发一帧，看单片机认不认。

为什么需要它：证明链路要**双向**，而现有工具里 `bench_status.py` 只收不发、
`pc/main.py --live` 会发但和记录器抢同一个 UDP 9100、还依赖相机流。车端没接相机
的时候，反向根本没有办法单独验。本工具只发不收（不 bind 端口），所以可以和
记录器同时开。

判据（现场最常用的两条）：
  nav  ->  `retrofit.c:102` 把 mode 置 AUTO，所以 STATUS 里 mode 从 MANUAL 跳成 AUTO
           就说明"字进了单片机"。
           **但不是"无条件"**：`retrofit.c:93` 那行是 `if (len < 9 || estop_latched) return;`
           —— payload 长度够（NAV 是 9 字节）且**没有 ESTOP 锁存**时才生效。
           ⚠ 这是 F1 那个权限洞，我们暂时**拿缺陷当探针**用；E3 补完五条件之后
           这条判据会失效（届时 NAV 不再单独决定进 AUTO），要改用别的探针。
  beat ->  若当前在 AUTO，`retrofit.c:70-73` 会把 mode 放回 MANUAL。

**用法上必须连续发，别单发一条**（09-28 现场踩过，写在这是为了防止再踩）：
`vehicle/bridge.py:206` 传的是 `auto_on=True`，而 `decide_forward` 的条件是"PC 发过真帧后
60 秒内一旦 500ms 没有下一条就自己往串口注一条 ESTOP"。所以单发一条 NAV 的后果是
0.5 秒后板子被注入 ESTOP → `estop_latched=1` → 之后所有 NAV 都被 `:93` 忽略。
而 `retrofit_clear_estop()`（`retrofit.c:124`）**全工程没有调用点**（台账 Fw-14），
锁存只能靠**板子断电**清。正确姿势：

    python -B tools/link_probe.py nav 0 0 --every 0.2 --count 30 --host <X5>

这样 NAV 每 0.2 秒一条、空窗永远不到 500ms，注入不会触发；数发完停手时反过来**应该**
看到 mode 自己跳成 ESTOP——那正是失联注入这条安全路径在动的证据。

两种接法（09-28 加第二种，用来把"是板子收不进"和"是 X5 发不出"分开）：

    # A) 走 X5 + bridge（默认）
    python -B tools/link_probe.py nav 0 0 --every 0.2 --count 30 --host 192.168.127.10
    # B) 走 USB-TTL 直连大板：给了 --serial 就不发 UDP，并且**自己一边发一边读 STATUS**，
    #    不需要第二个窗口当显示器。接法：USB-TTL RXD ↔ 大板 PC6，TXD ↔ 大板 PC7，共地必接。
    python -B tools/link_probe.py nav 0 0 --every 0.2 --count 30 --serial COM6 --watch 10

    ⚠️ 用 B 的时候**先把 X5 的 TX（Pin8）从那根网络上摘掉**：否则是 X5 与 USB-TTL 两个
    输出对顶同一根线，测出来什么都不能解释。3.3V 电平的 USB-TTL，别接 VCC 脚。

测试：UDP 那条路确实不含新逻辑（帧构造全走 `common/protocol.py` 的 `pack_*`，已被
`tests/test_protocol.py` 覆盖；剩下的只有 argparse 分支和一次 `socket.sendto`）。
但 `--serial` 那条有：`_read_status` 要自己拼帧、判模式序列，所以它配了
`tests/test_link_probe.py`（不需要硬件：假串口按脚本喂字节，钉"跨读边界拼帧"、
"模式跳变序列而不是最后一帧"、"序号回退的帧不计为好帧"三条）。
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

# 与固件 retrofit.h:11-13 一致；不在这三个值里的原样打印数字，不替它编名字。
MODE_NAME = {0: 'MANUAL', 1: 'AUTO', 2: 'ESTOP'}
# 每种命令应当把 mode 推到哪一态（依据 retrofit.c:93/:102/:110/:121 与 :70-73）。
# 心跳的"预期"是"从 AUTO 回 MANUAL"，所以只在发过 NAV 之后才有意义——单独发心跳
# 观察不到转移属正常，不算失败。
EXPECTED = {'nav': 1, 'estop': 2, 'tool': None, 'beat': 0}


def build(kind, args, seq):
    """把命令行选择变成一条完整协议帧。未知 kind 必须抛，不能静默发空包。"""
    if kind == 'nav':
        return P.pack_frame(P.TYPE_NAV, P.pack_nav(float(args[0]), float(args[1])), seq)
    if kind == 'tool':
        return P.pack_frame(P.TYPE_TOOL, P.pack_tool(float(args[0]), int(args[1])), seq)
    if kind in ('beat', 'estop'):
        t = P.TYPE_HEARTBEAT if kind == 'beat' else P.TYPE_ESTOP
        return P.pack_frame(t, b'', seq)
    raise ValueError('未知指令 %r：只有 nav / tool / beat / estop' % kind)


def _read_status(ser, stop, out):
    """后台读串口上的 STATUS，模式一跳就记下来。

    帧的切分复用 `vehicle.bridge.poll_serial_frames`（跨读边界不丢帧，那条有单测），
    新鲜度/乱序/重启重同步复用 `pc.status_rx.StatusReceiver`——**不另写一套解析**，
    否则"探针说通了、记录器说没通"这种分歧就没法解释。
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
            if 'baseline' not in out:
                out['baseline'] = st['mode']   # 发送开始前采到的 mode，判"是不是本次发送引起的"靠它
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
    out = {'good': 0, 'changes': [], 't0': time.time()}   # baseline 由读线程填
    stop = threading.Event()
    th = threading.Thread(target=_read_status, args=(ser, stop, out), daemon=True)
    th.start()
    n = 0
    try:
        time.sleep(0.6)                       # 先确认能听见板子说话，再开始发
        if out['good'] == 0:
            print('注意：前 0.6 秒一个 STATUS 都没读到。先别怪发送——'
                  'USB-TTL 的 RXD 有没有接到板子的 PC6、共地接了没、波特率对不对。')
        for frame in frame_iter:
            ser.write(frame)
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
        print('  %6.2fs  %s -> %s' % (t, MODE_NAME.get(frm, '-'), MODE_NAME.get(to, to)))
    # 09-30 复审（codex 新发现三）打中的正是这里：原来不管发什么都只问"有没有出现过 AUTO"，
    # 于是发 ESTOP（MANUAL→ESTOP 是预期响应）会被判成"一直在 MANUAL，去查接线"，
    # 而发送前本来就是 AUTO 时又会误判"收得进"。现在：先取**发送前基线**，再按命令要的预期
    # 转移来判，并且明确区分"没观察到变化"与"证据不足"。
    base = out.get('baseline')
    expect = EXPECTED.get(a.kind)
    print('发送前基线 mode=%s；本次发的是 %s，预期转移=%s'
          % (MODE_NAME.get(base, base if base is not None else '未采到'),
             a.kind, MODE_NAME.get(expect, '—')))
    seen = {to for _, _, to in out['changes']}
    if out['good'] == 0:
        print('判定：一帧 STATUS 都没读到 ⇒ 这条测试本身不成立（收的方向就没通），'
              '不能对发送方向下任何结论。')
    elif expect is not None and expect in seen and base != expect:
        print('判定：观察到 %s -> %s ⇒ **大板收进了我们发的帧**。'
              % (MODE_NAME.get(base, base), MODE_NAME.get(expect, expect)))
    elif expect in seen:
        print('判定：看到过 %s，但它与发送前基线相同 ⇒ **不能证明是本次发送引起的**，'
              '重测前先确认基线。' % MODE_NAME.get(expect, expect))
    else:
        print('判定：未观察到预期转移（实际看到 %s）。可能是没收到，也可能是'
              'ESTOP 锁存把 NAV/TOOL 正常拒绝了（Fw-14）——两者结论完全不同，'
              '先断电清锁存再测。' % (sorted({MODE_NAME.get(x, str(x)) for _, _, x in out['changes']}) or '无变化'))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('kind', choices=['nav', 'tool', 'beat', 'estop'])
    ap.add_argument('args', nargs='*', help='nav: vL vR (m/s)   tool: mm lift位')
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

    def frames():
        i = 0
        while True:
            yield build(a.kind, a.args, i & 0xFFFF)
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
        print('共发 %d 条。现在去 bench_status 那个窗口看 mode 有没有跳变。' % n)


if __name__ == '__main__':
    main()
