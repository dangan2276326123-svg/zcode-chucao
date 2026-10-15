# -*- coding: utf-8 -*-
"""Tests for tools/make_thesis_docx.py.

These guard the two ways this generator could do silent damage:
  * a symbol that is mangled but not flagged -- the file would look finished
    while showing wrong math (test_symbol_* below, found by an actual run);
  * a marker that is dropped instead of carried into the document -- the
    "resolve before submission" list would shrink on its own (the tallies must
    equal what the sources really contain).
"""
import io
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'tools'))
import make_thesis_docx as M  # noqa: E402


# ------------------------------------------------------------------ symbols
def test_greek_and_superscript_map_clean():
    s, clean = M.symbol_to_text(r'\delta_{fr}')
    assert s.startswith('\u03b4') and clean, s


def test_hat_and_dot_become_combining_marks():
    s, clean = M.symbol_to_text(r'\hat{\tau}')
    assert clean and '\u0302' in s and '\\' not in s, s
    s2, clean2 = M.symbol_to_text(r'\dot{e}')
    assert clean2 and '\u0307' in s2, s2


def test_nested_structure_is_flagged_not_garbled():
    """The regression this test exists for: `e^{-\\tau s}` used to come out as
    'e\u207b\u03c4 s}' -- braces left behind -- while still reporting itself as
    successfully converted, so nothing highlighted it."""
    s, clean = M.symbol_to_text(r'e^{-\tau s}')
    assert not clean, 'a leftover brace must be reported as unmapped: %r' % s


def test_unmapped_command_keeps_its_backslash_and_is_flagged():
    s, clean = M.symbol_to_text(r'\Bbbk')
    assert not clean and '\\' in s


# --------------------------------------------------------------------- emit
class _Font(object):
    def __init__(self):
        self.highlight_color = None
        self.size = None
        self.name = None


class _Run(object):
    """Minimal stand-in for a python-docx run: emit() touches .bold, .italic
    and .font.highlight_color, so the fake has to offer the same surface."""

    def __init__(self, text):
        self.text = text
        self.bold = False
        self.italic = False
        self.font = _Font()


class FakePara(object):
    """Stands in for a python-docx paragraph so emit() can be tested without
    writing a package."""

    def __init__(self):
        self.runs = []

    def add_run(self, text):
        r = _Run(text)
        self.runs.append(r)
        return r

    def plain(self):
        return ''.join(r.text for r in self.runs)


def test_emit_keeps_every_payload_visible():
    c = M.Counter()
    p = FakePara()
    M.emit(r'见[[SYM:\delta]]与[[EQ:x=\frac{a}{b}]]，另<待补充：台架实测>。'
           r'文献[[REF:Zhang 2000.]]', p, c)
    body = p.plain()
    assert c['sym_ok'] == 1 and c['eq'] == 1 and c['todo'] == 1
    assert c['ref_marker'] == 1
    # nothing may vanish: the formula text, the todo text and the citation text
    # all have to survive into the rendered runs
    assert r'\frac{a}{b}' in body
    assert '台架实测' in body and 'Zhang 2000' in body
    assert '见' in body and '。' in body


def test_bold_mark_produces_a_bold_run_and_no_asterisks():
    c = M.Counter()
    p = FakePara()
    M.emit('实际生效的是**比例控制加时延超前**（未整定）', p, c)
    assert '*' not in p.plain()
    assert any(r.bold and '比例控制' in r.text for r in p.runs)


def test_check_pass_counts_the_same_as_a_write():
    """add_table() used to return early in check mode, so table-cell markers
    were invisible to --check and its tallies quietly disagreed with a real
    run (seen as 27 vs 31)."""
    rows = [['指标', '值'], ['mIoU', '<待补充：独立测试集>']]
    c = M.Counter()
    M.add_table(None, rows, c, check_only=True)
    assert c['todo'] == 1, 'a <待补充> inside a table cell must still be tallied'


# ------------------------------------------------------------------ parsing
def test_parse_blocks_drops_separator_rows_and_keeps_cells():
    lines = ['表 2-2 参数', '', '| 参数 | 数值 |', '| --- | --- |',
             '| 车宽 | 2.15 m |', '']
    blocks = list(M.parse_blocks(lines))
    tables = [b for b in blocks if b[0] == 'table']
    assert len(tables) == 1
    assert tables[0][1] == [['参数', '数值'], ['车宽', '2.15 m']]


def test_parse_blocks_reads_heading_levels():
    blocks = list(M.parse_blocks(['# 章', '## 节', '### 小节', '正文一句']))
    assert [(b[0], b[1]) for b in blocks] == [('h', 1), ('h', 2), ('h', 3),
                                              ('p', '正文一句')]


# ------------------------------------------------- cross-check against source
def test_tallies_match_the_real_chapter_sources():
    """End-to-end guard: what the generator counts must equal what a plain
    scan of the .md sources contains. If a construct ever stops being parsed,
    this goes red instead of the document silently losing content."""
    if not os.path.isdir(M.CHAPTERS):
        pytest.skip('thesis chapter sources not on this machine')
    raw = {'todo': 0, 'ref': 0, 'eq': 0, 'fig': 0, 'sym': 0}
    for name in M.SOURCES:
        text = '\n'.join(M.read_source(name))
        raw['todo'] += len(re.findall(r'<待补充', text))
        raw['ref'] += len(re.findall(r'\[\[REF:', text))
        raw['eq'] += len(re.findall(r'\[\[EQ:', text))
        raw['fig'] += len(re.findall(r'\[\[FIG:', text))
        raw['sym'] += len(re.findall(r'\[\[SYM:', text))
    c, _refs = M.build(check_only=True)
    assert c['todo'] == raw['todo'], (c['todo'], raw['todo'])
    assert c['ref_marker'] == raw['ref']
    assert c['eq'] == raw['eq']
    assert c['fig'] == raw['fig']
    assert c['sym_ok'] + c['sym_raw'] == raw['sym']


# --------------------------------------------------------------------- cover
# The cover is carried over as template XML rather than retyped, so these tests
# exist to catch the failure modes that are invisible on screen: a field left
# behind, the dead external picture link surviving, or a relationship id that no
# longer resolves.
needs_template = pytest.mark.skipif(
    not os.path.exists(M.TEMPLATE), reason='school template not on this machine')


def _blocks():
    blocks, tally = M.extract_front_matter(M.TEMPLATE, keep_box='academic')
    assert blocks, 'front matter must not come back empty'
    from lxml import etree
    return ''.join(etree.tostring(b).decode('utf-8') for b in blocks), tally


@needs_template
def test_carried_cover_has_no_field_machinery():
    xml, tally = _blocks()
    for tag in ('w:fldChar', 'w:instrText', 'MACROBUTTON', 'INCLUDEPICTURE',
                'w:sdt', 'w:altChunk'):
        assert tag not in xml, '%s survived the strip' % tag
    assert tally['fields_stripped'] > 0, 'the template cover does contain fields'


@needs_template
def test_dead_external_picture_link_is_dropped():
    """The template's cover INCLUDEPICTURE points at a 2005 news.cau.edu.cn jpg
    that now redirects to the university homepage; leaving it means a red X."""
    xml, tally = _blocks()
    assert 'r:link=' not in xml
    assert 'news.cau.edu.cn' not in xml
    assert tally['external_links_dropped'] >= 1


@needs_template
def test_local_wordmark_survives_and_every_rid_resolves():
    """Dropping the link must not drop the picture, and no carried block may
    reference a relationship the output package does not have."""
    import re
    import zipfile
    xml, _ = _blocks()
    assert 'v:imagedata' in xml, 'the school wordmark must still be there'
    rels = zipfile.ZipFile(M.TEMPLATE).read('word/_rels/document.xml.rels').decode('utf-8')
    have = set(re.findall(r'Id="([^"]+)"', rels))
    used = set(re.findall(r'r:(?:id|embed|href)="([^"]+)"', xml))
    assert not (used - have), 'dangling relationship ids: %s' % sorted(used - have)


@needs_template
def test_academic_choice_keeps_box1_and_drops_box2():
    """Text of the kept blocks: 附件1 stays (with the template's own
    "delete this box" instruction), 附件2 goes."""
    blocks, _ = M.extract_front_matter(M.TEMPLATE, keep_box='academic')
    from lxml import etree
    W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    text = '\n'.join(''.join(t.text or '' for t in b.iter(W + 't'))
                     for b in blocks)
    assert '附件1' in text
    assert '附件2' not in text
    assert '独 创 性 声 明' in text or '独创性声明' in text.replace(' ', '')


@needs_template
def test_seam_between_cover_and_spine_is_page_broken():
    """The template keeps its only explicit page break at the end of 附件2, so
    dropping that box would pull the 书脊 page up onto the cover."""
    xml, tally = _blocks()
    assert 'w:type="page"' in xml or tally['page_breaks_added'] >= 1
