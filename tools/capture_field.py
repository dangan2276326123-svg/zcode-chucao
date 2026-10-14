# -*- coding: utf-8 -*-
"""秋季田间图像采集入口（C1，时限 2026-10-15）。

为什么要有这个文件：采集清单 `docs/秋季图像采集清单.md` 定了命名契约
`raw/{光照}_{视角}_{行况}/t{NN}_{MMDD}_{序号}.jpg`，而现有工具里**没有任何一个**能
按它落盘 —— `tools/stream_view.py` 的 `s` 键存的是 `results/stream_view_HHMMSS.png`，
名字、格式、目录三样全不对，`tools/pre_annotate.py` 扫不到。田里那两天没空对着
文档手改文件名，所以把契约写进按键里。

用法（笔记本，X5 侧先把 1080p 流推起来，见 vehicle/stream_pi.py 的 --width/--height）：

    python -B tools/capture_field.py --batch t01

按键（全部单键，HUD 上实时显示当前类别与序号）：

    空格   落一张 JPG（当前类别目录，序号自增）
    1/2/3  行况：疏 clean / 中 mid / 密 dense
    4/5/6  光照：顺光 sun_front / 逆光 sun_back / 阴天 overcast
    7/8/9  视角：正对 front / 左偏 offsetL / 右偏 offsetR
    v      录一段 30 秒验证视频（清单第 4 节，不进训练集）
    q      退出（落一张 capture_log.csv 到输出根目录）

不做的：不做去重、不做位移判定（清单要求帧间 ≥0.5 m，那是人眼在现场判断的事）。
"""
import argparse
import csv
import datetime
import os
import re
import socket
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from common import mjpeg  # StreamFeed：有界读，不会把这里挂死

# 类别词表：与 docs/秋季图像采集清单.md 第 1-2 节的矩阵一一对应。
# 顺序就是 1/2/3、4/5/6、7/8/9 的键序，别重排——重排了现场按错。
LIGHT = ['sun_front', 'sun_back', 'overcast']
VIEW = ['front', 'offsetL', 'offsetR']
DENSITY = ['clean', 'mid', 'dense']

BATCH_RE = re.compile(r'^t\d{2}$')
JPG_QUALITY = 95


def category(light_i, view_i, dens_i):
    """目录名 = {光照}_{视角}_{行况}（清单第 6 节的命名契约）。"""
    return '%s_%s_%s' % (LIGHT[light_i], VIEW[view_i], DENSITY[dens_i])


def next_index(folder):
    """该类别目录里已有的最大序号 + 1。

    按文件名里的序号取，不按文件数——中间删过一张也不会有两张同号，
    而 `split_dataset.py` 是按批次前缀切 train/val/test 的，撞号会串数据。
    """
    pat = re.compile(r'_(\d{4})\.jpg$')
    top = 0
    if os.path.isdir(folder):
        for name in os.listdir(folder):
            m = pat.search(name)
            if m:
                top = max(top, int(m.group(1)))
    return top + 1


def shot_path(folder, batch, day, index):
    """<out>/<类别>/<批次>_<MMDD>_<序号>.jpg"""
    return os.path.join(folder, '%s_%s_%04d.jpg' % (batch, day, index))


VIDEO_PATH = os.path.join('data', 'autumn_data', 'video')


def video_path(batch, day):
    return os.path.join(VIDEO_PATH, '%s_%s.avi' % (batch, day))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--host', default='192.168.127.10')
    ap.add_argument('--port', type=int, default=5000)
    ap.add_argument('--out', default=os.path.join('data', 'autumn_data', 'raw'))
    ap.add_argument('--batch', default='t01')
    ap.add_argument('--video-s', type=int, default=30, help='v 键录多长（清单要求 ≥30s）')
    a = ap.parse_args()

    if not BATCH_RE.match(a.batch):
        # 批次号是 split_dataset 切分的依据，写错了整批数据会归到一个假批次里。
        sys.exit('--batch 要写成 tNN（如 t01），收到 %r' % a.batch)

    import cv2
    import numpy as np              # 没画面时那块兜底画布要用它

    feed = mjpeg.StreamFeed(a.host, a.port, recv_timeout=0.05)
    day = datetime.date.today().strftime('%m%d')
    li = vi = di = 0
    saved = 0
    log = []
    last_shot = None
    last_noframe_print = 0.0

    print('capture: %s:%d  out=%s  batch=%s  day=%s' % (a.host, a.port, a.out, a.batch, day))
    print('keys: SPACE=shot  1/2/3=density  4/5/6=light  7/8/9=view  v=video  q=quit')
    try:
        while True:
            frame, age = feed.get(max_age_s=2.0)
            cat = category(li, vi, di)
            if frame is not None:
                h, w = frame.shape[:2]
                vis = frame.copy()
                cv2.putText(vis, '%s  %s_%s_####  %dx%d' % (cat, a.batch, day, w, h),
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
            else:
                # 没画面也要开窗：否则现场看到的是"程序没反应"，而真实原因可能是
                # X5 上 stream_pi 没起、或者相机 USB 又掉了（台账记过两次 dmesg -71）。
                vis = np.zeros((720, 1280, 3), 'uint8')
                cv2.putText(vis, 'NO FRAME - is stream_pi.py running on the X5?',
                            (20, 360), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
                cv2.putText(vis, 'camera USB drop shows the same way: ls /dev/video*',
                            (20, 400), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                cv2.putText(vis, 'category now: %s' % cat,
                            (20, 450), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                if time.time() - last_noframe_print > 5.0:
                    last_noframe_print = time.time()
                    print('no frame from %s:%d (st=%s)' % (a.host, a.port,
                                                           feed.snapshot()[0].get(
                                                               'connect_fails', '?')))
            cv2.putText(vis, 'SPACE=shot 123=dens 456=light 789=view v=video q=quit  '
                             'saved=%d' % saved,
                        (10, 62 if frame is not None else 500),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            cv2.imshow('capture', vis)
            k = cv2.waitKey(1) & 0xFF
            if frame is None:
                continue
            if k == ord('q'):
                break
            elif k == ord('1'):
                di = 0
            elif k == ord('2'):
                di = 1
            elif k == ord('3'):
                di = 2
            elif k == ord('4'):
                li = 0
            elif k == ord('5'):
                li = 1
            elif k == ord('6'):
                li = 2
            elif k == ord('7'):
                vi = 0
            elif k == ord('8'):
                vi = 1
            elif k == ord('9'):
                vi = 2
            elif k == ord(' '):
                folder = os.path.join(a.out, category(li, vi, di))
                os.makedirs(folder, exist_ok=True)
                idx = next_index(folder)
                path = shot_path(folder, a.batch, day, idx)
                cv2.imwrite(path, frame, [cv2.IMWRITE_JPEG_QUALITY, JPG_QUALITY])
                saved += 1
                last_shot = time.time()
                log.append([time.strftime('%H:%M:%S'), path, '%dx%d' % (frame.shape[1],
                                                                         frame.shape[0]),
                            '' if age is None else '%.2f' % age])
                print('saved %s' % path)
            elif k == ord('v'):
                saved_v = record_video(a, feed, day)
                if saved_v:
                    print('video -> %s' % saved_v)
    finally:
        feed.close()
        cv2.destroyAllWindows()
        if log:
            os.makedirs(a.out, exist_ok=True)
            lp = os.path.join(a.out, 'capture_log_%s_%s.csv' % (a.batch, day))
            with open(lp, 'w', newline='', encoding='utf-8') as f:
                wr = csv.writer(f)
                wr.writerow(['hhmmss', 'path', 'resolution', 'frame_age_s'])
                wr.writerows(log)
            print('%d shots -> %s ; log %s' % (saved, a.out, lp))


def record_video(a, feed, day):
    """录 --video-s 秒到 data/autumn_data/video/<批次>_<日期>.avi（清单第 4 节）。"""
    import cv2
    frame, _ = feed.get(max_age_s=2.0)
    if frame is None:
        print('no frame yet, video not started')
        return None
    h, w = frame.shape[:2]
    os.makedirs(VIDEO_PATH, exist_ok=True)
    path = video_path(a.batch, day)
    vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*'MJPG'), 25, (w, h))
    t_end = time.time() + a.video_s
    n = 0
    while time.time() < t_end:
        f, _age = feed.get(max_age_s=2.0)
        if f is None:
            continue
        if f.shape[:2] != (h, w):
            continue          # 分辨率中途变了就丢这一帧，别让 Writer 悄悄截断
        vw.write(f)
        n += 1
        cv2.putText(f, 'REC %ds' % int(t_end - time.time()), (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
        cv2.imshow('capture', f)
        if (cv2.waitKey(1) & 0xFF) == ord('q'):
            break
    vw.release()
    print('video frames=%d' % n)
    return path


if __name__ == '__main__':
    main()
