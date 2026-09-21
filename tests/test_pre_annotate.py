# -*- coding: utf-8 -*-
"""tools/pre_annotate 的护栏测试。

不跑模型（那要 GPU 与权重），只测三件真正容易出事的东西：
输出护栏、噪声轮廓过滤、标签默认值与 json2mask 冻结字典的一致性。
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
pytest.importorskip('albumentations', reason='预标注依赖 torch/albumentations，缺失时跳过')
pytest.importorskip('cv2')

from tools import pre_annotate as pa  # noqa: E402


def test_refuses_writing_into_readonly_repo(tmp_path, monkeypatch):
    monkeypatch.setattr(pa, 'WORKSPACE', str(tmp_path))
    with pytest.raises(SystemExit) as e:
        pa._guard_write(r'D:\JetBrains\chucao_prj\annotation_tools\out')
    assert '只读研究仓' in str(e.value)


def test_refuses_writing_outside_workspace_unless_explicit(tmp_path, monkeypatch):
    monkeypatch.setattr(pa, 'WORKSPACE', str(tmp_path))
    outside = os.path.join(os.path.dirname(str(tmp_path)), 'elsewhere')
    with pytest.raises(SystemExit) as e:
        pa._guard_write(outside)
    assert '--allow-outside' in str(e.value)
    assert pa._guard_write(outside, allow_outside=True) == os.path.abspath(outside)


def test_tiny_blobs_are_dropped_as_noise():
    """MIN_AREA_PX 以下的小连通域不该变成多边形——那会让 labelme 里全是碎块。"""
    import cv2
    mask = np.zeros((300, 300), np.uint8)
    mask[100:200, 100:200] = 1          # 100x100 = 10000 px，保留
    mask[10:14, 10:14] = 1              # 4x4 = 16 px，噪声，丢弃
    polys = pa.mask_to_polygons(mask)
    assert len(polys) == 1
    assert len(polys[0]) >= 3


def test_default_label_is_accepted_by_json2mask():
    """H1.2 冻结了标签字典；预标注写的 label 必须在其中，否则前景被静默丢掉。"""
    from tools import json2mask as j2m
    assert pa.DEFAULT_LABEL in j2m.PEONY_LABELS, (pa.DEFAULT_LABEL, j2m.PEONY_LABELS)


class _FakeModel:
    """替代模型推理，不替代写文件逻辑：右半前景、左半背景。"""

    def to(self, _):
        return self

    def __call__(self, x):
        import torch
        n, c, h, w = x.shape
        out = torch.zeros((n, c, h, w))
        out[:, 1, :, w // 2:] = 5.0
        out[:, 0, :, :w // 2] = 5.0
        return out


def _run_main(tmp_path, monkeypatch, args):
    import cv2
    monkeypatch.setattr(pa, 'WORKSPACE', str(tmp_path))
    monkeypatch.setattr(pa, 'load_model', lambda p: _FakeModel())
    src = tmp_path / 'in'
    src.mkdir(exist_ok=True)
    img = (np.random.RandomState(0).rand(120, 160, 3) * 255).astype(np.uint8)
    cv2.imencode('.jpg', img)[1].tofile(str(src / 'x_1.jpg'))
    w = tmp_path / 'dummy.pth'
    w.write_bytes(b'x')
    monkeypatch.setattr(sys, 'argv',
                        ['pre_annotate', '--input', str(src), '--output', str(tmp_path / 'out'),
                         '--weights', str(w)] + args)
    pa.main()
    return tmp_path / 'out' / 'labelme' / 'x_1.json'


def test_rerun_keeps_human_revisions(tmp_path, monkeypatch):
    """复审 2026-09-21 P1：README 流程是"先预标注后人工修正"，无条件 open('w')
    会让重跑把人工改过的多边形静默替换掉。原始症状 = 人工标记消失。"""
    import json
    dst = _run_main(tmp_path, monkeypatch, [])
    j = json.loads(dst.read_text(encoding='utf-8'))
    j['shapes'].append({'label': 'peony', 'points': [[5, 5], [30, 5], [30, 30]],
                        'description': 'HUMAN_REVISION', 'shape_type': 'polygon',
                        'group_id': None, 'flags': {}})
    dst.write_text(json.dumps(j, ensure_ascii=False, indent=1), encoding='utf-8')

    _run_main(tmp_path, monkeypatch, [])                       # 默认重跑
    after = json.loads(dst.read_text(encoding='utf-8'))
    assert any(s.get('description') == 'HUMAN_REVISION' for s in after['shapes']), \
        '重跑把人工修正覆盖掉了'
    assert len(after['shapes']) == len(j['shapes'])

    _run_main(tmp_path, monkeypatch, ['--overwrite'])          # 显式覆盖才允许毁数据
    forced = json.loads(dst.read_text(encoding='utf-8'))
    assert all(s.get('description') != 'HUMAN_REVISION' for s in forced['shapes'])


def test_same_stem_different_ext_is_rejected(tmp_path, monkeypatch):
    """a.jpg 与 a.png 只取 stem 会写进同一个 a.json，第二张静默盖掉第一张。"""
    import cv2
    monkeypatch.setattr(pa, 'WORKSPACE', str(tmp_path))
    src = tmp_path / 'in'
    src.mkdir()
    for name in ('a.jpg', 'a.png'):
        cv2.imencode(os.path.splitext(name)[1],
                     np.zeros((40, 40, 3), np.uint8))[1].tofile(str(src / name))
    w = tmp_path / 'dummy.pth'
    w.write_bytes(b'x')
    monkeypatch.setattr(sys, 'argv', ['pre_annotate', '--input', str(src),
                                      '--output', str(tmp_path / 'out'), '--weights', str(w)])
    with pytest.raises(SystemExit) as e:
        pa.main()
    assert '同名不同扩展' in str(e.value)
