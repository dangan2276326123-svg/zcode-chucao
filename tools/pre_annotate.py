# -*- coding: utf-8 -*-
"""半自动预标注：DeepLabV3+ → labelme JSON + 目检叠加图（qoder 工作区版）。

来源：`D:\\JetBrains\\chucao_prj\\annotation_tools\\pre_annotate.py`（只读仓，不改它）。
本版的三处差别，都是为了让它"能在本机跑起来、且不写坏别的仓"：

1. **解释器自检**：原脚本在 `labelme_env\\Scripts\\python.exe` 下直接
   `ModuleNotFoundError: No module named 'cv2'`（那个 venv 只有 labelme+numpy，
   没有 torch/albumentations/cv2）。这里把缺包变成一句能看懂的话，并给出正确入口。
2. **不再依赖只读仓的 network/**：模型定义用本工作区的 `network.modeling`。
3. **输出护栏**：默认拒绝写到工作区之外（沿用 `tools/split_dataset.py:_guard` 的口径），
   因为原脚本的默认输出路径落在只读仓里。确需写到别处时显式 `--allow-outside`。

用法（本机可用解释器）：
    D:\\ruanjian\\anac\\python.exe tools/pre_annotate.py --input 图片目录 --output 输出目录
或双击 `tools\\启动预标注.bat`。

输出结构：
    output/labelme/   原图 + 同名 labelme JSON（labelme 要求同目录）
    output/check/     叠加可视化 jpg（快速目检）
    output/重点检查清单.txt
"""
import argparse
import hashlib
import json
import os
import sys

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECOMMENDED_PY = r'D:\ruanjian\anac\python.exe'

# ---- 依赖自检：把 ModuleNotFoundError 换成人话 --------------------------
try:
    import cv2
    import numpy as np
    import torch
    import albumentations as A
    from albumentations.pytorch import ToTensorV2
except ImportError as e:
    sys.stderr.write(
        '\n缺少依赖：%s\n'
        '当前解释器：%s\n'
        'annotation_tools 里的 labelme_env 只装了 labelme+numpy，跑不了预标注。\n'
        '请改用：%s  或双击 tools\\启动预标注.bat\n\n' % (e, sys.executable, RECOMMENDED_PY))
    raise SystemExit(2)

sys.path.insert(0, WORKSPACE)
from network.modeling import deeplabv3plus_mobilenet  # noqa: E402

NUM_CLASSES = 2
MODEL_W, MODEL_H = 960, 720
MIN_AREA_PX = 400
SIMPLIFY_EPS = 1.5
# json2mask 现在认 peony/shaoyao/芍药/shao_yao（H1.2 冻结标签字典），默认沿用旧约定
DEFAULT_LABEL = 'shaoyao'

TRANSFORM = A.Compose([
    A.Resize(height=MODEL_H, width=MODEL_W, interpolation=cv2.INTER_LINEAR),
    A.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ToTensorV2(),
])


def _guard_write(path, allow_outside=False):
    """输出默认必须落在工作区内；只读仓路径一律拒绝。"""
    ap = os.path.abspath(path)
    if any(m in ap for m in ('JetBrains', 'chucao_prj', 'avi_project')):
        raise SystemExit('拒绝写入只读研究仓路径: %s' % path)
    if not allow_outside and not ap.startswith(os.path.abspath(WORKSPACE) + os.sep):
        raise SystemExit('拒绝写入工作区之外: %s（确有需要请加 --allow-outside）' % path)
    return ap


def load_model(weight_path):
    model = deeplabv3plus_mobilenet(num_classes=NUM_CLASSES, output_stride=16,
                                    pretrained_backbone=False)
    state = torch.load(weight_path, map_location='cpu')
    # 训练脚本存的是 {'model_state': ...} 还是裸 state_dict？两种都兼容，但要说清是哪种
    if isinstance(state, dict) and 'model_state' in state:
        state = state['model_state']
        print('权重容器：model_state 键')
    else:
        print('权重容器：裸 state_dict')
    model.load_state_dict(state)
    return model.eval()


def mask_to_polygons(mask, min_area=MIN_AREA_PX):
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    polys = []
    for c in contours:
        if cv2.contourArea(c) < min_area:
            continue
        approx = cv2.approxPolyDP(c, SIMPLIFY_EPS, True).reshape(-1, 2)
        if len(approx) >= 3:
            polys.append([[int(x), int(y)] for x, y in approx])
    return polys


def sha8(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()[:8]


def default_weights():
    cand = [os.path.join(WORKSPACE, 'model_data', 'weights', 'best_model.pth'),
            r'D:\JetBrains\chucao_prj\model_data\0.7428m\best_model.pth']
    for c in cand:
        if os.path.isfile(c):
            return c
    return cand[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', default=os.path.join(WORKSPACE, 'data', 'autumn_data', 'raw'),
                    help='待标注图片文件夹')
    ap.add_argument('--output', default=os.path.join(WORKSPACE, 'data', 'autumn_data', 'pre_annotated'))
    ap.add_argument('--weights', default=default_weights())
    ap.add_argument('--label', default=DEFAULT_LABEL)
    ap.add_argument('--fg-low', type=float, default=0.05)
    ap.add_argument('--fg-high', type=float, default=0.60)
    ap.add_argument('--limit', type=int, default=0, help='只处理前 N 张（0=全部），先小批试跑用')
    ap.add_argument('--allow-outside', action='store_true', help='允许输出到工作区之外')
    a = ap.parse_args()

    out = _guard_write(a.output, a.allow_outside)
    if not os.path.isdir(a.input):
        raise SystemExit('输入目录不存在: %s' % a.input)
    if not os.path.isfile(a.weights):
        raise SystemExit('权重不存在: %s' % a.weights)

    lm = os.path.join(out, 'labelme')
    ck = os.path.join(out, 'check')
    os.makedirs(lm, exist_ok=True)
    os.makedirs(ck, exist_ok=True)

    print('权重: %s  md5前8=%s  mtime=%d  大小=%d' % (
        a.weights, sha8(a.weights), int(os.path.getmtime(a.weights)), os.path.getsize(a.weights)))
    print('标签: %s   解释器: %s' % (a.label, sys.executable))
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model = load_model(a.weights).to(device)

    exts = ('.jpg', '.jpeg', '.png', '.bmp')
    imgs = sorted(f for f in os.listdir(a.input) if f.lower().endswith(exts))
    if a.limit:
        imgs = imgs[:a.limit]
    print('共 %d 张图片，设备 %s' % (len(imgs), device))
    if not imgs:
        raise SystemExit('输入目录里没有可处理的图片，未写任何输出')

    review = []
    for i, name in enumerate(imgs, 1):
        raw = np.fromfile(os.path.join(a.input, name), dtype=np.uint8)
        bgr = cv2.imdecode(raw, cv2.IMREAD_COLOR)
        if bgr is None:
            print('[%d/%d] %s 读不了，跳过' % (i, len(imgs), name))
            continue
        h, w = bgr.shape[:2]
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        with torch.no_grad():
            logits = model(TRANSFORM(image=rgb)['image'].unsqueeze(0).to(device))
            mask = torch.argmax(logits, dim=1).squeeze(0).cpu().numpy().astype(np.uint8)
        mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)
        fg = float((mask == 1).mean())

        j = {'version': '5.10.1', 'flags': {}, 'shapes': [], 'imagePath': name,
             'imageData': None, 'imageHeight': h, 'imageWidth': w}
        for poly in mask_to_polygons(mask):
            j['shapes'].append({'label': a.label, 'points': poly, 'group_id': None,
                                'description': '', 'shape_type': 'polygon', 'flags': {}})
        stem = os.path.splitext(name)[0]
        with open(os.path.join(lm, stem + '.json'), 'w', encoding='utf-8') as f:
            json.dump(j, f, ensure_ascii=False, indent=1)
        ext = os.path.splitext(name)[1]
        cv2.imencode(ext, bgr)[1].tofile(os.path.join(lm, name))
        overlay = bgr.copy()
        overlay[mask == 1] = [100, 255, 255]
        cv2.imencode(ext, cv2.addWeighted(bgr, 0.7, overlay, 0.3, 0))[1].tofile(
            os.path.join(ck, 'check_' + name))

        bad = fg < a.fg_low or fg > a.fg_high or not j['shapes']
        if bad:
            review.append('%s  前景占比=%.2f  多边形数=%d' % (name, fg, len(j['shapes'])))
        print('[%d/%d] %s 前景占比=%.2f 多边形=%d%s' % (
            i, len(imgs), name, fg, len(j['shapes']), '  ←重点检查' if bad else ''))

    with open(os.path.join(out, '重点检查清单.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(review) if review else '无异常，全部预标注正常。')
    print('完成，输出在 %s；重点检查 %d 张' % (out, len(review)))


if __name__ == '__main__':
    main()
