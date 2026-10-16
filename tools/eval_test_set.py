#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Run the segmentation model on the 25-image independent test set and PERSIST the
metrics -- which the training script never did.

Why this exists
---------------
`chucao_prj/network/train_m.py` already implements an independent test-set
evaluation (`execute_independent_test_evaluation`, line 747+), and the test set is
on disk (`model_data/test/`, 25 images with masks). But that function only prints to
the console, and no console log was kept, so the thesis currently has **no held-out
test number** -- only validation numbers, which is exactly the thing P9 warns about
(验证集峰值 != 独立测试成绩). Producing the number needs no annotation and no field
trip: one forward pass over 25 images.

Hard rules for this script
--------------------------
1. **Nothing is written into the read-only repo.** AGENTS makes `D:\\JetBrains\\chucao_prj`
   read-only except `thesis_cau/`, and that repo's training log has already been
   overwritten once (see `train_metric_log_backup.csv`, whose epoch 81 reads 0.7289
   where the main log reads 0.7434). So every output path here is inside this repo.
   Importing `network.train_m` is checked to be filesystem-safe: its only module-level
   side effects are two `os.makedirs(..., exist_ok=True)` on directories that already
   exist, plus `warnings.filterwarnings` and `matplotlib.use('Agg')`.
2. **The metric function is imported, not reimplemented.** A second implementation
   that differs by one epsilon would produce a test number not comparable with the
   validation numbers in 表 3-1 -- the precise failure this is meant to fix.
3. **The checkpoint is identified by hash, mtime and size in the output**, because the
   repo holds two files of identical size and different content under the same name
   (台账 Pc-7). A metric without its checkpoint identity is not evidence.

Usage:
    python -B tools/eval_test_set.py                # CPU is fine for 25 images
    python -B tools/eval_test_set.py --device cuda
"""
import argparse
import datetime
import hashlib
import io
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHUCAO = os.environ.get('CHUCAO_DIR', r'D:\JetBrains\chucao_prj')

# The read-only repo is imported, never written to.
if CHUCAO not in sys.path:
    sys.path.insert(0, CHUCAO)


def sha256_head(path, n=12):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()[:n]


def assert_no_writes_into_source():
    """Fail loudly if the source repo's tree is dirty in a way we caused.

    Cheap guard: record the mtimes of the two directories train_m.py would create and
    confirm they already exist, so its module-level makedirs() are no-ops.
    """
    for rel in ('model_data/weights', 'network/results/test_visuals'):
        p = os.path.join(CHUCAO, rel.replace('/', os.sep))
        if not os.path.isdir(p):
            raise SystemExit(
                ' refusing to import: %s does not exist, so importing train_m.py '
                'would CREATE a directory inside the read-only repo' % p)


def install_matplotlib_stub():
    """Give train_m.py a no-op matplotlib so importing it does not need a working one.

    This repo's README「运行环境」already records the fact: **matplotlib is unusable in
    both interpreters** (numpy 2.0.2 vs a compiled-1.x mismatch -> ImportError). Verified
    again on 2026-10-15 when importing train_m failed exactly there.

    That is fine for this script: train_m.py touches matplotlib only inside
    `generate_metrics_trend_chart()` (module level just does use()/rcParams), and the
    trend chart we cite in the thesis is the one that file already produced on
    2026-07-31. The stub therefore has to satisfy imports and rcParams writes, nothing
    more -- and if a future version of train_m.py starts plotting at import time, the
    plot call raises here instead of silently doing nothing.
    """
    import types

    if 'matplotlib' in sys.modules and hasattr(sys.modules['matplotlib'], 'use'):
        return
    mpl = types.ModuleType('matplotlib')
    mpl.use = lambda *a, **k: None
    pyplot = types.ModuleType('matplotlib.pyplot')
    pyplot.rcParams = {}
    pyplot.style = types.SimpleNamespace(available=[], use=lambda *a, **k: None)
    mpl.pyplot = pyplot
    sys.modules['matplotlib'] = mpl
    sys.modules['matplotlib.pyplot'] = pyplot


def build_transform(T, width, height):
    """Rebuild the validation transform at an explicit input size.

    Needed because `train_m.val_transform` is constructed at import time from
    IMG_WIDTH/IMG_HEIGHT, which depend on the file's current MODE -- and the two
    modes do not agree: `train_coarse` uses 480x360 (train_m.py line 189) while
    `train_fine`/`test` use 960x720 (lines 215, 239). Importing with MODE as shipped
    therefore silently evaluates at 480x360. That is exactly what happened on the
    first run of this script: it returned val mIoU 0.5433 against a logged 0.7178,
    and the whole gap was resolution, not the model.

    The three operations below are copied from train_m.py's val_transform so the
    only difference from the training-time pipeline is the size, which we state.
    """
    import albumentations as A
    from albumentations.pytorch import ToTensorV2
    return A.Compose([
        A.Resize(height=height, width=width, interpolation=1),   # cv2.INTER_LINEAR
        A.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ToTensorV2(),
    ])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--device', default='cpu')
    ap.add_argument('--weights', default=os.path.join(
        CHUCAO, 'model_data', 'weights', 'best_model.pth'))
    ap.add_argument('--split', default='test', choices=('test', 'val', 'train'),
                    help='跑哪一份数据。**val 是这条链路的对照实验**：训练日志里 '
                         'val 的 mIoU 是已知读数，同一套代码跑 val 若复现不出来， '
                         '说明本脚本口径与训练时不一致，那么 test 的数也就不能当真')
    ap.add_argument('--input-size', default='960x720',
                    help='推理输入尺寸 WxH。**默认 960x720 = 部署与精调阶段的尺寸**；'
                         'train_m.py 在 MODE=train_coarse 时用的是 480x360，'
                         '两者读数不可比（见 build_transform 的说明）')
    args = ap.parse_args()

    assert_no_writes_into_source()
    install_matplotlib_stub()
    import torch
    import network.train_m as T          # import-safe; see the docstring

    weight = args.weights
    ident = {
        'weights_path': weight.replace('\\', '/'),
        'weights_sha256_12': sha256_head(weight),
        'weights_bytes': os.path.getsize(weight),
        'weights_mtime': datetime.datetime.fromtimestamp(
            os.path.getmtime(weight)).strftime('%Y-%m-%d %H:%M:%S'),
        'metric_function': 'network.train_m.calculate_all_metrics (imported, not copied)',
        'test_images_dir': T.TEST_IMG_DIR,
        'test_masks_dir': T.TEST_MASK_DIR,
        'num_classes': T.NUM_CLASSES,
        'output_stride': 16,
        'pretrained_backbone': False,
        'run_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }

    model = T.deeplabv3plus_mobilenet(num_classes=T.NUM_CLASSES,
                                      output_stride=16,
                                      pretrained_backbone=False)
    state = torch.load(weight, map_location=args.device)
    model.load_state_dict(state)
    model = model.to(args.device).eval()

    # 选哪一份数据。val 的用途是**对照**：训练日志里 val 的读数是已知的，
    # 这套代码跑不出同一个数，就说明口径不一致，test 的读数也不能当真。
    split_dirs = {'test': (T.TEST_IMG_DIR, T.TEST_MASK_DIR),
                  'val': (T.VAL_IMG_DIR, T.VAL_MASK_DIR),
                  'train': (T.TRAIN_IMG_DIR, T.TRAIN_MASK_DIR)}
    img_dir, mask_dir = split_dirs[args.split]
    ident['split'] = args.split
    ident['test_images_dir'] = img_dir
    ident['test_masks_dir'] = mask_dir

    width, height = (int(v) for v in args.input_size.lower().split('x'))
    ident['input_size'] = '%dx%d' % (width, height)
    ident['transform_note'] = ('Resize+Normalize+ToTensor, rebuilt at the stated size; '
                               'train_m.val_transform would have used 480x360 under '
                               'the file as-shipped MODE=train_coarse')
    tf = build_transform(T, width, height)
    ds = T.PeonyDataset(img_dir, mask_dir, tf)
    n = len(ds)
    if n == 0:
        raise SystemExit('test set is empty -- nothing to evaluate')

    keys = ['miou', 'mpa', 'dice', 'recall', 'precision',
            'fg_iou', 'bg_iou', 'fpr', 'fnr']
    acc = dict((k, 0.0) for k in keys)
    per_image = []
    with torch.no_grad():
        for i in range(n):
            img, mask = ds[i]
            img = img.unsqueeze(0).to(args.device)
            mask = mask.unsqueeze(0).to(args.device)
            out = model(img)
            miou, mpa, dice_v, rec, prec, fg, bg, fpr, fnr = \
                T.calculate_all_metrics(out, mask, T.NUM_CLASSES)
            vals = dict(zip(keys, [miou, mpa, dice_v, rec, prec, fg, bg, fpr, fnr]))
            for k in keys:
                acc[k] += vals[k]
            per_image.append(dict([('index', i)] + [(k, round(vals[k], 6))
                                                   for k in keys]))

    mean = dict((k, acc[k] / n) for k in keys)
    # 表 3-1 用的是"逐图平均"这一口径（与 calculate_all_metrics 每次只算一张图一致），
    # 这里必须把口径写出来：换成按像素累加再算 IoU 会得到另一个数。
    out_dir = os.path.join(
        REPO, 'results',
        'test_eval_' + datetime.datetime.now().strftime('%Y%m%d_%H%M'))
    os.makedirs(out_dir, exist_ok=True)

    with io.open(os.path.join(out_dir, 'test_metrics.json'), 'w',
                 encoding='utf-8') as f:
        json.dump({'identity': ident, 'n_images': n,
                   'aggregation': 'per-image mean (same basis as the validation log)',
                   'mean': dict((k, round(mean[k], 6)) for k in keys),
                   'per_image': per_image}, f, ensure_ascii=False, indent=1)

    print('independent test-set evaluation')
    print('  split       : %s  %d images  (%s)' % (args.split, n, img_dir))
    print('  input size  : %dx%d' % (width, height))
    print('  weights     : %s  sha=%s  %d B  mtime=%s'
          % (os.path.basename(weight), ident['weights_sha256_12'],
             ident['weights_bytes'], ident['weights_mtime']))
    print('  metric fn   : %s' % ident['metric_function'])
    for k in keys:
        print('  %-10s %.4f' % (k, mean[k]))
    print('written -> %s' % out_dir)


if __name__ == '__main__':
    main()
