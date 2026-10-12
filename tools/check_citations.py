# -*- coding: utf-8 -*-
"""坐标式引用审计（2026-10-12 立，起因是接线图那批"出处指到空处"）。

要抓的错只有一个形状：**文档写的是坐标（行号／节号／路径），而坐标会随文件移动**——
移了之后没有任何一条单元测试会红，只有人翻到那一行才发现读到的是另一件事。
本仓已经为此付过学费：`以后指格子不指行号`（§4B 的规矩）、Fw-13 的行号被我自己这次
加说明推歪一行、台账 Hw-17 把 `telecontrol.c` 写成 `uart4/telecontrol.c`。

三档结论：
  HARD   —— 路径不存在，或行号越界（一定读不到东西）
  CHECK  —— 能读到那一行，但引用点旁边被引号包住的那段"被引内容"不在里面（人工看）
  SOFT   —— 大小写与真实目录不符：Windows 看不出来，Linux 克隆下来就断（已实测一例）

**退出码恒为 0**：这是一份报告，不是一道闸。写成硬失败会诱导人为了变绿去改坐标数字，
而那正是本工具要防的行为（AGENTS 审查清单第 2 条对基线数字是同一条理由）。
要拦回归，用 `--fail-on-hard`——只在你想让 CI 红的时候显式加。

跑法：
    python -B tools/check_citations.py
    python -B tools/check_citations.py --strict   # 连 CHECK 档一起打全量明细
"""
import argparse
import io
import os
import re
import subprocess
import sys
from collections import defaultdict

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 只读镜像与派生目录：不参与"文件名→路径"解析，否则裸名会撞出假歧义
SKIP_DIR = {'.git', '__pycache__', 'node_modules', '.superpowers', 'avi_frames',
            'calib_imgs', 'OBJ', 'Listings', 'Objects', 'hardware_ref', 'videos'}
# 仓内引用常用"相对 firmware/大车proj/大车 的写法"（如 `USER/main.c:553`），补全它
FIRMWARE_ROOT = 'firmware/大车proj/大车/'
EXT = r'(?:c|h|py|md|mdx|sh|bat|yaml|yml|json|npz|txt)'
LINE_RE = re.compile(
    r'(?P<path>(?:[A-Za-z0-9._\-]+/)*[A-Za-z0-9._\-]+\.' + EXT + r')'
    r'[:：](?P<lo>\d{1,4})(?:[-–~](?P<hi>\d{1,4}))?')
# 引用点紧邻的"被引内容"：中文书名号／反引号／直角引号里的片段
QUOTED = (re.compile(u'「([^」]{4,60)}」'),
          re.compile(r'`([^`]{4,60})`'))
IDENT = re.compile(r'[A-Za-z_][A-Za-z_0-9]{3,}')


def tracked_md():
    out = subprocess.check_output(['git', '-C', ROOT, 'ls-files', '-z', '*.md']).decode('utf-8')
    return [p for p in out.split('\0') if p and not p.startswith('.superpowers/')]


def build_name_index():
    idx = defaultdict(list)
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIR]
        for fn in filenames:
            rel = os.path.relpath(os.path.join(dirpath, fn), ROOT).replace('\\', '/')
            idx[fn.lower()].append(rel)
    return idx


def read(path):
    for enc in ('utf-8', 'gbk'):
        try:
            return io.open(os.path.join(ROOT, path), encoding=enc).read().split('\n')
        except UnicodeDecodeError:
            continue
        except (IOError, OSError):
            return None
    return None


def resolve(raw, idx, cache):
    """把一个引用里的路径解析成仓内相对路径；解析不到返回 (None, 原因)。

    返回前一定先把 cache[结果] 填好——调用方直接 `cache[rel]` 取行，
    漏填就 KeyError（第一版就是这么炸的）。
    """
    raw = raw.replace('\\', '/').lstrip('./')
    tries = [raw]
    if '/' not in raw:
        cands = idx.get(raw.lower(), [])
        if len(cands) == 1:
            tries = [cands[0]]
        elif len(cands) > 1:
            return None, None, '裸名多份: ' + ' | '.join(cands[:3])
        else:
            tries = []
    else:
        tries.append(FIRMWARE_ROOT + raw)          # `USER/main.c` 这类固件内相对写法
        tries.append('firmware/' + raw)
        tail = raw.split('/')[-1].lower()
        if tail in idx:
            tries.extend([p for p in idx[tail] if p.endswith('/' + raw)])
    for t in tries:
        if t not in cache:
            cache[t] = read(t)
        if cache[t] is not None:
            return t, cache[t], None
    return None, None, None


def parent_case_ok(rel):
    """目录大小写是否与磁盘一致（Windows 看不出来的那类）。"""
    d = os.path.dirname(rel)
    if not d:
        return True
    real = os.path.normpath(os.path.join(ROOT, d))
    try:
        listed = os.listdir(os.path.dirname(real))
    except OSError:
        return True
    return os.path.basename(real) in listed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--strict', action='store_true', help='CHECK 档打全量明细')
    ap.add_argument('--fail-on-hard', action='store_true',
                    help='有 HARD 就退出码 1（默认不退：这是报告不是闸）')
    a = ap.parse_args()

    idx = build_name_index()
    cache = {}
    hard, check, soft, ok, skipped = [], [], [], 0, 0
    for md in tracked_md():
        lines = read(md) or []
        for i, ln in enumerate(lines):
            for m in LINE_RE.finditer(ln):
                raw, lo = m.group('path'), int(m.group('lo'))
                hi = int(m.group('hi') or lo)
                if raw.startswith('ch0') or 'thesis' in raw:
                    skipped += 1                       # 论文正文在只读仓，本工具不判
                    continue
                # 两种"这条已经处理过"的样子都不再算待办：
                #  a) 带历史限定（`<sha>:` 前缀，或明说"板上那一版／已删／旧版"）；
                #  b) 同一行已有就地订正句——本仓的规矩是原文不删，坏引用留在句子里、
                #     后面跟一段订正。工具若对这种情况一直报警，人就会开始忽略它，那比不查更糟。
                hist = bool(re.search(r'[0-9a-f]{7}:', ln[max(0, m.start() - 12):m.start()])) or \
                    any(k in ln for k in (u'板上', u'现烧', u'旧版', u'已删', u'那一版', u'历史',
                                          u'订正', u'作废', u'已改指'))
                rel, L, why = resolve(raw, idx, cache)
                if why:
                    check.append((md, i + 1, raw, lo, why))
                    continue
                if rel is None:
                    if not hist:
                        hard.append((md, i + 1, raw, lo, '路径不存在'))
                    continue
                if lo > len(L):
                    hard.append((md, i + 1, raw, lo, '%s 只有 %d 行' % (rel, len(L))))
                    continue
                ok += 1
                if not hist and not parent_case_ok(rel):
                    soft.append((md, i + 1, raw, lo, '目录大小写与磁盘不符: ' + rel))
                after = ln[m.end():m.end() + 60]
                toks = []
                for pat in QUOTED:
                    g = pat.search(after)
                    if g:
                        toks.extend(IDENT.findall(g.group(1)))
                blob = u'\n'.join(L[lo - 1:min(len(L), hi)])
                miss = [t for t in toks if t not in blob]
                if miss and not hist and rel.endswith(('.c', '.h', '.py')):
                    check.append((md, i + 1, raw, lo,
                                  u'被引片段不在那几行: %s（解析为 %s）' % ('、'.join(miss[:3]), rel)))

    out = sys.stdout
    out.write(u'坐标式引用审计：可解析 %d 处｜HARD %d｜CHECK %d｜SOFT(大小写) %d｜跳过(论文等) %d\n'
              % (ok, len(hard), len(check), len(soft), skipped))
    out.write(u'  判据：HARD=读不到东西；CHECK=能读到但对不上被引内容；SOFT=Linux 上会断\n\n')
    for tag, rows in ((u'HARD', hard), (u'SOFT', soft), (u'CHECK', check)):
        if not rows:
            continue
        out.write(u'== %s ==\n' % tag)
        show = rows if (tag != u'CHECK' or a.strict) else rows[:15]
        for md, ln, raw, n, note in show:
            out.write(u'  %-52s 行%-6d %-30s %s\n' % (md[:52], ln, (raw + ':' + str(n))[:30], note[:96]))
        if tag == u'CHECK' and not a.strict and len(rows) > len(show):
            out.write(u'  …另 %d 条同类，用 --strict 看全量\n' % (len(rows) - len(show)))
        out.write(u'\n')
    out.write(u'注：本工具退出码恒 0（除非 --fail-on-hard）。报告不是闸——把坐标数字写成硬判据，'
              u'下一批就会有为了变绿去改数字的人，那比引用失效更糟。\n')
    if a.fail_on_hard and hard:
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
