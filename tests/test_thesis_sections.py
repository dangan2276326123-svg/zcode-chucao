# -*- coding: utf-8 -*-
"""Tests for tools/check_thesis_sections.py.

The checker exists because section numbers in this thesis are *derived* (from the
heading position), so a rename or a block move re-points every "见 3.5.1 节" while a
grep for the old number finds nothing. These tests pin both directions: it must find
a dangling reference when one exists, and the real chapter sources must be clean.
"""
import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'tools'))
import check_thesis_sections as C  # noqa: E402


def _fake(tmp_path, monkeypatch, body):
    (tmp_path / 'ch01_draft.md').write_text(body, encoding='utf-8')
    monkeypatch.setattr(C, 'CH', str(tmp_path))
    monkeypatch.setattr(C, 'FILES', ['ch01_draft.md'])


def test_dangling_reference_is_reported(tmp_path, monkeypatch):
    _fake(tmp_path, monkeypatch,
          u'# 第一章\n\n## 第一节\n\n见 1.3 节，另见 1.1 节。\n')
    valid = C.build_numbers()
    assert '1.1' in valid and '1.3' not in valid
    bad = C.find_dangling(valid)
    assert [b[2] for b in bad] == ['1.3'], bad


def test_nested_reference_resolves(tmp_path, monkeypatch):
    """1.2.1 must resolve through h2 -> h3 numbering."""
    _fake(tmp_path, monkeypatch,
          u'# 第一章\n\n## 第一节\n\n### 小节\n\n见 1.1.1 节。\n')
    valid = C.build_numbers()
    assert valid.get('1.1.1') == u'小节'
    assert C.find_dangling(valid) == []


def test_real_chapters_have_no_dangling_references():
    """The live sources: every 节 reference must resolve. Runs against the real tree."""
    if not os.path.isdir(C.CH):
        import pytest
        pytest.skip('thesis sources not on this machine')
    bad = C.find_dangling(C.build_numbers())
    assert not bad, 'dangling section refs: %s' % bad
