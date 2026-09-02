import os
import cv2
import numpy as np
import csv
import warnings
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader

# ===================== 基础环境配置 =====================
os.environ["ALBUMENTATIONS_DISABLE_VERSION_CHECK"] = "1"
# 针对 4GB 显存跑 720x960 高清大图微调的碎片整理配置
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "max_split_size_mb:96,garbage_collection_threshold:0.7"

import albumentations as A
from albumentations.pytorch import ToTensorV2
from tqdm import tqdm
from network.modeling import deeplabv3plus_xception

#  【V4.2 语法修正】：彻底移除 module 前方的反斜杠，确保脚本顺畅编译
warnings.filterwarnings("ignore", category=UserWarning, module="albumentations")
warnings.filterwarnings("ignore", category=FutureWarning)

# ===================== 全局基础配置（完美适配 GTX 1650 高清微调） =====================
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
NUM_CLASSES = 2

# 由于切换为 720x960 大图，Batch Size 设为 1 防 OOM，利用 6 步梯度累积稳固收敛
BATCH_SIZE = 1
ACCUM_STEPS = 6  # 等效总 Batch Size = 6
EPOCHS = 50  # 高清大图细节精调专场的集中突击轮次
EARLY_STOP_PATIENCE = 4

# 降温微调超参数：整体降低一个数量级，防止高清大图冲垮成熟特征
LR_BACKBONE = 5e-6
LR_DECODER = 2e-5
WEIGHT_DECAY = 3e-4
GRAD_CLIP_NORM = 1.0
USE_AMP = True

# 关闭强制新训练，允许双重断点加载逻辑介入
FORCE_NEW_TRAIN = False

# 损失函数复合权重
LOSS_CE_WEIGHT = 0.55
LOSS_DICE_WEIGHT = 0.45

# 路径配置
SAVE_WEIGHT_DIR = r"../model_data/weights"
TRAIN_IMG_DIR = r"../model_data/train/images"
TRAIN_MASK_DIR = r"../model_data/train/masks"
VAL_IMG_DIR = r"../model_data/val/images"
VAL_MASK_DIR = r"../model_data/val/masks"
LOG_CSV_PATH = "train_metric_log.csv"
RESUME_CHECKPOINT = os.path.join(SAVE_WEIGHT_DIR, "latest_checkpoint.pth")
BEST_WEIGHT_PATH = os.path.join(SAVE_WEIGHT_DIR, "best_model.pth")

LR_SCHEDULER_TYPE = "cosine"
ENABLE_ERROR_ANALYSIS = True
SAVE_WORST_SAMPLES = True
WORST_SAMPLE_NUM = 3

# Windows 单线程兼容配置
NUM_WORKERS = 0
PERSISTENT_WORKERS = False
PREFETCH_FACTOR = None
PIN_MEMORY = False

os.makedirs(SAVE_WEIGHT_DIR, exist_ok=True)


# ---------------------- 数据集类 ----------------------
class PeonyDataset(Dataset):
    def __init__(self, img_dir, mask_dir, transform=None, green_augment=True):
        self.img_dir = img_dir
        self.mask_dir = mask_dir
        self.transform = transform
        self.green_augment = green_augment
        self.img_list = sorted([f for f in os.listdir(img_dir) if f.endswith(("jpg", "png"))])

    def __len__(self):
        return len(self.img_list)

    def __getitem__(self, idx):
        img_name = self.img_list[idx]
        img_path = os.path.join(self.img_dir, img_name)
        mask_path = os.path.join(self.mask_dir, img_name.replace(".jpg", ".png"))

        img = cv2.imread(img_path, cv2.IMREAD_COLOR)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        if self.green_augment:
            hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
            lower_green = np.array([25, 40, 30], dtype=np.uint8)
            upper_green = np.array([95, 255, 255], dtype=np.uint8)
            green_mask = cv2.inRange(hsv, lower_green, upper_green)
            green_mask_3ch = cv2.cvtColor(green_mask, cv2.COLOR_GRAY2RGB)
            img = cv2.addWeighted(img, 0.8, green_mask_3ch, 0.3, 0)

        mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
        mask = np.where(mask == 255, 1, 0).astype(np.int64)

        if self.transform:
            aug_result = self.transform(image=img, mask=mask)
            img = aug_result["image"]
            mask = aug_result["mask"]

        return img, mask.long()


# ---------------------- 数据增强流水线（720x960 原始高清大图） ----------------------
train_transform = A.Compose([
    A.Resize(height=720, width=960),
    A.HueSaturationValue(hue_shift_limit=10, sat_shift_limit=(-35, 5), val_shift_limit=10, p=0.4),
    A.CLAHE(clip_limit=2.0, tile_grid_size=(8, 8), p=0.5),
    A.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2, hue=0.05, p=0.5),
    A.RandomBrightnessContrast(brightness_limit=0.15, contrast_limit=0.15, p=0.4),
    A.GaussianBlur(blur_limit=(1, 3), p=0.2),
    A.HorizontalFlip(p=0.5),
    A.VerticalFlip(p=0.2),
    A.Affine(translate_percent={"x": (-0.08, 0.08), "y": (-0.08, 0.08)}, scale=(0.9, 1.1), rotate=(-12, 12), p=0.4),
    A.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ToTensorV2()
])

val_transform = A.Compose([
    A.Resize(height=720, width=960),
    A.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ToTensorV2()
])


# ---------------------- 损失函数集合 ----------------------
class DiceLoss(nn.Module):
    def __init__(self):
        super().__init__()

    def forward(self, pred, target):
        smooth = 1e-6
        pred = torch.softmax(pred, dim=1)
        target_onehot = torch.zeros_like(pred).scatter(1, target.unsqueeze(1), 1)
        inter = (pred * target_onehot).sum(dim=(2, 3))
        union = pred.sum(dim=(2, 3)) + target_onehot.sum(dim=(2, 3))
        return 1 - ((2 * inter + smooth) / (union + smooth)).mean()


def compute_total_loss(pred, target, ce_fn, dice_fn):
    ce = ce_fn(pred, target)
    dice = dice_fn(pred, target)
    return LOSS_CE_WEIGHT * ce + LOSS_DICE_WEIGHT * dice


# ---------------------- 向量化指标计算 ----------------------
def calculate_all_metrics(pred_logits, mask_label, num_classes):
    smooth = 1e-6
    pred = torch.argmax(pred_logits, dim=1)

    pred_onehot = F.one_hot(pred, num_classes).permute(0, 3, 1, 2).float()
    label_onehot = F.one_hot(mask_label, num_classes).permute(0, 3, 1, 2).float()

    inter = torch.sum(pred_onehot * label_onehot, dim=(2, 3))
    union = torch.sum(pred_onehot, dim=(2, 3)) + torch.sum(label_onehot, dim=(2, 3)) - inter

    iou_per_class = (inter + smooth) / (union + smooth)
    acc_per_class = (inter + smooth) / (torch.sum(label_onehot, dim=(2, 3)) + smooth)

    miou = torch.mean(iou_per_class).item()
    mpa = torch.mean(acc_per_class).item()
    bg_iou = torch.mean(iou_per_class[:, 0]).item()
    fg_iou = torch.mean(iou_per_class[:, 1]).item()

    pred_fore = pred_onehot[:, 1, :, :]
    label_fore = label_onehot[:, 1, :, :]
    tp = torch.sum(pred_fore * label_fore).item()
    fp = torch.sum(pred_fore * (1 - label_fore)).item()
    fn = torch.sum((1 - pred_fore) * label_fore).item()
    tn = torch.sum((1 - pred_fore) * (1 - label_fore)).item()

    dice = (2 * tp + smooth) / (tp + fp + tp + fn + smooth)
    recall = (tp + smooth) / (tp + fn + smooth)
    precision = (tp + smooth) / (tp + fp + smooth)
    fpr = (fp + smooth) / (fp + tn + smooth)
    fnr = (fn + smooth) / (fn + tp + smooth)

    return miou, mpa, dice, recall, precision, fg_iou, bg_iou, fpr, fnr


# BN层拦截锁死工具函数，专治 Batch=1 全局平均池化层报错
def set_bn_eval(module):
    if isinstance(module, nn.BatchNorm2d):
        module.eval()


# ---------------------- 训练一轮 ----------------------
def train_one_epoch(model, loader, ce_fn, dice_fn, opt, scaler, epoch):
    model.train()
    model.apply(set_bn_eval)  # 强行把 BatchNorm 压回 eval 态，避开分母为 0 崩溃，保护成熟统计量
    total_loss = 0.0
    opt.zero_grad()
    bar = tqdm(loader, desc=f"Train Epoch {epoch}")

    for idx, (img, mask) in enumerate(bar):
        img, mask = img.to(DEVICE, non_blocking=True), mask.to(DEVICE, non_blocking=True)

        with torch.amp.autocast(device_type="cuda", enabled=USE_AMP):
            out = model(img)
            loss = compute_total_loss(out, mask, ce_fn, dice_fn)
            loss = loss / ACCUM_STEPS

        scaler.scale(loss).backward()

        if (idx + 1) % ACCUM_STEPS == 0:
            scaler.unscale_(opt)
            nn.utils.clip_grad_norm_(model.parameters(), GRAD_CLIP_NORM)
            scaler.step(opt)
            scaler.update()
            opt.zero_grad()

        total_loss += loss.item() * ACCUM_STEPS
        bar.set_postfix(loss=f"{total_loss / (idx + 1):.4f}")

    torch.cuda.empty_cache()
    return total_loss / len(loader)


# ---------------------- 验证一轮 ----------------------
def val_one_epoch(model, loader, ce_fn, dice_fn, epoch, dataset):
    model.eval()
    total_loss = total_miou = total_mpa = total_dice = total_recall = total_precision = 0.0
    total_fg_iou = total_bg_iou = total_fpr = total_fnr = 0.0
    batch_num = len(loader)
    sample_metrics = []

    with torch.no_grad():
        bar = tqdm(loader, desc=f"Val Epoch {epoch}")
        for idx, (img, mask) in enumerate(bar):
            img, mask = img.to(DEVICE, non_blocking=True), mask.to(DEVICE, non_blocking=True)

            with torch.amp.autocast(device_type="cuda", enabled=USE_AMP):
                out = model(img)
                loss = compute_total_loss(out, mask, ce_fn, dice_fn)

            total_loss += loss.item()
            miou, mpa, dice_val, recall, precision, fg_iou, bg_iou, fpr, fnr = calculate_all_metrics(
                out, mask, NUM_CLASSES
            )

            total_miou += miou
            total_mpa += mpa
            total_dice += dice_val
            total_recall += recall
            total_precision += precision
            total_fg_iou += fg_iou
            total_bg_iou += bg_iou
            total_fpr += fpr
            total_fnr += fnr

            for b_idx in range(img.size(0)):
                img_idx = idx * BATCH_SIZE + b_idx
                if img_idx < len(dataset.img_list):
                    img_name = dataset.img_list[img_idx]
                    sample_metrics.append((img_name, miou, recall, precision))

            bar.set_postfix(loss=f"{total_loss / (idx + 1):.4f}", miou=f"{total_miou / (idx + 1):.4f}")

    torch.cuda.empty_cache()
    worst_samples = sorted(sample_metrics, key=lambda x: x[1])[:WORST_SAMPLE_NUM]

    return (
        total_loss / batch_num,
        total_miou / batch_num,
        total_mpa / batch_num,
        total_dice / batch_num,
        total_recall / batch_num,
        total_precision / batch_num,
        total_fg_iou / batch_num,
        total_bg_iou / batch_num,
        total_fpr / batch_num,
        total_fnr / batch_num,
        worst_samples
    )


# ---------------------- 主训练入口 ----------------------
if __name__ == "__main__":
    train_dataset = PeonyDataset(TRAIN_IMG_DIR, TRAIN_MASK_DIR, train_transform, green_augment=False)
    val_dataset = PeonyDataset(VAL_IMG_DIR, VAL_MASK_DIR, val_transform, green_augment=False)

    loader_kwargs = dict(
        batch_size=BATCH_SIZE,
        num_workers=NUM_WORKERS,
        pin_memory=PIN_MEMORY,
        persistent_workers=False
    )
    train_loader = DataLoader(train_dataset, shuffle=True, drop_last=True, **loader_kwargs)
    val_loader = DataLoader(val_dataset, shuffle=False, **loader_kwargs)

    # 模型初始化
    model = deeplabv3plus_xception(num_classes=NUM_CLASSES, output_stride=8, pretrained_backbone=False)
    model = model.to(DEVICE)

    # 延续第六代打下的 2.5 黄金防虚检加权比例天平
    loss_ce = nn.CrossEntropyLoss(weight=torch.tensor([1.15, 2.5]).to(DEVICE))
    loss_dice = DiceLoss().to(DEVICE)

    backbone_params = list(model.backbone.parameters())
    decoder_params = [p for n, p in model.named_parameters() if "backbone" not in n]
    optimizer = torch.optim.AdamW([
        {"params": backbone_params, "lr": LR_BACKBONE},
        {"params": decoder_params, "lr": LR_DECODER}
    ], weight_decay=WEIGHT_DECAY)

    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=EPOCHS, eta_min=1e-6)
    scaler = torch.amp.GradScaler(device="cuda", enabled=USE_AMP)

    start_epoch = 1
    best_miou = 0.0
    no_improve_count = 0

    # 智能跨阶段加载核心：
    if not FORCE_NEW_TRAIN and os.path.exists(RESUME_CHECKPOINT) and (
            torch.load(RESUME_CHECKPOINT, map_location="cpu")["optimizer_state"]["param_groups"][0]["lr"] < 1e-5):
        print("检测到当前阶段的高清大图断点文件，执行接续训练加载...")
        checkpoint = torch.load(RESUME_CHECKPOINT, map_location=DEVICE)
        model.load_state_dict(checkpoint["model_state"])
        optimizer.load_state_dict(checkpoint["optimizer_state"])
        scheduler.load_state_dict(checkpoint["scheduler_state"])
        scaler.load_state_dict(checkpoint["scaler_state"])
        start_epoch = checkpoint["epoch"] + 1
        best_miou = checkpoint["best_miou"]
        no_improve_count = checkpoint["no_improve_count"]
        print(f"续训成功，起始Epoch: {start_epoch}, 当前最优mIoU={best_miou:.4f}")

    elif not FORCE_NEW_TRAIN and os.path.exists(BEST_WEIGHT_PATH):
        print(" 未检测到大图半途断点，但成功拦截上一阶段小图的最优权重 best_model.pth！")
        print("正式解包权重并载入模型，全新激活【720x960 高清大图突击细节精调阶段】...")
        model.load_state_dict(torch.load(BEST_WEIGHT_PATH, map_location=DEVICE))
        start_epoch = 1
        best_miou = 0.0
        no_improve_count = 0
    else:
        print("全新大图精调启动，从第 1 轮冷启动，目标分辨率：720x960，批量大小：1")

    if start_epoch == 1 or not os.path.exists(LOG_CSV_PATH):
        with open(LOG_CSV_PATH, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "epoch", "train_loss", "val_loss", "miou", "mpa", "dice",
                "recall", "precision", "fg_iou", "bg_iou", "fpr", "fnr"
            ])

    # 训练循环
    for epoch in range(start_epoch, EPOCHS + 1):
        print(f"\n===== Epoch {epoch}/{EPOCHS} =====")
        train_loss = train_one_epoch(model, train_loader, loss_ce, loss_dice, optimizer, scaler, epoch)
        (val_loss, val_miou, val_mpa, val_dice, val_recall, val_precision,
         val_fg_iou, val_bg_iou, val_fpr, val_fnr, worst_samples) = val_one_epoch(
            model, val_loader, loss_ce, loss_dice, epoch, val_dataset
        )

        scheduler.step()

        print(f"Train Loss: {train_loss:.4f} | Val Loss: {val_loss:.4f}")
        print(f"Val mIoU: {val_miou:.4f} | MPA: {val_mpa:.4f} | Dice: {val_dice:.4f}")
        print(f"Recall: {val_recall:.4f} | Precision: {val_precision:.4f}")
        print(f"前景IoU: {val_fg_iou:.4f} | 背景IoU: {val_bg_iou:.4f}")

        if ENABLE_ERROR_ANALYSIS:
            print(f"虚检率(FPR): {val_fpr:.4f} | 漏检率(FNR): {val_fnr:.4f}")
            if val_fpr > val_fnr:
                print("误差诊断：当前核心瓶颈为【虚检过多】，大量背景/杂草被误判为芍药，优先提升Precision")
            else:
                print("误差诊断：当前核心瓶颈为【漏检过多】，大量芍药未被识别，优先提升Recall")

        if SAVE_WORST_SAMPLES:
            print(f"本轮最差{WORST_SAMPLE_NUM}张验证样本代表：")
            for name, iou, rec, prec in worst_samples:
                print(f"  {name}: mIoU={iou:.4f}, Recall={rec:.4f}, Precision={prec:.4f}")

        with open(LOG_CSV_PATH, "a", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                epoch, round(train_loss, 4), round(val_loss, 4),
                round(val_miou, 4), round(val_mpa, 4), round(val_dice, 4),
                round(val_recall, 4), round(val_precision, 4),
                round(val_fg_iou, 4), round(val_bg_iou, 4),
                round(val_fpr, 4), round(val_fnr, 4)
            ])

        if val_miou > best_miou:
            best_miou = val_miou
            no_improve_count = 0
            torch.save(model.state_dict(), BEST_WEIGHT_PATH)
            print(f"保存最优大图微调模型，当前大图阶段最佳mIoU={best_miou:.4f}")
        else:
            no_improve_count += 1
            print(f"mIoU未上涨，连续{no_improve_count}轮")
            if no_improve_count >= EARLY_STOP_PATIENCE:
                print("触发精调阶段早停，大图细节榨取结束")
                break

        torch.save({
            "epoch": epoch,
            "model_state": model.state_dict(),
            "optimizer_state": optimizer.state_dict(),
            "scheduler_state": scheduler.state_dict(),
            "scaler_state": scaler.state_dict(),
            "best_miou": best_miou,
            "no_improve_count": no_improve_count
        }, RESUME_CHECKPOINT)

    print(f"\n大图总攻完成，微调最优mIoU={best_miou:.4f}，最终实车级权重已完美覆盖至 best_model.pth")