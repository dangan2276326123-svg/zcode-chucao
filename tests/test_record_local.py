# -*- coding: utf-8 -*-
"""vehicle/record_local.py — X5 本地录像（台账 Pc-20）。

这些测试钉的是四件**现场会丢数据**的事，不是"函数返回对不对"：

1. **段号与笔记本那一路同源**：`capture_field` 与 `record_local` 必须是同一个函数对象，
   而不是"两份写得一样的实现"——Pc-16 那条（同名开文件是写语义、不报错也不留备份）
   在田里的代价是一整天素材，抄一份迟早漂。
2. **一段不许冲掉另一段**：`plan()` 从已有最大号往上排，`--dry-run` 在未录之前就能看全。
3. **两道闸的形状**：空间那道可以按实测码率商量（`--force`），相机占用与失败退出码**不给越**
   （作者 10-21 拒过"加旁路开关"这一形状：物理与事实不当余量卖）。
4. **占用检测取的哪条命令**：`pgrep -f` 的 stdout 只有 PID、没有命令行，拿它判占用会
   **永远放行**，这道闸形同不存在（本文件初版就是这么错的）。纯文本测试抓不到这种错——
   所以 `test_ps_args_asks_for_command_lines_not_pids` 钉的是**取数用的 argv**，
   与判读那条 `test_stream_running_reads_command_lines_not_pids` 合起来才咬得住。

真机那三处（avimux 在不在、1080p30 实测 MB/s、录出来的文件能不能读出帧数）**这里测不到**：
11-05 登记时 X5 不通电（ping 192.168.127.10 无响应），要靠板子上第一次 `--check --probe`。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from tools import capture_field as cf          # noqa: E402
from tools import extract_frames as ef         # noqa: E402
from vehicle import record_local as rl         # noqa: E402


# ---------- 1) 命名契约同源 ----------

def test_segment_naming_is_the_same_object_as_the_pc_route():
    """不是"写得一样"，是同一个函数——`common/capture_naming.py` 搬过来就为了这个。"""
    assert rl.video_path is cf.video_path
    assert rl.video_next_index is cf.video_next_index
    assert rl.VIDEO_PATH == cf.VIDEO_PATH


def test_video_name_matches_what_extract_frames_parses(tmp_path):
    """record_local 落的名，`extract_frames.parse_video_name` 要能直接读出批次/日期/段号。"""
    p = rl.video_path('t03', '1105', 2, folder=str(tmp_path))
    batch, day, seg, warn = ef.parse_video_name(p)
    assert (batch, day, seg, warn) == ('t03', '1105', 2, None)


# ---------- 2) 段号只增不减 ----------

def test_plan_continues_after_existing_segments(tmp_path):
    (tmp_path / 't01_1105_v01.avi').write_bytes(b'x')
    (tmp_path / 't01_1105_v02.avi').write_bytes(b'x')
    paths = rl.plan(str(tmp_path), 't01', '1105', 3)
    names = [os.path.basename(p) for p in paths]
    assert names == ['t01_1105_v03.avi', 't01_1105_v04.avi', 't01_1105_v05.avi'], names


def test_plan_on_empty_folder_starts_at_v01(tmp_path):
    paths = rl.plan(str(tmp_path / 'no_such'), 't01', '1105', 2)
    assert [os.path.basename(p) for p in paths] == ['t01_1105_v01.avi',
                                                    't01_1105_v02.avi']


def test_plan_segments_never_repeat_a_name(tmp_path):
    """两段重名 = 后一段把前一段冲掉（Pc-16 的原症状），这里按集合钉死。"""
    names = set(os.path.basename(p) for p in rl.plan(str(tmp_path), 't02', '1105', 9))
    assert len(names) == 9


# ---------- 3) gst 那一行 ----------

def test_pipeline_is_argv_list_without_shell(tmp_path):
    argv = rl.pipeline_argv('/tmp/a.avi')
    assert isinstance(argv, list) and argv[0] == 'gst-launch-1.0'
    assert any(tok.startswith('location=/tmp/a.avi') for tok in argv)


def test_pipeline_pins_device_resolution_framerate_and_avimux():
    argv = rl.pipeline_argv('/d/t01_1105_v01.avi', device='/dev/video1',
                            w=1920, h=1080, fps=30)
    joined = ' '.join(argv)
    assert 'device=/dev/video1' in joined
    assert 'image/jpeg,width=1920,height=1080,framerate=30/1' in joined, joined
    assert 'avimux' in joined, '不解码直写 AVI 才是这块 ARM 板扛得住 1080p30 的原因'
    assert 'jpegenc' not in joined and 'x264' not in joined, '重编码会吃满 CPU 还换不来画质'


def test_build_pipeline_is_the_joined_argv():
    """打印给人核的那一行与实际执行的必须是同一条（同一个来源，不许两处拼）。"""
    path = '/d/x.avi'
    assert rl.build_pipeline(path) == ' '.join(rl.pipeline_argv(path))


# ---------- 4) 空间估算与那道可商量的闸 ----------

def test_estimate_mb_scales_with_pixels_and_framerate():
    base = rl.estimate_mb(1920, 1080, 30, 100)
    assert abs(base - rl.MB_PER_S_AT_1080P30 * 100) < 1e-6
    assert rl.estimate_mb(1280, 720, 30, 100) < base, '像素少了占的也该少'
    assert abs(rl.estimate_mb(1920, 1080, 15, 100) * 2 - base) < 1e-6


def test_estimate_is_labelled_as_an_estimate():
    """"估的"两个字必须在给人看的那句里——12 MB/s 没在这块相机上量过（AGENTS 铁律）。"""
    _ok, msg = rl.space_verdict(1e9, 1000.0)
    assert u'估' in msg, msg


def test_space_gate_refuses_below_margin():
    need = 1000.0
    ok, msg = rl.space_verdict(need * (rl.MIN_FREE_FACTOR - 0.01), need)
    assert not ok and u'停手' in msg, msg


def test_space_gate_passes_above_margin():
    ok, _msg = rl.space_verdict(10_000.0, 1000.0)
    assert ok


# ---------- 5) 占用检测：pgrep 的坑 ----------

def test_stream_running_reads_command_lines_not_pids():
    """`pgrep -f` 的 stdout 只有 PID；按它判占用会**永远放行**，这道闸就形同不存在。"""
    assert rl.stream_running('  PID COMMAND\n1234 python3 vehicle/stream_pi.py --width 1920\n')
    assert not rl.stream_running('1234\n')            # pgrep 那种输出：没命令行
    assert not rl.stream_running('')
    assert not rl.stream_running('1234 python3 vehicle/record_local.py --batch t01'), \
        '本工具自己不算占用者'


def test_ps_args_returns_empty_string_off_posix(monkeypatch):
    monkeypatch.setattr(rl, 'is_posix', lambda: False)
    assert rl.ps_args() == ''


def test_ps_args_asks_for_command_lines_not_pids(monkeypatch):
    """判读测的是文本，这条测的是**取数用的是哪条命令**——两条合起来才咬得住 pgrep 那个坑。"""
    seen = {}

    class _Out(object):
        stdout = 'x'

    def fake_run(argv, **kw):
        seen['argv'] = list(argv)
        return _Out()

    monkeypatch.setattr(rl, 'is_posix', lambda: True)
    monkeypatch.setattr(rl.subprocess, 'run', fake_run)
    rl.ps_args()
    assert seen['argv'][:3] == ['ps', '-eo', 'args'], seen['argv']
    assert 'pgrep' not in ' '.join(seen['argv']), (
        'pgrep -f 只印 PID ⇒ stream_running 恒假、相机占用那道闸形同不存在')


# ---------- 6) 日志行 ----------

def test_log_header_and_row_have_the_same_width():
    row = rl.log_row('10:00:00', 't01', '1105', 'a/b.avi', 150, 150.2, 0, 1234,
                     8.1, 4500, '/dev/video0', '1920x1080@30', 'gst')
    assert len(row) == len(rl.LOG_HEADER), (len(row), len(rl.LOG_HEADER))


def test_log_row_uses_forward_slashes_and_blank_for_unknown_frames():
    """反斜杠那件事 capture_log 那侧 10-21 栽过一次；没 cv2 时帧数留**空**不写 0。"""
    row = rl.log_row('10:00:00', 't01', '1105', 'data\\video\\t01.avi', 150, 150, 0,
                     1, 1.0, None, '/dev/video0', '1920x1080@30', 'gst')
    d = dict(zip(rl.LOG_HEADER, row))
    assert d['file'] == 'data/video/t01.avi', d['file']
    assert d['frames_read'] == '', d['frames_read']


def test_verify_file_reports_zero_for_unopenable_path(tmp_path):
    """打不开的文件要报 0 帧而不是抛异常——录完当场就是靠这一句判"这段还在不在"。"""
    got = rl.verify_file(str(tmp_path / 'nope.avi'))
    assert got is None or got[0] == 0, got


# ---------- 7) 入口的硬闸（参数与平台） ----------

@pytest.mark.parametrize('bad', ['t1', 'abc', 't001', '01'])
def test_batch_name_is_checked_at_parse_time(bad):
    with pytest.raises(SystemExit):
        rl.parse_args(['--batch', bad])


def test_segment_seconds_must_be_positive():
    """想停就 Ctrl-C。设 0 会绕过收尾、留下一堆没有索引的 AVI——所以直接不给。"""
    with pytest.raises(SystemExit):
        rl.parse_args(['--segment-s', '0'])
    with pytest.raises(SystemExit):
        rl.parse_args(['--segments', '0'])


def test_dry_run_prints_every_segment_and_nothing_else(tmp_path, capsys):
    rc = rl.main(['--batch', 't05', '--segments', '2', '--out', str(tmp_path),
                  '--day', '1105', '--dry-run'])
    out = capsys.readouterr().out
    assert rc == 0
    assert out.count('t05_1105_v') == 2, out
    assert u'估' in out, '打印的占量要带"估"字'
    assert os.listdir(str(tmp_path)) == [], '--dry-run 不许在盘上留东西'


def test_refuses_to_record_on_the_laptop(monkeypatch, capsys):
    """本工具的录像那一路只能在 X5（Linux）跑；笔记本要的是 capture_field。"""
    monkeypatch.setattr(rl, 'is_posix', lambda: False)
    rc = rl.main(['--batch', 't01'])
    out = capsys.readouterr().out
    assert rc == 2 and u'停手' in out and 'capture_field' in out, out


def test_space_gate_blocks_before_recording(monkeypatch, capsys):
    monkeypatch.setattr(rl, 'is_posix', lambda: True)
    monkeypatch.setattr(rl, 'free_mb', lambda folder: 5.0)
    called = []
    monkeypatch.setattr(rl, 'record', lambda *a, **k: called.append(a))
    rc = rl.main(['--batch', 't01', '--segments', '4', '--segment-s', '150'])
    assert rc == 2 and not called, capsys.readouterr().out


def test_force_passes_space_but_still_blocks_a_busy_camera(monkeypatch, capsys):
    """--force 只越"码率是估的"这一道；相机占用是物理，不给越。"""
    monkeypatch.setattr(rl, 'is_posix', lambda: True)
    monkeypatch.setattr(rl, 'free_mb', lambda folder: 5.0)
    monkeypatch.setattr(rl, 'ps_args',
                        lambda: '1234 python3 vehicle/stream_pi.py --width 1920')
    called = []
    monkeypatch.setattr(rl, 'record', lambda *a, **k: called.append(a))
    rc = rl.main(['--batch', 't01', '--force'])
    out = capsys.readouterr().out
    assert rc == 2 and not called, out
    assert 'pkill -f stream_pi.py' in out, out
    assert u'不给 --force 越' in out, out


# ---------- 8) extract_frames 要认识这条新链路 ----------

def test_extract_frames_accepts_the_x5_30fps_chain():
    assert 30.0 in ef.CHAIN_FPS and 25.0 in ef.CHAIN_FPS, \
        '笔记本那一路 25、X5 本地 30，两种都是本链路的正常值'


def test_extract_frames_still_warns_about_a_foreign_fps(tmp_path, capsys):
    v = tmp_path / 't07_1105_v01.avi'
    import cv2
    vw = cv2.VideoWriter(str(v), cv2.VideoWriter_fourcc(*'MJPG'), 12.0, (64, 48))
    import numpy as np
    for _ in range(24):
        vw.write(np.zeros((48, 64, 3), dtype='uint8'))
    vw.release()
    ef.extract(str(v), str(tmp_path / 'out'), 'sun_front_front_clean',
               stride_m=1.0, speed_mps=1.0, skip_s=0.0)
    out = capsys.readouterr().out
    assert '12.00 fps' in out and '25' in out and '30' in out, out


@pytest.mark.parametrize('fps', [25.0, 30.0])
def test_chain_fps_do_not_warn(tmp_path, capsys, fps):
    """25 = 笔记本 capture_field 那一路，30 = X5 record_local 那一路。

    把 CHAIN_FPS 退回只认 25，这条就该红——否则田里回来的每一段都白挨一句警告，
    而"警告满天飞"的下一步就是人把它关掉。
    """
    import cv2
    import numpy as np
    v = tmp_path / 't08_1105_v01.avi'
    vw = cv2.VideoWriter(str(v), cv2.VideoWriter_fourcc(*'MJPG'), fps, (64, 48))
    for _ in range(int(fps * 2)):
        vw.write(np.zeros((48, 64, 3), dtype='uint8'))
    vw.release()
    ef.extract(str(v), str(tmp_path / 'out'), 'sun_front_front_clean',
               stride_m=1.0, speed_mps=1.0, skip_s=0.0)
    out = capsys.readouterr().out
    assert '自报' not in out, out

def test_platform_check_goes_through_is_posix():
    """调用点不许再写 `os.name`——写了就等于把"能被测试替换"换成"能被打崩全局"。"""
    import inspect
    src = inspect.getsource(rl)
    assert src.count("os.name == 'posix'") == 1, src.count("os.name == 'posix'")
    assert src.count('if os.name') == 0, '平台判据只许在 is_posix() 里读 os.name'

