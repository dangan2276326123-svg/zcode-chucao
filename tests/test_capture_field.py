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

def test_capture_log_path_column_never_mixes_separators():
    """`capture_log` 的 path 列在 Windows 上也要用正斜杠（10-21 第一次真跑落出来的）。

    那天在笔记本上跑通 12 张，回头读日志发现这一列是混的：
    `data/autumn_data/_smoke_1021\\sun_front_front_mid\\t01_1021_0001.jpg`——前半是
    `/`（`--out` 传进来的写法）、后半是 `\`（`os.path.join` 在 Windows 上给的）。
    人眼看无所谓，但事后拿前缀过滤、跨机比对路径的脚本会**静默漏匹配**：
    秋采日志是唯一能对数的东西，它不该有一种写法只对一半。
    """
    win = os.path.join("data", "raw", "sun_front_front_mid", "t01_1021_0001.jpg")
    row = cf.log_row("17:03:36", win, (720, 960, 3), 0.023)
    assert chr(92) not in row[1], row[1]
    assert row[1].endswith("sun_front_front_mid/t01_1021_0001.jpg")
    assert row[2] == "960x720"          # 分辨率列 = 宽x高，别写反
    assert row[3] == "0.02"
    assert cf.log_row("17:03:36", "a/b/c.jpg", (720, 960, 3), None)[3] == ""   # 无帧龄留空不写 0


# ---- 视频那一侧的撞名（11-03 读码发现，登记为台账 Pc-16） --------------------

def test_three_videos_in_one_batch_get_three_names(tmp_path):
    """清单第 4 节要**三段**视频（逆光 / 阴天 / 任意），而 `cv2.VideoWriter` 开同名文件
    是写语义：旧写法 `t01_1105.avi` 连按三次 `v` 就只剩最后一段，且不报错、田里只走一趟。"""
    assert cf.video_next_index(str(tmp_path), 't01', '1105') == 1
    (tmp_path / 't01_1105_v01.avi').write_bytes(b'x')
    assert cf.video_next_index(str(tmp_path), 't01', '1105') == 2
    (tmp_path / 't01_1105_v02.avi').write_bytes(b'x')
    assert cf.video_next_index(str(tmp_path), 't01', '1105') == 3
    names = [cf.video_path('t01', '1105', i, folder=str(tmp_path)) for i in (1, 2, 3)]
    assert len(set(names)) == 3, names
    assert names[2].endswith('t01_1105_v03.avi'), names[2]


def test_video_index_ignores_other_batches_and_other_days(tmp_path):
    """序号只在"同批次同一天"里数——跨批次借号会把两次走动混成一个文件名的邻居，
    而分组键看的正是批次首段（清单第 6 节那条数据有效性警告）。"""
    for name in ('t02_1105_v07.avi', 't01_1106_v05.avi', 't01_1105.jpg',
                 't01_1105_vX.avi', 'capture_log_t01_1105.csv'):
        (tmp_path / name).write_bytes(b'x')
    assert cf.video_next_index(str(tmp_path), 't01', '1105') == 1


def test_record_video_asks_for_the_next_index():
    """文本钉：`record_video()` 必须现取序号。签名改三参以后漏处会 TypeError，
    但那条报错要到田里按第二次 `v` 才看得见——所以钉在源码上，不靠运行。"""
    import io
    import os as _os
    here = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    text = io.open(_os.path.join(here, 'tools', 'capture_field.py'),
                   encoding='utf-8').read()
    i = text.find('def record_video(')
    assert i > 0
    body = text[i:i + 1400]
    assert 'video_path(a.batch, day, video_next_index(VIDEO_PATH, a.batch, day))' in body, body[:600]
