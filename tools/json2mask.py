# -*- coding: utf-8 -*-
"""Labelme JSON -> binary mask (label-dict-safe rewrite, 2026-09-11).

Fixes from the 2026-09-09 external review (docs/reviews):
  * the collection checklist says to label peony, this tool only knew
    "shaoyao" and silently skipped everything else -> a fresh autumn
    dataset would convert to all-background masks with no error;
  * unknown labels now raise instead of being silently dropped;
  * a json that had foreground shapes but produced an empty mask is
    reported for manual inspection.

Usage:
  python tools/json2mask.py --input data/autumn_data/raw --output data/autumn_data/masks
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np

# Frozen label dictionary. Add synonyms HERE, never inline elsewhere.
PEONY_LABELS = {'peony', 'shaoyao', '芍药', 'shao_yao'}
BACKGROUND_LABELS = {'background', 'bg', '背景'}
KNOWN_LABELS = PEONY_LABELS | BACKGROUND_LABELS

PIXEL_PEONY = 255
PIXEL_BG = 0


def convert_one(json_path, out_dir, strict=True):
    """Convert one labelme json to <name>.png. Returns (fg_px, label_set)."""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    h, w = data['imageHeight'], data['imageWidth']
    mask = np.full((h, w), PIXEL_BG, dtype=np.uint8)

    labels = set()
    for shape in data.get('shapes', []):
        label = shape.get('label', '')
        labels.add(label)
        if label not in KNOWN_LABELS:
            if strict:
                raise ValueError('%s: 未冻结标签 %r（已冻结: %s）'
                                 % (os.path.basename(json_path), label,
                                    sorted(KNOWN_LABELS)))
            continue
        if label not in PEONY_LABELS:
            continue
        pts = np.array(shape['points'], dtype=np.int32)
        pts[:, 0] = np.clip(pts[:, 0], 0, w - 1)
        pts[:, 1] = np.clip(pts[:, 1], 0, h - 1)
        cv2.fillPoly(mask, [pts], PIXEL_PEONY)

    fg = int((mask > 0).sum())
    out = os.path.join(out_dir, os.path.splitext(os.path.basename(json_path))[0] + '.png')
    cv2.imwrite(out, mask)
    return fg, labels


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', required=True, help='含 .json 的目录')
    ap.add_argument('--output', required=True, help='mask 输出目录')
    ap.add_argument('--lenient', action='store_true',
                    help='未知标签只警告不报错（默认严格报错）')
    args = ap.parse_args()

    os.makedirs(args.output, exist_ok=True)
    jsons = sorted(f for f in os.listdir(args.input) if f.endswith('.json'))
    if not jsons:
        raise SystemExit('目录内没有 .json: %s' % args.input)

    n_ok, empty, errors = 0, [], []
    for name in jsons:
        try:
            fg, labels = convert_one(os.path.join(args.input, name),
                                     args.output, strict=not args.lenient)
        except Exception as e:
            errors.append('%s: %s' % (name, e))
            continue
        n_ok += 1
        if fg == 0:
            empty.append(name)
    print('转换完成: %d/%d 成功' % (n_ok, len(jsons)))
    if empty:
        print('⚠️  %d 个 JSON 生成了全背景掩码（可能标签名不对或未标注）: %s'
              % (len(empty), ', '.join(empty[:10])))
    if errors:
        print('❌ %d 个文件失败:' % len(errors))
        for e in errors[:20]:
            print('   ', e)
        sys.exit(1)


if __name__ == '__main__':
    main()
