"""Peony-field post-processing pipeline: wall-building, weed filtering, dual-wall centerline extraction.

Philosophy: "Build walls, find the road." 
We do NOT segment individual plants. Instead, we treat each peony row as a continuous
vertical barrier, then navigate the gap between the left and right walls.

Pipeline:
  mask_pred (0/1, 960x720) -> IPM (optional) -> large-kernel close -> 
  area/aspect filter -> extract left/right walls -> least-squares centerline.
"""

import cv2
import numpy as np

import sys

# Windows console here is cp936, which cannot encode the emoji used in the
# messages below.  A UnicodeEncodeError halfway through a 350-image batch is
# far worse than one dropped glyph, so replace unencodable characters instead
# of crashing.  (Observed live 2026-09-21 on tools/split_dataset.py.)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')
    sys.stderr.reconfigure(errors='replace')

# ---------------------------------------------------------------
# Configurable parameters
# ---------------------------------------------------------------
# Morphology kernel for closing: vertical rectangle to connect peony fragments
KERNEL_CLOSE = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 15))

# Connected-component filters
MIN_WALL_AREA = 500           # pixels: discard anything smaller
MIN_WALL_ASPECT_RATIO = 1.5   # height/width: peony rows are tall, weeds are squat

# Lookahead row (Y coordinate) for computing centerline deviation.
# 540 = roughly 3/4 down the image, where the tractor will actually cross.
LOOKAHEAD_Y = 540

# Image dimensions
IMG_W, IMG_H = 960, 720
MID_X = IMG_W // 2  # 480


# ---------------------------------------------------------------
# Step 1: Build walls from raw mask
# ---------------------------------------------------------------
def build_walls(mask, kernel=None):
    """Close small gaps in the peony row mask to form continuous walls.
    
    Args:
        mask: np.uint8 binary mask (0 or 1), shape (H, W).
        kernel: structuring element. Defaults to (5, 15) vertical rect.
    Returns:
        np.uint8 mask with gaps closed.
    """
    if kernel is None:
        kernel = KERNEL_CLOSE

    mask_u8 = (mask * 255).astype(np.uint8)
    closed = cv2.morphologyEx(mask_u8, cv2.MORPH_CLOSE, kernel)
    return (closed > 127).astype(np.uint8)


# ---------------------------------------------------------------
# Step 2: Filter noise: area + aspect ratio
# ---------------------------------------------------------------
def filter_noise(mask, min_area=MIN_WALL_AREA, min_aspect=MIN_WALL_ASPECT_RATIO):
    """Remove small blobs and squat-shaped regions (weeds).
    
    Keeps only connected components that are:
      - large enough (area >= min_area)
      - vertically elongated (height/width >= min_aspect)
    
    Returns:
        Cleaned binary mask.
    """
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)

    clean = np.zeros_like(mask)
    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        w = stats[i, cv2.CC_STAT_WIDTH]
        h = stats[i, cv2.CC_STAT_HEIGHT]
        aspect = h / max(w, 1)

        if area >= min_area and aspect >= min_aspect:
            clean[labels == i] = 1

    return clean


# ---------------------------------------------------------------
# Step 3: Extract left and right walls
# ---------------------------------------------------------------
def extract_dual_walls(mask):
    """Split the mask into left and right walls at the image midline.
    
    Each side keeps only the connected component nearest to the center.
    
    Returns:
        (left_wall, right_wall): two binary masks, each containing one wall.
    """
    left_mask = mask.copy()
    left_mask[:, MID_X:] = 0

    right_mask = mask.copy()
    right_mask[:, :MID_X] = 0

    return _pick_nearest_component(left_mask), _pick_nearest_component(right_mask)


def _pick_nearest_component(side_mask):
    """From a side mask, keep only the component closest to the midline."""
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
        side_mask, connectivity=8)

    if num_labels <= 1:
        return np.zeros_like(side_mask)

    best_label, best_dist = None, float("inf")
    for i in range(1, num_labels):
        cx = centroids[i, 0]
        dist = abs(cx - MID_X)
        if dist < best_dist:
            best_dist = dist
            best_label = i

    result = np.zeros_like(side_mask)
    if best_label is not None:
        result[labels == best_label] = 1
    return result


# ---------------------------------------------------------------
# Step 4: Least-squares centerline fitting
# ---------------------------------------------------------------
def fit_centerline_lsq(left_wall, right_wall, lookahead_y=LOOKAHEAD_Y):
    """Fit straight lines to both walls via least squares, then compute the centerline.
    
    Fits x = a*y + b for each wall (treating y as the independent variable
    since walls are roughly vertical).
    
    Args:
        left_wall, right_wall: binary masks (one wall each).
        lookahead_y: row at which to compute the deviation.
    
    Returns:
        dict with:
          - center_x:      float, centerline x at lookahead_y (pixels)
          - lateral_error: float, deviation from midline in pixels (+ = right of center)
          - left_x:        float or None
          - right_x:       float or None
          - left_slope, right_slope: fitted slopes
          - status:        "dual", "left_only", "right_only", "none"
    """
    result = {
        "center_x": None,
        "lateral_error": 0.0,
        "left_x": None,
        "right_x": None,
        "left_slope": None,
        "right_slope": None,
        "status": "none",
    }

    left_yx = np.argwhere(left_wall > 0)   # [[y, x], ...]
    right_yx = np.argwhere(right_wall > 0)

    have_left = len(left_yx) >= 30
    have_right = len(right_yx) >= 30

    if not have_left and not have_right:
        return result

    # --- Fit left wall: x = a_L * y + b_L ---
    if have_left:
        y_l = left_yx[:, 0].astype(np.float64)
        x_l = left_yx[:, 1].astype(np.float64)
        A_l = np.vstack([y_l, np.ones_like(y_l)]).T
        a_l, b_l = np.linalg.lstsq(A_l, x_l, rcond=None)[0]
        result["left_slope"] = a_l
        result["left_x"] = float(a_l * lookahead_y + b_l)

    # --- Fit right wall ---
    if have_right:
        y_r = right_yx[:, 0].astype(np.float64)
        x_r = right_yx[:, 1].astype(np.float64)
        A_r = np.vstack([y_r, np.ones_like(y_r)]).T
        a_r, b_r = np.linalg.lstsq(A_r, x_r, rcond=None)[0]
        result["right_slope"] = a_r
        result["right_x"] = float(a_r * lookahead_y + b_r)

    # --- Compute centerline ---
    if have_left and have_right:
        result["status"] = "dual"
        result["center_x"] = (result["left_x"] + result["right_x"]) / 2.0
    elif have_left:
        result["status"] = "left_only"
        # Degenerate: estimate center from left wall + typical row spacing
        result["center_x"] = result["left_x"] + 200  # rough offset, tune in field
    elif have_right:
        result["status"] = "right_only"
        result["center_x"] = result["right_x"] - 200

    result["lateral_error"] = result["center_x"] - MID_X
    return result


# ---------------------------------------------------------------
# Top-level pipeline
# ---------------------------------------------------------------
def peony_postprocess(raw_mask, lookahead_y=LOOKAHEAD_Y):
    """End-to-end post-processing pipeline for peony row navigation.
    
    Args:
        raw_mask: np.uint8 binary mask (0 or 1), shape (H, W) from model argmax.
        lookahead_y: row for centerline evaluation.
    
    Returns:
        (nav_result, left_wall, right_wall) where nav_result is the dict from
        fit_centerline_lsq and left_wall/right_wall are the filtered wall masks.
    """
    # 1. Build walls (close gaps)
    wall_mask = build_walls(raw_mask)

    # 2. Filter noise (area + aspect)
    clean_mask = filter_noise(wall_mask)

    # 3. Extract left and right walls
    left_wall, right_wall = extract_dual_walls(clean_mask)

    # 4. Fit centerline
    nav = fit_centerline_lsq(left_wall, right_wall, lookahead_y)

    return nav, left_wall, right_wall


def _fit_inner_edge(wall_mask, side, lookahead_y, tol_px=12.0):
    """按墙“靠草带那一侧的边”拟合直线 x = a*y + b（11-21，台账 Pc-24）。

    为什么不再用“逐行取中位 + 行内跨度>24 px 就丢行”：真实 IPM 墙有
    ~190 像素宽（25 张测试图中位），逐行跨度必然远超 24 px ⇒ 每一行都被判
    “多结构”丢掉 ⇒ 旧实现恒退化。墙的内侧边缘才是车要走的走廊边界，
    而且它不随墙“胖瘦”移动：一侧墙被杂草撑宽时，普通中点会被重心拉走，
    内边缘不会。

    side='L' 取每行最大 x（左墙靠草带的一侧）；side='R' 取每行最小 x。
    每行只有一票，再做剔野值的直线拟合（孤立杂草凸起是少数行，会被剔掉）。
    行数不足 30 返回 None——调用方据此原样退回普通中点。
    """
    yx = np.argwhere(wall_mask > 0)
    if len(yx) == 0:
        return None
    rows = {}
    for y, x in yx:
        rows.setdefault(int(y), []).append(int(x))
    if len(rows) < 30:
        return None
    ry = np.array(list(rows.keys()), dtype=np.float64)
    if side == 'L':
        rx = np.array([max(v) for v in rows.values()], dtype=np.float64)
    elif side == 'R':
        rx = np.array([min(v) for v in rows.values()], dtype=np.float64)
    else:
        raise ValueError("side must be 'L' or 'R'")
    A = np.vstack([ry, np.ones_like(ry)]).T
    a, b = np.linalg.lstsq(A, rx, rcond=None)[0]
    inlier = np.ones(len(ry), dtype=bool)
    for _ in range(3):
        resid = rx - (a * ry + b)
        inlier = np.abs(resid) < tol_px
        if inlier.sum() < 30:
            break
        a, b = np.linalg.lstsq(A[inlier], rx[inlier], rcond=None)[0]
    resid = rx - (a * ry + b)
    inlier = np.abs(resid) < tol_px
    if inlier.sum() == 0:
        return None
    rmse = float(np.sqrt(np.mean(resid[inlier] ** 2)))
    return a, b, float(inlier.mean()), rmse


def fit_centerline_lsq_weighted(left_wall, right_wall, lookahead_y=LOOKAHEAD_Y,
                                tol_px=12.0):
    """自适应双墙中心线：两墙各拟合**内侧边缘**，按贴合质量加权混合。

    11-21 之前用的是“逐行中位”，在真实厚墙上恒退化（台账 Pc-24：
    25 张测试图里 18 张左右墙位置被写成 0）；现在改成内侧边缘，
    权重逻辑不变：两边内点率都 >= 0.5 时取严格中点（不引入噪声），
    一边明显变差时按 内点率/(1+误差) 加权，且权重限制在 ±0.25 以内。

    **退化时原样退回普通中点**：普通拟合的 `center_x`/`left_x`/`right_x`
    一个都不改（旧实现先把左右位置覆盖成 0.0 再提前返回——那是 Pc-24 里
    顺带修掉的副作用）。

    Returns the fit_centerline_lsq dict plus "w_left"/"w_right"/"inlier_l"/"inlier_r".
    """
    result = fit_centerline_lsq(left_wall, right_wall, lookahead_y)
    if result["status"] != "dual":
        return result

    fl = _fit_inner_edge(left_wall, 'L', lookahead_y, tol_px)
    fr = _fit_inner_edge(right_wall, 'R', lookahead_y, tol_px)
    if fl is None or fr is None:
        return result                     # 保持普通中点，绝不改写左右位置

    a_l, b_l, i_l, rmse_l = fl
    a_r, b_r, i_r, rmse_r = fr
    result["left_x"] = float(a_l * lookahead_y + b_l)
    result["right_x"] = float(a_r * lookahead_y + b_r)
    result["left_slope"], result["right_slope"] = a_l, a_r

    # Weighting activates ONLY when one wall is critically degraded
    # (inlier ratio < 0.5).  Otherwise the trimmed edges are both accurate
    # and the exact midpoint is optimal — zero added noise.
    LOW = 0.5
    if i_l >= LOW and i_r >= LOW:
        w_l = 0.5
    else:
        q_l = i_l / (1.0 + rmse_l)
        q_r = i_r / (1.0 + rmse_r)
        if q_l + q_r <= 0.0:
            return result
        w_raw = q_l / (q_l + q_r)
        w_l = 0.5 + 0.25 * (2.0 * w_raw - 1.0)   # bounded ±0.25
    center = w_l * result["left_x"] + (1 - w_l) * result["right_x"]
    result["center_x"] = float(center)
    result["lateral_error"] = result["center_x"] - MID_X
    result["w_left"] = float(w_l)
    result["w_right"] = float(1 - w_l)
    result["inlier_l"], result["inlier_r"] = i_l, i_r
    return result
