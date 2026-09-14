# -*- coding: utf-8 -*-
"""Peony dataset 6:2:2 splitter (asset-safe rewrite, 2026-09-11).

Fixes from the 2026-09-09 external review (docs/reviews):
  * paths no longer point at the read-only JetBrains repos;
  * the source directory is validated BEFORE anything is cleared, so a
    typo'd/empty source can no longer wipe an existing split;
  * clearing the target dirs now requires an explicit --force, and any
    path outside the workspace is refused outright.

Usage:
  python tools/split_dataset.py --source data/autumn_data/raw --dry-run
  python tools/split_dataset.py --source data/autumn_data/raw --force
"""
import argparse
import json
import os
import random
import shutil
import sys

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORBIDDEN_MARKERS = ('JetBrains', 'chucao_prj', 'avi_project')


def _guard(path):
    """Refuse to touch anything outside the workspace or in a read-only repo."""
    ap = os.path.abspath(path)
    if not ap.startswith(os.path.abspath(WORKSPACE) + os.sep):
        raise SystemExit('拒绝操作工作区之外的路径: %s' % path)
    if any(m in ap for m in FORBIDDEN_MARKERS):
        raise SystemExit('拒绝操作只读研究仓路径: %s' % path)


def scan_pairs(source_dir):
    """Return sorted base names that have BOTH a .jpg and a same-name .json."""
    if not os.path.isdir(source_dir):
        raise SystemExit('源目录不存在: %s' % source_dir)
    names = []
    for f in os.listdir(source_dir):
        if f.lower().endswith('.jpg'):
            base = os.path.splitext(f)[0]
            if os.path.exists(os.path.join(source_dir, base + '.json')):
                names.append(base)
    return sorted(names)


def _group_of(base, delim):
    """Group key = stem up to the first delimiter token; a name with no
    delimiter is its own group (safe: it can't straddle sets)."""
    return base.split(delim)[0] if delim and delim in base else base


def assign_groups(pairs, delim, seed, ratios=(0.6, 0.2, 0.2)):
    """Assign WHOLE groups (video/plot/day) to train/val/test so no group ever
    straddles sets — the fix for H1.3 (random per-frame split leaks neighbours)."""
    groups = {}
    for b in pairs:
        groups.setdefault(_group_of(b, delim), []).append(b)
    keys = sorted(groups)
    random.seed(seed)
    random.shuffle(keys)
    n = len(keys)
    n_tr = int(round(n * ratios[0]))
    n_va = int(round(n * ratios[1]))
    if n >= 3:
        n_tr = max(1, n_tr)
        n_va = max(1, n_va)
    set_of = {}
    for i, g in enumerate(keys):
        set_of[g] = 'train' if i < n_tr else ('val' if i < n_tr + n_va else 'test')
    return groups, set_of


def split_peony_dataset(source_dir, out_root, seed=42, force=False, dry_run=False,
                        grouped=True, group_delim='_'):
    """Split <source_dir> pairs into <out_root>/{train,val,test}/{images,masks}.

    grouped=True (default): split by group key (video/plot/day prefix) so no
    group straddles sets; freeze the assignment in split_manifest.json.
    grouped=False: legacy per-file random split.
    Non-destructive by default: validates source first; clears targets only on
    --force; refuses non-empty targets otherwise.
    """
    _guard(source_dir)
    _guard(out_root)

    # R2 修复（复审 2026-09-14）：源与输出重叠时，force 清空会误删源数据。
    ap_src = os.path.abspath(source_dir)
    ap_out = os.path.abspath(out_root)
    if ap_src == ap_out or ap_out.startswith(ap_src + os.sep) \
            or ap_src.startswith(ap_out + os.sep):
        raise SystemExit('拒绝: 源目录与输出目录重叠，--force 会误删源数据')

    pairs = scan_pairs(source_dir)
    print('源目录: %s' % source_dir)
    print('找到成对 [.jpg + .json]: %d 对' % len(pairs))
    if len(pairs) == 0:
        raise SystemExit('中止: 源目录没有有效配对，未改动任何目标目录。')

    if grouped:
        groups, set_of = assign_groups(pairs, group_delim, seed)
    if grouped and len(groups) >= 3:
        stage_items = {s: [] for s in ('train', 'val', 'test')}
        for g, s in set_of.items():
            stage_items[s].extend(groups[g])
        manifest = {'seed': seed, 'group_delim': group_delim, 'grouped': True,
                    'groups': {g: set_of[g] for g in sorted(set_of)},
                    'counts': {s: len(stage_items[s]) for s in stage_items}}
    else:
        if grouped:
            print('⚠️  分组不足(<3, 分隔符 %r)，退回逐文件随机划分——正式训练前'
                  '请让文件名以 视频/地块/日期 为前缀以启用分组（H1.3）。'
                  % group_delim)
        random.seed(seed)
        random.shuffle(pairs)
        n_tr = int(len(pairs) * 0.6)
        n_va = int(len(pairs) * 0.2)
        stage_items = {'train': pairs[:n_tr], 'val': pairs[n_tr:n_tr + n_va],
                       'test': pairs[n_tr + n_va:]}
        manifest = {'seed': seed, 'grouped': False,
                    'counts': {s: len(stage_items[s]) for s in stage_items}}

    print('划分: ' + ' '.join('%s=%d' % (s, len(stage_items[s]))
                              for s in ('train', 'val', 'test')))
    if dry_run:
        print('[dry-run] 未写入任何文件。')
        return

    # R2 修复（复审 2026-09-14）：非 force 时，若目标已存在且非空，直接 copy
    # 会把旧样本混进新划分（同名覆盖 + 换 seed 后跨集合重复）。拒绝，除非
    # 显式 --force 清空，或换一个空的 --out-root。
    if not force:
        for stage in ('train', 'val', 'test'):
            for sub in ('images', 'masks'):
                d = os.path.join(out_root, stage, sub)
                if os.path.isdir(d) and os.listdir(d):
                    raise SystemExit(
                        '拒绝: 目标非空 %s —— 用 --force 覆盖，或换空的 --out-root'
                        '（防新旧样本混集，见复审 R2）' % d)

    for stage in ('train', 'val', 'test'):
        for sub in ('images', 'masks'):
            d = os.path.join(out_root, stage, sub)
            _guard(d)
            if force:
                _clear(d)
            os.makedirs(d, exist_ok=True)
        for base in stage_items[stage]:
            shutil.copy(os.path.join(source_dir, base + '.jpg'),
                        os.path.join(out_root, stage, 'images', base + '.jpg'))
            shutil.copy(os.path.join(source_dir, base + '.json'),
                        os.path.join(out_root, stage, 'images', base + '.json'))
        print('  %s: 复制 %d 对 -> %s' % (stage, len(stage_items[stage]),
                                          os.path.join(out_root, stage)))
    if grouped:
        mpath = os.path.join(out_root, 'split_manifest.json')
        with open(mpath, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=1)
        print('清单 -> %s（分组已冻结，训练/复核以此为准）' % mpath)


def _clear(folder):
    if not os.path.isdir(folder):
        return
    for name in os.listdir(folder):
        p = os.path.join(folder, name)
        if os.path.isfile(p) or os.path.islink(p):
            os.unlink(p)
        elif os.path.isdir(p):
            shutil.rmtree(p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', default=os.path.join(WORKSPACE, 'data',
                                                     'autumn_data', 'raw'))
    ap.add_argument('--out-root',
                    default=os.path.join(WORKSPACE, 'model_data'))
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--force', action='store_true',
                    help='清空目标目录后再写（默认拒绝破坏性操作）')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--group-delim', default='_',
                    help='分组键=文件名按该分隔符切首段（视频/地块/日期前缀）；'
                         '空串则逐文件为一组')
    ap.add_argument('--no-group', action='store_true',
                    help='退回旧的逐文件随机划分（不推荐：邻帧会跨集合）')
    args = ap.parse_args()
    split_peony_dataset(args.source, args.out_root, args.seed,
                        args.force, args.dry_run,
                        grouped=not args.no_group, group_delim=args.group_delim)


if __name__ == '__main__':
    main()
