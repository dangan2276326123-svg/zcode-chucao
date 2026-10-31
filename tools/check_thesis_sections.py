#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Check that every "X.Y[.Z] 节" reference in the thesis chapters points at a section
that exists, and that the heading tree matches the author's 目录.

Why this exists
---------------
The chapter sources carry no numbers: numbering comes from the Word outline, so a
heading rename or a block move silently re-points every "见 3.5.1 节" in the prose.
That is exactly the failure AGENTS 审查清单第 2 条 describes for 编号类改动, except
here the numbers are *derived*, so a grep for the old number finds nothing.

2026-10-27: restructuring to the author's 目录 moved four blocks and renamed nine
headings; this checker found one reference that no longer resolved (4.1.4) after the
first pass had already "looked fine".

Numbering rule (positional, since the sources have none):
  3     = the 3rd chapter file
  3.4   = the 4th h2 of that chapter
  3.4.1 = the 1st h3 under that h2
  3.4.1.2 = the 2nd h4 under that h3

Usage:  python -B tools/check_thesis_sections.py [--expect FILE]
Exit 0 = every reference resolves (and, with --expect, the tree matches the outline).
"""
import argparse
import io
import os
import re
import sys

THESIS = os.environ.get('THESIS_DIR') or r'D:\JetBrains\chucao_prj\thesis_cau'
CH = os.path.join(THESIS, '03_chapters')
FILES = ['ch%02d_draft.md' % i for i in range(1, 7)]

REF_RE = re.compile(u'([1-6](?:\\.[0-9]+){1,3})\\s*节')


def build_numbers():
    """-> {number: title}, in document order."""
    valid = {}
    for ci, name in enumerate(FILES, start=1):
        path = os.path.join(CH, name)
        if not os.path.exists(path):
            continue
        h2 = h3 = h4 = 0
        for line in io.open(path, encoding='utf-8').read().split('\n'):
            m = re.match(r'^## (.+)$', line)
            if m:
                h2, h3, h4 = h2 + 1, 0, 0
                valid['%d.%d' % (ci, h2)] = m.group(1).strip()
                continue
            m = re.match(r'^### (.+)$', line)
            if m:
                h3, h4 = h3 + 1, 0
                valid['%d.%d.%d' % (ci, h2, h3)] = m.group(1).strip()
                continue
            m = re.match(r'^#### (.+)$', line)
            if m:
                h4 += 1
                valid['%d.%d.%d.%d' % (ci, h2, h3, h4)] = m.group(1).strip()
    return valid


def find_dangling(valid):
    bad = []
    for ci, name in enumerate(FILES, start=1):
        path = os.path.join(CH, name)
        if not os.path.exists(path):
            continue
        for lineno, line in enumerate(io.open(path, encoding='utf-8').read().split('\n'), 1):
            for m in REF_RE.finditer(line):
                if m.group(1) not in valid:
                    # ignore "3.2.1" produced by "3.3.2.1"
                    bad.append((name, lineno, m.group(1), line.strip()[:90]))
    return bad


def load_expected(path=None):
    """The outline as (level, title) pairs; default = the author's 目录.docx headings."""
    if not path:
        return None
    rows = []
    for line in io.open(path, encoding='utf-8').read().split('\n'):
        m = re.match(r'^(\t*)(\S.*)$', line)
        if m:
            rows.append((len(m.group(1)), m.group(2).strip()))
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--expect', help='outline file: tab-indented "level<TAB>title" per line')
    args = ap.parse_args(argv)

    valid = build_numbers()
    print('sections declared: %d' % len(valid))
    bad = find_dangling(valid)
    print('references pointing at a missing section: %d' % len(bad))
    for name, lineno, num, ctx in bad:
        print('  %s L%d -> %s | %s' % (name, lineno, num, ctx))

    rc = 1 if bad else 0
    if args.expect:
        exp = load_expected(args.expect)
        # rebuild the tree as (level, title) for comparison
        tree = []
        for ci, name in enumerate(FILES, start=1):
            path = os.path.join(CH, name)
            if not os.path.exists(path):
                continue
            for line in io.open(path, encoding='utf-8').read().split('\n'):
                m = re.match(r'^(#{1,4}) (.+)$', line)
                if m:
                    tree.append((len(m.group(1)) - 1, m.group(2).strip()))
        if tree != exp:
            print('outline mismatch:')
            for i, (a, b) in enumerate(zip(tree, exp)):
                if a != b:
                    print('  first difference at #%d: source=%r outline=%r' % (i, a, b))
                    break
            if len(tree) != len(exp):
                print('  source has %d headings, outline %d' % (len(tree), len(exp)))
            rc = 1
        else:
            print('outline matches: %d headings' % len(tree))
    return rc


if __name__ == '__main__':
    sys.exit(main())
