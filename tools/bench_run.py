# -*- coding: utf-8 -*-
"""台架一键：把【X5 起桥】+【合成流】+【主控】三步收成一条命令（笔记本侧入口，非准入工具）。

为什么要这个：§5B／§5C 那两节里，笔记本要开三个窗、敲三条命令，而且顺序不能乱——
桥没起来就开主控 ⇒ HUD 全程 `MCU:STALE`；合成流路径写错 ⇒ 全程 `no_frame` 而 HUD 看着正常
（10-21 那一跑 1749 拍全是 `no_frame`，作者以为在跑，11-03 才被 `latency_ms=0.0` 反推出来，
见台账 Pc-15 的订正）。这两件事都不是判据问题，是**开法**问题，所以入口收成一条。

    python -B tools/bench_run.py                     # 默认：桥 + 合成流 + 主控
    python -B tools/bench_run.py --dry-run           # 只打印预检与三条命令，一个进程都不起
    python -B tools/bench_run.py --source <照片路径>  # 换第 2 步挑出来的那张图
    python -B tools/bench_run.py --no-fake           # 只要串口/控制环那类格（C22 那种"流本来就该断"）
    python -B tools/bench_run.py --deploy            # 先把 vehicle/ 与 common/ 推到 X5（改过才需要）
    python -B tools/bench_run.py --out results/my_01 # 指定输出目录（已存在则停手，run_log.csv 是覆盖写）

**这条命令替掉的是"怎么开"，不替任何判据与安全前置**：四轮架空、刀物理锁死、电池插头在手边、
按 `[A]` 之前核 HUD 那三样、拨油门杆——全部照 §5B/§5C 原样由人做。合成流是暂时的替代品，
它降低的是取景要求，不降低安全要求。

输出里不用 emoji：这台机器的控制台是 cp936，🔴/⚠️ 一类符号重定向时会抛（本仓踩过的坑）。
"""
import argparse
import datetime
import os
import subprocess
import sys
import time

X5_USER_HOST = 'sunrise@192.168.127.10'
BRIDGE_REMOTE = 'sh ~/qoder/vehicle/start_bench.sh nostream'
DEFAULT_SOURCE = (u'D:/JetBrains/chucao_prj/model_data/train/images/'
                  u'img_000070.jpg')
DEFAULT_FPS = 15
STREAM_HOST = '127.0.0.1'
STREAM_PORT = 5000
PROBE_S = 2.0
CREATE_NEW_CONSOLE = 0x00000010      # 每个外部进程占一个自己的控制台窗
PROFILE_YAML = os.path.join('config', 'vehicle_profile.yaml')


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _bad_arg(s):
    """cmd 元字符与换行不许混进路径——参数是按 argv 传的，但 `--deploy` 那一条走 scp，
    留一个字符校验比事后排查便宜。"""
    return any(c in s for c in ('&', '<', '>', '|', '^', '\n', '\r'))


def fresh_out_dir(results_dir, tag='bench', stamp=None, exists=os.path.exists):
    """默认输出目录：`results/<tag>_<YYYYMMDD_HHMMSS>`；撞上已存在就在名字后面加 -2/-3/…。

    `run_log.csv` 是覆盖写的（§5B 第 6 步那条警告）——宁可换个名字也不复用旧目录，
    10-14 那次三份证据冲成一份就是这么来的。
    """
    s = stamp or datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    cand = os.path.join(results_dir, '%s_%s' % (tag, s))
    n = 1
    while exists(cand):
        n += 1
        cand = os.path.join(results_dir, '%s_%s-%d' % (tag, s, n))
    return cand


def plan_commands(args, py, root, out_dir):
    """要跑的三条（或四条）命令，按**启动顺序**返回 [(窗口名, argv, 是否新窗口)]。

    返回的是 argv 列表而不是字符串——列表交给 `Popen` 不经过 cmd 解析，路径里的空格
    不会被拆成两条命令；测试钉的就是这些 argv 里必须出现的段。
    """
    cmds = []
    if args.deploy:
        cmds.append((u'0 deploy: vehicle/ + common/ -> X5',
                     ['scp', '-r', os.path.join(root, 'vehicle'),
                      os.path.join(root, 'common'), X5_USER_HOST + ':~/qoder/'],
                     True))
    cmds.append((u'1 X5 bridge (nostream)',
                 ['ssh', '-t', X5_USER_HOST, BRIDGE_REMOTE], True))
    if not args.no_fake:
        cmds.append((u'2 fake_cam synthetic stream',
                     [py, '-B', os.path.join(root, 'tools', 'fake_cam.py'),
                      '--source', args.source, '--fps', '%g' % args.fps], True))
    cmds.append((u'3 pc/main.py (this window)',
                 [py, '-B', os.path.join(root, 'pc', 'main.py'), '--live',
                  '--stream-host', args.stream_host,
                  '--stream-port', '%d' % args.stream_port,
                  '--out', out_dir], False))
    return cmds


def source_missing(args, exists=os.path.exists):
    """合成流的源图不存在吗？——这一条是**硬闸**，不是提示。

    理由就是 11-03 从台账 Pc-15 里挖出来的那件事：路径写错时 `pc/main.py` 不报任何异常，
    HUD 照常刷、CSV 每拍落 `no_frame`、`latency_ms` 恒 0，一整跑下来没人知道它没在看画面。
    `--no-fake` 时不适用（那种格要的就是"没有流"）。
    """
    return (not args.no_fake) and not exists(args.source)


def stream_verdict(stats, seconds=PROBE_S, host=STREAM_HOST, port=STREAM_PORT):
    """把探流那一圈的计数翻成一句人能照着行动的话。纯函数，好单测。"""
    frames = int(stats.get('frames', 0))
    fails = int(stats.get('connect_fails', 0))
    dfail = int(stats.get('decode_fail', 0))
    if frames <= 0:
        if fails > 0:
            return ('[WARN] %s:%d 连不上（connect_fails=%d）：合成流那一窗要么没起来、'
                    '要么端口不是这个。今天这一跑 HUD 会全程 NO_FRAME、CSV 全程 no_frame。'
                    '要的就是"流该断"那一类格（C22）就当没这句，否则回那一窗看横幅。'
                    % (host, port, fails))
        return ('[WARN] %s:%d 连着但 %.1f s 内 0 帧：要么 fake_cam 用了 `--once` 播完了、'
                '要么 --fps 太小。CSV 里每拍都会是 no_frame，`latency_ms` 恒 0——'
                '那正是 10-21 被当成"在跑"的那个形状。' % (host, port, seconds))
    extra = ('，decode_fail=%d' % dfail) if dfail else ''
    return '[OK] 合成流在发帧：%d 帧 / %.1f s%s' % (frames, seconds, extra)


def probe_stream(host=STREAM_HOST, port=STREAM_PORT, seconds=PROBE_S, sleep=time.sleep):
    """开一条自己的 StreamFeed 数几秒帧——不碰 main.py 那条链，只回答"那一窗到底在不在发"。"""
    from common.mjpeg import StreamFeed
    feed = StreamFeed(host, port)
    t_end = time.monotonic() + seconds
    while time.monotonic() < t_end:
        sleep(0.05)
    stats = feed.close()
    return stats


def preflight(args, root, exists=os.path.exists, py=None):
    """开跑前的六行打印。全部是"看一眼就知道对不对"的那种，不做任何判据。"""
    py = py or sys.executable
    out = []
    out.append('[i] 解释器：%s' % py)
    out.append('[i] 仓库根：%s' % root)
    # 第 3 步"核三行"变成看一眼打印——值本身还是他自己确认，这里只替他把 yaml 读出来。
    # 格式照抄主控启动行（`vehicle profile: id=1 permit=1 tag=prev`），两处读数长得一样才好互证。
    try:
        sys.path.insert(0, root)
        from pc import vehicle_profile
        prof = vehicle_profile.load(os.path.join(root, PROFILE_YAML))
        out.append('[i] 车辆档案：id=%s permit=%s tag=%s'
                   '（§5B 第 3 步要看的就是这三个值）'
                   % (prof['profile_id'], prof['permit'], prof['log_tag']))
    except Exception as exc:
        out.append('[WARN] 车辆档案读不出来：%s：%s' % (type(exc).__name__, exc))
    if args.no_fake:
        out.append('[i] 合成流：不起（--no-fake，只跑串口/控制环那一类格）')
    elif source_missing(args, exists):
        out.append('[!] 源图不存在：%s ⇒ 这一跑必然全程 no_frame、`latency_ms` 恒 0'
                   '（台账 Pc-15 那条订正），所以入口直接停手，连合成流那个窗都不弹'
                   % args.source)
    else:
        out.append('[i] 合成流源：%s（--fps %g）' % (args.source, args.fps))
    try:
        import cv2
        has_gui = hasattr(cv2, 'imshow')
        out.append('%s GUI 那条路：%s（手操键 [T] 与 W/S/D 长在 cv2 窗口上，'
                   'headless 装法会让它们无声失效）'
                   % ('[OK]' if has_gui else '[!]', 'cv2 有 imshow' if has_gui
                      else 'cv2 **没有 imshow**（多半是 opencv-python-headless）'))
    except Exception as exc:
        out.append('[!] cv2 导入失败：%s：%s' % (type(exc).__name__, exc))
    return out


def say(text):
    sys.stdout.write(text + '\n')
    sys.stdout.flush()


def start_support(cmds, root, stream_host, stream_port, popen=subprocess.Popen,
                  sleep=time.sleep, probe=None, say=say):
    """起"支撑"那几样（deploy / X5 桥 / 合成流），每样一个新控制台窗，然后探一次合成流。

    `popen` / `sleep` / `probe` 都可注入：单测用假 popen 钉"谁在新窗、谁留在本窗、顺序对不对"，
    不在测试里真起 ssh。**最后一个命令（主控）不在这里起**——它要留在本窗，stdout 与 CSV 才跟着它一起看得见。
    """
    probe = probe or probe_stream
    launched = []
    for name, argv_cmd, new_console in cmds[:-1]:
        launched.append((name, popen(argv_cmd, cwd=root,
                                     creationflags=CREATE_NEW_CONSOLE if new_console else 0)))
        say('[i] 起了 %s' % name)
        if 'bridge' in name:
            say('    -> 那个窗要 sudo 密码（ttyS1 要 root，09-28 实测）；输完等到它打印 '
                '== bridge up 或那句"判它起没起看笔记本那侧"')
    if any('fake_cam' in n for n, _c, _x in cmds[:-1]):
        sleep(1.0)
        try:
            say('[i] 探合成流 %.1f s …' % PROBE_S)
            say('    ' + stream_verdict(probe(stream_host, stream_port),
                                        host=stream_host, port=stream_port))
        except Exception as exc:
            say('[!] 探流本身失败：%s：%s（不代表流是好的，也不代表主控不能跑）'
                % (type(exc).__name__, exc))
    return launched


def build_parser():
    ap = argparse.ArgumentParser(
        description='台架一键：X5 起桥 + 合成流 + 主控（不替任何判据与安全前置）')
    ap.add_argument('--source', default=DEFAULT_SOURCE, help='合成流那一张照片/那个目录')
    ap.add_argument('--fps', type=float, default=DEFAULT_FPS, help='合成流帧率（默认 15）')
    ap.add_argument('--out', default=None, help='本次 run_log.csv 的目录（默认自动新起一个）')
    ap.add_argument('--tag', default='bench', help='自动目录名的前缀')
    ap.add_argument('--no-fake', action='store_true', help='不起合成流（只要串口/控制环）')
    ap.add_argument('--deploy', action='store_true',
                    help='先把 vehicle/ 与 common/ scp 到 X5（改过这两处才需要）')
    ap.add_argument('--stream-host', default=STREAM_HOST)
    ap.add_argument('--stream-port', type=int, default=STREAM_PORT)
    ap.add_argument('--dry-run', action='store_true', help='只打印，不起任何进程')
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    root = repo_root()
    py = sys.executable
    if args.out:
        out_dir = args.out
        if os.path.exists(os.path.join(out_dir, 'run_log.csv')):
            say('[!] 停手：%s 里已经有 run_log.csv——它是覆盖写的，'
                '换个目录名或先把它挪走（§5B 第 6 步那条警告）' % out_dir)
            return 2
    else:
        out_dir = fresh_out_dir(os.path.join(root, 'results'), tag=args.tag)
    say('=' * 76)
    say('台架一键（§5B/§5C 的"开法"收成一条；判据一条不替）')
    say('安全前置仍在人这一侧：四轮架空、三路刀物理锁死或拆下、电池插头在手边、'
        '禁止实车 AUTO、禁止按现有接线文档带动力接线')
    say('=' * 76)
    for line in preflight(args, root, py=py):
        say(line)
    if source_missing(args):
        say('[!] 停手：`--source` 指的东西不存在（上面那条 [!] 说的就是这件事）。')
        say('    要么改路径（§5B 第 2 步挑出来的那张），要么这一跑本来就不要画面 ⇒ 加 `--no-fake`。')
        say('    这一道闸不给旁路开关：带着错路径往下跑，落下来的是一份全程 no_frame 的 CSV，'
            '看起来"跑过了"。')
        return 2
    cmds = plan_commands(args, py, root, out_dir)
    say('[i] 输出目录：%s' % out_dir)
    say('')
    for name, argv_cmd, new_console in cmds:
        say('    %s%s' % (name, '  [新窗口]' if new_console else '  [本窗]'))
        say('        ' + subprocess.list2cmdline(argv_cmd))
    if args.dry_run:
        say('')
        say('[i] --dry-run：一个进程都没起。')
        return 0
    if any(_bad_arg(a) for _n, c, _x in cmds for a in c if isinstance(a, str)):
        say('[!] 停手：参数里有 cmd 元字符（& < > | ^ 换行），不换写法不要跑这一条')
        return 2

    say('')
    start_support(cmds, root, args.stream_host, args.stream_port)
    say('[i] 现在起主控：%s' % subprocess.list2cmdline(cmds[-1][1]))
    say('[!] HUD 里没有 `MCU:m` ⇒ 桥那一段没通，回第一个窗看；不要按 [A]')
    rc = subprocess.call(cmds[-1][1], cwd=root)
    say('')
    say('[i] 主控退出 rc=%d。收尾两步：先回到 X5 那个窗按 Ctrl-C（桥跟着 trap 一起走，'
        '别留孤儿），再关合成流那个窗')
    say('[i] 本次证据目录：%s' % out_dir)
    say('    （回填 §5B/§5C 时发回来的就是这个路径，别只发"跑完了"）')
    return rc


if __name__ == '__main__':
    sys.exit(main())
