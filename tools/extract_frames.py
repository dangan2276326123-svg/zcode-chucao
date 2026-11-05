# -*- coding: utf-8 -*-
"""从采集视频抽帧，按命名契约落成训练可用的图片（作者 11-03 定的路子："能走抽帧的走抽帧，剩下的拍照"）。

为什么走这条路：**夏季那批数据本来就是抽帧来的**（`docs/缺口清单.md` §G 那行
`avi_project/295 帧抽帧 frames1`），所以抽出来的帧与训练集在同一条 artifact 链上，域更一致；
田里也不用一边走一边按空格——一段视频 = 一个条件 = 一个批次，比手动换批次更干净
（`tools/split_dataset.py` 按文件名首段分组，一段连续拍摄天然就是一组，近重复帧不会跨集合）。

三条规矩写死在这里，不守住就是给自己挖坑：

1. **抽帧间隔按位移算，不按感觉算**：`--stride-m`（默认 1.0 m，清单第 3 节要求 ≥0.5 m）
   除以 `--speed`（走速 m/s，**田里要掐一次秒表**）再乘视频帧率。间隔按帧数写死是错的，
   因为走快走慢对应的米数不一样。
2. **一段视频只对应一种条件**：条件用 `--category` 一次给整段（词表与 `capture_field.py`
   同源，不许自己编），标签事后没法逐帧补。
3. **筛帧只筛训练集**：拿现有权重跑一遍挑 `status=dual` 是 S0 那一步，但**验证/测试集不许
   用模型筛**——模型提不出墙的帧正是最该留在测试集里的失败样本，扔了它们验证分数就虚高。
   本工具不做任何筛选，它只按间隔抽，筛是下游的事。

还有一条是读码读出来的坑：`capture_field.record_video()` 遇到 `f is None` 就 `continue`，
所以**流断续会让视频的时间轴不连续**——按帧号推位移会偏。工具因此把"帧号 / 视频内时刻 /
估计位移"三样一起写进 `extract_log_*.csv`，事后可查；同时如果 avi 自报的帧率既不是笔记本
那一路写死的 25、也不是 X5 本地录像（`vehicle/record_local.py`，台账 Pc-20）的 30，
会打一条警告——那说明这个文件不是本链路录的，位移换算得重算。

⚠️ 路径别带中文：这台机器上 `cv2.VideoCapture` 打不开含 CJK 的路径（本仓记过），
工具开头就检查并给人话提示，不要等到抽出一半才发现。
"""
import argparse
import csv
import math
import os
import re
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from tools.capture_field import (BATCH_RE, DENSITY, JPG_QUALITY, LIGHT,  # noqa: E402
                                 VIEW, next_index, shot_path)

VIDEO_NAME_RE = re.compile(r'^(t\d{2})_(\d{4})_v(\d{2})\.avi$', re.IGNORECASE)
LEGACY_NAME_RE = re.compile(r'^(t\d{2})_(\d{4})\.avi$', re.IGNORECASE)
RECORD_FPS = 25.0          # capture_field.record_video 里写死的那个 25
X5_RECORD_FPS = 30.0       # vehicle/record_local.py（Pc-20）按相机原生 MJPG 1080p30 录
CHAIN_FPS = (RECORD_FPS, X5_RECORD_FPS)   # 本工具链的两种来源，别的都算"来路不明"
VALID_CATEGORIES = set('%s_%s_%s' % (l, v, d)
                       for l in LIGHT for v in VIEW for d in DENSITY)


def parse_video_name(path):
    """从视频文件名读 (批次, 日期, 第几段)。

    Pc-16 之前的旧录像没有 `_vNN` 那一段，那种也能读（返回段号 0），但会另给一条警告——
    旧命名下同一个批次同一天只可能有一个文件，说明那次录制根本没有防撞号。
    """
    base = os.path.basename(path)
    m = VIDEO_NAME_RE.match(base)
    if m:
        return m.group(1).lower(), m.group(2), int(m.group(3)), None
    m = LEGACY_NAME_RE.match(base)
    if m:
        return m.group(1).lower(), m.group(2), 0, (
            u'旧命名（Pc-16 之前）：%s 里没有 _vNN 段号；这一支的录像名不带序号，'
            u'同批次同一天会互相冲掉' % base)
    raise ValueError(u'认不出这个视频名：%s —— 采集录像应当是 t{NN}_{MMDD}_v{NN}.avi '
                     u'（批次_日期_段号）' % base)


def stride_to_step(stride_m, speed_mps, fps):
    """位移间隔 -> 帧间隔，**向上取整**：清单第 3 节那个 ≥0.5 m 是下限，
    四舍五入会把间隔压到 12 帧（0.48 m）而悄悄违反下限（11-03 测试就是这么抓到的——
    Python 3 的 `round(12.5)` 还会银行家舍入到 12，更不该用）。"""
    if stride_m <= 0 or speed_mps <= 0 or fps <= 0:
        raise ValueError(u'stride/speed/fps 都得是正数（收到 %s / %s / %s）'
                         % (stride_m, speed_mps, fps))
    return max(1, int(math.ceil(stride_m / float(speed_mps) * float(fps))))


def check_category(cat):
    if cat not in VALID_CATEGORIES:
        raise ValueError(u'类别名不对：%s。词表 = {光照}_{视角}_{行况}，'
                         u'光照 %s / 视角 %s / 行况 %s（与 capture_field 的键序同源）'
                         % (cat, '/'.join(LIGHT), '/'.join(VIEW), '/'.join(DENSITY)))
    return cat


def log_path(out_root, batch, day):
    return os.path.join(out_root, 'extract_log_%s_%s.csv' % (batch, day))


LOG_HEADER = ['video', 'frame_idx', 't_s', 'est_move_m', 'step_frames', 'path']


def already_extracted(lp, video_base):
    """这个视频是不是已经抽过？抽过就停手——再抽一遍会得到同一批画面的第二套序号，
    近重复帧换了个名字跨进训练与测试，正是清单第 6 节警告的那个形状。"""
    if not os.path.exists(lp):
        return False
    with open(lp, encoding='utf-8', newline='') as f:
        for row in csv.DictReader(f):
            if row.get('video') == video_base:
                return True
    return False


def extract(video, out_root, cat, stride_m=1.0, speed_mps=1.0, step=None,
            skip_s=1.0, dry_run=False, overwrite=False, verbose=True):
    import cv2
    if not os.path.exists(video):
        raise IOError(u'视频不存在：%s' % video)
    if any(ord(c) > 127 for c in video):
        raise ValueError(u'视频路径里有非 ASCII 字符（%s）——这台机器上 cv2 打不开这种路径，'
                         u'先把文件挪到纯英文路径' % video)
    batch, day, seg, warn = parse_video_name(video)
    if warn and verbose:
        print(u'[!] ' + warn)
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        raise IOError(u'打不开视频：%s（编解码器缺？路径中文？）' % video)
    fps = cap.get(cv2.CAP_PROP_FPS) or RECORD_FPS
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if min(abs(fps - c) for c in CHAIN_FPS) > 0.5 and verbose:
        print(u'[!] 这个视频自报 %.2f fps，不是本工具链的两种录制帧率（capture_field 那条 '
              u'%.0f、X5 本地录像那条 %.0f）⇒ 位移换算按自报值算，但请确认它是哪来的'
              % (fps, RECORD_FPS, X5_RECORD_FPS))
    step = int(step) if step else stride_to_step(stride_m, speed_mps, fps)
    skip = max(0, int(round(skip_s * fps)))
    folder = os.path.join(out_root, cat)
    lp = log_path(out_root, batch, day)
    if not overwrite and already_extracted(lp, os.path.basename(video)):
        cap.release()
        raise RuntimeError(u'停手：%s 已经在 %s 里抽过一次（重抽会得到同一批画面的第二套序号，'
                           u'近重复帧换个名字就跨进训练与测试了）。确实要重抽加 --overwrite'
                           % (os.path.basename(video), lp))
    idx = next_index(folder) if (folder and os.path.isdir(folder)) else 1
    rows, n_written, n_read = [], 0, 0
    if not dry_run:
        os.makedirs(folder, exist_ok=True)
    if verbose:
        print(u'[i] %s：批次 %s、日期 %s、段 v%02d；fps=%.2f 总帧=%d；间隔 %d 帧 ≈ %.2f m '
              u'@ %.2f m/s；开头跳过 %d 帧'
              % (os.path.basename(video), batch, day, seg, fps, total, step,
                 step / fps * speed_mps, speed_mps, skip))
    want = skip
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        n_read += 1
        if n_read <= want:
            continue
        if (n_read - skip - 1) % step == 0:
            path = shot_path(folder, batch, day, idx) if not dry_run else \
                os.path.join(folder, '%s_%s_%04d.jpg' % (batch, day, idx))
            if not dry_run:
                cv2.imwrite(path, frame, [cv2.IMWRITE_JPEG_QUALITY, JPG_QUALITY])
            rows.append([os.path.basename(video), n_read - 1,
                         '%.3f' % ((n_read - 1) / fps),
                         '%.2f' % ((n_read - 1 - skip) / fps * speed_mps),
                         step, path.replace('\\', '/')])
            idx += 1
            n_written += 1
    cap.release()
    if verbose:
        print(u'[i] 读了 %d 帧，%s %d 张，覆盖位移约 %.1f m'
              % (n_read, u'将要写' if dry_run else u'写出', n_written,
                 n_written * step / fps * speed_mps))
    # 日志与 verbose 无关：早先这段缩进在 `if verbose:` 里面，于是 `verbose=False` 调用
    # 时不写日志，"同一个视频不许重抽"那道闸就形同不存在（11-03 测试抓到）。
    if not dry_run and rows:
        new = not os.path.exists(lp)
        with open(lp, 'a', encoding='utf-8', newline='') as f:
            w = csv.writer(f)
            if new:
                w.writerow(LOG_HEADER)
            w.writerows(rows)
        if verbose:
            print(u'[i] 日志：%s' % lp)
    return {'batch': batch, 'day': day, 'segment': seg, 'category': cat,
            'fps': fps, 'step_frames': step, 'frames_read': n_read,
            'written': n_written, 'rows': rows, 'log': lp, 'folder': folder}


def build_parser():
    ap = argparse.ArgumentParser(
        description='采集视频抽帧 -> 命名契约下的图片（不做任何筛选，筛是下游的事）')
    ap.add_argument('video', help='data/autumn_data/video/tNN_MMDD_vNN.avi')
    ap.add_argument('--category', required=True,
                    help='整段共用一个条件标签：{光照}_{视角}_{行况}，如 sun_front_front_mid')
    ap.add_argument('--out', default=os.path.join('data', 'autumn_data', 'raw'),
                    help='图片根目录（默认与 capture_field 同一处）')
    ap.add_argument('--stride-m', type=float, default=1.0,
                    help='抽帧位移间隔，米（清单第 3 节要求 ≥0.5；默认 1.0）')
    ap.add_argument('--speed', type=float, default=1.0,
                    help='走速 m/s —— 田里掐一次秒表，别猜')
    ap.add_argument('--step', type=int, default=None,
                    help='直接给帧间隔（给了就不看 stride/speed）')
    ap.add_argument('--skip-s', type=float, default=1.0,
                    help='开头丢掉几秒（起步、对准、画面糊的那几帧）')
    ap.add_argument('--dry-run', action='store_true', help='只报数，不落盘、不写日志')
    ap.add_argument('--overwrite', action='store_true',
                    help='允许对同一个视频重抽（默认拒绝，见文件头第 3 条）')
    return ap


def main(argv=None):
    a = build_parser().parse_args(argv)
    t0 = time.time()
    try:
        check_category(a.category)
        r = extract(a.video, a.out, a.category, stride_m=a.stride_m,
                    speed_mps=a.speed, step=a.step, skip_s=a.skip_s,
                    dry_run=a.dry_run, overwrite=a.overwrite)
    except (ValueError, IOError, RuntimeError) as exc:
        print(u'[!] %s' % exc)
        return 2
    print(u'[i] 完成：%s -> %s（%d 张，%.1f s）'
          % (os.path.basename(a.video), r['folder'], r['written'], time.time() - t0))
    return 0


if __name__ == '__main__':
    sys.exit(main())
