# -*- coding: utf-8 -*-
"""tools/bench_run.py — 台架一键入口。

这些测试钉的不是"函数返回对不对"，而是三个原始症状：
  1. **开法**：§5B/§5C 那三条命令的必需段（`ssh -t`、`nostream`、`--live`、
     `--stream-host 127.0.0.1`、不许 `--no-gui`）在一条命令里一个都不能少——
     少一个就是"桥没起 / HUD 没键 / 全窗 no_frame"那一类现场；
  2. **谁在哪个窗**：桥与合成流必须各占一个新控制台（`ssh -t` 的 sudo 密码要有人可输），
     主控必须留在本窗（stdout 与 CSV 路径才跟着它一起看得见）；
  3. **证据目录不许复用**：`run_log.csv` 是覆盖写的，10-14 那次三份证据冲成一份就是这么来的。

`start_support` 的 `popen` / `sleep` / `probe` 全部注入，所以这个文件里**不会真起 ssh**，
也不会碰网络。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import bench_run as br          # noqa: E402


class _Args(object):
    """替 argparse 的产物：只放 plan_commands 真正读的那几格。"""

    def __init__(self, **kw):
        self.source = kw.get('source', br.DEFAULT_SOURCE)
        self.fps = kw.get('fps', br.DEFAULT_FPS)
        self.no_fake = kw.get('no_fake', False)
        self.deploy = kw.get('deploy', False)
        self.stream_host = kw.get('stream_host', br.STREAM_HOST)
        self.stream_port = kw.get('stream_port', br.STREAM_PORT)


def _cmds(**kw):
    return br.plan_commands(_Args(**kw), r'PY.EXE', r'REPO', r'REPO\results\bench_x')


def _argv(name_part, cmds):
    for name, argv, _nc in cmds:
        if name_part in name:
            return ' '.join(argv)
    raise AssertionError('no command matching %r in %r' % (name_part, [c[0] for c in cmds]))


# ---- 1. 必需段一个都不能少 ----------------------------------------------

def test_bridge_command_carries_the_two_documented_musts():
    """`-t` 与 `nostream` 都是现场踩出来的：**没有 -t** ⇒ bridge 开 /dev/ttyS1 直接
    PermissionError；**没有 nostream** ⇒ X5 那路同时在发帧，日志里每一行 `dual`
    都说不清是谁拍的（§5B/§5C 第 4 步的原话）。"""
    s = _argv('bridge', _cmds())
    assert 'ssh -t' in s, s
    assert 'start_bench.sh nostream' in s, s
    assert '192.168.127.10' in s, s


def test_main_command_is_the_live_gui_form():
    """`--no-gui` 会把 `[A]`/`[T]`/`[E]` 那一整段按键绕开 ⇒ 这一键没进去是"屏上有字、
    板子没动"的那种排查地狱。所以钉三样：live、流地址、以及**不许出现 --no-gui**。"""
    s = _argv('main.py', _cmds())
    assert '--live' in s and '--stream-host 127.0.0.1' in s, s
    assert '--out' in s, s
    assert '--no-gui' not in s, s


def test_fake_stream_command_pins_source_and_fps():
    s = _argv('fake_cam', _cmds())
    assert '--source' in s and '--fps' in s, s
    assert br.DEFAULT_SOURCE in s, s


def test_order_is_bridge_then_stream_then_main():
    names = [n for n, _a, _x in _cmds()]
    assert len(names) == 3, names
    assert 'bridge' in names[0] and 'fake_cam' in names[1] and 'main.py' in names[2], names


def test_no_fake_drops_the_stream_and_keeps_bridge_and_main():
    """C22 那一类格（"流本来就该断"）用 `--no-fake`；这时不许再起合成流。"""
    names = [n for n, _a, _x in _cmds(no_fake=True)]
    assert len(names) == 2 and not any('fake_cam' in n for n in names), names


def test_deploy_pushes_only_what_lives_on_the_x5():
    """X5 上只有 `vehicle/` 与 `common/`；把 `pc/` 或 `tools/` 推过去是错的口径
    （§4A 第 67 行：改 `tools/`、`pc/` 是笔记本侧的事）。"""
    s = _argv('deploy', _cmds(deploy=True))
    assert 'scp -r' in s and 'vehicle' in s and 'common' in s, s
    for bad in ('main.py', 'fake_cam.py'):
        assert bad not in s, s


# ---- 2. 谁在哪个窗 -------------------------------------------------------

class _FakePopen(object):
    def __init__(self):
        self.calls = []

    def __call__(self, argv, cwd=None, creationflags=0):
        self.calls.append((argv, cwd, creationflags))
        return ('handle', tuple(argv))


def test_support_processes_get_their_own_console_and_main_stays_in_this_one():
    cmds = _cmds()
    assert cmds[-1][2] is False, '主控那条必须留在本窗'
    assert all(c[2] is True for c in cmds[:-1]), '桥与合成流各占一个新窗'
    popen = _FakePopen()
    probes = []
    launched = br.start_support(cmds, r'REPO', '127.0.0.1', 5000, popen=popen,
                                sleep=lambda s: None,
                                probe=lambda h, p: probes.append((h, p)) or {'frames': 7})
    assert len(launched) == 2, launched
    assert [c[2] for c in popen.calls] == [br.CREATE_NEW_CONSOLE, br.CREATE_NEW_CONSOLE]
    assert [c[1] for c in popen.calls] == [r'REPO', r'REPO'], 'cwd 必须是仓库根'
    assert probes == [('127.0.0.1', 5000)], '起了合成流就要探一次流'


def test_probe_is_skipped_when_the_stream_is_not_started():
    cmds = _cmds(no_fake=True)
    probes = []
    br.start_support(cmds, r'REPO', '127.0.0.1', 5000, popen=_FakePopen(),
                     sleep=lambda s: None,
                     probe=lambda h, p: probes.append(h) or {'frames': 0})
    assert probes == [], '没起合成流却去探流，会把 --no-fake 那一类格卡住 2 秒'


# ---- 3. 证据目录不许复用 -------------------------------------------------

def test_fresh_out_dir_never_returns_an_existing_directory():
    taken = set()

    def exists(p):
        return p in taken

    first = br.fresh_out_dir('results', tag='bench', stamp='20261103_101112', exists=exists)
    taken.add(first)
    second = br.fresh_out_dir('results', tag='bench', stamp='20261103_101112', exists=exists)
    taken.add(second)
    third = br.fresh_out_dir('results', tag='bench', stamp='20261103_101112', exists=exists)
    assert first.endswith('bench_20261103_101112'), first
    assert second.endswith('bench_20261103_101112-2'), second
    assert third.endswith('bench_20261103_101112-3'), third
    assert len({first, second, third}) == 3, (first, second, third)


def test_main_refuses_an_out_dir_that_already_has_a_run_log(tmp_path, capsys):
    """停手要停在**起进程之前**：这一条若放到后面，桥窗与合成流窗已经弹出来了，
    作者得先关两个窗再重开，现场比改目录名更容易出错。

    测试本身带 `--dry-run`：万一有人把这道闸拆了，这条也只该以 rc 变 0 失败，
    **不该在单测里真去 ssh 车上或弹一个窗出来**。
    """
    d = tmp_path / 'results_old'
    d.mkdir()
    (d / 'run_log.csv').write_text('t\n')
    rc = br.main(['--out', str(d), '--dry-run'])
    captured = capsys.readouterr().out
    assert rc == 2, rc
    assert 'run_log.csv' in captured and '停手' in captured, captured


# ---- 4. 探流那句读数要能指到行动 -----------------------------------------

def test_verdict_names_the_shape_that_fooled_us_on_1021():
    """10-21 那一跑 1749 拍全 `no_frame` 而 HUD 看着正常（11-03 靠 `latency_ms=0.0` 才反推
    出来，台账 Pc-15 的订正）。所以 0 帧这句话必须**自己说出后果**，不能只说"没帧"。"""
    s = br.stream_verdict({'frames': 0, 'connect_fails': 0, 'decode_fail': 0})
    assert s.startswith('[WARN]'), s
    assert 'no_frame' in s and 'latency_ms' in s, s
    s2 = br.stream_verdict({'frames': 0, 'connect_fails': 3, 'decode_fail': 0})
    assert 'connect_fails=3' in s2, s2
    ok = br.stream_verdict({'frames': 31, 'connect_fails': 0, 'decode_fail': 0})
    assert ok.startswith('[OK]') and '31' in ok, ok


def test_probe_failure_is_reported_as_a_probe_failure_not_as_a_healthy_stream():
    """探流自己炸了（没装 cv2、端口被占）不许被读成"流是好的"——本仓判据：读不到的量留空。"""
    cmds = _cmds()

    def boom(host, port):
        raise RuntimeError('no cv2')

    logs = []
    br.start_support(cmds, r'REPO', '127.0.0.1', 5000, popen=_FakePopen(),
                     sleep=lambda s: None, probe=boom, say=logs.append)
    text = '\n'.join(logs)
    assert '探流本身失败' in text, text
    assert '[OK]' not in text, text


# ---- 5. 源图这一道硬闸（不许有旁路） --------------------------------------

def test_missing_source_stops_before_any_window_opens(tmp_path, capsys):
    """带错路径往下跑，落下来的只是一份全程 `no_frame` 的 CSV——10-21 那一跑就是这么过去的
    （台账 Pc-15 的 11-03 订正）。所以这不是提示，是 `return 2`。

    测试带 `--dry-run`：闸要是被人拆了，这条也只该以 rc 变 0 失败，不许真去起进程。
    """
    rc = br.main(['--source', str(tmp_path / 'nope.jpg'), '--dry-run'])
    out = capsys.readouterr().out
    assert rc == 2, out[-400:]
    assert '停手' in out and '--no-fake' in out, out


def test_no_fake_makes_the_missing_source_harmless(tmp_path):
    """C22 那一类格要的就是"没有流"，不许被源图闸拦在门外。"""
    assert br.source_missing(_Args(source=str(tmp_path / 'nope.jpg'), no_fake=False)) is True
    assert br.source_missing(_Args(source=str(tmp_path / 'nope.jpg'), no_fake=True)) is False


def test_verdict_names_the_port_it_was_given():
    """指错端口的那句话比没说更糟：他会去翻另一个窗。"""
    s = br.stream_verdict({'frames': 0, 'connect_fails': 1}, host='127.0.0.1', port=5055)
    assert '5055' in s and '127.0.0.1' in s, s
