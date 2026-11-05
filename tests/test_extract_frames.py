# -*- coding: utf-8 -*-
"""`tools/extract_frames.py` —— 抽帧那条路（作者 11-03："能走抽帧的走抽帧，剩下的拍照"）。

钉的是四件会让数据集出事的事：
  1. **间隔从位移与走速算出来**，不是拍脑袋的帧数——走快走慢对应的米数不一样；
  2. **批次与日期从视频名读**，抽出来的帧沿用同一个批次号（`split_dataset.py` 按首段分组，
     一段视频=一组，近重复帧不可能跨集合）；
  3. **同一个视频不许重抽**，重抽会得到同一批画面的第二套序号，换个名字就跨进训练与测试；
  4. 命名与日志走的是 `capture_field` 那一套（`shot_path` / `next_index`），**不另写一遍**
     （AGENTS 审查清单第 2 条：把被判据保护的东西复制一份，判据就管不住它了）。

真视频用 `cv2.VideoWriter` 现造（25 fps、每帧一个不同的灰度值，好核对到底抽的是第几帧）。
"""
import csv
import os
import sys

import cv2
import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import extract_frames as ef        # noqa: E402


def make_avi(path, n=60, fps=25.0):
    """每帧灰度值 = 帧号，事后能一眼看出抽的是第几帧。"""
    vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*'MJPG'), fps, (64, 48))
    for i in range(n):
        vw.write(np.full((48, 64, 3), i % 255, dtype='uint8'))
    vw.release()
    return path


def video_in(tmp_path, name='t07_1105_v01.avi', n=60, fps=25.0):
    d = os.path.join(str(tmp_path), 'video')
    os.makedirs(d, exist_ok=True)
    return make_avi(os.path.join(d, name), n=n, fps=fps)


def out_root(tmp_path):
    return os.path.join(str(tmp_path), 'raw')


# ---- 1. 间隔怎么来 ------------------------------------------------------

def test_step_comes_from_stride_and_walk_speed():
    assert ef.stride_to_step(1.0, 1.0, 25) == 25        # 1 m @ 1 m/s、25 fps
    assert ef.stride_to_step(0.5, 1.0, 25) == 13        # 清单第 3 节那条 ≥0.5 m
    assert ef.stride_to_step(1.0, 0.5, 25) == 50        # 走慢一半 ⇒ 间隔翻倍
    assert ef.stride_to_step(1.0, 1.0, 30) == 30        # 帧率变了就跟着变
    for bad in ((0, 1.0, 25), (1.0, 0, 25), (1.0, 1.0, 0), (-1, 1.0, 25)):
        with pytest.raises(ValueError):
            ef.stride_to_step(*bad)


# ---- 2. 名字里读出批次与日期 --------------------------------------------

def test_batch_and_day_come_from_the_video_name():
    assert ef.parse_video_name('x/y/t07_1105_v02.avi') == ('t07', '1105', 2, None)
    batch, day, seg, warn = ef.parse_video_name('t07_1105.avi')
    assert (batch, day, seg) == ('t07', '1105', 0)
    assert warn and 'Pc-16' in warn, warn          # 旧命名（不带段号）要认出来并说清后果
    for bad in ('IMG_0001.avi', 't7_1105_v01.avi', 't07_11055_v01.avi'):
        with pytest.raises(ValueError):
            ef.parse_video_name(bad)


def test_category_vocabulary_is_the_capture_field_one():
    assert ef.check_category('sun_front_front_mid') == 'sun_front_front_mid'
    for bad in ('sun_front_front_mid ', 'sunlight_front_mid', 'front_mid', ''):
        with pytest.raises(ValueError):
            ef.check_category(bad)


# ---- 3. 真抽一遍：命名、日志、数量 --------------------------------------

def test_extract_writes_the_naming_contract_and_a_log(tmp_path):
    v = video_in(tmp_path, n=60)
    r = ef.extract(v, out_root(tmp_path), 'sun_back_front_mid',
                   stride_m=1.0, speed_mps=1.0, skip_s=1.0, verbose=False)
    folder = r['folder']
    names = sorted(os.listdir(folder))
    assert r['step_frames'] == 25
    assert names == ['t07_1105_0001.jpg', 't07_1105_0002.jpg'], names
    assert r['written'] == 2
    # 抽到的必须是第 25 与第 50 帧（0 基）：灰度值就是帧号。MJPG 有损，只能就近认，
    # 所以断言写成"离 25 比离 50 近得多"而不是等于——等于会把编解码器的量化噪声当成缺陷。
    img = cv2.imread(os.path.join(folder, names[0]), cv2.IMREAD_GRAYSCALE)
    m = float(img.mean())
    assert abs(m - 25) <= 4 and abs(m - 50) > 10, m
    lp = r['log']
    rows = list(csv.DictReader(open(lp, encoding='utf-8', newline='')))
    assert [x['frame_idx'] for x in rows] == ['25', '50'], rows
    assert rows[0]['video'] == 't07_1105_v01.avi'
    assert rows[0]['step_frames'] == '25'
    assert rows[0]['path'].startswith('data') or 'raw/sun_back_front_mid' in rows[0]['path']
    assert rows[1]['est_move_m'] == '1.00', rows      # 第二张距第一张正好一个 stride


def test_dry_run_writes_nothing(tmp_path):
    v = video_in(tmp_path, n=60)
    root = out_root(tmp_path)
    r = ef.extract(v, root, 'sun_front_front_clean', dry_run=True, verbose=False)
    assert r['written'] == 2
    assert not os.path.exists(root), os.listdir(root) if os.path.exists(root) else ''


def test_indices_continue_from_what_is_already_on_disk(tmp_path):
    """`next_index` 用的是 capture_field 那一个：删过一张也不会撞号，续到最大 +1。"""
    v = video_in(tmp_path, n=60)
    root = out_root(tmp_path)
    folder = os.path.join(root, 'sun_front_front_clean')
    os.makedirs(folder)
    open(os.path.join(folder, 't07_1105_0005.jpg'), 'wb').write(b'x')
    r = ef.extract(v, root, 'sun_front_front_clean', verbose=False)
    assert sorted(os.listdir(folder)) == ['t07_1105_0005.jpg', 't07_1105_0006.jpg',
                                          't07_1105_0007.jpg']


# ---- 4. 同一个视频不许重抽 ----------------------------------------------

def test_rerunning_the_same_video_is_refused_unless_overwritten(tmp_path):
    v = video_in(tmp_path, n=60)
    root = out_root(tmp_path)
    ef.extract(v, root, 'sun_front_front_mid', verbose=False)
    with pytest.raises(RuntimeError) as e:
        ef.extract(v, root, 'sun_front_front_mid', verbose=False)
    assert '停手' in str(e.value) and '--overwrite' in str(e.value)
    # 拒绝之后磁盘上不许多出一张（第二套序号 = 近重复帧跨集合的入口）
    assert len(os.listdir(os.path.join(root, 'sun_front_front_mid'))) == 2
    ef.extract(v, root, 'sun_front_front_mid', overwrite=True, verbose=False)
    assert len(os.listdir(os.path.join(root, 'sun_front_front_mid'))) == 4


def test_a_different_video_of_the_same_batch_is_allowed(tmp_path):
    """换一段走动就该是新的一批内容：拒绝只针对同一个文件。"""
    a = video_in(tmp_path, name='t07_1105_v01.avi', n=60)
    b = os.path.join(os.path.dirname(a), 't07_1105_v02.avi')
    make_avi(b, n=60)
    root = out_root(tmp_path)
    ef.extract(a, root, 'sun_front_front_mid', verbose=False)
    r = ef.extract(b, root, 'sun_front_front_mid', verbose=False)
    assert r['segment'] == 2 and r['written'] == 2


def test_fps_other_than_the_recorder_writes_is_flagged(tmp_path, capsys):
    """录制器写死 25 fps；自报值不是 25 说明这文件不是本链路录的，位移换算得重算。"""
    v = video_in(tmp_path, n=60, fps=12.0)
    ef.extract(v, out_root(tmp_path), 'sun_front_front_mid', stride_m=1.0,
               speed_mps=1.0, verbose=True)
    out = capsys.readouterr().out
    assert '12.00 fps' in out and '25' in out, out
