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
