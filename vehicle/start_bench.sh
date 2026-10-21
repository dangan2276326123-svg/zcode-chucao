#!/bin/sh
# X5 台架：一条命令把两件事起起来（09-28 的 start_bridge.sh 只做第一件）。
#   ssh -t sunrise@192.168.127.10 "sh ~/qoder/vehicle/start_bench.sh"
#   只要串口不要相机：末尾加  nostream   （C27 那种架空轮看转角的格子就是这一种，
#                                          见下方"为什么可以不起流"）
#
# 为什么必须带 -t：bridge.py 要 sudo 才能开 /dev/ttyS1（09-28 实测普通用户是
# PermissionError 直接退出）。脚本里先 `sudo -v` 把密码**在前面**要掉，再把 bridge
# 放后台——后台进程自己去读 tty 会被 SIGTTIN 挂住，密码提示就永远等不到答案。
#
# 为什么可以不起流：pc/main.py 的 live 源 `_from_stream()` 是**每个节拍出一条**，
# 没有新帧就出 None（HUD 显示 NO_FRAME、CSV 落 no_frame 行）。所以控制环不依赖相机；
# 起流只是为了看得见画面。
#
# Ctrl-C 一起收掉：stream 在前台，EXIT trap 负责把后台的 bridge 带走，不留孤儿。
pkill -f "cat /dev/ttyS" 2>/dev/null      # 防别的终端 cat 着串口（同 start_bridge.sh）
pkill -f stream_pi.py      2>/dev/null    # 防上一轮没退干净，5000 端口还被占着
cd "$(dirname "$0")" || exit 1

sudo -v || exit 1
sudo python3 bridge.py >/tmp/bridge.log 2>&1 &
BR=$!
trap 'kill $BR 2>/dev/null' INT TERM EXIT
sleep 1

if grep -q "bridge up" /tmp/bridge.log; then
    echo "== bridge up: udp:9000 -> /dev/ttyS1 (pid $BR, log /tmp/bridge.log)"
else
    if kill -0 $BR 2>/dev/null; then
        echo "?? 日志里还没有那行，但进程还在：python3 的 stdout 被重定向到文件时是**块缓冲**，"
        echo "   bridge up 那行可能几十秒才落进 /tmp/bridge.log。所以这句不等于没起来——"
        echo "   判它起没起看笔记本那侧：HUD 收到 STATUS、或 bench_status 出帧即为起。"
    else
        echo "!! bridge 进程已经不在了，那才是真没起来：看 /tmp/bridge.log（多半是 /dev/ttyS1 权限或串口被占）"
    fi
fi

if [ "$1" = "nostream" ]; then
    echo "== stream skipped（只跑串口/控制环的格子用这个）"
    wait $BR
    exit 0
fi

echo "== stream: :5000 1920x1080（Ctrl-C 两个一起停）"
python3 stream_pi.py --width 1920 --height 1080
