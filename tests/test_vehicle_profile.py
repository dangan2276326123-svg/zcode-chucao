# -*- coding: utf-8 -*-
"""E3 批 1b Task 5：车辆档案加载器（spec §6）。

这个文件守的是一件安全事：档案里的 profile_id 决定一切米<->像素换算，
permit 决定门 N 期间刀能不能落。读不到就用默认值 = 让车带着错参数进无人，
所以"缺失/非法"必须报错停下。下面的 raises 用例都在钉这一条。
"""
import os

import pytest

from common import protocol as P
from pc import vehicle_profile as VP
from pc import wire

# 独立于被测模块推导仓库根（不用它的算法去验它的算法）。
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_FILE = os.path.join(REPO_ROOT, 'config', 'vehicle_profile.yaml')


def _write(tmp_path, text):
    p = tmp_path / 'vehicle_profile.yaml'
    p.write_text(text, encoding='utf-8')
    return str(p)


# ---------- brief Step 1 的 5 条（逐字照抄）----------
def test_load_repo_default():
    cfg = VP.load()
    assert cfg['profile_id'] in (P.PROFILE_PREV, P.PROFILE_REAL)
    assert cfg['permit'] in (wire.GATE_N, wire.GATE_F)


def test_load_parses_both_fields(tmp_path):
    p = _write(tmp_path, 'profile_id: 2\npermit: gate_f\n')
    cfg = VP.load(p)
    assert cfg['profile_id'] == P.PROFILE_REAL
    assert cfg['permit'] == wire.GATE_F


def test_missing_file_raises(tmp_path):
    with pytest.raises(ValueError):
        VP.load(str(tmp_path / 'nope.yaml'))


def test_unknown_permit_name_raises(tmp_path):
    with pytest.raises(ValueError):
        VP.load(_write(tmp_path, 'profile_id: 1\npermit: gate_x\n'))


def test_bad_profile_id_raises(tmp_path):
    for bad in ('profile_id: 0\npermit: gate_n\n',
                'profile_id: 3\npermit: gate_n\n',
                'permit: gate_n\n'):
        with pytest.raises(ValueError):
            VP.load(_write(tmp_path, bad))


# ---------- 默认路径：相对仓库根，不靠当前工作目录 ----------
def test_default_path_matches_repo_layout():
    assert VP.DEFAULT_PATH == os.path.join('config', 'vehicle_profile.yaml')
    assert os.path.isfile(DEFAULT_FILE), DEFAULT_FILE


def test_default_load_does_not_depend_on_cwd(tmp_path, monkeypatch):
    # 台架脚本真实的调用方式：cwd 可能是 tools/ 或任何目录。
    monkeypatch.chdir(tmp_path)
    cfg = VP.load()
    assert os.path.normpath(cfg['path']) == os.path.normpath(DEFAULT_FILE)
    assert cfg == VP.load(DEFAULT_FILE)


# ---------- permit 的数字只能来自 wire.PERMIT_BY_NAME（不许第二份表）----------
def test_permit_number_comes_from_wire_mapping(tmp_path, monkeypatch):
    monkeypatch.setitem(wire.PERMIT_BY_NAME, 'gate_z', 99)
    cfg = VP.load(_write(tmp_path, 'profile_id: 1\npermit: gate_z\n'))
    assert cfg['permit'] == 99


def test_permit_name_removed_from_wire_is_rejected(tmp_path, monkeypatch):
    monkeypatch.delitem(wire.PERMIT_BY_NAME, 'gate_f')
    with pytest.raises(ValueError):
        VP.load(_write(tmp_path, 'profile_id: 2\npermit: gate_f\n'))


def test_gate_n_name_maps_to_wire_gate_n(tmp_path):
    cfg = VP.load(_write(tmp_path, 'profile_id: 1\npermit: gate_n\n'))
    assert cfg['permit'] == wire.GATE_N


# ---------- 其余 fail-fast 形态 ----------
def test_empty_file_raises(tmp_path):
    with pytest.raises(ValueError):
        VP.load(_write(tmp_path, ''))


def test_non_integer_profile_id_raises(tmp_path):
    for bad in ('profile_id: one\npermit: gate_n\n',
                'profile_id: 1.5\npermit: gate_n\n',
                'profile_id: \npermit: gate_n\n'):
        with pytest.raises(ValueError):
            VP.load(_write(tmp_path, bad))


def test_comments_are_not_read_as_keys(tmp_path):
    # 档案注释里就有 "# profile_id: 1 = PREV ..." 这种行；值后面也可能有人加行尾注释。
    text = ('# profile_id: 9 = 注释里的假键\n'
            '#permit: gate_f\n'
            'profile_id: 1\n'
            'permit: gate_n   # 秋季门 N\n')
    cfg = VP.load(_write(tmp_path, text))
    assert cfg['profile_id'] == P.PROFILE_PREV
    assert cfg['permit'] == wire.GATE_N


def test_non_utf8_file_raises_value_error(tmp_path):
    # 本仓 firmware 是 GBK：万一有人用 GBK 存了这个 yaml，要报错而不是静默读出鬼值。
    p = tmp_path / 'vehicle_profile.yaml'
    p.write_bytes('profile_id: 1\npermit: gate_n\n#'.encode('utf-8') + b'\xd6\xd0\xce\xc4')
    with pytest.raises(ValueError):
        VP.load(str(p))


def test_returns_exactly_the_three_contract_keys(tmp_path):
    cfg = VP.load(_write(tmp_path, 'profile_id: 2\npermit: gate_f\n'))
    assert sorted(cfg) == ['path', 'permit', 'profile_id']
    assert isinstance(cfg['profile_id'], int)
    assert isinstance(cfg['permit'], int)
    assert isinstance(cfg['path'], str) and os.path.isabs(cfg['path'])
    # 相对路径进来也必须绝对出去（Task 6 要把这个路径写进日志取证）。
    assert os.path.isabs(VP.load(VP.DEFAULT_PATH)['path'])


# ---------- Task 6 前置：Task 5 审查 P1/P2/P3（三条都必须先钉住）----------
def test_missing_permit_key_raises(tmp_path):
    """P3：只有 profile_id 一行、permit 键整体缺失也必须抛。

    实现今天就走 kv.get('permit') -> None 不在 PERMIT_BY_NAME -> ValueError，
    但没有任何用例钉着：谁把它"顺手"改成 kv.get('permit', 'gate_n')，
    门 N 就会被静默当成写在档案里的值。
    """
    with pytest.raises(ValueError):
        VP.load(_write(tmp_path, 'profile_id: 1'))


def test_directory_path_raises_value_error(tmp_path):
    """P1：契约是"读不到 => ValueError"，而"存在但打不开"旧实现漏在外面。

    os.path.exists(目录) 为真，之后裸 open() 抛 PermissionError（OSError 子类、
    **不是** ValueError）。调用方（pc/main.py）按 except ValueError 决定
    "能不能进无人"，这条路径就会漏成崩溃；编辑器锁文件/杀软占用是同一形态。
    """
    d = tmp_path / 'vehicle_profile.yaml'
    d.mkdir()
    with pytest.raises(ValueError):
        VP.load(str(d))


def test_empty_path_does_not_fall_back_to_default(tmp_path):
    """P2：`path = path or DEFAULT_PATH` 让 '' 静默读默认档案。

    传空串的人想的是"我没指定路径"，拿到的是**另一台车**的换算量与许可位——
    这正好绕开了本文件存在的全部理由。契约：未指定一律传 None。
    """
    with pytest.raises(ValueError):
        VP.load('')
    # 默认值仍然只在 None 时生效（别把修法做过头）
    assert VP.load(None)['profile_id'] in (P.PROFILE_PREV, P.PROFILE_REAL)
