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
