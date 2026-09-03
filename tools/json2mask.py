import os
import json
import cv2
import numpy as np

IMG_JSON_FOLDER = r"model_data/test/images"
MASK_OUTPUT = r"model_data/test/masks"
LABEL_NAME = "shaoyao"
PIXEL_PEONY = 255
PIXEL_BG = 0

os.makedirs(MASK_OUTPUT, exist_ok=True)

for file in os.listdir(IMG_JSON_FOLDER):
    if not file.endswith(".json"):
        continue
    json_path = os.path.join(IMG_JSON_FOLDER, file)
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    h = data["imageHeight"]
    w = data["imageWidth"]
    mask = np.full((h, w), fill_value=PIXEL_BG, dtype=np.uint8)

    for shape in data["shapes"]:
        if shape["label"] != LABEL_NAME:
            continue
        pts = np.array(shape["points"], dtype=np.int32)  # 强制转整数坐标
        # 裁剪越界坐标到图片范围内，防止填充失效
        pts[:, 0] = np.clip(pts[:, 0], 0, w - 1)
        pts[:, 1] = np.clip(pts[:, 1], 0, h - 1)
        cv2.fillPoly(mask, [pts], PIXEL_PEONY)

    mask_name = file.replace(".json", ".png")
    cv2.imwrite(os.path.join(MASK_OUTPUT, mask_name), mask)
    print(f"生成掩码：{mask_name}")
print("全部掩码生成完成")