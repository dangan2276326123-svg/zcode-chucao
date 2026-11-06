#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Render the thesis chapter sources in `thesis_cau/03_chapters/*.md` into a
field-free Word file, reusing the CAU template's styles but none of its body.

Why this exists
---------------
The previous deliverable (`thesis_draft_v14.docx`) was made by patching the
school template's own `document.xml`, so it inherited the template's field
clutter. Counted in that file: 818 `w:fldChar`, 348 `w:instrText`, 47
MACROBUTTON, 41 REF, 28 PAGEREF, 7 SEQ, 1 TOC, 14 `w:pict`. That is what makes
the document slow to open and fragile to edit. This generator works the other
way round: it starts from the template package (so styles, fonts, theme and
page setup stay the school's) and writes a fresh body containing no field codes
at all -- headings use Heading styles, tables are real tables, and the table of
contents is dead text.

Conventions understood (these are what the chapter .md files use)
----------------------------------------------------------------
  # / ## / ### / ####   -> Heading 1..4
  | a | b |             -> three-line (三线表) Word table
  [[EQ:...]]            -> centred, raw LaTeX kept and flagged 〔公式待录〕;
                           formulas are entered by hand in Word, this tool
                           never guesses their meaning
  [[SYM:...]]           -> inline symbol; common escapes mapped to Unicode.
                           A token only counts as converted when nothing
                           structural survived -- see symbol_to_text()
  [[FIG:key]]           -> visible slot 〔待补图：key〕
  [[REF:text]]          -> 【待补引文：text】, highlighted
  <待补充：...>          -> kept visible and highlighted; these are the
                           resolve-before-submission list
  a line starting 表n-m / 图n-m -> centred caption line

Front matter
------------
摘要 and Abstract come from `abstract_draft.md`. The reference list is carried
over verbatim from the previous docx (P14 has not rewritten it yet, so this is
a transport, not an edit). The table of contents has no page numbers on
purpose: pagination is only meaningful once the layout is final, and generating
it early leaves PAGEREF fields behind -- exactly what this file avoids.

A note on how not to experiment with this script
-----------------------------------------------
Never open this file for writing and then compute the replacement text: the
open truncates it first, so any exception between the two leaves nothing
behind. That happened once while mutation-testing the checks and the source had
to be rewritten. Commit before you experiment.

Usage (from the repo root)
--------------------------
    python -B tools/make_thesis_docx.py            # write the docx
    python -B tools/make_thesis_docx.py --check    # parse only, print tallies
    python -B tools/make_thesis_docx.py --verify   # re-open output, count fields
"""
import argparse
import io
import os
import re
import zipfile

import docx
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.shared import Cm            # 插图宽度
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_COLOR_INDEX
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.enum.section import WD_SECTION
from docx.shared import Pt

THESIS = os.environ.get('THESIS_DIR') or r'D:\JetBrains\chucao_prj\thesis_cau'
TEMPLATE = os.path.join(THESIS, '01_template', 'original_template.docx')
CHAPTERS = os.path.join(THESIS, '03_chapters')
OUTDIR = os.path.join(THESIS, '10_output')
PREV_DOCX = os.path.join(OUTDIR, 'thesis_draft_v14.docx')
OUT_DOCX = os.path.join(OUTDIR, 'thesis_draft_v15_clean.docx')
# 作者要"在 qoder 文件夹里直接看到最新一版"。这一份是**覆盖式副本**：每次生成都重写，
# 只保留最新；权威产物（含版本清单）仍在 thesis_cau/10_output/，这里不进版本库。
LATEST = os.environ.get('THESIS_LATEST') or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'thesis_latest.docx')
FIGDIR = os.path.join(THESIS, '04_figures')
FIGMAN = os.path.join(FIGDIR, 'figures_manifest.md')
# 占位标记 -> 图片文件名。由 load_figure_map() 从清单读入；
# 清单是论文插图的唯一事实源，代码里不再第二处记文件名。
FIGURE_MAP = {}

SOURCES = ['abstract_draft.md'] + ['ch%02d_draft.md' % i for i in range(1, 7)]

# relationship namespace, needed to drop the cover's dead INCLUDEPICTURE link
_REL_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
_W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'

# what the last build() carried over as front matter; printed by main() so the
# cover never becomes an unreported side effect
_fm_stats = {'blocks': 0, 'fields_stripped': 0, 'links_dropped': 0,
            'breaks_added': 0}

GREEK = {
    'alpha': 'α', 'beta': 'β', 'gamma': 'γ', 'delta': 'δ', 'epsilon': 'ε',
    'zeta': 'ζ', 'eta': 'η', 'theta': 'θ', 'iota': 'ι', 'kappa': 'κ',
    'lambda': 'λ', 'mu': 'μ', 'nu': 'ν', 'xi': 'ξ', 'pi': 'π', 'rho': 'ρ',
    'sigma': 'σ', 'tau': 'τ', 'upsilon': 'υ', 'phi': 'φ', 'chi': 'χ',
    'psi': 'ψ', 'omega': 'ω',
    'Gamma': 'Γ', 'Delta': 'Δ', 'Theta': 'Θ', 'Lambda': 'Λ', 'Xi': 'Ξ',
    'Pi': 'Π', 'Sigma': 'Σ', 'Phi': 'Φ', 'Psi': 'Ψ', 'Omega': 'Ω',
}
CMDS = {'approx': '≈', 'times': '×', 'cdot': '·', 'pm': '±', 'leq': '≤',
        'geq': '≥', 'in': '∈', 'sum': '∑', 'quad': ' ', 'qquad': '  ',
        'circ': '°', 'left': '', 'right': '', 'ldots': '…', 'dots': '…'}
FUNCTIONS = ('arctan', 'arcsin', 'arccos', 'atan', 'sin', 'cos', 'tan',
             'max', 'min', 'log', 'ln', 'exp')
SUP = {'0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴', '5': '⁵', '6': '⁶',
       '7': '⁷', '8': '⁸', '9': '⁹', 'n': 'ⁿ', 'i': 'ⁱ', '+': '⁺', '-': '⁻'}


def _expand_cmd(name):
    """Map one `\\name` to Unicode, or leave it literal so the caller can see
    and flag that it was not understood."""
    if name in GREEK:
        return GREEK[name]
    if name in CMDS:
        return CMDS[name]
    if name in FUNCTIONS:
        return name + ' '
    return '\\' + name


def symbol_to_text(raw):
    """Best-effort inline LaTeX -> Unicode, plus an honest verdict.

    The verdict is the important half. A token only counts as converted when no
    backslash, brace or caret survives: `e^{-\\tau s}` otherwise collapses to
    something like 'e⁻τ s}', and if that were reported as finished the document
    would show mangled maths with nothing to point at. Wrong-and-flagged beats
    wrong-and-clean.
    """
    s = raw.replace('\\\\', '\\')
    s = re.sub(r'\\hat\{([^{}]*)\}', lambda m: m.group(1) + '̂', s)
    s = re.sub(r'\\dot\{([^{}]*)\}', lambda m: m.group(1) + '̇', s)
    s = re.sub(r'\\bar\{([^{}]*)\}', lambda m: m.group(1) + '̄', s)
    s = re.sub(r'\\sqrt\{([^{}]*)\}', lambda m: '√(' + m.group(1) + ')', s)
    s = re.sub(r'sqrt\(([^()]*(?:\([^()]*\)[^()]*)*)\)',
               lambda m: '√(' + m.group(1) + ')', s)
    s = re.sub(r'\\frac\{([^{}]*)\}\{([^{}]*)\}',
               lambda m: '(' + m.group(1) + ')/(' + m.group(2) + ')', s)
    s = re.sub(r'\\([A-Za-z]+)', lambda m: _expand_cmd(m.group(1)), s)
    s = re.sub(r'_\{([^{}]*)\}', r'_\1', s)
    s = re.sub(r'\^\{?([0-9ni+\-=])\}?',
               lambda m: SUP.get(m.group(1), '^' + m.group(1)), s)
    s = s.strip()
    clean = not any(ch in s for ch in '\\{}') and '^' not in s
    return s, clean


MARKS = [
    (re.compile(r'\[\[EQ:(.*?)\]\]', re.S), 'eq'),
    (re.compile(r'\[\[SYM:(.*?)\]\]', re.S), 'sym'),
    (re.compile(r'\[\[REF:(.*?)\]\]', re.S), 'ref'),
    (re.compile(r'\[\[FIG:(.*?)\]\]', re.S), 'fig'),
    # 清零清单不只一种关键词：正文里除 `<待补充：…>` 外还有 `<待核实：…>`、
    # `<待登记：…>`、`<待实测：…>`。原先只认"待补充"，那几处就以普通文字落纸、
    # 既不高亮也不计数——清单少报，比格式不好看更糟。
    # 行内反引号在 Word 里不该原样露出来：源码里 18 处 `标识符` 只是在强调
    # 那是个代码名，落纸时去掉反引号、文字保留。
    (re.compile(r'`([^`]+)`'), 'code'),
    (re.compile(r'<待[^\n<>]{0,200}>', re.S), 'todo'),
    (re.compile(r'\*\*(.+?)\*\*', re.S), 'bold'),
]

TALLY_KEYS = ('para', 'h1', 'h2', 'h3', 'h4', 'table', 'eq', 'sym_ok',
              'sym_raw', 'fig', 'fig_embedded', 'fig_placeholder',
              'fig_missing_file', 'ref_marker', 'ref_num', 'ref_pending',
              'todo', 'ref_entry')


class Counter(dict):
    def __init__(self):
        dict.__init__(self)
        for key in TALLY_KEYS:
            self[key] = 0


def strip_marks(text):
    text = re.sub(r'\[\[([^\]:]+):([^\]]*)\]\]', lambda m: m.group(2), text)
    # 表题/图题走的是这条路径（不经 emit），反引号在这里也要去掉
    return re.sub(r'`([^`]+)`', lambda m: m.group(1), text).strip()


def _flag(p, text, colour):
    run = p.add_run(text)
    run.font.highlight_color = colour
    return run


def set_cjk(run, name):
    """Pin the east-asian face of one run.

    python-docx's `font.name` writes only w:ascii / w:hAnsi, so setting it to
    黑体 leaves every Chinese glyph on the template's docDefaults face (宋体) --
    the size changes and the typeface does not, which is the kind of defect that
    reads fine in the XML dump and wrong on paper.
    """
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.get_or_add_rFonts()
    rFonts.set(qn('w:eastAsia'), name)
    rFonts.set(qn('w:ascii'), 'Times New Roman')
    rFonts.set(qn('w:hAnsi'), 'Times New Roman')
    return run


def emit(text, p, c):
    """Write `text` into paragraph `p`, splitting on inline marks. `p` may be
    None for a count-only pass, in which case the tallies still move -- that is
    what lets `--check` agree with a real write."""
    while text:
        hit = None
        for rx, kind in MARKS:
            m = rx.search(text)
            if m and (hit is None or m.start() < hit[0]):
                hit = (m.start(), m.end(), kind, m)
        if hit is None:
            if p is not None:
                p.add_run(text)
            return
        start, end, kind, m = hit
        if start and p is not None:
            p.add_run(text[:start])
        inner = m.group(1) if m.groups() else m.group(0)
        inner = inner or ''
        if kind == 'eq':
            c['eq'] += 1
            if p is not None:
                _flag(p, '〔公式待录〕', WD_COLOR_INDEX.YELLOW)
                p.add_run(' ' + inner.replace('\\\\', '\\').strip())
        elif kind == 'sym':
            sym, clean = symbol_to_text(inner)
            c['sym_ok' if clean else 'sym_raw'] += 1
            if p is not None:
                run = p.add_run(sym)
                run.italic = True
                if not clean:
                    run.font.highlight_color = WD_COLOR_INDEX.GRAY_25
        elif kind == 'ref':
            c['ref_marker'] += 1
            num = inner.strip()
            if num.isdigit():
                # 已定号的引文：GB/T 7714 顺序编码制在正文里是**上标 [n]**，
                # 不是灰底占位。这一支是 2026-10-17 那次机械替换之后才会走到的。
                c['ref_num'] += 1
                c['ref_max'] = max(c.get('ref_max', 0), int(num))
                if p is not None:
                    run = p.add_run('[%s]' % num)
                    run.font.superscript = True
            else:
                c['ref_pending'] += 1
                if p is not None:
                    _flag(p, '【待补引文：%s】' % re.sub(r'\s+', ' ', inner).strip(),
                          WD_COLOR_INDEX.GRAY_25)
        elif kind == 'fig':
            key = inner.strip()
            c['fig'] += 1
            fname = FIGURE_MAP.get(key, 'MISSING')
            path = os.path.join(FIGDIR, fname) if fname else None
            if fname and os.path.exists(path):
                c['fig_embedded'] += 1
                if p is not None:
                    run = p.add_run()
                    run.add_picture(path, width=Cm(figure_size_cm(fname)))
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    # 正文样式用的是"固定值"行距，嵌入图片会被裁成一行高——v15 第一次
                    # 导出 PDF 实测：两张 9×16 cm 的板卡照片在页面上各只推进 36 pt
                    # （图块起点 33.48 与 69.48 pt），而且互相重叠。图所在这一段必须
                    # 改回单倍行距，段前段后各留 6 pt 让图不贴着正文。
                    p.paragraph_format.line_spacing = 1
                    p.paragraph_format.space_before = Pt(6)
                    p.paragraph_format.space_after = Pt(6)
                    # 正文样式还带首行缩进，居中的图会被它推右半个字（PDF 实测图块
                    # 中心 315.0 pt，版心中心 304.7 pt）。而且缩进是**按字符**给的
                    # （校模板样式里 `w:firstLineChars="200"` 有 4 处），只写
                    # `w:firstLine="0"` 顶不掉它——模板自己的"无缩进"样式都是两个属性
                    # 一起写 0，这里照它做。
                    p.paragraph_format.first_line_indent = Cm(0)
                    p._p.get_or_add_pPr().get_or_add_ind().set(
                        qn('w:firstLineChars'), '0')
            else:
                # 没有资产就留可见占位，绝不静默丢掉标记：标记丢了，"这张图还没做"
                # 这件事就从正文和清单两边同时消失了。清单里登记了却没找到文件，
                # 是一种比"没登记"更糟的状态（说明清单在说谎），所以单独计数。
                c['fig_missing_file' if fname not in (None, 'MISSING')
                  else 'fig_placeholder'] += 1
                if p is not None:
                    _flag(p, u'〔待补图：%s〕' % key, WD_COLOR_INDEX.YELLOW)
        elif kind == 'code':
            if p is not None:
                p.add_run(inner)
        elif kind == 'todo':
            c['todo'] += 1
            if p is not None:
                _flag(p, m.group(0), WD_COLOR_INDEX.YELLOW)
        elif kind == 'bold':
            if p is not None:
                run = p.add_run(inner)
                run.bold = True
        text = text[end:]


# ------------------------------------------------------------------ numbering
_CN = u'零一二三四五六七八九十'


def cn_num(n):
    """1 -> 一. Chapter titles take the Chinese numeral (第一章) because that is
    what the CAU 撰写规范 writes for a 一级标题 and what every graduated thesis in
    the author's reference folder prints -- the author's own 目录.docx says
    "第1章", which is the one shape the规范 does not use."""
    return _CN[n] if 0 < n < len(_CN) else str(n)


def chapter_of(name):
    """'ch01_draft.md' -> 1, 'abstract_draft.md' -> None (None = never numbered).

    Taken from the file name rather than an incrementing counter, so a chapter
    this tool skips cannot silently shift every later chapter number -- the same
    reason check_thesis_sections.build_numbers() enumerates the FILES list.
    """
    m = re.match(r'ch0*(\d+)', name)
    return int(m.group(1)) if m else None


class Numbering(object):
    """Positional heading numbers: 第一章 / 1.1 / 1.1.1 / 1.1.1.1.

    The rule is deliberately the same one tools/check_thesis_sections.py uses to
    resolve the "见 3.4.1 节" references in the prose, and it is *not* re-derived
    here: the sources carry no numbers, so if the renderer and that checker ever
    disagreed, the paper would print numbers its own cross-references do not
    point at. tests/test_make_thesis_docx.py pins the two against each other.

    State advances only on the headings that are fed in, in document order -- so
    every caller must walk the same block stream (see _heading_rows()).
    """

    def __init__(self, chapter):
        self.chapter = chapter
        self.count = [0, 0, 0]          # h2, h3, h4

    def prefix(self, level):
        if self.chapter is None:
            return u''
        level = min(level, 4)
        if level == 1:
            self.count = [0, 0, 0]
            return u'第%s章 ' % cn_num(self.chapter)
        self.count[level - 2] += 1
        for i in range(level - 1, 3):   # deeper levels restart, as in build_numbers
            self.count[i] = 0
        parts = [str(self.chapter)] + [str(x) for x in self.count[:level - 1]]
        return u'%s ' % '.'.join(parts)


def _heading_rows(name):
    """[(level, prefix, title)] for one source, counters advanced on every
    heading whether or not the caller keeps it. outline() and render_source()
    both go through here, which is what keeps the table of contents and the
    printed headings from ever disagreeing."""
    num = Numbering(chapter_of(name))
    rows = []
    for kind, a, b in [(x[0], x[1], x[2] if len(x) > 2 else '')
                       for x in parse_blocks(read_source(name))]:
        if kind == 'h':
            rows.append((a, num.prefix(a), strip_marks(b)))
    return rows


def hanging_indent(p, chars=2):
    """Give a paragraph a 悬挂缩进 (first line flush, continuation indented).

    Reference lists are set this way -- 王硕(2024) 那一页就是这样排的。段落若沿用
    Normal 的 firstLineChars=200，结果正好相反："[1]" 缩两格、第二行顶格，条目之间
    的边界看不出来。twips 与 *Chars 两套都写：WPS 认字符单位，Word 两个都吃，
    只写一个时另一家会退回默认。
    """
    ind = p._p.get_or_add_pPr().get_or_add_ind()
    size = int(p.runs[0].font.size.pt * 20) if (p.runs and p.runs[0].font.size) \
        else 210
    ind.set(qn('w:left'), str(size * chars))
    ind.set(qn('w:hanging'), str(size * chars))
    ind.set(qn('w:leftChars'), str(chars * 100))
    ind.set(qn('w:hangingChars'), str(chars * 100))
    ind.set(qn('w:firstLine'), '0')
    ind.set(qn('w:firstLineChars'), '0')
    return p


class Renderer(object):
    """Writes blocks into a docx document, or only tallies when check_only."""

    def __init__(self, doc, counter, check_only=False):
        self.doc = doc
        self.c = counter
        self.check = check_only

    def para(self, align=None, tight=False):
        if self.check:
            return None
        p = self.doc.add_paragraph()
        if align is not None:
            p.alignment = align
        if tight:
            p.paragraph_format.space_after = Pt(0)
        return p

    def heading(self, level, text):
        self.c['h%d' % min(level, 4)] += 1
        if not self.check:
            p = self.doc.add_heading(strip_marks(text), level=min(level, 4))
            if level == 1:
                # 校模板的"标题 1"里没有段前分页（当场查 styles.xml：
                # pageBreakBefore 出现 0 次），章标题会接在上一章末尾。学校格式
                # 要求每章另起一页，所以这里逐段加。
                p.paragraph_format.page_break_before = True
            if level >= 2:
                # 模板只在"标题 1"和"标题 3"的样式里写了 firstLine=0，"标题 2"
                # 与"标题 4"没有 ind 覆盖，于是继承 Normal 的首行缩进 2 字符——
                # 1.1 那一行会被推进去两格。规范写"1.1□□□□□（二级标题，左对齐，
                # 单列一行）"，作者参考夹里王硕(2024)、班超(2025)两篇的 1.1 都是
                # 顶格的。与嵌图那一处同理：w:firstLine 顶不过 w:firstLineChars，
                # 两个都得清。
                p.paragraph_format.first_line_indent = 0
                p._p.get_or_add_pPr().get_or_add_ind().set(
                    qn('w:firstLineChars'), '0')

    def caption(self, text):
        p = self.para(align=WD_ALIGN_PARAGRAPH.CENTER, tight=True)
        if p is not None:
            run = p.add_run(strip_marks(text))
            run.font.size = Pt(9)
            # 规范："图、表标题采用小五号黑体"。此前只给了 9pt，中文字形仍由模板
            # docDefaults 的 eastAsia=宋体 决定，落纸是小五宋体。
            set_cjk(run, u'黑体')

    def paragraph(self, text):
        self.c['para'] += 1
        emit(text, self.para(), self.c)

    def note(self, text):
        p = self.para(tight=True)
        if p is not None:
            run = _flag(p, text, WD_COLOR_INDEX.YELLOW)
            run.font.size = Pt(9)


# ------------------------------------------------------------------- tables
def parse_blocks(lines):
    """Yield ('h', level, text) | ('p', text) | ('table', rows)."""
    i, n = 0, len(lines)
    while i < n:
        s = lines[i].strip()
        if not s or s.startswith('<!--') or s == '---':
            i += 1
            continue
        m = re.match(r'^(#{1,4})\s+(.*)$', s)
        if m:
            yield ('h', len(m.group(1)), m.group(2))
            i += 1
            continue
        if s.startswith('|'):
            rows = []
            while i < n and lines[i].strip().startswith('|'):
                cells = [x.strip() for x in lines[i].strip().strip('|').split('|')]
                if not all(re.fullmatch(r':?-{2,}:?', x) for x in cells if x):
                    rows.append(cells)
                i += 1
            yield ('table', rows)
            continue
        buf = []
        while i < n and lines[i].strip() \
                and not lines[i].strip().startswith('|') \
                and not re.match(r'^#{1,4}\s', lines[i].strip()):
            buf.append(lines[i].strip())
            i += 1
        yield ('p', ' '.join(buf))


def three_line(table):
    """三线表: heavy rules above and below the table, a light rule under the
    header row, no vertical rules."""
    tblPr = table._tbl.tblPr
    borders = tblPr.makeelement(qn('w:tblBorders'), {})
    for edge, size in (('top', 12), ('left', 0), ('bottom', 12), ('right', 0),
                       ('insideH', 0), ('insideV', 0)):
        borders.append(borders.makeelement(qn('w:' + edge), {
            qn('w:val'): 'single' if size else 'none', qn('w:sz'): str(size),
            qn('w:space'): '0', qn('w:color'): '000000'}))
    tblPr.append(borders)
    for cell in table.rows[0].cells:
        tcPr = cell._tc.get_or_add_tcPr()
        b = tcPr.makeelement(qn('w:tcBorders'), {})
        b.append(b.makeelement(qn('w:bottom'), {
            qn('w:val'): 'single', qn('w:sz'): '6', qn('w:space'): '0',
            qn('w:color'): '000000'}))
        tcPr.append(b)


def add_table(doc, rows, c, check_only):
    c['table'] += 1
    if not rows:
        return
    ncol = max(len(r) for r in rows)
    if check_only:
        # walk every cell anyway: a check pass that skips table content prints
        # tallies that disagree with a real run (seen as 27 vs 31 待补充)
        for row in rows:
            for j in range(ncol):
                emit(row[j] if j < len(row) else '', None, c)
        return
    t = doc.add_table(rows=len(rows), cols=ncol)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, row in enumerate(rows):
        for j in range(ncol):
            cell = t.cell(i, j)
            cell.text = ''
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            emit(row[j] if j < len(row) else '', p, c)
            for run in p.runs:
                run.font.size = Pt(9)
                run.bold = (i == 0)
    three_line(t)


# ------------------------------------------------------------------ sources
def read_source(name):
    path = os.path.join(CHAPTERS, name)
    if not os.path.exists(path):
        raise SystemExit('missing chapter source: %s' % path)
    with io.open(path, encoding='utf-8') as fh:
        return fh.read().split('\n')


def outline():
    """Heading tree for the dead-text table of contents, with the same numbers
    the body headings carry -- a 目录 that says "研究背景与意义" while the page
    says "1.1 研究背景与意义" is the defect this closes."""
    tree = []
    for name in SOURCES:
        for level, prefix, title in _heading_rows(name):
            if level <= 3:
                tree.append((level, prefix + title))
    return tree


def collect_symbols():
    """Every [[SYM:...]] token with the chapter it first appears in. This is a
    transport of what the sources already say -- meanings are not invented, so
    the 含义 column stays empty for anything this tool could not read."""
    seen = {}
    for name in SOURCES:
        if name.startswith('abstract'):
            continue
        m = re.match(r'ch(\d+)', name)
        chapter = m.group(1) if m else '?'
        text = '\n'.join(read_source(name))
        for hit in re.finditer(r'\[\[SYM:(.*?)\]\]', text, re.S):
            sym, clean = symbol_to_text(hit.group(1))
            if sym and sym not in seen:
                seen[sym] = (clean, chapter)
    return seen


def load_figure_map(path=FIGMAN):
    """Read `04_figures/figures_manifest.md` into {占位标记: 图片文件名}.

    The manifest is the single source for "which figures exist and which are still
    placeholders", so the answer to 'how many figures are missing' is read from one
    table rather than counted out of the Word file. Rows whose File cell is an
    em-dash (no asset yet) are kept in the map with a None value: the generator then
    writes the visible 〔待补图〕 slot instead of silently dropping the marker.
    """
    mapping = {}
    if not os.path.exists(path):
        return mapping
    with io.open(path, encoding='utf-8') as fh:
        for line in fh:
            if not line.strip().startswith('|'):
                continue
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            if len(cells) < 3 or cells[0] in ('ID', '---') or set(cells[0]) <= set('-: '):
                continue
            m = re.search(r'\[\[FIG:([^\]]*)\]\]', cells[2])
            if not m:
                continue
            fname = cells[1].strip('`')
            mapping[m.group(1)] = fname if fname and fname != u'\u2014' else None
    return mapping


def figure_size_cm(name, width_cm=14.0, tall_cm=9.0):
    """Portrait shots (the board photos) get a narrow column so they do not eat
    a whole page; everything else goes full text width."""
    try:
        from PIL import Image
        with Image.open(os.path.join(FIGDIR, name)) as im:
            w, h = im.size
        return tall_cm if h > w * 1.3 else width_cm
    except Exception:
        return width_cm


def _strip_field_machinery(el, tally):
    """Remove Word field machinery from a copied block, keeping what it shows.

    The template's cover is built out of text boxes, a VML shape holding the
    school wordmark, and fields. Two of those are worth naming because they are
    the reason this function exists:

      * MACROBUTTON / other instrText -- the leftovers that made the old file
        slow to open and easy to break;
      * the cover's INCLUDEPICTURE, whose `r:link` points at
        news.cau.edu.cn/upload/2005/...jpg. Checked 2026-10-15: that URL answers
        307 and lands on https://www.cau.edu.cn/ -- it is no longer an image, so
        leaving the link in place puts a red X on the cover. The local copy
        (media/image1.jpeg, reached through rId47) is what actually renders, so
        the link attribute is dropped and the picture is kept.

    Field results are cached text between `separate` and `end`; dropping the
    `fldChar`/`instrText` runs leaves that text behind, which is what we want
    for a cover whose content is fixed wording.
    """
    for tag in ('w:instrText', 'w:fldChar'):
        for node in list(el.iter(qn(tag))):
            parent = node.getparent()
            if parent is None:
                continue
            tally['fields_stripped'] += 1
            if len(parent):
                parent.remove(node)
    # an empty run left behind by the above is noise in the package
    for r in list(el.iter(qn('w:r'))):
        parent = r.getparent()
        if parent is not None and len(r) == 0:
            parent.remove(r)
    # INCLUDEPICTURE's external link: drop the attribute, keep the image
    for attr in ('{%s}link' % _REL_NS, '{%s}href' % _REL_NS):
        for node in list(el.iter()):
            if node.get(attr):
                del node.attrib[attr]
                tally['external_links_dropped'] += 1
    # w:fldSimple wraps content: unwrap it so no field remains
    for simple in list(el.iter(qn('w:fldSimple'))):
        parent = simple.getparent()
        if parent is None:
            continue
        idx = list(parent).index(simple)
        for child in list(simple):
            parent.insert(idx, child)
            idx += 1
        parent.remove(simple)
        tally['fields_stripped'] += 1
    return el


def extract_front_matter(path, keep_box='academic'):
    """Return the template's cover / 书脊 / 声明 blocks, field-free.

    These pages are layout machinery (text boxes, a VML wordmark, four section
    breaks that give the cover its own page numbering). Re-typing them as plain
    paragraphs produces something that only looks like a cover, so they are
    carried over as XML instead -- with the fields stripped by
    _strip_field_machinery() so the result stays as openable as the body.

    keep_box='academic' drops the 专业学位 box (附件2) and keeps 附件1, per the
    author's choice on 2026-10-15; the template's own "使用后删除本框" line is
    left in place so it is visible what still has to go.
    """
    from lxml import etree
    from copy import deepcopy
    tally = {'fields_stripped': 0, 'external_links_dropped': 0,
           'page_breaks_added': 0}
    if not os.path.exists(path):
        return [], tally
    root = etree.fromstring(zipfile.ZipFile(path).read('word/document.xml'))
    kids = list(root.find(qn('w:body')))

    def text_of(el):
        return ''.join(t.text or '' for t in el.iter(qn('w:t'))).strip()

    def find(pattern, start=0):
        for i in range(start, len(kids)):
            if re.match(pattern, text_of(kids[i])):
                return i
        return None

    i_box2 = find(r'^使用后删除本框-附件2')
    i_spine = find(r'^论文成文后删除此页')
    i_abstract = find(r'^摘\s*要')
    if i_abstract is None:
        return [], tally
    blocks = [deepcopy(k) for k in kids[:i_box2 if (
        keep_box == 'academic' and i_box2) else i_abstract]]
    if keep_box == 'academic' and i_box2 is not None and i_spine is not None:
        tail = [deepcopy(k) for k in kids[i_spine:i_abstract]]
        # The template keeps its only explicit page break at the end of the
        # 附件2 block (child 62 as measured 2026-10-15). Dropping that box takes
        # the break with it and the 书脊 page slides up onto the cover, so the
        # join is checked and re-broken rather than assumed.
        joined = ''.join(etree.tostring(k).decode('utf-8') for k in blocks)
        has_break = ('w:type="page"' in joined
                     or 'pageBreakBefore' in joined)
        if not has_break:
            br = etree.SubElement(etree.SubElement(
                etree.fromstring('<w:p xmlns:w="%s"/>' % _W_NS), qn('w:r')),
                qn('w:br'))
            br.set(qn('w:type'), 'page')
            blocks.append(br.getparent().getparent())
            tally['page_breaks_added'] += 1
        blocks += tail
    for el in blocks:
        _strip_field_machinery(el, tally)
    return blocks, tally


def extract_references(path):
    """Carry the reference entries over verbatim from the previous docx."""
    if not os.path.exists(path):
        return []
    from lxml import etree
    W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    root = etree.fromstring(zipfile.ZipFile(path).read('word/document.xml'))
    paras = root.find(W + 'body').findall(W + 'p')

    def text_of(p):
        return ''.join(t.text or '' for t in p.iter(W + 't')).strip()

    hits = [i for i, p in enumerate(paras) if text_of(p) == '参考文献']
    if not hits:
        return []
    out = []
    for p in paras[hits[-1] + 1:]:          # last match = the real section
        t = text_of(p)
        if re.match(r'^(致\s*谢|附\s*录|作者简介)', t):
            break
        if t:
            out.append(t)
    return out


# -------------------------------------------------------------------- build
# 2026-10-17 逐条核过的两处页码订正。表只记"改了什么、凭什么"，判据在下面。
# 为什么只这两处：26 条逐条核到外部记录，20 条一致、2 条核不到权威记录（[12] ICLR、
# [26] CMU 技术报告，没核到就不动）、2 条中文要 CNKI 与国知局（[1]、[8]，留给作者）。
# ⚠️ 反面教训一并留下：[13] PSPNet、[19] Xception、[22] McKyes 这三条，第一轮抓到的
# 读数与正文**不一致**，而复核下来是**注册表那边错、正文对**（CVF 官方页 Xception =
# 1251-1258；多篇独立引用 PSPNet = 2881-2890；[22] 抓到的是两条**书评**记录而不是专著本体）。
# 所以"API 说有差异"不等于"论文写错了"，必须有第二个独立来源才动手——照单全改会一次改坏三条。
REFERENCE_FIXES = (
    (4, '2009: 741-747', '2009: 841-847',
     'Crossref 该章 DOI 10.3920/9789086866649_101 记录 841-847，另有独立引用同读数'),
    (16, '2018: 801-818', '2018: 833-851',
     'Springer 该章 DOI 10.1007/978-3-030-01234-2_49（ECCV 2018 PT VII）= 833-851，'
     '维普与兰州理工检索页同读数'),
)


def apply_reference_fixes(refs):
    """按 REFERENCE_FIXES 改条目文本；找不到原串就抛，不静默跳过。

    "找不到原串"意味着参考文献表已经变了（换版、有人手改过），这时**必须**让人知道，
    否则订正会悄悄失效、错页码又回到正文里。
    """
    n = 0
    for num, old, new, _why in REFERENCE_FIXES:
        idx = num - 1
        if idx >= len(refs):
            raise ValueError('reference [%d] does not exist (%d entries)'
                             % (num, len(refs)))
        if old not in refs[idx]:
            raise ValueError('reference [%d] no longer contains %r; the list '
                             'changed, re-verify before fixing' % (num, old))
        refs[idx] = refs[idx].replace(old, new)
        n += 1
    return refs, n


def repoint_running_header(doc, tag, pred):
    """把**最后一节（正文）**的 default 页眉/页脚指向包里第一份满足 pred 的部件。

    为什么需要：产物沿用的是校模板**最后一节**的页面设置，而模板最后一节是"作者简介"
    ——它的 default 页眉里写死了"作者简介"四个字和"博/硕士"那个待选文本，真正的正文
    页眉（左"中国农业大学硕士学位论文"、右 STYLEREF 标题 1）挂在 **even** 上。
    本包没开奇偶页（settings.xml 里没有 evenAndOddHeaders），所以 Word 永远只用
    default，每一页就打上了"作者简介"。

    另一处坑：`Document.add_section()` 造出来的**新末节是空的**（当场实测：模板 17 节
    加一节变 18 节，第 18 节一条 headerReference 都没有），所以这里不能"在本节里找供体"，
    必须跨全篇按部件内容找，再往末节挂——找不到就返回 0，不静默假装修好。
    """
    rid = _find_rid_with(doc, tag, pred)
    if rid is None:
        return 0
    _default_ref(doc.sections[-1], tag).set(qn('r:id'), rid)
    return 1


def _find_rid_with(doc, tag, pred):
    """在全文档已有的页眉/页脚引用里，找第一份"部件内容满足 pred(blob)"的 rId。

    一律按部件内容找、不按 rId 找：rId 每次生成都会变（包内其它部件一挪就重排）。
    """
    parts = doc.part.related_parts
    for sect in doc.sections:
        for ref in sect._sectPr.findall(qn(tag)):
            rid = ref.get(qn('r:id'))
            blob = getattr(parts.get(rid), 'blob', b'') or b''
            if pred(blob):
                return rid
    return None


def _is_running_header(blob):
    """正文跑动页眉 = 含 STYLEREF，且**不含模板那句占位提示**。

    后半个条件不是洁癖：模板里带 STYLEREF 的页眉部件有七份，其中三份的正文是
    "第二章 双击页眉修改此处章节名称"这类占位文本（当场逐份读 `<w:t>` 得到）。
    只按 STYLEREF 挑就可能挑中那三份之一，于是每一页右上角都印着"双击页眉修改此处"。
    """
    return b'STYLEREF' in blob and u'双击页眉'.encode('utf-8') not in blob


def _is_page_field(blob):
    """带 PAGE 域的页脚（页码的来源）。\\b 是必要的：PAGEREF 里也含 PAGE 子串。"""
    return re.search(rb'\bPAGE\b', blob) is not None


def _default_ref(section, tag, create=True):
    """取（必要时补）某一节的 default 页眉/页脚引用元素。"""
    sectPr = section._sectPr
    for ref in sectPr.findall(qn(tag)):
        if (ref.get(qn('w:type')) or 'default') == 'default':
            return ref
    if not create:
        return None
    el = OxmlElement(tag)
    el.set(qn('w:type'), 'default')
    sectPr.insert(0, el)          # headerReference/footerReference 排在 sectPr 最前
    return el


def _set_pg_num_type(section, fmt, start):
    """写 w:pgNumType。它在 sectPr 里排在 pgMar 之后、cols 之前，所以按后继元素插入。"""
    sectPr = section._sectPr
    el = sectPr.find(qn('w:pgNumType'))
    if el is None:
        el = OxmlElement('w:pgNumType')
        sectPr.insert_element_before(
            el, 'w:cols', 'w:formProt', 'w:vAlign', 'w:noEndnote', 'w:titlePg',
            'w:textDirection', 'w:bidi', 'w:rtlGutter', 'w:docGrid', 'w:docVars',
            'w:sectPrChange')
    el.set(qn('w:fmt'), fmt)
    el.set(qn('w:start'), str(start))
    return el


def apply_pagination(doc):
    """按校模板**自己**的分页方案给产物编页码。

    模板的做法是当场读它 17 个 sectPr 得到的，不是我们发明的：封面那一节
    `upperRoman start=2` 且页眉页脚为空；从摘要起 `upperRoman start=1`、页脚挂 PAGE
    （所以前置页码是 I、II…）；从第 1 章起 **`start=1` 且不带 fmt（即阿拉伯数字）**、
    页脚挂 PAGE、页眉是"校名 + STYLEREF 标题 1"。

    本产物此前只沿用模板最后一节，等于把"作者简介"那一节的设置用到了整篇——
    既没有页码，页眉也错。这里假定调用方已经在"前置／正文"交界处插了一个分节符，
    于是倒数第二节是前置、最后一节是正文，各自设 pgNumType 与页脚。

    返回一份读数供当场打印：挂上了什么、没挂上什么，不返回一个布尔把失败吞掉。
    """
    out = {'front_fmt': '', 'body_fmt': '', 'footer': '', 'front_header': ''}
    if len(doc.sections) < 2:
        return out                          # 没分节，什么都不做（也不假装成功）
    front, body = doc.sections[-2], doc.sections[-1]

    # 正文页眉：先交给 repoint_running_header（它只动最后一节），这里只管页码与页脚。
    page_rid = _find_rid_with(doc, 'w:footerReference', _is_page_field)
    if page_rid:
        _default_ref(front, 'w:footerReference').set(qn('r:id'), page_rid)
        _default_ref(body, 'w:footerReference').set(qn('r:id'), page_rid)
        out['footer'] = page_rid

    # 前置页眉：沿用封面那一节的空页眉（模板的前置节页眉也是空的），
    # 否则摘要与目录头上会顶着正文的跑动章名。
    cover_rid = None
    for ref in doc.sections[0]._sectPr.findall(qn('w:headerReference')):
        if (ref.get(qn('w:type')) or 'default') == 'default':
            cover_rid = ref.get(qn('r:id'))
            break
    if cover_rid:
        _default_ref(front, 'w:headerReference').set(qn('r:id'), cover_rid)
        out['front_header'] = cover_rid

    _set_pg_num_type(front, 'upperRoman', 1)
    _set_pg_num_type(body, 'decimal', 1)
    out['front_fmt'] = 'upperRoman@1'
    out['body_fmt'] = 'decimal@1'
    return out


# 2026-10-27 新增的 7 条文献（编号接在 v14 搬运的 26 条之后）。
# 只收**本机能读到全文或已发表摘要**的文献：五篇学位论文来自作者桌面的 PDF（摘要逐字读过），
# 两篇 Elsevier 综述的卷期页取自 Crossref 记录，期刊论文（农业工程学报）页码取自 PDF
# 首页 34 与末页 44。查不到卷期页的**不收**——"题名看着对就编一条引用"是本仓明令禁止的事。
DROP_REF_NO = 1   # 作者 2026-10-31 裁定删除的那一条

EXTRA_REFERENCES = (
    u'[27] 赖汉荣. 玉米行间除草机器人控制技术研究[D]. 北京: 中国农业大学, 2023.',
    u'[28] 李俊. 玉米作物行间除草机器人行走控制方法与系统设计[D]. 合肥: 安徽农业大学, 2021.',
    u'[29] 张硕. 面向对行视觉导航的作物行识别与跟踪方法研究[D]. 北京: 中国农业大学, 2025.',
    u'[30] 苏童. 基于单目相机的玉米中后期智能农机导航方法研究[D]. 北京: 中国农业大学, 2025.',
    u'[31] 王硕, 苏道毕力格, 王子蒙, 等. 凸轮摆杆式生菜株间除草装置设计与试验[J]. '
    u'农业工程学报, 2021, 37(21): 34-44.',
    u'[32] Upadhyay A, Zhang Y, Koparan C, et al. Advances in ground robotic technologies '
    u'for site-specific weed management in precision agriculture: A review[J]. '
    u'Computers and Electronics in Agriculture, 2024, 225: 109363.',
    u'[33] Saini P, Nagesh D S. A review of deep learning applications in weed detection: '
    u'UAV and robotic approaches for precision agriculture[J]. European Journal of '
    u'Agronomy, 2025, 168: 127652.',
    u'[34] 王硕. 基于深度学习与自适应模型预测控制的株间除草机器人导航方法研究[D]. '
    u'北京: 中国农业大学, 2024.',
    u'[35] 李湘南. 基于视觉的农业机器人生菜田导航算法研究[D]. 北京: 中国农业大学, 2024.',
    u'[36] 班超. 基于多传感器融合的玉米田无人农机环境感知与定位方法研究[D]. '
    u'北京: 中国农业大学, 2025.',
    u'[37] 邱益清. 基于视觉与 GPS 组合的农业机器人自主导航方法研究[D]. 北京: 中国农业大学, 2024.',
)


FINAL_REFERENCES = (
    '[1] Åstrand B, Baerveldt A J. An agricultural mobile robot with vision-based perception for mechanical weed control[J]. Autonomous Robots, 2002, 13(1): 21-35.',
    '[2] Slaughter D C, Giles D K, Downey D. Autonomous robotic weed control systems: A review[J]. Computers and Electronics in Agriculture, 2008, 61(1): 63-78.',
    "[3] Ruckelshausen A, Bise P B, Heme P, et al. BoniRob—an autonomous field robot platform for individual plant phenotyping[C]//Precision Agriculture '09. Wageningen: Wageningen Academic Publishers, 2009: 841-847.",
    '[4] Hague T, Marchant J A, Tillett N D. Ground based sensing systems for autonomous agricultural vehicles[J]. Computers and Electronics in Agriculture, 2000, 25(1/2): 11-28.',
    '[5] Bakker T, Wouters H, van Asselt K, et al. A vision based row detection system for sugar beet[J]. Computers and Electronics in Agriculture, 2008, 60(1): 87-95.',
    '[6] Kise M, Zhang Q, Rovira Más F. A stereovision-based crop row detection method for tractor-automated guidance[J]. Biosystems Engineering, 2005, 90(4): 357-367.',
    '[7] 谭彧, 等. 谷物联合收割机视觉导航路径识别系统: 中国专利 CN103914071.',
    '[8] 李俊. 玉米作物行间除草机器人行走控制方法与系统设计[D]. 合肥: 安徽农业大学, 2021.',
    '[9] 赖汉荣. 玉米行间除草机器人控制技术研究[D]. 北京: 中国农业大学, 2023.',
    '[10] Upadhyay A, Zhang Y, Koparan C, et al. Advances in ground robotic technologies for site-specific weed management in precision agriculture: A review[J]. Computers and Electronics in Agriculture, 2024, 225: 109363.',
    '[11] 王硕. 基于深度学习与自适应模型预测控制的株间除草机器人导航方法研究[D]. 北京: 中国农业大学, 2024.',
    '[12] 周海丽, 马华涛, 俞高红, 王旭, 徐家盛. 旱地株间除草机器人设计与试验[J]. 农业机械学报, 2026, 57(12): 34-43.',
    '[13] 郭宗峻, 车刚, 万霖, 赵乃辰, 臧帅. 基于RecurDyn—EDEM耦合的垄作大豆株间除草装置设计与试验[J]. 中国农机化学报, 2026, 47(6): 66-74.',
    '[14] 陈学深, 钟广泽, 黄凯文, 纪浩楠, 陈土佳, 齐龙. 作业模式可切换的弹齿式稻田除草机器人设计与试验[J]. 农业工程学报, 2026, 42(2): 72-80.',
    '[15] 段宗科, 黄玉巧, 李晓康, 吕凤玉, 古伟, 丁立利. 田间除草机器人机械结构设计与分析[J]. 中国农机化学报, 2025, 46(7): 21-27+42.',
    '[16] 施印炎, 徐浪涛, 汪小旵, 黄薛凯, 王磊, 郑恩来, 王博炜, 袁明华, 沈成. 割台前置式果园除草机器人设计与试验[J]. 农业工程学报, 2026, 42(2): 81-93.',
    '[17] 9 刘星星,车金宁,杨潇,等.枸杞株间电驱动避障除草机设计与试验[J].农业工程学报,2024,40(23):104-114.',
    '[18] 尹麒麟.丘陵果园除草机器人结构设计与控制研究[D].华中农业大学,2023.',
    '[19] 赖长兴.高地隙田间除草机器人系统设计与性能分析[D].福州大学,2023.',
    '[20] 罗强,韩彬,叶松林,等. 丘陵山地果园多功能除草机的设计与试验[J].中国工程机械学报,2026,24 (1):150-15 4.',
    '[21] 黄锋.甘蓝中耕除草机器人结构设计与运动控制研究[D].苏州大学,2024.',
    '[22] 王天健.甘蓝除草机器人视觉识别与伺服控制关键技术研究[D].苏州大学,2023.',
    '[23] 赵鹏.面向草莓田间育苗的激光除草机器人设计与实现[D].西北农林科技大学,2025.',
    '[24] 吴少聪.玉米田间自主导航除草机器人设计与研究[D].河北农业大学,2023.',
    '[25] 赵康.水田除草机器人组合导航控制方法研究[D].哈尔滨工业大学,2025.',
    '[26] 程凯东.水田除草机器人控制系统设计[D].哈尔滨工业大学,2024.',
    '[27] 龚政.基于FPGA 的果园除草机器人控制系统设计与实现[D].华中农业大学,2022.',
    '[28] 张伟康.基于机器视觉的除草机器人目标检测与导航方法研究[D].福州大学,2023.',
    '[29] 付程.红小豆弹齿式苗间除草机设计与试验研究[D].黑龙江八一农垦大学,2025.',
    '[30] 陈海洋.玉米除草机横移机构的设计与研究[D].黑龙江八一农垦大学,2025.',
    '[31] 石文锐.轮式农业移动机器人轨迹跟踪控制研究[D].四川农业大学,2020. 二、研究方案（以下各项均可加页） （包括研究目标、研究内容、拟采取的研究方法、技术路线、实验方案及可行性分析和预期的研究进展） 1、研究目标、研究内容 1.1 研究目标 面向卫星信号全遮挡、林木排布无规律，且伴有高动态破碎斑',
    '[32] 李兆旭.大棚除草机器人导航与作物识别方法研究[D].昆明理工大学,2022.',
    '[33] 胡炼,刘海龙,何杰,等.智能除草机器人研究现状与展望[J].华南农业大学学报, 2023,44(1):34-42.',
    '[34] 张馨悦, 王庆杰, 王超, 徐征鑫, 卢彩云, 何进, 李洪文. 旱田智能化机械除草技术与装备研究进展[J]. 农业机械学报, 2025, 56(4): 22-41+71.',
    '[35] 王真真, 彭强吉, 康建明, 王小瑜, 陈英凯. 果园机械除草发展分析及前景展望[J]. 中国农机化学报, 2025, 46(7): 190-197.',
    '[36] Fountas S,Mylonas N,Malounas I,Rodias E,Hellmann Santos C,Pekkeriet E.Agricultural Robotics for Field Operations[J].Sensors,2020,20(9):2672.',
    '[37] Machleb J,Peteinatos G G,Kollenda B L,Andújar D,Gerhards R.Sensor-based mechanical weed control:Present state and prospects[J].Computers and Electroni',
    '[38] Long J, Shelhamer E, Darrell T. Fully convolutional networks for semantic segmentation[C]//Proceedings of the IEEE Conference on Computer Vision and Pattern Recognition. Boston: IEEE, 2015: 3431-3440.',
    '[39] Ronneberger O, Fischer P, Brox T. U-Net: Convolutional networks for biomedical image segmentation[C]//Medical Image Computing and Computer-Assisted Intervention (MICCAI 2015). Cham: Springer, 2015: 234-241.',
    '[40] He K, Zhang X, Ren S, et al. Deep residual learning for image recognition[C]//Proceedings of the IEEE Conference on Computer Vision and Pattern Recognition. Las Vegas: IEEE, 2016: 770-778.',
    '[41] Yu F, Koltun V. Multi-scale context aggregation by dilated convolutions[C]//International Conference on Learning Representations (ICLR). San Juan, 2016.',
    '[42] Zhao H, Shi J, Qi X, et al. Pyramid scene parsing network[C]//Proceedings of the IEEE Conference on Computer Vision and Pattern Recognition. Honolulu: IEEE, 2017: 2881-2890.',
    '[43] Badrinarayanan V, Kendall A, Cipolla R. SegNet: A deep convolutional encoder-decoder architecture for image segmentation[J]. IEEE Transactions on Pattern Analysis and Machine Intelligence, 2017, 39(12): 2481-2495.',
    '[44] Chen L C, Papandreou G, Schroff F, et al. Rethinking atrous convolution for semantic image segmentation[EB/OL]. (2017-06-15). arXiv: 1706.05587.',
    '[45] Chen L C, Zhu Y, Papandreou G, et al. Encoder-decoder with atrous separable convolution for semantic image segmentation[C]//Proceedings of the European Conference on Computer Vision (ECCV). Munich: Springer, 2018: 833-851.',
    '[46] Howard A G, Zhu M, Chen B, et al. MobileNets: Efficient convolutional neural networks for mobile vision applications[EB/OL]. (2017-04-17). arXiv: 1704.04861.',
    '[47] Sandler M, Howard A, Zhu M, et al. MobileNetV2: Inverted residuals and linear bottlenecks[C]//Proceedings of the IEEE Conference on Computer Vision and Pattern Recognition. Salt Lake City: IEEE, 2018: 4510-4520.',
    '[48] Chollet F. Xception: Deep learning with depthwise separable convolutions[C]//Proceedings of the IEEE Conference on Computer Vision and Pattern Recognition. Honolulu: IEEE, 2017: 1251-1258.',
    '[49] Oktay O, Schlemper J, Folgoc L L, et al. Attention U-Net: Learning where to look for the pancreas[EB/OL]. (2018-04-11). arXiv: 1804.03999.',
    '[50] Redmon J, Farhadi A. YOLOv3: An incremental improvement[EB/OL]. (2018-04-08). arXiv: 1804.02767.',
    '[51] 张硕. 面向对行视觉导航的作物行识别与跟踪方法研究[D]. 北京: 中国农业大学, 2025.',
    '[52] 苏童. 基于单目相机的玉米中后期智能农机导航方法研究[D]. 北京: 中国农业大学, 2025.',
    '[53] Saini P, Nagesh D S. A review of deep learning applications in weed detection: UAV and robotic approaches for precision agriculture[J]. European Journal of Agronomy, 2025, 168: 127652.',
    '[54] Li Y,Guo Z,Shuang F,Zhang M,Li X.Key technologies of machine vision for weeding robots:A review and benchmark[J].Computers and Electronics in Agricult',
    '[55] Sampurno M R, Liu Z, Nakaguchi M V, et al. Development of a new Single-Tree-Row-Tracking robot navigation for intra-row weeding operations in orchard',
    '[56] Kanagasingham S, Ekpanyapong M, Chaihan R. Integrating machine vision-based row guidance with G PS and compass-based routing to achieve autonomous na',
    '[57] 刘子翔, 李彦明, 肖扬帆, 黄飞, 郭溢波. 基于车轮-水稻行线位姿关系的水田除草机器人视觉导航[J]. 农机化研究, 2025, 47(11): 220-227.',
    '[58] 赖汉荣,张亚伟,张宾,等. 玉米除草机器人视觉导航系统设计与试验[J].农业工程学报,2023,39 (1):18-27.',
    '[59] 高颖, 祁媚, 王敏, 徐卫明. 面向大规模农田作业的除草机器人路径规划算法[J]. 中国农机化学报, 2025, 46(11): 178-187.',
    '[60] 李湘南. 基于视觉的农业机器人生菜田导航算法研究[D]. 北京: 中国农业大学, 2024.',
    '[61] 班超. 基于多传感器融合的玉米田无人农机环境感知与定位方法研究[D]. 北京: 中国农业大学, 2025.',
    '[62] 邱益清. 基于视觉与 GPS 组合的农业机器人自主导航方法研究[D]. 北京: 中国农业大学, 2024.',
    '[63] McKyes E. Soil cutting and tillage[M]. Amsterdam: Elsevier, 1985.',
    '[64] Zhang M, Liu D, Xu J, et al. A non-contact intra-row weeding device for rice based on high-speed ga s jet: Design and experiment[J].Biosystems Engine',
    '[65] Zhou W, Song K, Sun X, et al. Design Optimization and Mechanism Analysis of Water Jet-Type Inter -Plant Weeding Device for Water Fields[J].Agronomy,2',
    '[66] Yu Z, He X, Qi P, et al. A Static Laser Weeding Device and System Based on Fiber Laser: Develop ment, Experimentation, and Evaluation[J].Agronomy,202',
    '[67] Hu R, Niu T L, Su H W. A novel mechanical-laser collaborative intra-row weeding prototype: structur al design and optimization, weeding knife simulat',
    '[68] Ye S, Xue X, Si S, et al. Design and Testing of an Elastic Comb Reciprocating a Soybean Plant-to-Pl ant Seedling Avoidance and Weeding Device[J].Agri',
    '[69] Jiao J, Hu L, Chen G, et al. Development and Experimentation of Intra-Row Weeding Device for Org anic Rice[J].Agriculture,2024,14 (1):146-.',
    '[70] Khadatkar A, Sujit P, Agrawal R, et al. WeeRo: Design, development and application of a remotely co ntrolled robotic weeder for mechanical weeding in',
    '[71] 王硕, 苏道毕力格, 王子蒙, 等. 凸轮摆杆式生菜株间除草装置设计与试验[J]. 农业工程学报, 2021, 37(21): 34-44.',
    '[72] Zhang Z. A flexible new technique for camera calibration[J]. IEEE Transactions on Pattern Analysis and Machine Intelligence, 2000, 22(11): 1330-1334.',
    '[73] Kalman R E. A new approach to linear filtering and prediction problems[J]. Journal of Basic Engineering, 1960, 82(1): 35-45.',
    '[74] Coulter R C. Implementation of the pure pursuit path tracking algorithm[R]. Pittsburgh: Carnegie Mellon University, CMU-RI-TR-92-01, 1992.',
    '[75] Snider J M. Automatic steering methods for autonomous automobile path tracking[R]. Pittsburgh: Carnegie Mellon University, CMU-RI-TR-09-08, 2009.',
    '[76] 吴江东,潮群,刘成良,等. 无人驾驶农机曲率自适应轨迹规划与跟踪控制协同优化方法[J].农业工程学报,20 26,42 (3):1-12.',
    '[77] 沈跃,王辉,张亚飞,等. 基于扰动补偿的林果园轮式机器人ENMPC 轨迹跟踪方法[J].农业工程学报,2026,42 (3):26-35.',
    '[78] Liu H, Han Z, Yin J, et al. Path tracking control method for tracked agricultural vehicles based on sli p-aware look-ahead point offset[J].Frontiers',
    '[79] An G, Du J, Jin C, et al. Error Threshold-Based Autonomous Navigation with Right-Angle Turning for Crawler-Type Combine Harvesters in Paddy Fields[J]',
    '[80] 韩豹, 郭畅, 高英玲, 刘俏, 孙硕, 董小伟. 大豆株间除草单体机构及关键部件设计与试验[J]. 农业机械学报, 2020, 51(6): 112-121.',
    '[81] 权龙哲, 王旗, 张景禹, 冯槐区, 吴冰. 立式旋转智能株间机械除草装置设计与试验[J]. 江苏大学学报(自然科学版), 2021, 42(5): 582-588.',
    '[82] 赵世帝. 白菜苗间机械除草装置及控制系统设计与试验[D]. 黑龙江八一农垦大学, 2025.',
    '[83] 潘博宇. 垄作玉米避苗除草装置设计与试验[D]. 黑龙江八一农垦大学, 2026.',
    '[84] 龚长江.垄作白芍机械除草装置设计与试验[D].安徽农业大学,2024.',
    '[85] 李祺. 玉米机械行间除草电控液压驱动控制系统研究[D]. 黑龙江八一农垦大学, 2025.',
    '[86] 冀杰, 贺庆, 赵立军, 李平, 刘洋, 王小康. 除草机器人自适应快速积分终端滑模跟踪控制技术[J]. 农业机械学报, 2023, 54(6): 55-64.',
    '[87] 臧帅. 基于改进YOLO11的大豆株间机械除草识别算法与试验验证[D]. 黑龙江八一农垦大学, 2026.',
    '[88] 唐子昊. 大豆玉米复合种植对行除草机设计与试验研究[D]. 扬州大学, 2025.',
    '[89] 郑和, 李紫琪, 单以才, 朱烨均, 肖茂华. 农田机械除草技术与装备研究现状与发展趋势[J]. 南京农业大学学报, 2025, 48(2): 285-295.',
    '[90] 邢钦淞, 丁素明, 薛新宇, 崔龙飞, 乐飞翔, 李鹰航. 智能田间除草机器人发展现状研究[J]. 中国农机化学报, 2022, 43(8): 173-181.',
    '[91] 王欣星, 王新利. 农业劳动力老龄化对农业碳排放的影响——基于农业技术创新调节效应[J]. 黑龙江八一农垦大学学报, 2021, 33(3): 121-126.',
    '[92] 农业农村部. “十四五”全国农业机械化发展规划[Z]. 2021.',
    '[93] 邓佳玉, 胡军, 李庆达, 李海亮, 于天驰. 基于EDEM离散元法的深松铲仿真与试验研究[J]. 中国农机化学报, 2016, 37(4): 14-18.',
    '[94] 贾洪雷, 王万鹏, 陈志, 郑铁志, 张鹏, 庄健. 农业机械触土部件优化研究现状与展望[J]. 农业机械学报, 2017, 48(7): 1-13.',
)

# ------------------------------------------------------- reference-list cleanup
# FINAL_REFERENCES was merged from three sources (v14 搬运、作者 10-31 导出的
# CNKI .net、开题报告参考文献). Each source brought its own spacing habits, and
# the 外文那一族是从 PDF 里复制的——复制被截断在约 120 字符处，于是 13 条只到
# 期刊名一半。2026-11-02 按作者"论文格式也要合格"的要求统一处理，分两层：
#   REFERENCE_COMPLETIONS —— 补内容（截断的条目按 Crossref 逐条 DOI 回填）
#   normalize_reference() —— 补格式（空格、断词、三位以上责任者）
# 两层都在 build() 里做，测试钉住"产物里不许再出现这些形状"。
#
# 补全的每一条都带 DOI：数值不是记忆，是当场 API 读数，作者可十秒复核。
REFERENCE_COMPLETIONS = {
    # 专利：GB/T 7714 的著录责任者是申请人；公开日 2014-07-09、申请号取自
    # Google Patents 的 CN103914071A/B 页（原条目只写了发明人和公开号）。
    7: u'[7] 中国农业大学. 一种用于谷物联合收割机的视觉导航路径识别系统: '
       u'CN201410132110.3[P]. 2014-07-09.',
    # 开题那条是从开题报告里整段复制的，把"二、研究方案……"的模板正文一起带进了
    # 参考文献表（原条目末尾 200 多字都是开题文字）。这里只留著录项本身。
    31: u'[31] 石文锐. 轮式农业移动机器人轨迹跟踪控制研究[D]. 四川农业大学, 2020.',
    # 下面 12 条原文被复制截断（期刊名/年/卷/页缺失）。每一条的 DOI 记在本条注释
    # 里，不进论文正文（GB/T 7714 的期刊条目不要求 DOI，且句末句点会粘在 URL 上）：
    #   37 10.1016/j.compag.2020.105638   54 10.1016/j.compag.2022.106880
    #   55 10.1016/j.compag.2026.111491   56 10.1007/s11119-019-09697-z
    #   64 10.1016/j.biosystemseng.2025.104227
    #   65 10.3390/agronomy13051305       66 10.3390/agronomy14071426
    #   67 10.3389/fpls.2024.1469098      68 10.3390/agriculture13112157
    #   70 10.1016/j.rineng.2025.105202   78 10.3389/fpls.2025.1754679
    #   79 10.3390/agriculture16010042
    # 年、卷、页一律取 Crossref 当场读数（tools/_ref_doi.py、tools/_ref_dates.py）。
    37: u'[37] Machleb J, Peteinatos G G, Kollenda B L, et al. Sensor-based '
        u'mechanical weed control: Present state and prospects[J]. Computers and '
        u'Electronics in Agriculture, 2020, 176: 105638.',
    54: u'[54] Li Y, Guo Z, Shuang F, et al. Key technologies of machine vision '
        u'for weeding robots: A review and benchmark[J]. Computers and Electronics '
        u'in Agriculture, 2022, 196: 106880.',
    55: u'[55] Sampurno R M, Liu Z, Nakaguchi V M, et al. Development of a new '
        u'Single-Tree-Row-Tracking robot navigation for intra-row weeding '
        u'operations in orchards using a machine stereo vision system and LiDAR[J]. '
        u'Computers and Electronics in Agriculture, 2026, 244: 111491.',
    56: u'[56] Kanagasingham S, Ekpanyapong M, Chaihan R. Integrating machine '
        u'vision-based row guidance with GPS and compass-based routing to achieve '
        u'autonomous navigation for a rice field weeding robot[J]. Precision '
        u'Agriculture, 2020, 21(4): 831-855.',
    64: u'[64] Zhang M, Liu D, Xu J, et al. A non-contact intra-row weeding device '
        u'for rice based on high-speed gas jet: Design and experiment[J]. '
        u'Biosystems Engineering, 2025, 257: 104227.',
    65: u'[65] Zhou W, Song K, Sun X, et al. Design optimization and mechanism '
        u'analysis of water jet-type inter-plant weeding device for water '
        u'fields[J]. Agronomy, 2023, 13(5): 1305.',
    66: u'[66] Yu Z, He X, Qi P, et al. A static laser weeding device and system '
        u'based on fiber laser: Development, experimentation, and evaluation[J]. '
        u'Agronomy, 2024, 14(7): 1426.',
    67: u'[67] Hu R, Niu L T, Su W H. A novel mechanical-laser collaborative '
        u'intra-row weeding prototype: structural design and optimization, weeding '
        u'knife simulation and laser weeding experiment[J]. Frontiers in Plant '
        u'Science, 2024, 15: 1469098.',
    68: u'[68] Ye S, Xue X, Si S, et al. Design and testing of an elastic comb '
        u'reciprocating a soybean plant-to-plant seedling avoidance and weeding '
        u'device[J]. Agriculture, 2023, 13(1): 2157.',
    70: u'[70] Khadatkar A, Sujit P, Agrawal R, et al. WeeRo: Design, development '
        u'and application of a remotely controlled robotic weeder for mechanical '
        u'weeding in row crops for sustainable crop production[J]. Results in '
        u'Engineering, 2025, 26: 105202.',
    78: u'[78] Liu H, Han Z, Yin J, et al. Path tracking control method for tracked '
        u'agricultural vehicles based on slip-aware look-ahead point offset[J]. '
        u'Frontiers in Plant Science, 2026, 16: 1754679.',
    79: u'[79] An G, Du J, Jin C, et al. Error threshold-based autonomous navigation '
        u'with right-angle turning for crawler-type combine harvesters in paddy '
        u'fields[J]. Agriculture, 2025, 16(1): 42.',
}

# 从 PDF 复制时按行断开留下的"词中被拆开"。逐条列出、不做通用猜测：
# 通用规则会把 "in A" 这类正常搭配也粘上，宁可漏一处也不制造错词。
REF_SPLIT_WORDS = (
    (u'G PS', u'GPS'),
    (u'ga s jet', u'gas jet'),
    (u'Inter -Plant', u'Inter-Plant'),
    (u'Inter - row', u'Inter-row'),
    (u'Intra- Row', u'Intra-Row'),
    (u'Develop ment', u'Development'),
    (u'structur al', u'structural'),
    (u'Plant-to-Pl ant', u'Plant-to-Plant'),
    (u'Org anic', u'Organic'),
    (u'co ntrolled', u'controlled'),
    (u'sli p-aware', u'slip-aware'),
    (u'Single- Tree', u'Single-Tree'),
    (u'visu al', u'visual'),
    (u'reciprocat ing', u'reciprocating'),
)


_REF_TYPE_MARK = re.compile(r'\[(?:J|D|C|M|R|S|EB/OL|DB/OL|CP/OL|A|Z)\]')


def _author_span(s):
    """Index range of the 责任者 segment, or None when it cannot be told apart.

    The segment ends at the first '.' that is followed by a space, a capital or a
    Chinese character, and it never runs past the type mark -- that is what keeps
    "Pekkeriet E.Agricultural Robotics for Field Operations[J]" from being read as
    one long author list, which is how [36] lost its title on the first attempt.
    """
    m = re.match(r'^\[\d+\]\s*', s)
    if not m:
        return None
    start = m.end()
    mark = _REF_TYPE_MARK.search(s)
    limit = mark.start() if mark else len(s)
    j = start
    while j < limit:
        k = s.find('.', j, limit)
        if k < 0:
            break
        nxt = s[k + 1:k + 2]
        if nxt == u' ' or (nxt and (nxt.isupper()
                                    or u'\u4e00' <= nxt <= u'\u9fff')):
            return (start, k)
        j = k + 1
    return None


def normalize_reference(entry):
    """One reference line -> the shape GB/T 7714 顺序编码制 prints.

    Mechanical only: no bibliographic claim is invented here. Everything that
    needed a fact (year, volume, pages) went through REFERENCE_COMPLETIONS, whose
    DOIs are recorded in the comment above that table.
    """
    s = entry.strip()
    # 1. 复制时混进来的裸数字（开题正文的条目序号被当成作者名第一个 token）
    s = re.sub(r'^(\[\d+\])\s+\d+\s+', r'\1 ', s)
    for bad, good in REF_SPLIT_WORDS:
        s = s.replace(bad, good)
    # 2. 数字被拆开：'20 26'（年）、'42 (3)'（卷期）、'150-15 4'（页码）、'146-.'
    s = re.sub(r'\b(19|20)\s+(\d{2})\b', r'\1\2', s)
    s = re.sub(r'(\d)\s+\((\d+)\)', r'\1(\2)', s)
    s = re.sub(r'(?<=\d)-(\d{1,3})\s+(\d)', r'-\1\2', s)
    s = re.sub(r'(?<=\d)-\s+(\d)', r'-\1', s)
    s = re.sub(r'(?<=\d)-(?=\.?\s*$)', '', s)
    # 3. 类型标记之后统一 '. '（'[C]//' 是会议录的写法，斜杠前不加点）
    s = re.sub(r'\[(J|D|C|M|R|S|EB/OL|DB/OL|CP/OL|A|Z)\]\.(?=\S)', r'[\1]. ', s)
    s = re.sub(r'\[(J|D|C|M|R|S|EB/OL|DB/OL|CP/OL|A|Z)\](?=[^\s./])', r'[\1]. ', s)
    # 4. 逗号之后先统一一个空格——**必须在责任者截断之前**：'Fountas S,Mylonas N,…'
    #    这种没有空格的写法若后处理，split(', ') 会把六个作者读成一个，截断静默失效。
    s = re.sub(u'，', u', ', s)
    s = re.sub(r',(?=[0-9A-Za-z\u4e00-\u9fff(])', ', ', s)
    # 5. GB/T 7714：责任者 3 名以上只列前 3 名，其后加"等"/"et al."
    span = _author_span(s)
    if span:
        head = s[span[0]:span[1]]
        parts = [p.strip() for p in head.split(u', ') if p.strip()]
        if len(parts) > 3 and not any(p.startswith((u'等', 'et al'))
                                      for p in parts[3:]):
            tail = u'et al.' if re.search(r'[A-Za-z]', parts[0]) else u'等'
            s = s[:span[0]] + u', '.join(parts[:3]) + u', ' + tail + s[span[1]:]
    # 6. 句点之后统一一个空格（'尹麒麟.丘陵'、'2020.105638' 里的数字除外）
    s = re.sub(r'\.(?=[A-Z\u4e00-\u9fff])', '. ', s)
    # 6. 页码前统一 ': '
    s = re.sub(r':(?=\d)', r': ', s)
    # 7. 收尾：全角冒号、多余空格、句点叠印、句末点号
    s = s.replace(u'：', ': ')
    s = re.sub(r':\s{2,}', ': ', s)
    # 责任者截断把 "…Pekkeriet E" 换成 "…et al." 时，原来那个分隔句点还在，
    # 于是印出 "et al.."。参考文献里没有合法的连续句点，直接压成一个。
    s = re.sub(r'\.{2,}', '.', s)
    s = re.sub(r'\s{2,}', ' ', s)
    if not s.endswith('.'):
        s += '.'
    return s


def build_references():
    """The list that actually goes on paper: completions first, then format."""
    refs = []
    for i, entry in enumerate(FINAL_REFERENCES, 1):
        refs.append(normalize_reference(REFERENCE_COMPLETIONS.get(i, entry)))
    return refs


def build(check_only=False, cover='academic'):
    doc = docx.Document(TEMPLATE)
    if not check_only:
        body = doc.element.body
        sect = body.find(qn('w:sectPr'))     # keep page setup and the section
        for child in list(body):
            if child is not sect:
                body.remove(child)
        # 正文尺寸**不由这里决定**（2026-11-02 撤掉原先的
        # `doc.styles['Normal'].font.size = Pt(10.5)`）。撤的理由是实测：
        # 模板自己的 Normal 是 sz=24（小四 12pt）+ 行距 360 exact（18 磅），而
        # 作者参考夹里 10 篇中国农业大学已毕业硕士论文（王硕/班超/苏童/赖汉荣/
        # 邱益清/程园/张硕/李湘南/李俊/V11）正文可抽取字数的众数**全是 12pt
        # SimSun**，没有一篇是 10.5pt。那句覆盖是首版生成器顺手加的、没有出处，
        # 它让整篇正文比模板和所有样本小一档。规范条文里"五号宋体/18 磅"这一句
        # 与模板和样本都不一致，按模板与样本执行。
        #
        # 也不是写成 `font.size = None`：那会把模板 Normal 里那条 <w:sz w:val="24"/>
        # 删掉，而 docDefaults 没有 sz，Word 会退回 10pt——正文反而更小。
        # 什么都不做才是"用模板的 12pt"。
        if cover in ('academic', 'both'):
            blocks, fm_tally = extract_front_matter(
                TEMPLATE, keep_box=cover)
            for el in blocks:
                sect.addprevious(el)         # front matter goes first
            _fm_stats['blocks'] = len(blocks)
            _fm_stats['fields_stripped'] = fm_tally['fields_stripped']
            _fm_stats['links_dropped'] = fm_tally['external_links_dropped']
            _fm_stats['breaks_added'] = fm_tally['page_breaks_added']

    global FIGURE_MAP
    FIGURE_MAP = load_figure_map()

    c = Counter()
    r = Renderer(doc, c, check_only=check_only)

    def render_source(name):
        num = Numbering(chapter_of(name))
        for kind, a, b in [(x[0], x[1], x[2] if len(x) > 2 else '')
                           for x in parse_blocks(read_source(name))]:
            if kind == 'h':
                r.heading(a, num.prefix(a) + b)
            elif kind == 'table':
                add_table(doc, a, c, check_only)
            else:
                if re.match(r'^(表|图)\s*\d+[-–]\d+', a) and '[[FIG' not in a:
                    r.caption(a)
                else:
                    r.paragraph(a)

    render_source('abstract_draft.md')

    # 目录 -- after the abstracts, as the school format requires
    r.heading(1, '目 录')
    for level, title in outline():
        c['para'] += 1
        p = r.para(tight=True)
        if p is not None:
            run = p.add_run(('' if level == 1 else '　' * (level - 1)) + title)
            run.font.size = Pt(10.5 if level == 1 else 9)
    r.note('〔本目录为死文本、不含页码：版式定稿后用 Word「引用—目录—自动目录」'
           '一次性生成，免得每次改动都留下 PAGEREF 域〕')

    # 主要符号表 -- collected from the sources, meanings left to the author
    r.heading(1, '主要符号表')
    syms = collect_symbols()
    c['table'] += 1
    if not check_only and syms:
        t = doc.add_table(rows=len(syms) + 1, cols=3)
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        for j, head in enumerate(('符号', '含义', '首次出现')):
            cell = t.cell(0, j)
            cell.text = ''
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(head)
            run.bold = True
            run.font.size = Pt(9)
        for i, (sym, (clean, chapter)) in enumerate(sorted(syms.items()), start=1):
            cells = (sym, '' if clean else '（未能安全转码，见正文灰底处）',
                     '第 %s 章' % chapter)
            for j, value in enumerate(cells):
                cell = t.cell(i, j)
                cell.text = ''
                run = cell.paragraphs[0].add_run(value)
                run.font.size = Pt(9)
                run.italic = (j == 0)
        three_line(t)

    if not check_only:
        # 前置（摘要/Abstract/目录/符号表）与正文分节：模板自己就是这么分的
        # （摘要起 upperRoman、第 1 章起 decimal 且 start=1），不分节就没法给两套页码。
        doc.add_section(WD_SECTION.NEW_PAGE)

    for name in SOURCES[1:]:
        render_source(name)

    # 2026-10-31 起参考文献表是**固定列表**（90 条，按正文首次出现排序），不再从 v14 搬：
    # 三条来源合并去重后人工挑定，逐条都在正文有引用。extract_references/apply_reference_fixes
    # 保留下来给测试与追溯用，build() 不再调用。
    # 2026-11-02：落纸前再过一层 build_references()——12 条被复制截断的外文按
    # Crossref 当场读数补全，其余做格式归一（空格、断词、三位以上责任者）。
    refs = build_references()
    n_fixed = 0   # 两条页码订正已写进 FINAL_REFERENCES 本体，运行时不再单独订正
    # 2026-10-31 作者裁定删掉 [1]（潘月占等：期刊不合格且未发表），其后全部前移一位。
    # 两条号码订正在上面按**旧号**做完再删，所以 apply_reference_fixes 里的编号不用动。
    # 渲染完再查：正文里最大的引文号不得超过参考文献条数。2026-10-27 差点栽在这里——
    # 先把 [[REF:27..33]] 写进正文、参考文献表还是 26 条，产物会印出指向空号的 [27]。
    if not check_only:
        assert c.get('ref_max', 0) <= len(refs), (
            'citation [%d] points past the %d-entry reference list'
            % (c.get('ref_max', 0), len(refs)))
    c['ref_fixed'] = n_fixed
    r.heading(1, '参考文献')
    for entry in refs:
        c['ref_entry'] += 1
        p = r.para(tight=True)
        if p is not None:
            run = p.add_run(entry)
            run.font.size = Pt(9)
            hanging_indent(p)

    if not check_only:
        # 页眉改向：不修的话每一页右上角都是"作者简介"（理由见函数 docstring）。
        n = repoint_running_header(doc, 'w:headerReference', _is_running_header)
        c['hdr_repointed'] = n
        # 页码：分节之后才能挂（上面已经 add_section 了），方案照模板自己那套。
        pg = apply_pagination(doc)
        c['page_front'] = pg['front_fmt']
        c['page_body'] = pg['body_fmt']
        c['page_footer'] = pg['footer']
        if not os.path.isdir(OUTDIR):
            os.makedirs(OUTDIR)
        doc.save(OUT_DOCX)
        # 覆盖式副本：只留最新一版。复制后比一次字节数，避免"看着复制了其实是旧文件"。
        try:
            import shutil
            shutil.copyfile(OUT_DOCX, LATEST)
            assert os.path.getsize(LATEST) == os.path.getsize(OUT_DOCX)
            c['latest_copy'] = LATEST
        except OSError as e:
            c['latest_copy'] = 'FAILED: %s' % e
    return c, len(refs)


# ------------------------------------------------------------------- verify
# a:blip 与 w:pict 是图片/图形，不是域；分开列才不会被读成「还有域没清」。
FIELD_TAGS = ('w:fldChar', 'w:instrText', 'w:pict', 'w:object', 'a:blip',
              'w:hyperlink', 'w:altChunk', 'w:sdt')
FIELD_KINDS = ('MACROBUTTON', 'INCLUDEPICTURE', 'PAGEREF', 'SEQ', 'TOC', 'REF')


def verify(path=OUT_DOCX):
    """Re-open the written package and count the things the user is paying us to
    get rid of. Body and header/footer are reported separately on purpose: the
    body is field-free, while the running heads still carry the template's own
    PAGE and STYLEREF fields."""
    z = zipfile.ZipFile(path)
    xml = z.read('word/document.xml').decode('utf-8', 'replace')
    counts = dict((tag, xml.count(tag)) for tag in FIELD_TAGS)
    for kind in FIELD_KINDS:
        counts['instr ' + kind] = len(re.findall(
            r'<w:instrText[^>]*>[^<]*\b%s\b' % kind, xml))
    hf_parts = [n for n in z.namelist() if 'header' in n or 'footer' in n]
    hf_fields = sum(z.read(n).decode('utf-8', 'replace').count('w:fldChar')
                    for n in hf_parts)
    return (counts, xml.count('</w:p>'), xml.count('<w:tbl>'),
            len(z.namelist()), len(hf_parts), hf_fields)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true', help='parse only, write nothing')
    ap.add_argument('--verify', action='store_true',
                    help='re-open the output and count fields')
    ap.add_argument('--cover', choices=('academic', 'both', 'none'),
                    default='academic',
                    help='which cover box to carry from the template '
                         '(academic = 附件1 only, the author\'s choice 2026-10-15)')
    args = ap.parse_args()

    if args.verify:
        counts, paras, tables, parts, hf_parts, hf_fields = verify()
        print('verify %s' % OUT_DOCX)
        print('  body: paragraphs %d, tables %d, package parts %d'
              % (paras, tables, parts))
        for key in sorted(counts):
            note = ''
            if key in ('a:blip', 'w:pict'):
                note = '   <- 图片/图形，不是域'
            print('  %-18s %d%s' % (key, counts[key], note))
        print('  header/footer parts %d, their fldChar %d (template PAGE / '
              'STYLEREF, not body fields)' % (hf_parts, hf_fields))
        return

    c, nrefs = build(check_only=args.check, cover=args.cover)
    print('mode        : %s' % ('check (nothing written)' if args.check
                                else 'write -> ' + OUT_DOCX))
    print('cover       : %s -> %d template blocks carried, %d field nodes '
          'stripped, %d dead external picture link(s) dropped, '
          '%d page break(s) re-added at the box seam'
          % (args.cover, _fm_stats['blocks'], _fm_stats['fields_stripped'],
             _fm_stats['links_dropped'], _fm_stats['breaks_added']))
    print('headings    : %d/%d/%d (h1/h2/h3)   paragraphs %d   tables %d'
          % (c['h1'], c['h2'], c['h3'], c['para'], c['table']))
    print('formulas    : %d kept raw (entered by hand in Word)' % c['eq'])
    print('symbols     : %d converted, %d flagged as not safely convertible'
          % (c['sym_ok'], c['sym_raw']))
    print('figures     : %d embedded, %d placeholder (no asset yet), '
          '%d registered but file missing'
          % (c['fig_embedded'], c['fig_placeholder'], c['fig_missing_file']))
    # 标签用 ASCII：这一行要被人复制进版本清单，而控制台编码（本机 cp936）会把
    # 中文标签打成问号——读数是对的，标签却不可读。
    print('placeholders: fig markers %d, ref %d, todo %d'
          % (c['fig'], c['ref_marker'], c['todo']))
    # 引文分两栏报，是因为"还剩几处没定号"这件事不能藏在"41 处标记"这种混合计数里。
    print('citations   : %d resolved [n] (superscript), %d still placeholder'
          % (c['ref_num'], c['ref_pending']))
    print('references  : %d entries carried over, %d corrected against registry'
          % (nrefs, c.get('ref_fixed', 0)))
    print('latest copy : %s' % (c.get('latest_copy') or '-'))
    # 页眉改向是"写了才算做了"的那类事，所以把当场结果打出来，不让人靠读代码推断。
    # check 模式不写文件也不改页眉，这里如实报 0。
    print('running hdr : %d body-section header reference(s) repointed'
          ' (0 in --check: nothing is written)'
          % c.get('hdr_repointed', 0))
    # 页码是"挂上没挂上"必须能被读出来的那一类，所以把方案与页脚部件一起打出来。
    print('pagination  : front %s  body %s  footer part %s'
          ' (--check writes nothing, so all three read "-")'
          % (c.get('page_front') or '-', c.get('page_body') or '-',
             c.get('page_footer') or '-'))


if __name__ == '__main__':
    main()
