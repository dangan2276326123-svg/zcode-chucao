import os

import cv2

import numpy as np

import csv

import warnings

import torch

import torch.nn as nn

import torch.nn.functional as F

from torch.utils.data import Dataset, DataLoader

import random



# 最高规格警告拦截招牌，彻底还终端一片清静

warnings.filterwarnings("ignore")

os.environ["ALBUMENTATIONS_DISABLE_VERSION_CHECK"] = "1"

os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "max_split_size_mb:64,garbage_collection_threshold:0.8"



# 【学术级绘图核心】：挂载非交互式后端，防止工控机或服务器闪退

import matplotlib



matplotlib.use('Agg')

import matplotlib.pyplot as plt



# 纯英文化标签，完美杜绝 Glyph 黄色乱码弹窗，自带顶级论文高级感

plt.rcParams['font.sans-serif'] = ['Arial', 'sans-serif']

plt.rcParams['axes.unicode_minus'] = False



# =====================================================================

# 【主控面板】：切换此开关，全套流水线超参数将自动物理自适应，绝无冲突！

# =====================================================================

# 可选模式：

#   1. "train_coarse" : 阶段一，480x360 小图暴力打桩，开启自适应 BN，

#   2. "train_fine"   : 阶段二（960x720 大图细节总攻，连续承接指标，锁定并借调 BN 成果），

#   3. "test"         : 阶段三（独立外部测试集 6:2:2 规范化出厂全量评测与大图高精抠图独占落盘），

MODE = "train_coarse"



# ===================== 基础路径与环境配置 =====================

import albumentations as A

from albumentations.pytorch import ToTensorV2

from tqdm import tqdm

import ssl



ssl._create_default_https_context = ssl._create_unverified_context



# 引入工业级轻量化极速流 MobileNetV2 语义分割底盘

from network.modeling import deeplabv3plus_mobilenet



DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

NUM_CLASSES = 2



# 补齐全局共享优化器、损失函数与样本记录超参数

WEIGHT_DECAY = 3e-4

GRAD_CLIP_NORM = 1.0

USE_AMP = True

LOSS_CE_WEIGHT = 0.55

LOSS_DICE_WEIGHT = 0.45

WORST_SAMPLE_NUM = 3



# 学术级 6:2:2 数据集物理路径配置中心

TRAIN_IMG_DIR = r"D:/JetBrains/chucao_prj/model_data/train/images"

TRAIN_MASK_DIR = r"D:/JetBrains/chucao_prj/model_data/train/masks"

VAL_IMG_DIR = r"D:/JetBrains/chucao_prj/model_data/val/images"

VAL_MASK_DIR = r"D:/JetBrains/chucao_prj/model_data/val/masks"

TEST_IMG_DIR = r"D:/JetBrains/chucao_prj/model_data/test/images"

TEST_MASK_DIR = r"D:/JetBrains/chucao_prj/model_data/test/masks"



# 权重存盘路径

SAVE_WEIGHT_DIR = r"D:/JetBrains/chucao_prj/model_data/weights"

RESUME_CHECKPOINT = os.path.join(SAVE_WEIGHT_DIR, "latest_checkpoint.pth")

BEST_WEIGHT_PATH = os.path.join(SAVE_WEIGHT_DIR, "best_model.pth")



# 结果可视化输出根目录

RESULTS_DIR = r"./results"

TEST_VISUALS_DIR = os.path.join(RESULTS_DIR, "test_visuals")

LOG_CSV_PATH = "train_metric_log.csv"



os.makedirs(SAVE_WEIGHT_DIR, exist_ok=True)

os.makedirs(TEST_VISUALS_DIR, exist_ok=True)





# 【新增】：工业级全局防震荡种子流控锁，强行摁住随机扰动

def seed_everything(seed=42):

    random.seed(seed)

    os.environ['PYTHONHASHSEED'] = str(seed)

    np.random.seed(seed)

    torch.manual_seed(seed)

    torch.cuda.manual_seed(seed)

    torch.backends.cudnn.deterministic = True

    torch.backends.cudnn.benchmark = False





# =====================================================================

# 【自适应引擎控制中心】：根据 MODE 自动重组所有底层硬件与算法天平

# =====================================================================

if MODE == "train_coarse":

    IMG_WIDTH, IMG_HEIGHT = 480, 360

    # 【荣耀复位】：严格执行你原本打出 0.7720 神级上限的环境参数

    BATCH_SIZE = 4

    ACCUM_STEPS = 2

    EPOCHS = 100

    EARLY_STOP_PATIENCE = 5

    FORCE_NEW_TRAIN = True

    LR_BACKBONE = 3e-5

    LR_DECODER = 1e-4

    WEIGHT_CE = torch.tensor([1.15, 2.85])  # 你之前跑出 0.73 mIoU 的黄金准星

    NUM_WORKERS = 2



elif MODE == "train_fine":

    IMG_WIDTH, IMG_HEIGHT = 960, 720

    BATCH_SIZE = 1

    ACCUM_STEPS = 8

    EPOCHS = 140

    EARLY_STOP_PATIENCE = 5

    FORCE_NEW_TRAIN = False

    LR_BACKBONE = 5e-6

    LR_DECODER = 2e-5

    WEIGHT_CE = torch.tensor([1.0, 2.75])    # 精调接棒继续冲

    NUM_WORKERS = 0



elif MODE == "test":

    IMG_WIDTH, IMG_HEIGHT = 960, 720

    BATCH_SIZE = 1

    ACCUM_STEPS = 1

    NUM_WORKERS = 0

    EARLY_STOP_PATIENCE = 5





# ---------------------- 数据流控闭环 ----------------------

class PeonyDataset(Dataset):

    def __init__(self, img_dir, mask_dir, transform=None):

        self.img_dir = img_dir

        self.mask_dir = mask_dir

        self.transform = transform

        self.img_list = sorted([f for f in os.listdir(img_dir) if f.endswith(("jpg", "png"))])



    def __len__(self):

        return len(self.img_list)



    def __getitem__(self, idx):

        img_name = self.img_list[idx]

        img_path = os.path.join(self.img_dir, img_name)

        mask_path = os.path.join(self.mask_dir, img_name.replace(".jpg", ".png"))



        img = cv2.imread(img_path, cv2.IMREAD_COLOR)

        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)



        mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)

        mask = np.where(mask == 255, 1, 0).astype(np.int64)



        if self.transform:

            aug_result = self.transform(image=img, mask=mask)

            img = aug_result["image"]

            mask = aug_result["mask"]



        return img, mask.long()





# ---------------------- 数据增强流水线 ----------------------

train_transform = A.Compose([

    A.Resize(height=IMG_HEIGHT, width=IMG_WIDTH, interpolation=cv2.INTER_LINEAR),

    A.HueSaturationValue(hue_shift_limit=10, sat_shift_limit=(-35, 5), val_shift_limit=10, p=0.4),

    A.CLAHE(clip_limit=2.0, tile_grid_size=(8, 8), p=0.5),

    A.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.3, hue=0.1, p=0.7),

    A.RandomBrightnessContrast(brightness_limit=0.15, contrast_limit=0.15, p=0.4),

    A.GaussianBlur(blur_limit=(1, 3), p=0.2),

    A.HorizontalFlip(p=0.5),

    A.VerticalFlip(p=0.2),

    A.Affine(translate_percent={"x": (-0.08, 0.08), "y": (-0.08, 0.08)}, scale=(0.9, 1.1), rotate=(-12, 12), p=0.4),

    A.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),

    ToTensorV2()

])



val_transform = A.Compose([

    A.Resize(height=IMG_HEIGHT, width=IMG_WIDTH, interpolation=cv2.INTER_LINEAR),

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





# ---------------------- 指标计算核 ----------------------

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





def set_bn_eval(module):

    if isinstance(module, nn.BatchNorm2d):

        module.eval()





# ---------------------- 核心公共渲染大拼接引擎（MODE='test' 时独占） ----------------------

def save_academic_comparison_strip(img, mask, out_logits, batch_idx, save_root_dir):

    pred_mask = torch.argmax(out_logits, dim=1).squeeze(0).cpu().numpy().astype(np.uint8)

    img_np = img[0].cpu().numpy().transpose(1, 2, 0)

    img_np = (img_np * np.array([0.229, 0.224, 0.225]) + np.array([0.485, 0.456, 0.406])) * 255.0

    img_bgr = cv2.cvtColor(img_np.astype(np.uint8), cv2.COLOR_RGB2BGR)



    mask_np = mask[0].cpu().numpy().astype(np.uint8)

    mask_bgr = np.stack([mask_np * 0, mask_np * 255, mask_np * 0], axis=-1)



    pred_bgr = np.stack([pred_mask * 100, pred_mask * 255, pred_mask * 255], axis=-1)



    comparison_strip = np.hstack([img_bgr, mask_bgr, pred_bgr])

    cv2.imwrite(os.path.join(save_root_dir, f"test_id_{batch_idx:04d}.png"), comparison_strip)





# ---------------------- 自动重绘指标全量合一三视图线图引擎（包含全周期 FPR 与 FNR 独立显化盘） ----------------------

def generate_metrics_trend_chart(csv_log_path, output_chart_path):

    if not os.path.exists(csv_log_path): return

    epochs, train_losses, val_losses, mious, recalls, precisions, fprs, fnrs = [], [], [], [], [], [], [], []

    with open(csv_log_path, "r", encoding="utf-8") as f:

        reader = csv.reader(f)

        next(reader)

        for row in reader:

            if not row: continue

            epochs.append(int(row[0]))

            train_losses.append(float(row[1]))

            val_losses.append(float(row[2]))

            mious.append(float(row[3]))

            recalls.append(float(row[6]))

            precisions.append(float(row[7]))

            fprs.append(float(row[10]))  # 满血找回虚检率一列

            fnrs.append(float(row[11]))  # 满血找回漏检率一列

    if not epochs: return



    plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')

    # 【升级为三视图独立大盘】：画布横向舒展至 20x6，三图并排排列

    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(20, 6))



    # 瑙嗗浘1锛歀oss 鏀舵暃鏇茬嚎

    ax1.plot(epochs, train_losses, label='Train Loss', color='#E64B35', linewidth=2, linestyle='--')

    ax1.plot(epochs, val_losses, label='Val Loss', color='#4DBBD5', linewidth=2)

    ax1.set_title('Combined Loss Convergence Curve', fontsize=13, fontweight='bold', pad=10)

    ax1.set_xlabel('Total Cumulative Epochs');

    ax1.set_ylabel('Loss Value');

    ax1.legend(frameon=True, facecolor='white')



    # 瑙嗗浘2锛氭牳蹇冧笁澶т欢 (mIoU, Precision, Recall)

    ax2.plot(epochs, mious, label='Mean IoU (mIoU)', color='#00A087', linewidth=2.5)

    ax2.plot(epochs, precisions, label='Precision', color='#3C5488', linewidth=1.8, alpha=0.8)

    ax2.plot(epochs, recalls, label='Recall', color='#F39B7F', linewidth=1.8, alpha=0.8)

    ax2.set_title('Combined Evaluation Metrics Growth Trend', fontsize=13, fontweight='bold', pad=10)

    ax2.set_xlabel('Total Cumulative Epochs');

    ax2.set_ylabel('Score Ratio');

    ax2.set_ylim(0.0, 1.05)

    ax2.legend(frameon=True, facecolor='white', loc='lower right')



    # 视图3（专属硬核独占）：误差率变化曲线（虚检 FPR 与 漏检 FNR 专场，让你一眼看清降噪全周期）

    ax3.plot(epochs, fprs, label='False Positive Rate (FPR)', color='#91D1C2', linewidth=2)

    ax3.plot(epochs, fnrs, label='False Negative Rate (FNR)', color='#8491B4', linewidth=2)

    ax3.set_title('Combined Error Rates Curve (FPR & FNR)', fontsize=13, fontweight='bold', pad=10)

    ax3.set_xlabel('Total Cumulative Epochs');

    ax3.set_ylabel('Error Ratio');

    ax3.set_ylim(0.0, 1.05)

    ax3.legend(frameon=True, facecolor='white', loc='upper right')



    plt.tight_layout()

    plt.savefig(output_chart_path, dpi=300, bbox_inches='tight')

    plt.close()





# ---------------------- 训练与验证流 ----------------------

def train_one_epoch(model, loader, ce_fn, dice_fn, opt, scaler, epoch):

    model.train()

    if MODE == "train_fine":

        model.apply(set_bn_eval)

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

        if (idx + 1) % ACCUM_STEPS == 0 or (idx + 1) == len(loader):

            scaler.unscale_(opt)

            nn.utils.clip_grad_norm_(model.parameters(), GRAD_CLIP_NORM)

            scaler.step(opt)

            scaler.update()

            opt.zero_grad()

        total_loss += loss.item() * ACCUM_STEPS

        bar.set_postfix(loss=f"{total_loss / (idx + 1):.4f}")

    return total_loss / len(loader)





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

            miou, mpa, dice_val, recall, precision, fg_iou, bg_iou, fpr, fnr = calculate_all_metrics(out, mask,

                                                                                                     NUM_CLASSES)

            total_miou += miou;

            total_mpa += mpa;

            total_dice += dice_val;

            total_recall += recall

            total_precision += precision;

            total_fg_iou += fg_iou;

            total_bg_iou += bg_iou;

            total_fpr += fpr;

            total_fnr += fnr



            for b_idx in range(img.size(0)):

                img_idx = idx * BATCH_SIZE + b_idx

                if img_idx < len(dataset.img_list):

                    sample_metrics.append((dataset.img_list[img_idx], miou, recall, precision))

            bar.set_postfix(loss=f"{total_loss / (idx + 1):.4f}", miou=f"{total_miou / (idx + 1):.4f}")

    worst_samples = sorted(sample_metrics, key=lambda x: x[1])[:WORST_SAMPLE_NUM]

    return (total_loss / batch_num, total_miou / batch_num, total_mpa / batch_num, total_dice / batch_num,

            total_recall / batch_num, total_precision / batch_num, total_fg_iou / batch_num, total_bg_iou / batch_num,

            total_fpr / batch_num, total_fnr / batch_num, worst_samples)





# ---------------------- 测试集出厂评测分支 ----------------------

def execute_independent_test_evaluation():

    print("\n=====================================================================")

    print("=== Starting independent test evaluation on Test Set ===")
    print("=====================================================================")

    test_dataset = PeonyDataset(TEST_IMG_DIR, TEST_MASK_DIR, val_transform)

    test_loader = DataLoader(test_dataset, batch_size=1, shuffle=False)



    model = deeplabv3plus_mobilenet(num_classes=NUM_CLASSES, output_stride=16, pretrained_backbone=False)

    if os.path.exists(BEST_WEIGHT_PATH):

        print("=== Starting independent test evaluation on Test Set ===")
        model.load_state_dict(torch.load(BEST_WEIGHT_PATH, map_location=DEVICE))

    else:

        print(f"Loading best model from {BEST_WEIGHT_PATH} for evaluation...")
        return

    model = model.to(DEVICE).eval()



    t_miou = t_mpa = t_dice = t_recall = t_precision = t_fg = t_bg = t_fpr = t_fnr = 0.0

    bar = tqdm(test_loader, desc="Testing Progress")



    with torch.no_grad():

        for idx, (img, mask) in enumerate(bar):

            img, mask = img.to(DEVICE), mask.to(DEVICE)

            out = model(img)

            miou, mpa, dice_v, rec, prec, fg, bg, fpr, fnr = calculate_all_metrics(out, mask, NUM_CLASSES)

            t_miou += miou;

            t_mpa += mpa;

            t_dice += dice_v;

            t_recall += rec;

            t_precision += prec

            t_fg += fg;

            t_bg += bg;

            t_fpr += fpr;

            t_fnr += fnr



            save_academic_comparison_strip(img, mask, out, idx, TEST_VISUALS_DIR)



    num = len(test_loader)
    print("\n=== Test Set Final Report ===")
    print(f"Test samples: {num}  |  Backbone: DeepLabV3+ (MobileNetV2)")
    print(f"Test mIoU: {t_miou / num:.4f}")
    print(f"Test Precision: {t_precision / num:.4f}")
    print(f"Test Recall:    {t_recall / num:.4f}")
    print(f"FG IoU: {val_fg_iou:.4f}     | BG IoU: {val_bg_iou:.4f}")
    print(f"FPR: {val_fpr:.4f}     | FNR: {val_fnr:.4f}")
    print(f"All test results saved to: {TEST_VISUALS_DIR}\n")




# ---------------------- 一体化脚本主程序入口 ----------------------

if __name__ == "__main__":

    # 【核心功能】：一上来立马锁定全局种子，消除随机扰动，拼死迎回当初的 0.77 状态！

    seed_everything(42)



    if MODE == "train_coarse":

        print("=== Starting independent test evaluation on Test Set ===")
    elif MODE == "train_fine":

        print("=== Starting independent test evaluation on Test Set ===")
    elif MODE == "test":

        print("=== Starting independent test evaluation on Test Set ===")


    if MODE == "test":

        execute_independent_test_evaluation()

    else:

        train_dataset = PeonyDataset(TRAIN_IMG_DIR, TRAIN_MASK_DIR, train_transform)

        val_dataset = PeonyDataset(VAL_IMG_DIR, VAL_MASK_DIR, val_transform)



        loader_kwargs = dict(batch_size=BATCH_SIZE, num_workers=NUM_WORKERS, pin_memory=False, persistent_workers=False)

        train_loader = DataLoader(train_dataset, shuffle=True, drop_last=True, **loader_kwargs)

        val_loader = DataLoader(val_dataset, shuffle=False, **loader_kwargs)



        model = deeplabv3plus_mobilenet(num_classes=NUM_CLASSES, output_stride=16, pretrained_backbone=True)

        model = model.to(DEVICE)



        loss_ce = nn.CrossEntropyLoss(weight=WEIGHT_CE.to(DEVICE))

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

        epoch_offset = 0

        best_miou = 0.0

        no_improve_count = 0



        if not FORCE_NEW_TRAIN and os.path.exists(RESUME_CHECKPOINT):

            print("\n=== Test Set Final Report ===")
            checkpoint = torch.load(RESUME_CHECKPOINT, map_location=DEVICE)

            model.load_state_dict(checkpoint["model_state"])

            optimizer.load_state_dict(checkpoint["optimizer_state"])

            scheduler.load_state_dict(checkpoint["scheduler_state"])

            scaler.load_state_dict(checkpoint["scaler_state"])

            start_epoch = checkpoint["epoch"] + 1

            best_miou = checkpoint["best_miou"]

            no_improve_count = checkpoint["no_improve_count"]

            epoch_offset = checkpoint.get("epoch_offset", 0)

        elif not FORCE_NEW_TRAIN and os.path.exists(BEST_WEIGHT_PATH):

            print(f"Loading best model from {BEST_WEIGHT_PATH} for evaluation...")
            print("=== Starting independent test evaluation on Test Set ===")
            model.load_state_dict(torch.load(BEST_WEIGHT_PATH, map_location=DEVICE))

            if os.path.exists(LOG_CSV_PATH):

                with open(LOG_CSV_PATH, "r", encoding="utf-8") as f:

                    rows = list(csv.reader(f))

                    if len(rows) > 1:

                        epoch_offset = int(rows[-1][0])

                        print(

                            f"[数据合流外挂] 检测到上一阶段已完成 {epoch_offset} 轮。大图精调将从第 {epoch_offset + 1} 轮顺延记录！")



        if MODE == "train_coarse" and (start_epoch == 1 or not os.path.exists(LOG_CSV_PATH)):

            with open(LOG_CSV_PATH, "w", encoding="utf-8", newline="") as f:

                writer = csv.writer(f)

                writer.writerow(

                    ["epoch", "train_loss", "val_loss", "miou", "mpa", "dice", "recall", "precision", "fg_iou",

                     "bg_iou", "fpr", "fnr"])



        # 涓诲惊鐜?

        for epoch in range(start_epoch, EPOCHS + 1):

            display_epoch = epoch_offset + epoch

            print(f"\n===== Epoch {display_epoch} (Inner Loop: {epoch}/{EPOCHS}) =====")



            train_loss = train_one_epoch(model, train_loader, loss_ce, loss_dice, optimizer, scaler, epoch)

            (val_loss, val_miou, val_mpa, val_dice, val_recall, val_precision, val_fg_iou, val_bg_iou, val_fpr, val_fnr,

             worst_samples) = val_one_epoch(model, val_loader, loss_ce, loss_dice, epoch, val_dataset)



            scheduler.step()



            with open(LOG_CSV_PATH, "a", encoding="utf-8", newline="") as f:

                writer = csv.writer(f)

                writer.writerow(

                    [display_epoch, f"{train_loss:.4f}", f"{val_loss:.4f}", f"{val_miou:.4f}", f"{val_mpa:.4f}",

                     f"{val_dice:.4f}", f"{val_recall:.4f}", f"{val_precision:.4f}", f"{val_fg_iou:.4f}",

                     f"{val_bg_iou:.4f}", f"{val_fpr:.4f}", f"{val_fnr:.4f}"])



            # 【彻底解除大碍】：每一轮结束直接重绘最新的【全周期学术级三视图指标图】，第一轮就能亲眼见证 FPR/FNR

            try:

                trend_chart_path = os.path.join(RESULTS_DIR, "training_metrics_trend.png")

                generate_metrics_trend_chart(LOG_CSV_PATH, trend_chart_path)

            except Exception as e:

                print("=== Starting independent test evaluation on Test Set ===")


            print(f"Train Loss: {train_loss:.4f} | Val Loss: {val_loss:.4f}")

            print(f"Val mIoU: {val_miou:.4f} | MPA: {val_mpa:.4f} | Dice: {val_dice:.4f}")

            print(f"Recall: {val_recall:.4f} | Precision: {val_precision:.4f}")

            print(f"FG IoU: {val_fg_iou:.4f}     | BG IoU: {val_bg_iou:.4f}")
            # 找回控制台高亮回显

            print(f"FPR: {val_fpr:.4f}     | FNR: {val_fnr:.4f}")


            if val_miou > best_miou:

                best_miou = val_miou

                no_improve_count = 0

                torch.save(model.state_dict(), BEST_WEIGHT_PATH)

                print("\n=== Test Set Final Report ===")
            else:

                no_improve_count += 1

                print(f"mIoU not improved, consecutive {no_improve_count} rounds")
                if no_improve_count >= EARLY_STOP_PATIENCE:

                    print("\n=== Test Set Final Report ===")
                    break



            torch.save({"epoch": epoch, "epoch_offset": epoch_offset, "model_state": model.state_dict(),

                        "optimizer_state": optimizer.state_dict(), "scheduler_state": scheduler.state_dict(),

                        "scaler_state": scaler.state_dict(), "best_miou": best_miou,

                        "no_improve_count": no_improve_count}, RESUME_CHECKPOINT)



        print("\n=== Test Set Final Report ===")
