# -*- coding: utf-8 -*-
"""Mutation check for the new format tests: does each one actually bite?

For every mutation we rewrite tools/make_thesis_docx.py in memory, run just the
test that should catch it, and restore the file byte-for-byte afterwards. A test
that stays green under its own mutation is decoration.
"""
import io
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, 'tools', 'make_thesis_docx.py')
BAK = TOOL + '.mutbak'
PY = sys.executable

MUTATIONS = [
    ('numbering never reaches the heading',
     "r.heading(a, num.prefix(a) + b)", "r.heading(a, b)",
     'tests/test_make_thesis_docx.py::test_printed_numbers_equal_the_section_checker'),
    ('numbering never reaches the outline',
     "tree.append((level, prefix + title))", "tree.append((level, title))",
     'tests/test_make_thesis_docx.py::test_front_matter_headings_stay_unnumbered_in_the_outline'),
    ('chapter uses arabic instead of chinese numeral',
     "return u'第%s章 ' % cn_num(self.chapter)", "return u'第%d章 ' % self.chapter",
     'tests/test_make_thesis_docx.py::test_heading_numbers_follow_the_positional_rule'),
    ('h3 does not reset h4',
     "for i in range(level - 1, 3):   # deeper levels restart, as in build_numbers",
     "for i in range(0, 0):   # deliberately broken",
     'tests/test_make_thesis_docx.py::test_heading_numbers_follow_the_positional_rule'),
    ('abstract treated as chapter 0 and numbered',
     "return int(m.group(1)) if m else None", "return int(m.group(1)) if m else 0",
     'tests/test_make_thesis_docx.py::test_chapter_number_comes_from_the_file_name'),
    ('caption loses the heiti pin',
     "set_cjk(run, u'黑体')", "pass",
     'tests/test_make_thesis_docx.py::test_caption_is_xiaowu_heiti'),
    ('sub-heading flush-left fix removed',
     "                p.paragraph_format.first_line_indent = 0\n"
     "                p._p.get_or_add_pPr().get_or_add_ind().set(\n"
     "                    qn('w:firstLineChars'), '0')",
     "                pass",
     'tests/test_make_thesis_docx.py::test_sub_headings_are_flush_left'),
    ('body size override comes back',
     "global FIGURE_MAP", "doc.styles['Normal'].font.size = Pt(10.5)\n    global FIGURE_MAP",
     'tests/test_make_thesis_docx.py::test_body_text_keeps_the_templates_own_size'),
    ('double period no longer collapsed',
     "s = re.sub(r'\\.{2,}', '.', s)", "pass",
     'tests/test_make_thesis_docx.py::test_normalize_reference_fixes_the_known_shapes'),
    ('author truncation disabled',
     "    span = _author_span(s)\n    if span:",
     "    span = None\n    if span:",
     'tests/test_make_thesis_docx.py::test_normalize_reference_fixes_the_known_shapes'),
    ('type-mark rule also touches [C]// (the bug that ate it)',
     "r'\\[(J|D|C|M|R|S|EB/OL|DB/OL|CP/OL|A|Z)\\](?=[^\\s./])'",
     "r'\\[(J|D|C|M|R|S|EB/OL|DB/OL|CP/OL|A|Z)\\](?=[^\\s.])'",
     'tests/test_make_thesis_docx.py::test_normalize_reference_fixes_the_known_shapes'),
    ('stray leading digit kept',
     "s = re.sub(r'^(\\[\\d+\\])\\s+\\d+\\s+', r'\\1 ', s)", "pass",
     'tests/test_make_thesis_docx.py::test_normalize_reference_fixes_the_known_shapes'),
    ('completions never applied',
     "refs.append(normalize_reference(REFERENCE_COMPLETIONS.get(i, entry)))",
     "refs.append(normalize_reference(entry))",
     'tests/test_make_thesis_docx.py::test_completed_references_carry_their_pages'),
    ('hanging indent not applied to the list',
     "            hanging_indent(p)", "            pass",
     'tests/test_make_thesis_docx.py::test_built_reference_entries_are_hanging'),
    ('split-word table disabled',
     "for bad, good in REF_SPLIT_WORDS:\n        s = s.replace(bad, good)",
     "pass",
     'tests/test_make_thesis_docx.py::test_reference_list_prints_clean'),
]

orig = io.open(TOOL, encoding='utf-8').read()
shutil.copyfile(TOOL, BAK)
rows = []
try:
    for label, needle, repl, testid in MUTATIONS:
        assert needle in orig, 'anchor gone, mutation not applicable: %s' % label
        io.open(TOOL, 'w', encoding='utf-8', newline='').write(
            orig.replace(needle, repl, 1))
        p = subprocess.Popen([PY, '-B', '-m', 'pytest', testid, '-q',
                              '-p', 'no:cacheprovider'], cwd=ROOT,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out = p.stdout.read().decode('utf-8', 'replace')
        p.wait()
        bit = p.returncode != 0
        rows.append((label, bit, out.strip().split('\n')[-1]))
finally:
    shutil.copyfile(BAK, TOOL)
    os.remove(BAK)
    assert io.open(TOOL, encoding='utf-8').read() == orig, 'RESTORE FAILED'

io.open(os.path.join(ROOT, '_mut_report.txt'), 'w', encoding='utf-8').write(
    u'\n'.join(u'%-46s bites=%-5s %s' % r for r in rows) + u'\n')
for label, bit, tail in rows:
    print('%-46s bites=%s  %s' % (label, bit, tail[:70]))
print('restored ok')
