# -*- coding: utf-8 -*-
"""`tools/md_to_docx_sheet.py` —— 打印件的钉。

这里钉的全是**计数器看不见的东西**：纸上的方框是不是豆腐块、表头会不会掉在上一页、
一行会不会被分页切成半截让人对着空格猜是哪一项、粗体里套的代码会不会把反引号印出来。
11-03 第一次生成时，反引号泄漏就是靠"把生成的文件读回来验"才发现的（本仓的老规矩）。
"""
import os
import sys

from docx import Document

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import md_to_docx_sheet as m        # noqa: E402


def _all_text(doc):
    parts = [p.text for p in doc.paragraphs]
    for t in doc.tables:
        for r in t.rows:
            for c in r.cells:
                parts.append(c.text)
    return '\n'.join(parts)


def _render(tmp_path, md, name='s.docx'):
    src = os.path.join(str(tmp_path), 'in.md')
    with open(src, 'w', encoding='utf-8') as f:
        f.write(md)
    out = os.path.join(str(tmp_path), name)
    m.render(open(src, encoding='utf-8').read(), out)
    return Document(out)


def test_bold_containing_code_does_not_leak_backticks(tmp_path):
    """粗体里套代码那种写法（星号包着反引号）印到纸上不许带着反引号。"""
    doc = _render(tmp_path, u'## 标题\n\n**按两次 `v` 落两个 .avi**，`saved=` 会加。\n')
    text = _all_text(doc)
    assert '`' not in text, repr(text)
    assert u'按两次 v 落两个 .avi' in text
    assert u'saved=' in text


def test_emoji_and_the_ballot_box_become_printable_marks(tmp_path):
    """U+2610(☐) 与 emoji 在中文字体集里没字形，Word 回退成豆腐块——
    而勾选栏正是这张表最需要看得清的地方。"""
    doc = _render(tmp_path, u'| 勾 | 事项 |\n|---|---|\n| ☐ | 🔴 停手 |\n'
                            u'| ☐ | 🟢 已答 |\n\n> ⚠️ 边界\n')
    text = _all_text(doc)
    for bad in (u'☐', u'🔴', u'🟢', u'⚠'):
        assert bad not in text, bad
    assert u'□' in text and u'[!]' in text and u'[OK]' in text


def test_rows_cannot_split_and_the_header_row_repeats(tmp_path):
    """填空表跨页时：表头必须再来一次，且一行不许被切成两半。"""
    rows = u'\n'.join(u'| M%d | 要什么 |  |  |' % i for i in range(1, 30))
    doc = _render(tmp_path, u'## 量表\n\n| 项 | 一句话 | 第1次 | 第2次 |\n'
                            u'|---|---|---|---|\n%s\n' % rows)
    table = doc.tables[0]
    xml0 = table.rows[0]._tr.xml
    assert 'cantSplit' in xml0
    assert 'tblHeader' in xml0
    assert 'cantSplit' in table.rows[5]._tr.xml
    assert 'tblHeader' not in table.rows[5]._tr.xml      # 只有表头那一行带重复标记


def test_page_geometry_is_a4_portrait_with_print_margins(tmp_path):
    doc = _render(tmp_path, u'# 表\n\n正文\n')
    sec = doc.sections[0]
    assert round(sec.page_width.mm) == 210 and round(sec.page_height.mm) == 297
    assert round(sec.left_margin.mm) == 12 and round(sec.top_margin.mm) == 15


def test_fill_in_cells_stay_empty(tmp_path):
    """空栏就是给人写的：渲染不许往里塞占位符（塞了字就没法填，也过不了"不预填读数"那条）。"""
    doc = _render(tmp_path, u'| 项 | 数 |\n|---|---|\n| M3 |  |\n| M14 |  |\n')
    table = doc.tables[0]
    assert [c.text for c in (table.rows[1].cells[1], table.rows[2].cells[1])] == ['', '']
def test_fenced_commands_keep_indent_and_are_not_parsed(tmp_path):

    """田里要照抄的那几行是命令：缩进、`~`、`--width` 一个都不许被"聪明地"处理掉。



    这里全用 chr(10)/chr(96) 拼，不写反斜杠转义——本仓已经被 shell 吃掉转义咬过两次。

    """

    NL = chr(10)

    FENCE = chr(96) * 3

    cmd = u'    python3 ~/qoder/vehicle/stream_pi.py --width 1920 --height 1080'

    md = (u'## 命令' + NL + NL + FENCE + NL

          + u'【X5】ssh sunrise@192.168.127.10' + NL + cmd + NL + FENCE + NL)

    doc = _render(tmp_path, md)

    joined = NL.join(p.text for p in doc.paragraphs)

    assert FENCE not in joined, repr(joined)

    assert cmd in joined, repr(joined)      # 四个空格的缩进原样留着

    assert u'--width' in joined and u'~' in joined


def test_third_level_heading_does_not_print_hash_marks(tmp_path):
    """`### ` 早先不认，会掉到兜底分支，纸上真印出三个井号。"""
    doc = _render(tmp_path, u'### 命令一览\n\n正文\n')
    joined = chr(10).join(p.text for p in doc.paragraphs)
    assert u'###' not in joined, repr(joined)
    assert u'命令一览' in joined
