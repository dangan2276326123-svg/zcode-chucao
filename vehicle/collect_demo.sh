#!/bin/sh
# 画线漏沙采集 demo（X5 一键）：检查 → 后台开录 → 到点自停；断开 SSH 也不停。
#
# 用法（X5 仓库根目录 ~/qoder 下）:
#   sh vehicle/collect_demo.sh                 # 批次 t20、20 分钟、每段 120 s
#   sh vehicle/collect_demo.sh t21 15 90 1120  # 批次、分钟、每段秒、文件名日期段(MMDD)
#
# 为什么后台：车一开走，网线/SSH 就断；前台进程会跟着 SIGHUP 死在第 N 段。
# 收尾：到点自己停；要提前停，车接回网线后 kill -INT <PID>（本脚本会打印 PID），
# 不要 kill -9 —— AVI 的索引在收尾（EOS）时才写，-9 留下的是打不开的 0 帧文件。

set -u

BATCH=${1:-t20}
MINUTES=${2:-20}
SEG_S=${3:-120}
OUT=data/paint_data/video

cd "$(dirname "$0")/.." || exit 2

DAY=${4:-$(date +%m%d)}
LOG="$OUT/record_${BATCH}_${DAY}.out"
mkdir -p "$OUT"

echo "== 1/2 上板检查（有 🔴 就别开录）=="
CHECK_OUT=$(python3 vehicle/record_local.py --check --probe 2>&1) || {
    RC=$?
    printf '%s\n' "$CHECK_OUT"
    echo "上板检查命令本身失败（退出码 $RC），先查 python3 / 相机 / gst"
    exit 2
}
printf '%s\n' "$CHECK_OUT"
if printf '%s' "$CHECK_OUT" | grep -q '🔴'; then
    echo "检查里有 🔴（见上）⇒ 停手，先解决；别在田里改代码。"
    exit 2
fi

echo
echo "检查没 🔴 就按回车开录；有事按 Ctrl-C 退出。"
if [ -t 0 ]; then
    read -r _ || true
fi

echo "== 2/2 后台开录：$BATCH，$MINUTES 分钟，每段 ${SEG_S}s =="
nohup python3 -u vehicle/record_local.py \
    --batch "$BATCH" --segment-s "$SEG_S" --session-min "$MINUTES" \
    --out "$OUT" --day "$DAY" >"$LOG" 2>&1 &
PID=$!

echo "已开始，PID=$PID。现在可以去遥控了；网线可以拔（后台在跑，不跟着 SSH 死）。"
echo "到点自停。要提前停（车接回网线后）：kill -INT $PID   ← 别用 -9"
echo "进度：tail -f $LOG    进程还在不在：ps -ef | grep record_local"
echo "回来拷：scp -r sunrise@192.168.127.10:~/qoder/$OUT ./paint_video"