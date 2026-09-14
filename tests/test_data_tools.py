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
        sd.split_peony_dataset(str(src), str(out), force=True)
    assert sentinel.exists(), 'target was cleared before source validated!'


def test_dry_run_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(sd, 'WORKSPACE', str(tmp_path))
    src, out = tmp_path / 'src', tmp_path / 'out'
    _make_pairs(str(src), 10)
    sd.split_peony_dataset(str(src), str(out), dry_run=True)
    assert not os.path.exists(str(out))


def test_split_counts_and_copy(tmp_path, monkeypatch):
    monkeypatch.setattr(sd, 'WORKSPACE', str(tmp_path))
    src, out = tmp_path / 'src', tmp_path / 'out'
    _make_pairs(str(src), 10)
    sd.split_peony_dataset(str(src), str(out), seed=1)
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


def test_r2_nonempty_target_refused_without_force(tmp_path, monkeypatch):
    """R2: re-running without --force into a non-empty split must be refused
    (otherwise old samples silently mix into the new split)."""
    monkeypatch.setattr(sd, 'WORKSPACE', str(tmp_path))
    src, out = tmp_path / 'src', tmp_path / 'out'
    _make_pairs(str(src), 10)
    sd.split_peony_dataset(str(src), str(out), seed=1)      # first run OK
    with pytest.raises(SystemExit):
        sd.split_peony_dataset(str(src), str(out), seed=2)  # re-run must refuse


def test_r2_force_allows_resplit(tmp_path, monkeypatch):
    monkeypatch.setattr(sd, 'WORKSPACE', str(tmp_path))
    src, out = tmp_path / 'src', tmp_path / 'out'
    _make_pairs(str(src), 10)
    sd.split_peony_dataset(str(src), str(out), seed=1)
    sd.split_peony_dataset(str(src), str(out), seed=2, force=True)  # no raise
    n = len([f for f in os.listdir(os.path.join(str(out), 'train', 'images'))
             if f.endswith('.jpg')])
    assert n == 6


def test_r2_source_output_overlap_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(sd, 'WORKSPACE', str(tmp_path))
    src = tmp_path / 'src'
    _make_pairs(str(src), 6)
    with pytest.raises(SystemExit):
        sd.split_peony_dataset(str(src), str(src / 'split_out'), force=True)
