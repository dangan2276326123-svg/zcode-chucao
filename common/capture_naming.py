# -*- coding: utf-8 -*-
"""采集落盘的命名契约（唯一事实源）：录像段号与批次格式。

为什么从 `tools/capture_field.py` 搬进 `common/`：**X5 侧也要算段号**。车上本地录像
（`vehicle/record_local.py`，台账 Pc-20）落的是同一条契约 `t{NN}_{MMDD}_v{NN}.avi`，
而 X5 上只 scp `vehicle/` 与 `common/` 两个目录（执行清单 §部署），`tools/` 在板子上不存在。
契约留在 tools 里就只有两种结局——板子上抄一份，或者现场手改名，两种都会漂
（AGENTS 审查清单第 6 条：消灭单一事实源漂移）。

⚠️ 这个文件**只准依赖标准库**（`os`/`re`）：板子上没有 cv2 也得能 import，
所以别把任何图像处理挪进来。
"""
import os
import re

BATCH_RE = re.compile(r'^t\d{2}$')

VIDEO_PATH = os.path.join('data', 'autumn_data', 'video')


def video_next_index(folder, batch, day):
    """同一批次、同一天里已有的 `_vNN.avi` 最大号 + 1。

    存在理由是清单第 4 节要**三段**视频（逆光 / 阴天 / 任意）：原来 `video_path()` 不带序号，
    同一天同一批次按第二次 `v` 就把第一段**直接冲掉**——`cv2.VideoWriter` 开同名文件是写语义，
    不报错也不留备份，而田里只走这一趟。照片那侧一直有自增序号，视频这侧漏了
    （11-03 读码发现，登记为台账 Pc-16）。
    """
    pat = re.compile(r'^%s_%s_v(\d{2})\.avi$' % (re.escape(batch), re.escape(day)))
    top = 0
    if os.path.isdir(folder):
        for name in os.listdir(folder):
            m = pat.match(name)
            if m:
                top = max(top, int(m.group(1)))
    return top + 1


def video_path(batch, day, index, folder=VIDEO_PATH):
    """`<视频目录>/<批次>_<MMDD>_v<NN>.avi`——序号是必给参数，不许回到无名那一份。"""
    return os.path.join(folder, '%s_%s_v%02d.avi' % (batch, day, index))
