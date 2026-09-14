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


def split_peony_dataset(source_dir, out_root, seed=42, force=False, dry_run=False):
    """Split <source_dir> pairs 6:2:2 into <out_root>/{train,val,test}/{images,masks}.

    Non-destructive by default: validates the source first, and only clears
    existing target dirs when force=True.
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

    random.seed(seed)
    random.shuffle(pairs)
    n_train = int(len(pairs) * 0.6)
    n_val = int(len(pairs) * 0.2)
    train = pairs[:n_train]
    val = pairs[n_train:n_train + n_val]
    test = pairs[n_train + n_val:]
    print('划分: train=%d val=%d test=%d' % (len(train), len(val), len(test)))

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

    for stage, items in (('train', train), ('val', val), ('test', test)):
        for sub in ('images', 'masks'):
            d = os.path.join(out_root, stage, sub)
            _guard(d)
            if force:
                _clear(d)
            os.makedirs(d, exist_ok=True)
        for base in items:
            shutil.copy(os.path.join(source_dir, base + '.jpg'),
                        os.path.join(out_root, stage, 'images', base + '.jpg'))
            shutil.copy(os.path.join(source_dir, base + '.json'),
                        os.path.join(out_root, stage, 'images', base + '.json'))
        print('  %s: 复制 %d 对 -> %s' % (stage, len(items),
                                          os.path.join(out_root, stage)))
    print('完成。注意：6:2:2 单图随机划分存在邻帧跨集合风险，'
          '正式训练前请按视频/地块分组（见缺口清单 H 区）。')


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
                    default=os.path.join(WORKSPACE, 'model_data', 'dataset'))
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--force', action='store_true',
                    help='清空目标目录后再写（默认拒绝破坏性操作）')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    split_peony_dataset(args.source, args.out_root, args.seed,
                        args.force, args.dry_run)


if __name__ == '__main__':
    main()
