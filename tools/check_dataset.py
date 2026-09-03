import os
import cv2
import numpy as np

img_dir = r"D:\JetBrains\chucao_prj\model_data\test\images"
mask_dir = r"D:\JetBrains\chucao_prj\model_data\test\masks"
err = []

for name in os.listdir(img_dir):
    if not name.lower().endswith(("jpg", "jpeg", "png")):
        continue
    base = os.path.splitext(name)[0]
    mask_path = os.path.join(mask_dir, base + ".png")
    if not os.path.exists(mask_path):
        err.append(f"{name} 缺少掩码")
        continue

    img = cv2.imread(os.path.join(img_dir, name))
    mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
    if img.shape[:2] != mask.shape[:2]:
        err.append(f"{name} 图和掩码尺寸不匹配")
    pix_set = set(np.unique(mask))
    # 合法像素改为0、255
    if not pix_set.issubset({0, 255}):
        err.append(f"{name} 存在异常像素：{pix_set}")

if err:
    print("发现问题：")
    for e in err:
        print(e)
else:
    print("✅ 数据集校验全部通过")