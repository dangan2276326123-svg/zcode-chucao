# -*- coding: utf-8 -*-
"""Asset-safety tests for the 2026-09-09 review findings #1 and #7.

#1 split_dataset.py must never clear a target before validating the source,
   and must refuse paths in the read-only JetBrains repos.
#7 json2mask.py must accept the checklist's 'peony' label and raise on
   unknown labels instead of silently dropping foreground.
"""
import json
import os

import numpy as np
import pytest

from tools import split_dataset as sd
from tools import json2mask as j2m


# ---- #1 split_dataset asset safety ---------------------------------------

def _make_pairs(src, n):
    os.makedirs(src, exist_ok=True)
    for i in range(n):
        with open(os.path.join(src, 'img_%03d.jpg' % i), 'wb') as f:
            f.write(b'\xff\xd8\xff\xd9')          # not a real jpeg; content unused
        with open(os.path.join(src, 'img_%03d.json' % i), 'w') as f:
            f.write('{}')


def test_forbidden_path_refused(tmp_path):
    with pytest.raises(SystemExit):
        sd._guard(r'D:\JetBrains\chucao_prj\model_data\train\images')
    with pytest.raises(SystemExit):
        sd._guard('C:/somewhere/else/avi_project/img')


def test_outside_workspace_refused():
    with pytest.raises(SystemExit):
        sd._guard(os.path.join(os.path.dirname(sd.WORKSPACE), 'evil'))


def test_empty_source_does_not_clear_targets(tmp_path, monkeypatch):
    """The review's core scenario: bad/empty source must NOT wipe targets."""
    src = tmp_path / 'src'
    os.makedirs(src)
    out = tmp_path / 'out'
    # a pre-existing, precious target split
    img_dir = out / 'train' / 'images'
    os.makedirs(img_dir)
    sentinel = img_dir / 'keep.jpg'
    sentinel.write_bytes(b'precious')

    # force the guard to allow tmp_path (simulate a workspace-local run)
    monkeypatch.setattr(sd, 'WORKSPACE', str(tmp_path))
    with pytest.raises(SystemExit):
        sd.split_peony_dataset(str(src), str(out), force=True, grouped=False)
    assert sentinel.exists(), 'target was cleared before source validated!'


def test_dry_run_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(sd, 'WORKSPACE', str(tmp_path))
    src, out = tmp_path / 'src', tmp_path / 'out'
    _make_pairs(str(src), 10)
    sd.split_peony_dataset(str(src), str(out), dry_run=True, grouped=False)
    assert not os.path.exists(str(out))


def test_split_counts_and_copy(tmp_path, monkeypatch):
    monkeypatch.setattr(sd, 'WORKSPACE', str(tmp_path))
    src, out = tmp_path / 'src', tmp_path / 'out'
    _make_pairs(str(src), 10)
    sd.split_peony_dataset(str(src), str(out), seed=1, grouped=False)
    counts = {s: len([f for f in os.listdir(os.path.join(str(out), s, 'images'))
                      if f.endswith('.jpg')])
              for s in ('train', 'val', 'test')}
    assert counts == {'train': 6, 'val': 2, 'test': 2}
    for s in ('train', 'val', 'test'):
        assert os.path.isdir(os.path.join(str(out), s, 'masks'))


# ---- #7 label dictionary --------------------------------------------------

def _labelme(path, labels, with_peony=True):
    shapes = []
    if with_peony:
        shapes.append({'label': labels[0],
                       'points': [[1, 1], [5, 1], [5, 5], [1, 5]]})
    for lb in labels[1:]:
        shapes.append({'label': lb, 'points': [[0, 0], [2, 0], [2, 2]]})
    data = {'imageHeight': 8, 'imageWidth': 8, 'shapes': shapes}
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f)


def test_peony_label_matches_checklist(tmp_path):
    """The checklist says label 'peony'; it must produce foreground."""
    src = tmp_path / 'raw'
    os.makedirs(src)
    _labelme(src / 'a.json', ['peony', 'background'])
    fg, labels = j2m.convert_one(str(src / 'a.json'), str(tmp_path))
    assert fg > 0, "'peony' (checklist spelling) produced an empty mask"


def test_shaoyao_still_accepted(tmp_path):
    src = tmp_path / 'raw'
    os.makedirs(src)
    _labelme(src / 'a.json', ['shaoyao', 'background'])
    fg, _ = j2m.convert_one(str(src / 'a.json'), str(tmp_path))
    assert fg > 0


def test_unknown_label_raises(tmp_path):
    src = tmp_path / 'raw'
    os.makedirs(src)
    _labelme(src / 'a.json', ['peony', 'weed'])   # 'weed' not frozen
    with pytest.raises(ValueError):
        j2m.convert_one(str(src / 'a.json'), str(tmp_path))


def test_all_background_reported(tmp_path):
    src = tmp_path / 'raw'
    os.makedirs(src)
    _labelme(src / 'a.json', ['background'], with_peony=False)
    fg, labels = j2m.convert_one(str(src / 'a.json'), str(tmp_path))
    assert fg == 0   # caller (main) turns this into a warning


# ---- R2 (review 2026-09-14): non-empty target must refuse, not mix --------

def test_nonempty_target_refused_without_force(tmp_path, monkeypatch):
    """Reproduces the review's 7/4/3 cross-set scenario: two runs with
    different seeds into the same target used to mix old+new files
    (img_4/img_8 in both train and val). Now the second run must refuse."""
    monkeypatch.setattr(sd, 'WORKSPACE', str(tmp_path))
    src, out = tmp_path / 'src', tmp_path / 'out'
    _make_pairs(str(src), 10)

    sd.split_peony_dataset(str(src), str(out), seed=1, grouped=False)# first run OK
    img_dir = os.path.join(str(out), 'train', 'images')
    n_after_first = len([f for f in os.listdir(img_dir) if f.endswith('.jpg')])
    assert n_after_first == 6

    with pytest.raises(SystemExit):                          # second run refuses
        sd.split_peony_dataset(str(src), str(out), seed=2, grouped=False)
    # nothing changed by the refused run
    assert len([f for f in os.listdir(img_dir) if f.endswith('.jpg')]) == 6


def test_force_run_clears_before_write(tmp_path, monkeypatch):
    monkeypatch.setattr(sd, 'WORKSPACE', str(tmp_path))
    src, out = tmp_path / 'src', tmp_path / 'out'
    _make_pairs(str(src), 10)
    sd.split_peony_dataset(str(src), str(out), seed=1, grouped=False)
    sd.split_peony_dataset(str(src), str(out), seed=2, force=True, grouped=False)
    counts = {s: len([f for f in os.listdir(os.path.join(str(out), s, 'images'))
                      if f.endswith('.jpg')])
              for s in ('train', 'val', 'test')}
    assert counts == {'train': 6, 'val': 2, 'test': 2}      # exact, no mixing


# ---- R1 / R2 (2026-09-14 re-review) ------------------------------------

def test_r1_train_weights_not_in_readonly_repo():
    """R1: SAVE_WEIGHT_DIR must not point at the read-only JetBrains repo and
    must be workspace-derived. Checked statically (no torch import)."""
    import io
    path = os.path.join(sd.WORKSPACE, 'network', 'train_m.py')
    with io.open(path, encoding='utf-8') as f:
        text = f.read()
    assert 'SAVE_WEIGHT_DIR = r"D:/JetBrains' not in text, \
        'R1 回归：训练权重仍写死到只读原仓'
    assert 'SAVE_WEIGHT_DIR = os.path.join(_WS' in text, \
        'R1 回归：SAVE_WEIGHT_DIR 未改为工作区路径'
    """R1: SAVE_WEIGHT_DIR must not point at the read-only JetBrains repo and
    must be workspace-derived. Checked statically (no torch import)."""
    import io
    path = os.path.join(sd.WORKSPACE, 'network', 'train_m.py')
    with io.open(path, encoding='utf-8') as f:
        text = f.read()
    assert 'SAVE_WEIGHT_DIR = r"D:/JetBrains' not in text, \
        'R1 回归：训练权重仍写死到只读原仓'
    assert 'SAVE_WEIGHT_DIR = os.path.join(_WS' in text, \
        'R1 回归：SAVE_WEIGHT_DIR 未改为工作区路径'


def test_r2_nonempty_target_refused_without_force(tmp_path, monkeypatch):
    """R2: re-running without --force into a non-empty split must be refused
    (otherwise old samples silently mix into the new split)."""
    monkeypatch.setattr(sd, 'WORKSPACE', str(tmp_path))
    src, out = tmp_path / 'src', tmp_path / 'out'
    _make_pairs(str(src), 10)
    sd.split_peony_dataset(str(src), str(out), seed=1, grouped=False)# first run OK
    with pytest.raises(SystemExit):
        sd.split_peony_dataset(str(src), str(out), seed=2, grouped=False)# re-run must refuse


def test_r2_force_allows_resplit(tmp_path, monkeypatch):
    monkeypatch.setattr(sd, 'WORKSPACE', str(tmp_path))
    src, out = tmp_path / 'src', tmp_path / 'out'
    _make_pairs(str(src), 10)
    sd.split_peony_dataset(str(src), str(out), seed=1, grouped=False)
    sd.split_peony_dataset(str(src), str(out), seed=2, force=True, grouped=False)
    counts = {s: len([f for f in os.listdir(os.path.join(str(out), s, 'images'))
                      if f.endswith('.jpg')])
              for s in ('train', 'val', 'test')}
    assert counts == {'train': 6, 'val': 2, 'test': 2}      # exact, no mixing
    sd.split_peony_dataset(str(src), str(out), seed=2, force=True, grouped=False)# no raise
    n = len([f for f in os.listdir(os.path.join(str(out), 'train', 'images'))
             if f.endswith('.jpg')])
    assert n == 6


def test_r2_source_output_overlap_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(sd, 'WORKSPACE', str(tmp_path))
    src = tmp_path / 'src'
    _make_pairs(str(src), 6)
    with pytest.raises(SystemExit):
        sd.split_peony_dataset(str(src), str(src / 'split_out'), force=True, grouped=False)


# ---- H1.3 / H1.7 grouped split + frozen manifest ----------------------

def _make_grouped(src, groups):
    os.makedirs(src, exist_ok=True)
    n = 0
    for g, cnt in groups.items():
        for _ in range(cnt):
            base = '%s_%03d' % (g, n)
            n += 1
            with open(os.path.join(src, base + '.jpg'), 'wb') as f:
                f.write(b'\xff\xd8\xff\xd9')
            with open(os.path.join(src, base + '.json'), 'w') as f:
                f.write('{}')


def test_group_of_helper():
    assert sd._group_of('videoA_000123', '_') == 'videoA'
    assert sd._group_of('nosep', '_') == 'nosep'      # no delim -> own group


def test_grouped_split_no_straddle(tmp_path, monkeypatch):
    """H1.3: a group (video/plot/day) must never appear in two sets."""
    monkeypatch.setattr(sd, 'WORKSPACE', str(tmp_path))
    src, out = tmp_path / 'src', tmp_path / 'out'
    _make_grouped(str(src), {'videoA': 4, 'videoB': 4, 'videoC': 4, 'videoD': 4})
    sd.split_peony_dataset(str(src), str(out), seed=1, grouped=True)
    seen = {}
    for stage in ('train', 'val', 'test'):
        d = os.path.join(str(out), stage, 'images')
        for f in os.listdir(d):
            if f.endswith('.jpg'):
                seen.setdefault(f.split('_')[0], set()).add(stage)
    assert all(len(v) == 1 for v in seen.values()), 'group straddled: %s' % seen


def test_grouped_split_manifest_frozen(tmp_path, monkeypatch):
    monkeypatch.setattr(sd, 'WORKSPACE', str(tmp_path))
    src, out = tmp_path / 'src', tmp_path / 'out'
    _make_grouped(str(src), {'videoA': 3, 'videoB': 3, 'videoC': 3})
    sd.split_peony_dataset(str(src), str(out), seed=1, grouped=True)
    import json
    m = json.load(open(os.path.join(str(out), 'split_manifest.json'), encoding='utf-8'))
    assert m['grouped'] is True
    assert set(m['groups']) == {'videoA', 'videoB', 'videoC'}
    assert sum(m['counts'].values()) == 9


# ---- E1② 分组划分的三集合非空保证（09-21 复审复现场景）----------------
def test_three_groups_still_yields_nonempty_test_set(tmp_path, monkeypatch):
    """旧写法 round(3*0.6)=2 + round(3*0.2)=1 -> test 组为 0，独立测试集被静默清空。"""
    monkeypatch.setattr(sd, 'WORKSPACE', str(tmp_path))
    src, out = tmp_path / 'raw', tmp_path / 'out'
    _make_grouped(str(src), {'videoA': 3, 'videoB': 3, 'videoC': 3})
    sd.split_peony_dataset(str(src), str(out), seed=1, grouped=True)
    m = json.loads((out / 'split_manifest.json').read_text(encoding='utf-8'))
    assert m['counts']['test'] >= 1, m['counts']
    assert m['counts']['train'] >= 1 and m['counts']['val'] >= 1, m['counts']


def test_assign_groups_pure_function_never_leaves_a_set_empty():
    for n in range(3, 12):
        pairs = ['g%d_%03d' % (g, i) for g in range(n) for i in range(2)]
        groups, set_of = sd.assign_groups(pairs, '_', seed=7)
        used = set(set_of.values())
        assert used == {'train', 'val', 'test'}, (n, set_of)


def test_fewer_than_three_groups_is_refused_not_silently_degraded(tmp_path, monkeypatch):
    """<3 组不得静默退回逐文件随机——那等于悄悄失去独立测试前提（H1.3）。"""
    monkeypatch.setattr(sd, 'WORKSPACE', str(tmp_path))
    src, out = tmp_path / 'raw', tmp_path / 'out'
    _make_grouped(str(src), {'videoA': 4, 'videoB': 4})
    with pytest.raises(SystemExit) as e:
        sd.split_peony_dataset(str(src), str(out), seed=1, grouped=True)
    assert '至少需要 3 个组' in str(e.value)
    assert not (out / 'train').exists(), '拒绝时不得写任何目标目录'


# ---- 采集清单命名契约（09-21 加）------------------------------------------
# 采集清单原来写 `IMG_0001.jpg`，分组键 = 文件名首段 = 每张都是 IMG →
# 240 张塌成 1 组，独立测试集根本不存在。工具必须说清这是命名问题。

def test_all_same_prefix_names_are_flagged_as_a_naming_problem(tmp_path, monkeypatch):
    monkeypatch.setattr(sd, 'WORKSPACE', str(tmp_path))
    src = tmp_path / 'raw'
    os.makedirs(src)
    for i in range(8):
        (src / ('IMG_%04d.jpg' % i)).write_bytes(b'\xff\xd8\xff\xd9')
        (src / ('IMG_%04d.json' % i)).write_text('{}')
    with pytest.raises(SystemExit) as e:
        sd.split_peony_dataset(str(src), str(tmp_path / 'out'), seed=1, grouped=True)
    msg = str(e.value)
    assert '命名问题' in msg, msg                   # 不能只喊"请补采集批次"
    assert 'IMG' in msg                             # 并且要点出塌掉的那个前缀


def test_take_prefixed_names_split_into_real_groups(tmp_path, monkeypatch):
    """按修正后的命名（{批次}_{日期}_{序号}）就应该是 3 组、三集合各 1 组。"""
    monkeypatch.setattr(sd, 'WORKSPACE', str(tmp_path))
    src = tmp_path / 'raw'
    os.makedirs(src)
    for take in ('t01', 't02', 't03'):
        for i in range(3):
            base = '%s_0928_%04d' % (take, i)
            (src / (base + '.jpg')).write_bytes(b'\xff\xd8\xff\xd9')
            (src / (base + '.json')).write_text('{}')
    groups, set_of = sd.assign_groups(sd.scan_pairs(str(src)), '_', seed=3)
    assert sorted(groups) == ['t01', 't02', 't03']
    assert sorted(set(set_of.values())) == ['test', 'train', 'val']


def test_nested_batch_dirs_are_refused_not_silently_skipped(tmp_path, monkeypatch):
    """只扫一层是刻意的，但必须说出来——否则嵌套布局读成"0 对配对"，
    报的是配对问题而不是目录结构问题。"""
    monkeypatch.setattr(sd, 'WORKSPACE', str(tmp_path))
    src = tmp_path / 'raw'
    os.makedirs(src / 'sun_front_dense')
    (src / 't01_0928_0001.jpg').write_bytes(b'\xff\xd8\xff\xd9')
    (src / 't01_0928_0001.json').write_text('{}')
    (src / 'sun_front_dense' / 't02_0928_0001.jpg').write_bytes(b'\xff\xd8\xff\xd9')
    with pytest.raises(SystemExit) as e:
        sd.scan_pairs(str(src))
    assert '子目录' in str(e.value) and 'sun_front_dense' in str(e.value)


def test_non_jpg_with_json_is_reported_not_dropped_quietly(tmp_path, monkeypatch,
                                                           capsys):
    """scan_pairs 只认 .jpg（历史数据集就是 .jpg）。预标注却接受 PNG/BMP，
    两边对不上时必须点名，不能悄悄把这一批漏出训练集。"""
    monkeypatch.setattr(sd, 'WORKSPACE', str(tmp_path))
    src = tmp_path / 'raw'
    os.makedirs(src)
    (src / 't01_0928_0001.jpg').write_bytes(b'\xff\xd8\xff\xd9')
    (src / 't01_0928_0001.json').write_text('{}')
    (src / 't01_0928_0002.png').write_bytes(b'\x89PNG')
    (src / 't01_0928_0002.json').write_text('{}')
    assert sd.scan_pairs(str(src)) == ['t01_0928_0001']
    out = capsys.readouterr().out
    assert 't01_0928_0002.png' in out and '只认 .jpg' in out

