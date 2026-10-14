# -*- coding: utf-8 -*-
"""秋采入口的命名契约钉住（C1，时限 2026-10-15）。

这些测试钉的不是"代码能不能跑"，是**田里落下来的文件名对不对**：
`docs/秋季图像采集清单.md` 第 6 节定的是
`raw/{光照}_{视角}_{行况}/t{NN}_{MMDD}_{序号}.jpg`，而 `tools/split_dataset.py`
按批次前缀切 train/val/test、`tools/pre_annotate.py` 按目录扫图 —— 名字或目录错一层，
回来那 240 张就是一片扫不到的孤儿文件，而现场没有第二次机会（草枯了就换域了）。
"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import capture_field as cf        # noqa: E402
from vehicle import stream_pi                # noqa: E402


def test_category_word_order_is_the_checklists_order():
    """键序 1/2/3、4/5/6、7/8/9 直接对应清单矩阵的三档，顺序错了现场就按错。"""
    assert cf.DENSITY == ['clean', 'mid', 'dense']          # 疏 / 中 / 密
    assert cf.LIGHT == ['sun_front', 'sun_back', 'overcast']  # 顺光 / 逆光 / 阴天
    assert cf.VIEW == ['front', 'offsetL', 'offsetR']        # 正对 / 左偏 / 右偏
    assert cf.category(0, 0, 0) == 'sun_front_front_clean'
    assert cf.category(2, 1, 2) == 'overcast_offsetL_dense'


def test_shot_path_matches_the_naming_contract():
    path = cf.shot_path('data/autumn_data/raw/sun_back_offsetL_mid', 't07', '1015', 12)
    name = os.path.basename(path)
    assert re.match(r'^t\d{2}_\d{4}_\d{4}\.jpg$', name), name
    assert name == 't07_1015_0012.jpg'
    assert os.path.dirname(path).endswith('sun_back_offsetL_mid')


def test_batch_pattern_rejects_free_text():
    """批次号是 split_dataset 的分组键：写成 `10-15` 或 `t7` 会让整批归到一个假组。"""
    assert cf.BATCH_RE.match('t01')
    assert cf.BATCH_RE.match('t12')
    for bad in ('1', 't1', 'T01', 't001', 'batch01', '10-15'):
        assert not cf.BATCH_RE.match(bad), bad


def test_next_index_is_max_plus_one_not_file_count(tmp_path):
    """删过一张也不能撞号：撞号会让同一批次里两张图共用一个键。"""
    folder = str(tmp_path / 'overcast_front_dense')
    os.makedirs(folder)
    assert cf.next_index(folder) == 1                       # 空目录
    for n in ('t01_1014_0001.jpg', 't01_1014_0003.jpg'):
        open(os.path.join(folder, n), 'wb').write(b'x')
    assert cf.next_index(folder) == 4                       # 2 个文件，但按最大序号 +1
    open(os.path.join(folder, 'notes.txt'), 'w').write('x')  # 非图文件不参与
    assert cf.next_index(folder) == 4


def test_missing_folder_starts_at_one(tmp_path):
    assert cf.next_index(str(tmp_path / 'never_created')) == 1


# ---- X5 推流参数：默认 720p，秋采要 1080p（清单第 1 节：>=1920x1080） ----

def test_stream_pi_default_stays_720p():
    assert 'width=1280,height=720' in stream_pi.build_pipeline()


def test_stream_pi_can_be_asked_for_1080p():
    cmd = stream_pi.build_pipeline(w=1920, h=1080)
    assert 'width=1920,height=1080' in cmd
    assert 'framerate=30/1' in cmd


def test_stream_pi_port_positional_still_works_and_flag_wins():
    """老命令 `stream_pi.py 6000` 必须照旧能用（现场有人手打过），旗标是同义的。"""
    assert stream_pi.parse_args(['6000'])[0] == 6000
    assert stream_pi.parse_args(['--port', '6000'])[0] == 6000
    assert stream_pi.parse_args([])[0] == stream_pi.PORT
    assert stream_pi.parse_args(['--width', '1920', '--height', '1080'])[1:] == (1920, 1080, 30)


def test_stream_pi_refuses_the_port_given_twice():
    with pytest.raises(SystemExit):
        stream_pi.parse_args(['6000', '--port', '7000'])


def test_stream_pi_rejects_an_ip_where_the_port_belongs():
    """09-22 那条坑：旧文档写 `stream_pi.py 192.168.127.100`，端口位是 int，
    照抄会 ValueError 崩。argparse 至少给一句干净的用法错误。"""
    with pytest.raises(SystemExit):
        stream_pi.parse_args(['192.168.127.100'])
