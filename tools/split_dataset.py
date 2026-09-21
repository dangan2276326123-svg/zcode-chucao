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

# Windows console here is cp936, which cannot encode the emoji used in the
# messages below.  A UnicodeEncodeError halfway through a 350-image batch is
# far worse than one dropped glyph, so replace unencodable characters instead
# of crashing.  (Observed live 2026-09-21 on tools/split_dataset.py.)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')
    sys.stderr.reconfigure(errors='replace')

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORBIDDEN_MARKERS = ('JetBrains', 'chucao_prj', 'avi_project')


def _guard(path):
    """Refuse to touch anything outside the workspace or in a read-only repo."""
    ap = os.path.abspath(path)
    if not ap.startswith(os.path.abspath(WORKSPACE) + os.sep):
        raise SystemExit('拒绝操作工作区之外的路径: %s' % path)
    if any(m in ap for m in FORBIDDEN_MARKERS):
        raise SystemExit('拒绝操作只读研究仓路径: %s' % path)


def _subdirs_with_images(source_dir):
    """Names of sub-folders that hold images.  Both this script and
    pre_annotate.py scan ONE level, so a nested layout would otherwise read as
    '0 valid pairs' and abort with a message about pairing, not about nesting."""
    out = []
    for name in sorted(os.listdir(source_dir)):
        p = os.path.join(source_dir, name)
        if os.path.isdir(p) and any(
                f.lower().endswith(IMG_EXT) for f in os.listdir(p)):
            out.append(name)
    return out


IMG_EXT = ('.jpg', '.jpeg', '.png', '.bmp')


def scan_pairs(source_dir):
    """Return sorted base names that have BOTH a .jpg and a same-name .json.

    Only .jpg pairs count (the shipped datasets are .jpg); PNG/BMP alongside a
    .json are reported so a mis-converted batch cannot silently shrink the set.
    """
    if not os.path.isdir(source_dir):
        raise SystemExit('源目录不存在: %s' % source_dir)
    subdirs = _subdirs_with_images(source_dir)
    if subdirs:
        raise SystemExit(
            '拒绝: 源目录下还有含图片的子目录（%s…）；本脚本只扫一层，'
            '递归下去会把同一段连续拍摄拆成看不见的组，划分与预标注都会漏掉它们。'
            '要么把某个批次目录本身当 --source，'
            '要么先合并成一个平铺目录（合并前确认文件名前缀能区分组）'
            % ', '.join(subdirs[:4]))
    names = []
    skipped_ext = []
    for f in os.listdir(source_dir):
        low = f.lower()
        if not low.endswith(IMG_EXT):
            continue
        base = os.path.splitext(f)[0]
        if not os.path.exists(os.path.join(source_dir, base + '.json')):
            continue
        if low.endswith('.jpg'):
            names.append(base)
        else:
            skipped_ext.append(f)
    if skipped_ext:
        print('⚠️  %d 张有同名 JSON 但不是 .jpg，未参与划分（scan_pairs 只认 .jpg）：'
              '%s%s' % (len(skipped_ext), ', '.join(skipped_ext[:5]),
                        ' …' if len(skipped_ext) > 5 else ''))
    return sorted(names)


def _group_of(base, delim):
    """Group key = stem up to the first delimiter token; a name with no
    delimiter is its own group (safe: it can't straddle sets)."""
    return base.split(delim)[0] if delim and delim in base else base


def assign_groups(pairs, delim, seed, ratios=(0.6, 0.2, 0.2)):
    """Assign WHOLE groups (video/plot/day) to train/val/test so no group ever
    straddles sets — the fix for H1.3 (random per-frame split leaks neighbours).

    E1② 修复（09-21 复审）：旧写法 n=3 时 `round(3*0.6)=2` 且 `round(3*0.2)=1`
    → train 2 / val 1 / **test 0**，独立测试集被静默清空。现在硬性保证三集合
    各≥1 组；组数不足 3 时**报错拒绝**，不再悄悄退回逐文件随机划分。
    """
    groups = {}
    for b in pairs:
        groups.setdefault(_group_of(b, delim), []).append(b)
    n = len(groups)
    if n:
        share = max(len(v) for v in groups.values()) / float(len(pairs))
        print('分组形态: %d 张 → %d 组，最大组占 %.0f%%（分隔符 %r）'
              % (len(pairs), n, 100 * share, delim))
        if share > 0.6:
            print('⚠️  单组占比 >60% 以上。分组键切的是文件名首段，'
                  '如果所有文件名同一个前缀（IMG_0001 之类），整批会塌成一组。')
    if n < 3:
        biggest = max(groups.values(), key=len) if groups else []
        raise SystemExit(
            '拒绝: 分组模式至少需要 3 个组（train/val/test 各≥1），实得 %d 组'
            '（%d 张图 → %d 组，最大组 %d 张，分隔符 %r）。\n'
            '  先分清是哪种情况：\n'
            '  ① 文件名没带批次前缀（如 IMG_0001.jpg → 每张切出来都是 %s）：'
            '这是命名问题，不是数据不够。改命名为 {批次}_{日期}_{序号}.jpg '
            '再划，一组＝一段连续拍摄/一块田/一天。\n'
            '  ② 真的只采了 %d 个批次：补采集，或显式 --no-group 走逐图模式'
            '（邻帧跨集合风险 H1.3 自负，且正式评价不得用这一档）。'
            % (n, len(pairs), n, len(biggest), delim,
               (biggest[0].split(delim)[0] if biggest and delim else 'IMG'), n))
    keys = sorted(groups)
    random.seed(seed)
    random.shuffle(keys)
    n_tr = max(1, int(round(n * ratios[0])))
    n_va = max(1, int(round(n * ratios[1])))
    for _ in range(n):                       # 把 test 挤回至少 1 组
        if n_tr + n_va <= n - 1:
            break
        if n_va > 1:
            n_va -= 1
        elif n_tr > 1:
            n_tr -= 1
    if n_tr + n_va > n - 1:                  # n>=3 时理论不可达，留作硬护栏
        raise SystemExit('拒绝: 无法在 %d 组上同时保证 train/val/test 非空' % n)
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
        groups, set_of = assign_groups(pairs, group_delim, seed)   # <3 组直接拒绝
        stage_items = {s: [] for s in ('train', 'val', 'test')}
        for g, s in set_of.items():
            stage_items[s].extend(groups[g])
        manifest = {'seed': seed, 'group_delim': group_delim, 'grouped': True,
                    'groups': {g: set_of[g] for g in sorted(set_of)},
                    'counts': {s: len(stage_items[s]) for s in stage_items}}
    else:
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
