import os
import shutil
import random

# =====================================================================
# 🛠️ 路径配置中心（直接填入你电脑上的真实物理路径）
# =====================================================================
# 1. 存放原始 .jpg 和 .json 的源文件夹绝对路径
SOURCE_DIR = r"D:\JetBrains\avi_project\caijian\images"  # 👈 改成你的原始数据文件夹

# 2. 存放 images 图片的物理目录
TRAIN_IMG_DIR = r"D:\JetBrains\chucao_prj\model_data\train\images"
VAL_IMG_DIR = r"D:\JetBrains\chucao_prj\model_data\val\images"
TEST_IMG_DIR = r"D:\JetBrains\chucao_prj\model_data\test\images"

# 3. 存放 masks 真值图的物理目录（本次运行将对其进行只抹除清空处理）
TRAIN_MASK_DIR = r"D:\JetBrains\chucao_prj\model_data\train\masks"
VAL_MASK_DIR = r"D:\JetBrains\chucao_prj\model_data\val\masks"
TEST_MASK_DIR = r"D:\JetBrains\chucao_prj\model_data\test\masks"


def clean_folder_contents(folder_path):
    """
    🧹 工业级物理清空：只删除文件夹内部的所有文件，保留文件夹本身
    """
    if not os.path.exists(folder_path):
        os.makedirs(folder_path, exist_ok=True)
        return

    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print(f"⚠️ 清除 {file_path} 失败: {e}")


def split_peony_dataset(source_dir,
                        train_img_dir, val_img_dir, test_img_dir,
                        train_mask_dir, val_mask_dir, test_mask_dir,
                        seed=42):
    # 🚨【核心新功能】：重新运行时，强行一键清空旧的 Images 与 Masks 目录
    print("🧹 正在自动清空原先的 train/val/test 下的所有 images 与 masks 文件...")
    clean_targets = [
        ("训练集图片", train_img_dir),
        ("验证集图片", val_img_dir),
        ("测试集图片", test_img_dir),
        ("训练集真值", train_mask_dir),
        ("验证集真值", val_mask_dir),
        ("测试集真值", test_mask_dir),
    ]
    for label, path in clean_targets:
        clean_folder_contents(path)
        print(f"   └─ 已物理清空: {label} -> {path}")
    print("✅ 所有旧图片与旧真值图已彻底干掉，恢复绝对纯净状态！\n")

    # 寻找源文件夹里所有的 .jpg 及其对应的同名 .json
    all_files = os.listdir(source_dir)
    valid_pairs = []

    for f in all_files:
        if f.lower().endswith(".jpg"):
            base_name = os.path.splitext(f)[0]
            json_name = base_name + ".json"
            # 校验同名 json 是否物理存在
            if os.path.exists(os.path.join(source_dir, json_name)):
                valid_pairs.append(base_name)

    total_count = len(valid_pairs)
    print(f"📦 源文件夹中共找到 {total_count} 对有效的 [.jpg + .json] 文件！")

    if total_count == 0:
        print("❌ 未找到成对的 jpg 和 json 文件，请检查 SOURCE_DIR 路径！")
        return

    # 固定随机种子并随机打乱
    random.seed(seed)
    random.shuffle(valid_pairs)

    # 按照 6:2:2 严格取整计算数量
    n_train = int(total_count * 0.6)
    n_val = int(total_count * 0.2)
    n_test = total_count - n_train - n_val  # 余数全归 test，保证 100% 精准无遗漏

    train_pairs = valid_pairs[:n_train]
    val_pairs = valid_pairs[n_train:n_train + n_val]
    test_pairs = valid_pairs[n_train + n_val:]

    def copy_file_pairs(pair_list, target_folder, stage_label):
        for base_name in pair_list:
            jpg_src = os.path.join(source_dir, base_name + ".jpg")
            json_src = os.path.join(source_dir, base_name + ".json")

            shutil.copy(jpg_src, os.path.join(target_folder, base_name + ".jpg"))
            shutil.copy(json_src, os.path.join(target_folder, base_name + ".json"))
        print(f"✅ [{stage_label}] 成功分发 {len(pair_list)} 对新文件 -> {target_folder}")

    # 执行物理分发复制
    print("🚀 开始重新分发新数据...")
    copy_file_pairs(train_pairs, train_img_dir, f"训练集 Train (60%, 共{n_train}对)")
    copy_file_pairs(val_pairs, val_img_dir, f"验证集 Val   (20%, 共{n_val}对)")
    copy_file_pairs(test_pairs, test_img_dir, f"测试集 Test  (20%, 共{n_test}对)")

    print(f"\n🎉 重新洗牌与 6:2:2 重新划分圆满成功！总计分配 {total_count} 对文件。")


if __name__ == "__main__":
    split_peony_dataset(
        SOURCE_DIR,
        TRAIN_IMG_DIR, VAL_IMG_DIR, TEST_IMG_DIR,
        TRAIN_MASK_DIR, VAL_MASK_DIR, TEST_MASK_DIR
    )