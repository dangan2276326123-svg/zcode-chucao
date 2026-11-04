# -*- coding: utf-8 -*-
"""把 docs/ 下的 markdown 执行表渲染成可打印、可手填的 A4 Word。

为什么要有这个生成器而不是手写一份 docx：**权威只有一份**。表里的内容以 md 为准，
docx 每次由本脚本重出，改了 md 就重跑一次——两份各写一遍迟早漂成两个数
（AGENTS 审查清单第 6 条"单一事实源"，同 thesis_latest.docx 那条规矩：产物不进仓，
只放最新，见 .gitignore）。

渲染范围（故意小）：一级/二级标题、引用块 `>`、表格、`---` 分隔线跳过、
行内 `**粗体**` / `` `代码` `` / `~~删除线~~`。够执行表用，不做通用 markdown 引擎。

打印取向的三个决定：A4 竖版、页边距 15/12 mm（表格宽 = 186 mm，六列各 31 mm 起，
长文字自动换行，不缩字号到看不清）；正文与表格中文用**宋体**、数字与英文用
Times New Roman（Word 的 eastAsia 字体要单独设，只设 font.name 中文不落）；
表头行加底纹并**跨页重复**（量表那张要写在第二页，表头没了就没法对着填）。

emoji 一律换成 ASCII 标记：🔴→[!] 🟢→[OK] ⚠️→[!] 📋→去掉，`☐`(U+2610)→`□`(U+25A1)。
理由是这台机器的中文字体集里 U+2610 没有字形，Word 会回退成豆腐块——一张满是方框的
打印表正好是这张表最需要勾选的地方。
"""
import argparse
import os
import re
import sys

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor

CJK_FONT = u'宋体'
LATIN_FONT = 'Times New Roman'
MONO_FONT = 'Consolas'

_SUBS = [(u'🔴', u'[!]'), (u'🟢', u'[OK]'), (u'⚠️', u'[!]'), (u'⚠', u'[!]'),
         (u'📋', u''), (u'☐', u'□'), (u'—', u'-'), (u'​', u'')]

_INLINE = re.compile(r'(\*\*.+?\*\*|`[^`]+`|~~.+?~~)')


def scrub(text):
    out = text
    for a, b in _SUBS:
        out = out.replace(a, b)
    return out.strip()


def set_fonts(run, cjk=CJK_FONT, latin=LATIN_FONT, size=None):
    run.font.name = latin
    rpr = run._element.get_or_add_rPr()
    fonts = rpr.find(qn('w:rFonts'))
    if fonts is None:
        fonts = rpr.makeelement(qn('w:rFonts'), {})
        rpr.append(fonts)
    fonts.set(qn('w:eastAsia'), cjk)
    fonts.set(qn('w:ascii'), latin)
    fonts.set(qn('w:hAnsi'), latin)
    if size is not None:
        run.font.size = Pt(size)


def add_inline(par, text, size, bold_all=False):
    """一行文本 -> 若干 run，认 `**粗**`、`` `代码` ``、`~~删除~~`，**并且认嵌套**。

    嵌套不是装饰性问题：表里"按两次 `v` 落两个 .avi"这种写法很常见，早先的实现把
    `**…**` 整段当一个 run、不再看里面的反引号，结果打印出来的纸上真带着两个反引号
    （11-03 第一次 QA 就是这么抓出来的——生成的文件不读回来验就看不见这种事）。
    """
    for piece in _INLINE.split(text):
        if not piece:
            continue
        body, bold, strike, mono = piece, bold_all, False, False
        nested = False
        if piece.startswith('**') and piece.endswith('**') and len(piece) > 4:
            body, bold, nested = piece[2:-2], True, True
        elif piece.startswith('~~') and piece.endswith('~~') and len(piece) > 4:
            body, strike, nested = piece[2:-2], True, True
        elif piece.startswith('`') and piece.endswith('`') and len(piece) > 2:
            body, mono = piece[1:-1], True
        if nested and _INLINE.search(body):
            add_inline(par, body, size, bold_all=bold)
            continue
        run = par.add_run(body)
        run.bold = bold
        run.font.strike = strike
        if mono:
            set_fonts(run, cjk=CJK_FONT, latin=MONO_FONT, size=size)
            run.font.color.rgb = RGBColor(0x1F, 0x3B, 0x73)
        else:
            set_fonts(run, size=size)
    return par


def split_row(line):
    return [scrub(c) for c in line.strip().strip('|').split('|')]


def add_table(doc, rows, size=9.0):
    ncol = max(len(r) for r in rows)
    table = doc.add_table(rows=0, cols=ncol)
    table.style = 'Table Grid'
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    for i, cells in enumerate(rows):
        row = table.add_row()
        trpr = row._tr.get_or_add_trPr()
        # 一行不许被分页切成两半：填空表被切开时，写在纸上的人会对着半截格子猜
        # "这一栏到底是 M14 还是 M15"。表头那一行另外设 tblHeader，跨页重复。
        trpr.append(trpr.makeelement(qn('w:cantSplit'), {}))
        if i == 0:
            trpr.append(trpr.makeelement(qn('w:tblHeader'), {}))
        for j in range(ncol):
            cell = row.cells[j]
            text = cells[j] if j < len(cells) else ''
            par = cell.paragraphs[0]
            if text == '' and i > 0:
                # 空栏就是给人手写的位置：上下各留 4 pt，比塞空格稳（塞的空格会被
                # 自动换行吃掉，不同字号一调就塌成一行）
                par.paragraph_format.space_before = Pt(4)
                par.paragraph_format.space_after = Pt(4)
                set_fonts(par.add_run(''), size=size)
            else:
                par.paragraph_format.space_before = Pt(1)
                par.paragraph_format.space_after = Pt(1)
                add_inline(par, text, size, bold_all=(i == 0))
            if i == 0:
                shd = cell._element.get_or_add_tcPr().makeelement(qn('w:shd'), {
                    qn('w:val'): 'clear', qn('w:fill'): 'E8E8E8'})
                cell._element.get_or_add_tcPr().append(shd)
    return table


def render(md_text, out_path, title_size=15.0):
    doc = Document()
    sec = doc.sections[0]
    sec.orientation = WD_ORIENT.PORTRAIT
    sec.page_width, sec.page_height = Mm(210), Mm(297)
    sec.top_margin = sec.bottom_margin = Mm(15)
    sec.left_margin = sec.right_margin = Mm(12)
    normal = doc.styles['Normal']
    normal.font.size = Pt(10.5)
    normal.font.name = LATIN_FONT          # 先设 latin 才会生成 rPr/rFonts 节点
    normal.element.rPr.rFonts.set(qn('w:eastAsia'), CJK_FONT)

    lines = md_text.replace('\r\n', '\n').split('\n')
    i, first_heading_done = 0, False
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if not s or set(s) <= set('- '):
            i += 1
            continue
        if s.startswith('# '):
            par = doc.add_paragraph()
            par.alignment = WD_ALIGN_PARAGRAPH.CENTER
            add_inline(par, scrub(s[2:]), title_size, bold_all=True)
            i += 1
            continue
        if s.startswith('## '):
            par = doc.add_paragraph()
            par.paragraph_format.space_before = Pt(0 if not first_heading_done else 10)
            par.paragraph_format.space_after = Pt(3)
            add_inline(par, scrub(s[3:]), 11.5, bold_all=True)
            first_heading_done = True
            i += 1
            continue
        if s.startswith('> '):
            body = scrub(s[2:])
            par = doc.add_paragraph()
            par.paragraph_format.left_indent = Mm(4)
            par.paragraph_format.space_after = Pt(3)
            add_inline(par, body, 9.0)
            i += 1
            continue
        if s.startswith('|'):
            rows = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                cells = split_row(lines[i])
                if all(set(c) <= set('-: ') and c for c in cells):
                    i += 1                       # 分隔行不渲染
                    continue
                rows.append(cells)
                i += 1
            add_table(doc, rows)
            doc.add_paragraph()
            continue
        if re.match(r'^\d+\.\s', s) or s.startswith('- '):
            par = doc.add_paragraph()
            par.paragraph_format.left_indent = Mm(5)
            par.paragraph_format.space_after = Pt(2)
            add_inline(par, scrub(s), 9.5)
            i += 1
            continue
        par = doc.add_paragraph()
        add_inline(par, scrub(s), 10.0)
        i += 1
    doc.save(out_path)
    return out_path


def main(argv=None):
    ap = argparse.ArgumentParser(description='docs/ 下的 md 执行表 -> A4 Word')
    ap.add_argument('md', help='源 markdown（权威只有这一份）')
    ap.add_argument('-o', '--out', default=None, help='输出的 .docx')
    a = ap.parse_args(argv)
    with open(a.md, encoding='utf-8') as f:
        text = f.read()
    out = a.out or os.path.splitext(a.md)[0] + '.docx'
    render(text, out)
    print('wrote %s (%d bytes) from %s' % (out, os.path.getsize(out), a.md))
    return 0


if __name__ == '__main__':
    sys.exit(main())
