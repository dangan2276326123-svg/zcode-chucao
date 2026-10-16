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
from docx.shared import Pt

THESIS = os.environ.get('THESIS_DIR') or r'D:\JetBrains\chucao_prj\thesis_cau'
TEMPLATE = os.path.join(THESIS, '01_template', 'original_template.docx')
CHAPTERS = os.path.join(THESIS, '03_chapters')
OUTDIR = os.path.join(THESIS, '10_output')
PREV_DOCX = os.path.join(OUTDIR, 'thesis_draft_v14.docx')
OUT_DOCX = os.path.join(OUTDIR, 'thesis_draft_v15_clean.docx')
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
    (re.compile(r'<待补充[^\n]*?>', re.S), 'todo'),
    (re.compile(r'\*\*(.+?)\*\*', re.S), 'bold'),
]

TALLY_KEYS = ('para', 'h1', 'h2', 'h3', 'h4', 'table', 'eq', 'sym_ok',
              'sym_raw', 'fig', 'fig_embedded', 'fig_placeholder',
              'fig_missing_file', 'ref_marker', 'todo', 'ref_entry')


class Counter(dict):
    def __init__(self):
        dict.__init__(self)
        for key in TALLY_KEYS:
            self[key] = 0


def strip_marks(text):
    return re.sub(r'\[\[([^\]:]+):([^\]]*)\]\]',
                  lambda m: m.group(2), text).strip()


def _flag(p, text, colour):
    run = p.add_run(text)
    run.font.highlight_color = colour
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
        elif kind == 'todo':
            c['todo'] += 1
            if p is not None:
                _flag(p, m.group(0), WD_COLOR_INDEX.YELLOW)
        elif kind == 'bold':
            if p is not None:
                run = p.add_run(inner)
                run.bold = True
        text = text[end:]


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

    def caption(self, text):
        p = self.para(align=WD_ALIGN_PARAGRAPH.CENTER, tight=True)
        if p is not None:
            run = p.add_run(strip_marks(text))
            run.font.size = Pt(9)

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
    """Heading tree for the dead-text table of contents."""
    tree = []
    for name in SOURCES:
        for kind, a, b in [(x[0], x[1], x[2] if len(x) > 2 else '')
                           for x in parse_blocks(read_source(name))]:
            if kind == 'h' and a <= 3:
                tree.append((a, strip_marks(b)))
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
def repoint_running_header(doc, tag, needle):
    """把正文那一节的 default 页眉/页脚改指向模板里"跑动标题"那一份部件。

    为什么需要：产物沿用的是校模板**最后一节**的页面设置，而模板最后一节是"作者简介"
    ——它的 default 页眉里写死了"作者简介"四个字和"博/硕士"那个待选文本，真正的正文
    页眉（左"中国农业大学硕士学位论文"、右 STYLEREF 标题 1）挂在 **even** 上。
    本包没开奇偶页（settings.xml 里没有 evenAndOddHeaders），所以 Word 永远只用
    default，每一页就打上了"作者简介"。这里按部件内容找，不按 rId 找——rId 每次生成都会变。

    返回 1 表示改向成功，0 表示没找到可改向的部件（保持原样，不静默假装修好）。
    """
    sectPr = doc.sections[-1]._sectPr
    parts = doc.part.related_parts
    default = donor = None
    for ref in sectPr.findall(qn(tag)):
        rid = ref.get(qn('r:id'))
        blob = getattr(parts.get(rid), 'blob', b'') or b''
        if (ref.get(qn('w:type')) or 'default') == 'default':
            default = ref
        elif needle.search(blob):
            donor = ref
    if donor is None:
        return 0
    if default is None:
        # 本节根本没有 default 引用（页脚就是这种）：补一个，指向 donor。
        # headerReference/footerReference 在 sectPr 里排在最前，所以插到 0 位。
        default = OxmlElement(tag)
        default.set(qn('w:type'), 'default')
        sectPr.insert(0, default)
    default.set(qn('r:id'), donor.get(qn('r:id')))
    sectPr.remove(donor)                    # 同一份部件挂两次没有意义
    return 1


def build(check_only=False, cover='academic'):
    doc = docx.Document(TEMPLATE)
    if not check_only:
        body = doc.element.body
        sect = body.find(qn('w:sectPr'))     # keep page setup and the section
        for child in list(body):
            if child is not sect:
                body.remove(child)
        doc.styles['Normal'].font.size = Pt(10.5)
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
        for kind, a, b in [(x[0], x[1], x[2] if len(x) > 2 else '')
                           for x in parse_blocks(read_source(name))]:
            if kind == 'h':
                r.heading(a, b)
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

    for name in SOURCES[1:]:
        render_source(name)

    refs = extract_references(PREV_DOCX)
    r.heading(1, '参考文献')
    for entry in refs:
        c['ref_entry'] += 1
        p = r.para(tight=True)
        if p is not None:
            run = p.add_run(entry)
            run.font.size = Pt(9)

    if not check_only:
        # 页眉改向：不修的话每一页右上角都是"作者简介"（理由见函数 docstring）。
        # 页脚不一起改：正文与前置部分现在同属一节，直接挂 PAGE 会让摘要页从
        # 模板继承的 upperRoman 继续排，页码格式反而更错；等分节定稿一并处理。
        n = repoint_running_header(doc, 'w:headerReference', re.compile(rb'STYLEREF'))
        c['hdr_repointed'] = n
        if not os.path.isdir(OUTDIR):
            os.makedirs(OUTDIR)
        doc.save(OUT_DOCX)
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
    print('references  : %d entries carried over' % nrefs)
    # 页眉改向是"写了才算做了"的那类事，所以把当场结果打出来，不让人靠读代码推断。
    # check 模式不写文件也不改页眉，这里如实报 0。
    print('running hdr : %d body-section header reference(s) repointed'
          ' (0 in --check: nothing is written)'
          % c.get('hdr_repointed', 0))


if __name__ == '__main__':
    main()
