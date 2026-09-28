#!/bin/sh
# X5 侧一条命令起桥（09-28 加）。用法，在 X5 上：
#     sh ~/qoder/vehicle/start_bridge.sh
# 它做两件本来要分开敲的事：
#   1) 清掉会跟 bridge 抢 /dev/ttyS1 的 `cat`——两个读者同读一个串口会把帧撕成半截，
#      谁都解不出来，而笔记本那边看到的是"一帧都没有"，很容易误判成接线问题。
#   2) 用 sudo 起 bridge。09-28 实测：普通用户开不了 /dev/ttyS1，不带 sudo 会直接
#      PermissionError 退出，而它退出后笔记本的 CSV 是空的——所以这一步不能省。
#      想彻底省掉 sudo：`sudo usermod -aG dialout sunrise` 后重新登录（**未在本机验证**，
#      见 docs/X5验机与接入执行清单.md §0A）。
# 起来的那行凭证是 `bridge up: udp:9000 -> /dev/ttyS1`，没看见就是没起来。
pkill -f "cat /dev/ttyS" 2>/dev/null
cd "$(dirname "$0")" || exit 1
exec sudo python3 bridge.py
