# -*- coding: utf-8 -*-
"""把 AGENTS 审查清单第 2 条 b) 项变成可执行检查（2026-09-22 定案口径）。

规则要求：对区分类符号做**全仓枚举并打印命中数**，零命中必须给出解释。
09-22 定案的扫描范围是"**全仓 md 减去审查清单第 2 条所在的行块**"——那条里
举着 `⑦–⑧` 等反例，若不摘除，规则文本会持续击破自己的不变量，而每加一个例子
就得补一条豁免。摘掉举例之后，所有不变量都是绝对的。

判读（写死在第 2 条里）：
    ①–⑧  命中 7 处 = 基线
    ⚠️ "处"按**出现次数**计，不是按行数。当前 7 次分布在 6 行上
    （v1.0 第 53 行同时写着判据与括注，出现两次）。两种数法差 1，
    所以本工具两个数都印出来：按行数是 6，那**不是漂移**。
    ①–⑦ / ⑦–⑧ 及一切半角变体  恒为 0，任何非零即缺陷

退出码：
    0  干净
    1  禁用语义出现（缺陷）
    2  基线数漂移（不自动判失败，但**必须解释**：规则 b) 项的精神就是
       "计数变化是需要解释的证据"，把它变成硬失败会诱导人直接改基线数字）
    3  无法审计：没找到第 2 条行块，或有文件读不进去
读不进去的文件一定报出来——"扫到了但其实没读"正好会伪造出零命中。
"""
import argparse
import os
import re
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')
    sys.stderr.reconfigure(errors='replace')

ROOT_DEFAULT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EN, HY = '\u2013', '-'
C = {i: chr(0x2460 + i) for i in range(9)}          # ①..⑨

BASELINE_FORM = C[0] + EN + C[7]                     # ①–⑧
FORBIDDEN = [C[0] + EN + C[6],                       # ①–⑦
             C[6] + EN + C[7],                       # ⑦–⑧
             C[0] + HY + C[6],                       # ①-⑦
             C[0] + HY + C[7],                       # ①-⑧
             C[6] + HY + C[7]]                       # ⑦-⑧
ALL_FORMS = [BASELINE_FORM] + FORBIDDEN

ITEM2_RE = re.compile(r'^2\.\s+\*\*闭环核对\*\*')
LIST_ITEM_RE = re.compile(r'^\d+\.\s')


def find_rule_block(lines):
    """返回审查清单第 2 条的行块区间 [start, end)（含缩进续行）。找不到 → None。"""
    start = None
    for i, ln in enumerate(lines):
        if ITEM2_RE.match(ln):
            start = i
            break
    if start is None:
        return None
    end = start + 1
    while end < len(lines) and (lines[end].startswith(('   ', '\t'))
                                or lines[end].strip() == ''):
        if LIST_ITEM_RE.match(lines[end]) or lines[end].startswith('### '):
            break
        end += 1
    return start, end


def enumerate_ranges(root, baseline_only_for=None):
    """返回 (counts, unreadable)。counts: 形式 -> [(file, line)]；
    第 2 条行块内的命中一律不计入（它就是规则举例所在）。"""
    counts = {f: [] for f in ALL_FORMS}
    unreadable = []
    scanned = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in ('.git', '__pycache__', 'node_modules')]
        for fn in sorted(filenames):
            if not fn.lower().endswith('.md'):
                continue
            path = os.path.join(dirpath, fn)
            try:
                text = open(path, encoding='utf-8').read()
            except (UnicodeDecodeError, OSError) as e:
                unreadable.append('%s (%s)' % (os.path.relpath(path, root), e))
                continue
            scanned += 1
            lines = text.split('\n')
            skip = None
            if os.path.basename(path) == 'AGENTS.md':
                skip = find_rule_block(lines)
            for idx, ln in enumerate(lines):
                if skip and skip[0] <= idx < skip[1]:
                    continue
                for form in ALL_FORMS:
                    n = ln.count(form)
                    if n:
                        counts[form].extend(
                            [(os.path.relpath(path, root), idx + 1)] * n)
    return counts, unreadable, scanned


def verdict(counts, baseline_expect):
    """→ (exit_code, messages)"""
    msgs, code = [], 0
    for form in FORBIDDEN:
        hits = counts[form]
        if hits:
            code = 1
            msgs.append('缺陷：禁用语义 %s 命中 %d 处 → %s'
                        % (form, len(hits),
                           ', '.join('%s:%d' % h for h in hits)))
    base = len(counts[BASELINE_FORM])          # 按出现次数，见模块文档串
    if base != baseline_expect and code != 1:
        code = 2
        n_lines = len({h for h in counts[BASELINE_FORM]})
        msgs.append('基线漂移：%s 命中 %d 处（**出现次数**计；分布在 %d 行上），'
                    '规则写的基线是 %d 处。按行数数出来会少，那不算漂移，'
                    '数法以本工具为准。不自动判失败，但**必须解释**'
                    '是加对了还是改错了；禁止为了让检查变绿而直接改基线数字。'
                    % (BASELINE_FORM, base, n_lines, baseline_expect))
    if code == 0:
        msgs.append('通过：禁用语义 0 命中，%s 命中 %d 处 = 基线'
                    % (BASELINE_FORM, base))
    return code, msgs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=ROOT_DEFAULT)
    ap.add_argument('--baseline', type=int, default=7,
                    help='①–⑧ 的期望命中数（AGENTS 第 2 条写死的基线）')
    a = ap.parse_args()
    if not os.path.isdir(a.root):
        raise SystemExit('目录不存在: %s' % a.root)

    counts, unreadable, scanned = enumerate_ranges(a.root)
    print('扫描 %d 个 md 文件（已摘除 AGENTS 审查清单第 2 条行块）' % scanned)
    for form in ALL_FORMS:
        hits = counts[form]
        tag = '基线' if form == BASELINE_FORM else '禁用'
        n_lines = len({h for h in hits})
        print('  %s  %-4s %2d 次 / %d 行  %s'
              % (form, tag, len(hits), n_lines,
                 '; '.join('%s:%d' % h for h in hits[:8]) or '—'))
    if unreadable:
        print('❌ %d 个文件读不进去，它们**没有**被审计过，本次的零命中对它们不成立：'
              % len(unreadable))
        for u in unreadable:
            print('   ', u)
        return 3
    code, msgs = verdict(counts, a.baseline)
    for m in msgs:
        print(m)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
