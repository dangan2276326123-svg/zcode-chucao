import os
import cv2
import numpy as np
import torch
import albumentations as A
from albumentations.pytorch import ToTensorV2

# 引入你的 DeepLabV3+ (MobileNetV2) 神经网络底盘
from network.modeling import deeplabv3plus_mobilenet

# =====================================================================
# 🛠️ 路径与推理配置中心
# =====================================================================
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
NUM_CLASSES = 2

# 1. 你训练好的最强权重物理绝对路径
BEST_WEIGHT_PATH = r"D:\JetBrains\chucao_prj\model_data\0.7428m\best_model.pth"

# 2. 从网上找的测试图片绝对路径（可以是单张 .jpg 图片，也可以是一个放满了网络图片的文件夹！）
INPUT_IMAGE_PATH = r"D:\JetBrains\avi_project\caijian\001\img_000146.jpg"  # 👈 改成你的网络图片路径或文件夹路径

# 3. 分割渲染结果输出文件夹
OUTPUT_DIR = r"./results/demo_predictions"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 4. 模型推理时的标准输入尺寸（维持模型最熟悉的 960x720 满血视野）
MODEL_WIDTH, MODEL_HEIGHT = 960, 720

# 数据归一化（严格对齐训练时的标准化参数）
inference_transform = A.Compose([
    A.Resize(height=MODEL_HEIGHT, width=MODEL_WIDTH, interpolation=cv2.INTER_LINEAR),
    A.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ToTensorV2()
])


def load_trained_model(weight_path):
    print("🧠 正在加载 DeepLabV3+ (MobileNetV2) 除草大脑...")
    model = deeplabv3plus_mobilenet(num_classes=NUM_CLASSES, output_stride=16, pretrained_backbone=False)

    if not os.path.exists(weight_path):
        raise FileNotFoundError(f"❌ 未找到指定的权重文件: {weight_path}")

    model.load_state_dict(torch.load(weight_path, map_location=DEVICE))
    model = model.to(DEVICE).eval()
    print("✅ 最优训练权重载入成功，已进入评估状态！")
    return model


def predict_single_image(model, img_path, save_dir):
    # 1. 读取任意尺寸的原始图片 (BGR)
    orig_bgr = cv2.imread(img_path, cv2.IMREAD_COLOR)
    if orig_bgr is None:
        print(f"⚠️ 无法读取图像: {img_path}，已跳过")
        return

    # 记录原始图像的宽高物理尺寸
    orig_h, orig_w = orig_bgr.shape[:2]
    img_rgb = cv2.cvtColor(orig_bgr, cv2.COLOR_BGR2RGB)

    # 2. 图像标准化并转为 Tensor 喂给网络
    aug = inference_transform(image=img_rgb)
    input_tensor = aug["image"].unsqueeze(0).to(DEVICE)

    # 3. 前向推理预测
    with torch.no_grad():
        out_logits = model(input_tensor)
        # 提取概率最大的类别 (0: 背景, 1: 芍药)
        pred_mask = torch.argmax(out_logits, dim=1).squeeze(0).cpu().numpy().astype(np.uint8)

    # 4. 🚨 核心步骤：将预测出的掩码无损缩放还原回【原始图片的物理尺寸】
    pred_mask_orig_size = cv2.resize(pred_mask, (orig_w, orig_h), interpolation=cv2.INTER_NEAREST)

    # 5. 渲染 2.85 经典黄 (蓝100, 绿255, 红255) 蒙版，并与原图进行 7:3 半透明叠加
    yellow_overlay = np.zeros_like(orig_bgr, dtype=np.uint8)
    yellow_overlay[pred_mask_orig_size == 1] = [100, 255, 255]  # 前景芍药像素涂黄

    # 图像混合：0.7 深度原图 + 0.3 黄色语义蒙版
    result_visualization = cv2.addWeighted(orig_bgr, 0.7, yellow_overlay, 0.3, 0)

    # 6. 保存无损可视化图片
    base_name = os.path.basename(img_path)
    save_file_path = os.path.join(save_dir, f"seg_{base_name}")
    cv2.imwrite(save_file_path, result_visualization)

    print(f"📸 成功预测！原图尺寸: ({orig_w}x{orig_h}) | 已无损导出至: {save_file_path}")


def main():
    model = load_trained_model(BEST_WEIGHT_PATH)

    print(f"\n📡 开始对目标路径进行语义分割推理: {INPUT_IMAGE_PATH}")
    if os.path.isfile(INPUT_IMAGE_PATH):
        # 处理单张图片
        predict_single_image(model, INPUT_IMAGE_PATH, OUTPUT_DIR)
    elif os.path.isdir(INPUT_IMAGE_PATH):
        # 批量处理文件夹下的所有测试图片
        valid_exts = (".jpg", ".jpeg", ".png", ".bmp")
        img_files = [f for f in os.listdir(INPUT_IMAGE_PATH) if f.lower().endswith(valid_exts)]
        print(f"📁 文件夹中共找到 {len(img_files)} 张测试图片，开始批量推理...")

        for file in img_files:
            full_path = os.path.join(INPUT_IMAGE_PATH, file)
            predict_single_image(model, full_path, OUTPUT_DIR)
    else:
        print(f"❌ 路径不存在，请检查 INPUT_IMAGE_PATH 设置: {INPUT_IMAGE_PATH}")

    print(f"\n🎉 语义分割预测完成！所有结果图均已存入: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()