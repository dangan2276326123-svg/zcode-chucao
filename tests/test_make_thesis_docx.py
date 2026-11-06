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
        self.superscript = False


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


def test_resolved_citation_becomes_a_superscript_number():
    """[[REF:12]] 是**已定号**的引文：排成上标 [12]，不再进灰底占位那一桶。

    两栏计数必须分开——"还剩几处没定号"不能藏在"41 处标记"这种混合读数里。
    """
    c = M.Counter()
    p = FakePara()
    M.emit('如文献[[REF:12]]所示。', p, c)
    assert c['ref_marker'] == 1 and c['ref_num'] == 1 and c['ref_pending'] == 0
    assert '[12]' in p.plain() and '待补引文' not in p.plain()
    run = [r for r in p.runs if r.text == '[12]'][0]
    assert run.font.superscript is True, '顺序编码制的引用标记是上标'
    # 没定号的仍然走灰底占位，一条不许静默消失
    c2 = M.Counter()
    p2 = FakePara()
    M.emit('如[[REF:KEYWORD_PLACEHOLDER: Someone 2020.]]所示。', p2, c2)
    assert c2['ref_pending'] == 1 and c2['ref_num'] == 0
    assert '待补引文' in p2.plain()


def test_other_pending_markers_are_highlighted_too():
    """清零清单不只 `<待补充>`：正文里还有 `<待核实>`、`<待登记>`、`<待实测>`。

    原先只认"待补充"，那几处就以普通文字落纸——不高亮、也不进计数。
    清单少报比格式不好看更糟，因为这份文档里的 `<待…>` 计数就是送审前的清零对象。
    """
    c = M.Counter()
    p = FakePara()
    M.emit(u'见<待核实：HRNet 文献>与<待登记：轮盘外径>与<待实测：X>。', p, c)
    assert c['todo'] == 3, c['todo']
    marked = [r for r in p.runs if r.text.startswith(u'<待')]
    assert len(marked) == 3
    assert all(r.font.highlight_color is not None for r in marked), \
        '一处待办标记都不许以普通文字混过版面'


def test_inline_code_backticks_are_dropped_not_printed():
    """源码用 `标识符` 强调代码名；纸面上露反引号就是排版事故。

    118 处反引号散在 ch02/ch03/ch06，其中表题那一条走的是 strip_marks（不经 emit），
    所以两条路径都得去；这条测试把两处都钉住。
    """
    c = M.Counter()
    p = FakePara()
    M.emit(u'见 `status` 与 `train_metric_log.csv` 两处。', p, c)
    assert '`' not in p.plain(), p.plain()
    assert 'status' in p.plain() and 'train_metric_log.csv' in p.plain()
    assert '`' not in M.strip_marks(u'表 3-1 指标（取自 `train_metric_log.csv`）')


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
        raw['todo'] += len(re.findall(r'<待[^\n<>]{0,200}>', text, re.S))
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


# ------------------------------------------------------------------ figures
def test_figure_map_splits_assets_from_placeholders(tmp_path):
    """清单里 File 有值 -> 嵌图；写 em-dash -> 留占位。

    这张表是论文插图的唯一事实源，所以两种状态必须分得开：
    「登记了但文件不在」是清单在说谎，不能和「还没做」混成同一个计数。
    """
    man = tmp_path / 'figures_manifest.md'
    bt = chr(96)                     # 反引号，清单里用它包文件名与标记
    rows = [
        (u'图3-2', bt + 'a.png' + bt, u'训练指标三段走势'),
        (u'图2-1', u'—', u'系统总体架构图'),
    ]
    man.write_text(
        u'# m' + chr(10) + chr(10)
        + u'| ID | File | 正文里的占位标记 | Related Chapter | Source | Status | Notes |'
        + chr(10)
        + u'| --- | --- | --- | --- | --- | --- | --- |' + chr(10)
        + chr(10).join(u'| %s | %s | %s[[FIG:%s]]%s | ch3 | x | ok | y |'
                       % (r[0], r[1], bt, r[2], bt) for r in rows) + chr(10),
        encoding='utf-8')
    m = M.load_figure_map(str(man))
    assert m[u'训练指标三段走势'] == 'a.png'
    assert m[u'系统总体架构图'] is None


def test_placeholder_is_kept_when_no_asset(monkeypatch):
    """没有资产时标记必须留在正文里，不能静默消失——标记一丢，
    「这张图还没做」这件事就从正文和清单两边同时蒸发了。"""
    monkeypatch.setattr(M, 'FIGURE_MAP', {u'某图': None})
    c = M.Counter()
    p = FakePara()
    M.emit(u'见图[[FIG:某图]]。', p, c)
    assert c['fig_placeholder'] == 1
    assert u'待补图' in p.plain()


def test_registered_but_missing_file_is_counted_separately(monkeypatch, tmp_path):
    """清单登记了文件名、盘上却没有 -> 单独计数，不与「还没做」合并。"""
    monkeypatch.setattr(M, 'FIGURE_MAP', {u'某图': 'no_such_file_anywhere.png'})
    monkeypatch.setattr(M, 'FIGDIR', str(tmp_path))   # 空目录：登记了但没有文件
    c = M.Counter()
    M.emit(u'[[FIG:某图]]', FakePara(), c)
    assert c['fig_missing_file'] == 1
    assert c['fig_placeholder'] == 0


def test_embedded_figure_paragraph_drops_exact_line_spacing(tmp_path, monkeypatch):
    """嵌图那一段必须离开"固定值"行距。

    这是 v15 导出 PDF 才看见的缺陷：正文样式是固定值行距，Word 会把嵌入图片裁到
    一行高——两张 9×16 cm 的板卡照片在页面上各只推进 36 pt，图块还互相重叠。
    计数、`--verify` 的域读数、`Fields.Count` 全都看不出这件事，
    所以这条测试按 XML 判：段间距的 lineRule 不许还是 exact。
    """
    from docx import Document
    from docx.enum.text import WD_LINE_SPACING
    from docx.oxml.ns import qn
    from docx.shared import Pt
    from PIL import Image

    png = tmp_path / 'f.png'
    Image.new('RGB', (600, 200), 'white').save(str(png))
    monkeypatch.setattr(M, 'FIGURE_MAP', {u'某图': 'f.png'})
    monkeypatch.setattr(M, 'FIGDIR', str(tmp_path))

    doc = Document()
    p = doc.add_paragraph()
    p.paragraph_format.line_spacing = Pt(12)          # 模板正文样式就是这样
    assert p.paragraph_format.line_spacing_rule == WD_LINE_SPACING.EXACTLY, \
        '这条测试的前提要先成立：先做出固定值行距，才谈得上被改掉'
    # 校模板的缩进是**按字符**给的（样式里 w:firstLineChars="200" 有 4 处），
    # 只清 w:firstLine 顶不掉它——第一版就是这么漏的，图仍被推右半个字。
    p._p.get_or_add_pPr().get_or_add_ind().set(qn('w:firstLineChars'), '200')

    c = M.Counter()
    M.emit(u'[[FIG:某图]]', p, c)
    assert c['fig_embedded'] == 1

    spacing = p._p.get_or_add_pPr().find(qn('w:spacing'))
    assert spacing is not None and spacing.get(qn('w:lineRule')) == 'auto', \
        '图段仍是固定值行距，Word 会把图片压成一行高'
    assert p.paragraph_format.line_spacing == 1
    ind = p._p.get_or_add_pPr().find(qn('w:ind'))
    assert p.paragraph_format.first_line_indent.cm == 0, \
        '图段带首行缩进会把居中的图推偏半个字'
    assert ind.get(qn('w:firstLineChars')) == '0', \
        '字符单位的缩进没清：w:firstLine="0" 顶不过 w:firstLineChars'


# ---------------------------------------------------------------- page layout
def test_level_one_heading_starts_a_new_page():
    """校模板的"标题 1"没有段前分页（styles.xml 里 pageBreakBefore 出现 0 次），
    所以章标题会接在上一章末尾——学校格式要求每章另起一页。"""
    from docx import Document
    doc = Document()
    r = M.Renderer(doc, M.Counter())
    r.heading(1, u'第 1 章 绪论')
    r.heading(2, u'1.1 研究背景')
    assert doc.paragraphs[-2].paragraph_format.page_break_before is True
    assert not doc.paragraphs[-1].paragraph_format.page_break_before, \
        '二级标题不该另起一页'


needs_prev = pytest.mark.skipif(
    not os.path.exists(M.PREV_DOCX), reason='previous docx not on this machine')


@needs_template
@needs_prev
def test_body_section_carries_running_header_and_page_numbers(tmp_path, monkeypatch):
    """整份生成一次，验正文那一节的页眉与两节的页码。

    这条只能整份建：症状来自"沿用模板最后一节的页面设置"，而模板最后一节是作者简介
    ——它的 default 页眉写死"作者简介"和"博/硕士"待选文本，真正的正文页眉
    （右格 STYLEREF 标题 1）挂在 even 上，而本包没开奇偶页，于是每一页右上角都是
    "作者简介"。域计数、Fields.Count、嵌图计数全都看不出这件事。
    """
    import re

    from docx import Document
    from docx.oxml.ns import qn

    monkeypatch.setattr(M, 'OUTDIR', str(tmp_path))     # 绝不往 thesis_cau 里写
    monkeypatch.setattr(M, 'OUT_DOCX', str(tmp_path / 'built.docx'))
    # 生成器还会往"最新副本"写一份；不钉住的话这一跑会落进仓库根目录
    monkeypatch.setattr(M, 'LATEST', str(tmp_path / 'latest.docx'))
    c, _ = M.build(check_only=False)
    assert c['hdr_repointed'] == 1, '没找到可改向的跑动页眉，改动就没生效'
    # 覆盖式副本：内容必须与主产物逐字节相同（"看着有文件、其实是旧的"是最坏形状）
    latest = tmp_path / 'latest.docx'
    assert latest.exists() and latest.read_bytes() == (tmp_path / 'built.docx').read_bytes()

    d = Document(str(tmp_path / 'built.docx'))
    front, body = d.sections[-2], d.sections[-1]

    def default_rid(section, tag):
        rids = [r.get(qn('r:id')) for r in section._sectPr.findall(qn(tag))
                if (r.get(qn('w:type')) or 'default') == 'default']
        assert len(rids) == 1, '%s 的 default %s 应有且只有一条：%s' % (
            'front' if section is front else 'body', tag, rids)
        return rids[0]

    blob = d.part.related_parts[default_rid(body, 'w:headerReference')].blob
    assert b'STYLEREF' in blob, '正文页眉没指向跑动标题部件'
    assert u'作者简介'.encode('utf-8') not in blob, '页眉仍是作者简介那一份'
    assert u'双击页眉'.encode('utf-8') not in blob, \
        '挑中了模板的占位页眉——那会把"双击页眉修改此处章节名称"印在每一页上'

    # 页码：分节之后前置走罗马数字、正文从 1 起阿拉伯数字，两节都挂带 PAGE 域的页脚。
    assert c['page_front'] == 'upperRoman@1' and c['page_body'] == 'decimal@1'
    for name, section in (('front', front), ('body', body)):
        pg = section._sectPr.find(qn('w:pgNumType'))
        assert pg is not None and pg.get(qn('w:start')) == '1', name
        foot = d.part.related_parts[default_rid(section, 'w:footerReference')].blob
        assert re.search(rb'\bPAGE\b', foot), '%s 页脚没挂 PAGE' % name
    assert d.part.related_parts[default_rid(front, 'w:headerReference')].blob \
        == d.part.related_parts[default_rid(d.sections[0], 'w:headerReference')].blob, \
        '前置页眉应沿用封面那份空的，否则摘要头上会顶着跑动章名'
    # 正文那一节是 add_section 造出来的空节：页眉页脚都得显式挂上，缺一即回归。
    assert default_rid(body, 'w:footerReference') != default_rid(body, 'w:headerReference')


# ------------------------------------------------------------------ 参考文献订正
def _fake_refs():
    out = ['[%d] filler entry %d.' % (i, i) for i in range(1, 30)]
    out[3] = ("[4] Ruckelshausen A, et al. BoniRob—an autonomous field robot "
              "platform[C]//Precision Agriculture '09. Wageningen, 2009: 741-747.")
    out[15] = ("[16] Chen L C, et al. Encoder-decoder with atrous separable "
               "convolution[C]//ECCV. Munich: Springer, 2018: 801-818.")
    return out


def test_reference_fixes_apply_and_are_counted():
    refs, n = M.apply_reference_fixes(_fake_refs())
    assert n == len(M.REFERENCE_FIXES) == 2
    assert '841-847' in refs[3] and '741-747' not in refs[3]
    assert '833-851' in refs[15] and '801-818' not in refs[15]


def test_reference_fix_bites_when_the_list_changes():
    """订正**不许静默失效**：表换版或有人手改过，原串找不到就必须抛。

    否则错页码会悄悄回到正文里，而输出照旧打印"26 条搬运完成"。
    """
    refs = _fake_refs()
    refs[3] = refs[3].replace('741-747', '999-999')
    with pytest.raises(ValueError) as e:
        M.apply_reference_fixes(refs)
    assert '[4]' in str(e.value)

    short = ['[1] only one entry.']
    with pytest.raises(ValueError):
        M.apply_reference_fixes(short)


# --------------------------------------------------------------- heading numbers
# The chapter sources carry no numbers on purpose: there is then exactly one
# place that decides what "3.4.1" means. These tests guard that single place --
# if the printed numbers and tools/check_thesis_sections.py (which resolves the
# "见 3.4.1 节" references in the prose) ever disagree, the paper shows numbers
# its own cross-references do not point at, and no grep finds it.
needs_chapters = pytest.mark.skipif(
    not os.path.exists(os.path.join(M.CHAPTERS, 'ch01_draft.md')),
    reason='chapter sources not on this machine')


def test_heading_numbers_follow_the_positional_rule():
    n = M.Numbering(3)
    got = [n.prefix(l) for l in (1, 2, 3, 3, 4, 2, 3)]
    assert got == [u'第三章 ', u'3.1 ', u'3.1.1 ', u'3.1.2 ', u'3.1.2.1 ',
                   u'3.2 ', u'3.2.1 '], got
    # a deeper level must not survive its parent: after 3.2.1 a new h2 restarts
    assert n.prefix(2) == u'3.3 '


def test_chapter_number_comes_from_the_file_name():
    assert M.chapter_of('ch01_draft.md') == 1
    assert M.chapter_of('ch06_draft.md') == 6
    assert M.chapter_of('abstract_draft.md') is None, '摘要不能被编成章号'
    assert M.Numbering(M.chapter_of('abstract_draft.md')).prefix(1) == u''


@needs_chapters
def test_outline_rows_match_the_section_checker():
    """_heading_rows()（目录与正文共用的那一路）与节号检查器同源。"""
    import check_thesis_sections as S
    want = S.build_numbers()
    got = {}
    for name in M.SOURCES[1:]:
        for level, prefix, title in M._heading_rows(name):
            if level > 1:
                got[prefix.strip()] = title
    assert got == want, sorted(set(got) ^ set(want))[:5]
    rows = M._heading_rows('ch03_draft.md')
    h2 = [r for r in rows if r[0] == 2]
    assert h2[0][1] == u'3.1 ' and h2[-1][1] == u'3.%d ' % len(h2), h2


@needs_template
@needs_prev
def test_printed_numbers_equal_the_section_checker(tmp_path, monkeypatch):
    """整份建一次，把**产物里印出来的号**对回 check_thesis_sections。

    上一条只对齐到 _heading_rows，删掉 render_source 里那次 prefix() 调用它照样
    绿（当场变异验出来过）——真正要保的是纸面上那一行。正文里"见 3.4.1 节"是
    按 build_numbers() 那套位置号解的，印出来的号若是另一套，读者翻过去是空的，
    而全文 grep 抓不到（号是派生的，不是写死的）。
    """
    import check_thesis_sections as S
    from docx import Document

    monkeypatch.setattr(M, 'OUTDIR', str(tmp_path))
    monkeypatch.setattr(M, 'OUT_DOCX', str(tmp_path / 'built.docx'))
    monkeypatch.setattr(M, 'LATEST', str(tmp_path / 'latest.docx'))
    M.build(check_only=False)

    got, chapters = {}, {}
    for par in Document(str(tmp_path / 'built.docx')).paragraphs:
        if not par.style.name.startswith('Heading'):
            continue
        t = par.text.strip()
        m = re.match(u'第([一二三四五六])章 (.+)', t)
        if m:
            chapters[u'一二三四五六'.index(m.group(1)) + 1] = m.group(2)
            continue
        m = re.match(u'([1-6](?:\\.[0-9]+)+) (.+)', t)
        if m:
            got[m.group(1)] = m.group(2)
    assert got == S.build_numbers(), '印出的节号与检查器不一致：%s' % sorted(
        set(got) ^ set(S.build_numbers()))[:5]
    assert len(chapters) == 6, '六章的章号没全印出来：%s' % sorted(chapters)


@needs_chapters
def test_front_matter_headings_stay_unnumbered_in_the_outline():
    """目录条目要么完全不带号（摘要/Abstract），要么带正文那一套号。

    注意 outline() 只走 SOURCES：目 录 / 主要符号表 / 参考文献 是 build() 里手写
    的 heading(1, …)，不经过这条——它们不带号是由 Numbering(None) 那条分支之外
    的"根本不调用 prefix"保证的，产物侧的反证在 _fmt_verify 那一次整份回读里。
    """
    tree = M.outline()
    heads = [t for _, t in tree]
    assert heads[0] == u'摘要' and heads[1] == u'Abstract', heads[:3]
    for _, t in tree:
        if t.startswith(u'第'):
            assert re.match(u'^第[一二三四五六]章 ', t), t
        elif re.match(u'^[0-9]', t):
            assert re.match(u'^[1-6](\\.[0-9]+){1,2} ', t), t
        else:
            assert t in (u'摘要', u'Abstract'), u'不该有号的地方出现了 %r' % t


@needs_template
def test_caption_is_xiaowu_heiti():
    """规范写"图、表标题采用小五号黑体"。只设 size 不设 eastAsia 的话，中文字形
    仍由模板 docDefaults 的宋体决定——尺寸对了、字体没对，屏幕上看不出来。"""
    from docx import Document
    from docx.oxml.ns import qn
    doc = Document()
    r = M.Renderer(doc, M.Counter())
    r.caption(u'图 2-6 车载控制板丝印与接口位号核对')
    run = doc.paragraphs[-1].runs[0]
    assert run.font.size.pt == 9, run.font.size
    ea = run._element.rPr.rFonts.get(qn('w:eastAsia'))
    assert ea == u'黑体', '图题仍是宋体：%r' % ea


@needs_template
def test_body_text_keeps_the_templates_own_size(tmp_path, monkeypatch):
    """正文尺寸归模板管（小四 12pt + 行距 18 磅），生成器不许再覆盖一次。

    首版在这里写过 `Normal.font.size = Pt(10.5)`，没有出处；作者参考夹里 10 篇
    中国农大已毕业硕士论文的正文众数字号当场量出来全是 12pt，模板自己的 Normal
    也是 sz=24。那一行让整篇正文比模板和所有样本小一档，而任何计数器都看不出。
    """
    import zipfile

    monkeypatch.setattr(M, 'OUTDIR', str(tmp_path))
    monkeypatch.setattr(M, 'OUT_DOCX', str(tmp_path / 'built.docx'))
    monkeypatch.setattr(M, 'LATEST', str(tmp_path / 'latest.docx'))
    M.build(check_only=False)

    def normal_sz(path):
        xml = zipfile.ZipFile(path).read('word/styles.xml').decode('utf-8')
        m = re.search(r'<w:style [^>]*w:styleId="1".*?</w:style>', xml, re.S)
        assert m, '没找到 Normal 那条样式'
        found = re.findall(r'<w:sz w:val="(\d+)"', m.group(0))
        return found

    tpl = normal_sz(M.TEMPLATE)
    got = normal_sz(str(tmp_path / 'built.docx'))
    assert got == tpl, 'Normal 字号被生成器改过：模板 %s -> 产物 %s' % (tpl, got)
    assert tpl and int(tpl[0]) == 24, '模板自身就不是 12pt，这条测试的前提变了'


def test_sub_headings_are_flush_left():
    """1.1 / 1.1.1 / 1.1.1.1 必须顶格——模板只在"标题 1""标题 3"里清了首行缩进，
    "标题 2""标题 4"没有 ind 覆盖，会继承 Normal 的 2 字符缩进，于是节标题被推进
    两格，而规范和王硕(2024)、班超(2025)两篇都是顶格的。"""
    from docx import Document
    from docx.oxml.ns import qn
    doc = Document()
    r = M.Renderer(doc, M.Counter())
    for lvl in (2, 3, 4):
        r.heading(lvl, u'%d.1 标题' % lvl)
        p = doc.paragraphs[-1]
        assert p.paragraph_format.first_line_indent == 0, '第 %d 级仍带首行缩进' % lvl
        ind = p._p.get_or_add_pPr().find(qn('w:ind'))
        assert ind.get(qn('w:firstLineChars')) == '0', \
            '第 %d 级只清了 w:firstLine，字符单位的缩进会盖过它' % lvl


# ------------------------------------------------------------ reference list
def test_normalize_reference_fixes_the_known_shapes():
    """三种来源各带各的毛病，逐条给一个"输入→必须输出"。"""
    # 开题复制：条目序号混成了作者名第一个 token
    assert M.normalize_reference(u'[17] 9 刘星星,车金宁,杨潇,等.枸杞[J].农业工程学报,'
                                 u'2024,40(23):104-114.').startswith(
        u'[17] 刘星星, 车金宁, 杨潇, 等. 枸杞[J]. 农业工程学报, 2024, 40(23): 104-114.')
    # 年份与卷期被拆开、页码中间有空格
    out = M.normalize_reference(u'[20] 罗强,韩彬,叶松林,等. 丘陵山地果园多功能除草机的'
                                u'设计与试验[J].中国工程机械学报,2026,24 (1):150-15 4.')
    assert u'24(1): 150-154.' in out, out
    # PDF 换行把词拆开
    assert u'based on slip-aware look-ahead' in M.normalize_reference(
        u'[78] Liu H, Han Z, Yin J, et al. Path tracking control method for tracked '
        u'agricultural vehicles based on sli p-aware look-ahead point offset[J].'
        u'Frontiers in Plant Science, 2026, 16: 1754679.')
    # 六个责任者 → 前三个 + et al.，题名不许被吃掉（第一版就吃掉了 [36]）
    out = M.normalize_reference(
        u'[36] Fountas S,Mylonas N,Malounas I,Rodias E,Hellmann Santos C,'
        u'Pekkeriet E.Agricultural Robotics for Field Operations[J].Sensors,'
        u'2020,20(9):2672.')
    assert out.startswith(u'[36] Fountas S, Mylonas N, Malounas I, et al. '
                          u'Agricultural Robotics for Field Operations[J]. '
                          u'Sensors, 2020, 20(9): 2672.'), out
    assert u'..' not in out, u'截断时把原来的分隔句点留下了'
    # [C]// 是会议录的写法，不许被改成 "[C]. //"
    assert u'[C]//Proceedings' in M.normalize_reference(
        u'[38] Long J, Shelhamer E, Darrell T. Fully convolutional networks for '
        u'semantic segmentation[C]//Proceedings of the IEEE CVPR. Boston: IEEE, '
        u'2015: 3431-3440.')


def test_reference_list_prints_clean():
    """94 条落纸前的硬形状：不许有截断、叠句点、粘连、裸序号、开题模板文字。"""
    refs = M.build_references()
    assert len(refs) == len(M.FINAL_REFERENCES) == 94
    problems = []
    for i, s in enumerate(refs, 1):
        if not re.match(u'^\\[%d\\] ' % i, s):
            problems.append((i, u'编号不连续或前缀不对'))
        if u'..' in s:
            problems.append((i, u'连续句点'))
        if re.search(u'研究方案|以下各项均可加页|拟采取的研究方法', s):
            problems.append((i, u'开题模板文字混进参考文献'))
        if re.search(r'\[(J|D|C|M|R|S)\]\.(?=\S)', s):
            problems.append((i, u'类型标记后没有空格'))
        if re.search(r',(?=[^\s])', s):
            problems.append((i, u'逗号后没有空格'))
        if re.search(r'\b(19|20)\s+\d{2}\b', s):
            problems.append((i, u'年份被拆开'))
        if not s.endswith(u'.'):
            problems.append((i, u'句末缺点号'))
        if u'[J]' in s and not re.search(r':\s*\d', s):
            problems.append((i, u'期刊条目没有页码'))
        if u'[D]' in s and not re.search(r'(19|20)\d{2}\.$', s):
            problems.append((i, u'学位论文没有年'))
        for bad, _ in M.REF_SPLIT_WORDS:
            if bad in s:
                problems.append((i, u'PDF 断词未修：%s' % bad))
        if re.search(r'\d-\.(?=\s|$)', s):
            problems.append((i, u'页码末尾悬着一个连字符'))
    assert not problems, problems[:8]


def test_completed_references_carry_their_pages():
    """被复制截断的条目：补全后必须带齐自己那一类的必备项。

    [J] 要年+卷+页码；[D] 只有年（学位论文没有卷期）；[P] 要公开日。
    """
    refs = M.build_references()
    for num in M.REFERENCE_COMPLETIONS:
        s = refs[num - 1]
        assert u'doi.org' not in s, u'[%d] DOI 不该印进论文' % num
        if num == 7:
            assert u'[P]' in s and u'2014-07-09' in s, s
            continue
        if u'[D]' in s:
            assert re.search(u'(19|20)\\d{2}\\.$', s), u'[%d] 学位论文缺年：%s' % (num, s)
            continue
        assert re.search(r'\d{4},\s*\d+', s), u'[%d] 仍缺年/卷：%s' % (num, s)
        assert re.search(r':\s*\d', s), u'[%d] 仍缺页码：%s' % (num, s)


def test_reference_paragraph_is_hanging_not_first_line():
    """参考文献用悬挂缩进："[1]" 顶格、第二行缩两格。"""
    from docx import Document
    from docx.oxml.ns import qn
    from docx.shared import Pt
    doc = Document()
    p = doc.add_paragraph()
    run = p.add_run(u'[1] 示例条目')
    run.font.size = Pt(9)
    M.hanging_indent(p)
    ind = p._p.get_or_add_pPr().find(qn('w:ind'))
    assert ind.get(qn('w:hangingChars')) == '200', ind.get(qn('w:hangingChars'))
    assert ind.get(qn('w:firstLineChars')) == '0', \
        '首行缩进没清：Normal 的 2 字符会盖过悬挂'
    assert int(ind.get(qn('w:hanging'))) == 360, ind.get(qn('w:hanging'))


@needs_template
@needs_prev
def test_built_reference_entries_are_hanging(tmp_path, monkeypatch):
    """整份建一次：90 条参考文献在产物里必须真的带上悬挂缩进。"""
    from docx import Document
    from docx.oxml.ns import qn
    monkeypatch.setattr(M, 'OUTDIR', str(tmp_path))
    monkeypatch.setattr(M, 'OUT_DOCX', str(tmp_path / 'built.docx'))
    monkeypatch.setattr(M, 'LATEST', str(tmp_path / 'latest.docx'))
    M.build(check_only=False)
    d = Document(str(tmp_path / 'built.docx'))
    refs = [p for p in d.paragraphs
            if re.match(u'^\\[[0-9]+\\] ', p.text.strip())]
    assert len(refs) == 94, '产物里的参考文献条数：%d' % len(refs)
    bad = [p.text[:24] for p in refs
           if (p._p.pPr is None or p._p.pPr.find(qn('w:ind')) is None
               or p._p.pPr.find(qn('w:ind')).get(qn('w:hangingChars')) != '200')]
    assert not bad, u'这些条目没带悬挂缩进：%s' % bad[:3]
