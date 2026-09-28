# -*- coding: utf-8 -*-
"""PC -> 大板 的链路探针：往 X5 的 bridge 发一帧，看单片机认不认。

为什么需要它：证明链路要**双向**，而现有工具里 `bench_status.py` 只收不发、
`pc/main.py --live` 会发但和记录器抢同一个 UDP 9100、还依赖相机流。车端没接相机
的时候，反向根本没有办法单独验。本工具只发不收（不 bind 端口），所以可以和
记录器同时开。

判据（现场最常用的两条）：
  nav  ->  大板 `retrofit.c:102` 会无条件把 mode 置 AUTO，所以 STATUS 里
           mode 从 MANUAL 跳成 AUTO 就说明"字进了单片机"。
           ⚠ 这是 F1 那个权限洞，我们暂时**拿缺陷当探针**用；E3 补完五条件之后
           这条判据会失效（届时 NAV 不再单独决定进 AUTO），要改用别的探针。
  beat ->  若当前在 AUTO，`retrofit.c:70-73` 会把 mode 放回 MANUAL。

为什么本工具没有新测试：它不含新逻辑——帧构造全部走 `common/protocol.py` 的
`pack_*`（已被 `tests/test_protocol.py` 覆盖），剩下的只有 argparse 分支和一次
`socket.sendto`。写测试只会钉住参数名，钉不住任何行为。
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


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('kind', choices=['nav', 'tool', 'beat', 'estop'])
    ap.add_argument('args', nargs='*', help='nav: vL vR (m/s)   tool: mm lift位')
    ap.add_argument('--host', default='192.168.127.10', help='X5 地址（网桥阶段改这里）')
    ap.add_argument('--port', type=int, default=9000, help='bridge 监听端口')
    ap.add_argument('--every', type=float, default=0.0,
                    help='>0 则周期发送（秒），用于模拟"PC 一直在发"')
    ap.add_argument('--count', type=int, default=0, help='周期发送的条数上限，0=不限')
    a = ap.parse_args()

    if a.kind == 'nav' and len(a.args) != 2:
        sys.exit('nav 需要两个速度参数，例如：nav 0.05 0.05')
    if a.kind == 'tool' and len(a.args) != 2:
        sys.exit('tool 需要 <横移mm> <lift位>，例如：tool 0 7')
    if a.kind == 'nav' and max(abs(float(x)) for x in a.args) > 0.20:
        sys.exit('探针限速 0.20 m/s，别拿它当行车工具——要跑闭环请用 pc/main.py')

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)   # 不 bind：可与记录器共存
    n = 0
    try:
        while True:
            frame = build(a.kind, a.args, n & 0xFFFF)
            sock.sendto(frame, (a.host, a.port))
            n += 1
            print('#%-5d -> %s:%d  %d B  %s' % (n, a.host, a.port, len(frame),
                                                frame.hex(' ')))
            if not a.every:
                break
            if a.count and n >= a.count:
                break
            time.sleep(a.every)
    except KeyboardInterrupt:
        print('中断')
    finally:
        sock.close()
        print('共发 %d 条。现在去 bench_status 那个窗口看 mode 有没有跳变。' % n)


if __name__ == '__main__':
    main()
