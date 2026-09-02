"""Real-time peony-row navigation system -- onboard deployment.

Pipeline:
  1. Multi-threaded camera capture (1920x1080 raw -> 960x720 crop)
  2. DeepLabV3+ inference (MobileNetV2, 2-class: bg / peony-wall)
  3. IPM projection to bird's-eye view
  4. Wall-building morphology + noise filtering
  5. Dual-wall least-squares centerline fitting
  6. Visualization overlay with FPS / lateral error / heading

Press ESC to exit.
"""

import os
import sys
import cv2
import torch
import math
import time
import threading
import numpy as np

# Add project root to path so imports work from any working directory
_PROJ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from network.modeling import deeplabv3plus_mobilenet
from morph_process import peony_postprocess
from network.camera_calib import undistort, apply_ipm, ipm_mask_to_physical, IPM_SCALE_X

# ===================== Deployment parameters =====================
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
WEIGHT_PATH = os.path.join(_PROJ_ROOT, "model_data", "weights", "best_model.pth")

# Model fixed resolution
WIDTH, HEIGHT = 960, 720
MID_X = WIDTH // 2

# Preprocessing normalization (on GPU)
MEAN = torch.tensor([0.485, 0.456, 0.406], device=DEVICE).view(1, 3, 1, 1)
STD  = torch.tensor([0.229, 0.224, 0.225], device=DEVICE).view(1, 3, 1, 1)

# Camera config -- adjust for your actual setup
CAMERA_INDEX = 0
TOP_CUT, BOTTOM_CUT = 180, 180
LEFT_CUT, RIGHT_CUT = 480, 480

# Safety
LATERAL_SAFETY_LIMIT_M = 0.15   # 15 cm: trigger E-STOP if exceeded

# Visualization colors (BGR)
COLOR_LEFT_WALL  = (255, 100, 100)   # blue-ish
COLOR_RIGHT_WALL = (100, 255, 100)   # green-ish
COLOR_CENTERLINE = (0, 255, 255)     # yellow
COLOR_INFO       = (0, 255, 0)


# ===================== Multi-threaded camera stream =====================
class CameraStreamThread:
    def __init__(self, src=0):
        self.cap = cv2.VideoCapture(src, cv2.CAP_DSHOW)
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1920)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
        self.grabbed, self.frame = self.cap.read()
        self.started = False
        self.read_lock = threading.Lock()

    def start(self):
        self.started = True
        self.thread = threading.Thread(target=self.update, daemon=True)
        self.thread.start()
        return self

    def update(self):
        while self.started:
            grabbed, frame = self.cap.read()
            if grabbed:
                with self.read_lock:
                    self.grabbed, self.frame = grabbed, frame

    def read(self):
        with self.read_lock:
            return self.grabbed, self.frame.copy() if self.frame is not None else (False, None)

    def release(self):
        self.started = False
        if hasattr(self, 'thread'):
            self.thread.join(timeout=1.0)
        self.cap.release()


# ===================== Model loader =====================
def load_model():
    if not os.path.exists(WEIGHT_PATH):
        raise FileNotFoundError(f"Weight file not found: {WEIGHT_PATH}")
    model = deeplabv3plus_mobilenet(num_classes=2, output_stride=16,
                                     pretrained_backbone=False)
    model.load_state_dict(torch.load(WEIGHT_PATH, map_location=DEVICE))
    model.to(DEVICE).eval()
    return model


# ===================== Visualization helpers =====================
def draw_walls_overlay(display, left_wall, right_wall, alpha=0.35):
    """Semi-transparent overlay of wall masks onto the display image."""
    overlay = np.zeros_like(display)
    overlay[left_wall  > 0] = COLOR_LEFT_WALL
    overlay[right_wall > 0] = COLOR_RIGHT_WALL
    return cv2.addWeighted(display, 1.0 - alpha, overlay, alpha, 0)


def draw_centerline(display, nav_result):
    """Draw the centerline on the display image."""
    if nav_result["center_x"] is None:
        return
    cx = int(nav_result["center_x"])
    cv2.line(display, (cx, HEIGHT), (cx, 0), COLOR_CENTERLINE, 2)
    # Also draw the midline reference
    cv2.line(display, (MID_X, HEIGHT), (MID_X, 0), (128, 128, 128), 1)


def draw_left_right_lines(display, nav_result, lookahead_y=540):
    """Draw the fitted wall lines."""
    h = display.shape[0]
    for key, color in [("left_x", COLOR_LEFT_WALL), ("right_x", COLOR_RIGHT_WALL)]:
        if nav_result[key] is not None and nav_result.get(key.replace("_x", "_slope")) is not None:
            slope = nav_result[key.replace("_x", "_slope")]
            intercept = nav_result[key] - slope * lookahead_y
            x0 = int(slope * 0 + intercept)
            x1 = int(slope * h + intercept)
            cv2.line(display, (x0, 0), (x1, h), color, 1)


# ===================== Main loop =====================
def main():
    print(f"Loading model from {WEIGHT_PATH} ...")
    model = load_model()
    stream = CameraStreamThread(src=CAMERA_INDEX).start()
    print("System ready. Press ESC to exit.")

    prev_time = time.time()
    fps_smooth = 0.0

    with torch.inference_mode():
        while True:
            ret, frame = stream.read()
            if frame is None:
                continue

            # --- 1. Crop to ROI ---
            cropped = frame[TOP_CUT:-BOTTOM_CUT, LEFT_CUT:-RIGHT_CUT]

            # --- 2. Undistort ---
            pure = undistort(cropped)

            # --- 3. Normalize + infer ---
            img_tensor = torch.from_numpy(pure).to(DEVICE).permute(2,0,1).unsqueeze(0).float() / 255.0
            img_tensor = (img_tensor - MEAN) / STD
            out = model(img_tensor)
            torch.cuda.synchronize()

            # --- 4. Prediction mask ---
            pred = torch.argmax(out, dim=1).squeeze(0).cpu().numpy().astype(np.uint8)

            # --- 5. IPM projection ---
            mask_ipm = apply_ipm(pred)

            # --- 6. Wall-building + centerline ---
            nav, left_wall, right_wall = peony_postprocess(mask_ipm)

            # --- 7. Physical conversion ---
            lateral_m = 0.0
            if nav["center_x"] is not None:
                lateral_m = nav["lateral_error"] * IPM_SCALE_X

            # --- 8. Visualization ---
            # Project walls back to display space via inverse IPM
            left_disp = left_wall  # work in IPM space for display simplicity
            right_disp = right_wall

            # Build display on the IPM-view mask
            mask_overlay = np.stack([
                pred * 100,
                pred * 255,
                pred * 255
            ], axis=-1).astype(np.uint8)
            display = cv2.addWeighted(pure, 0.7, mask_overlay, 0.3, 0)
            display = draw_walls_overlay(display, left_disp, right_disp)
            draw_centerline(display, nav)
            draw_left_right_lines(display, nav)

            # --- 9. FPS ---
            now = time.time()
            dt = now - prev_time
            prev_time = now
            fps = 1.0 / max(dt, 1e-6)
            fps_smooth = fps_smooth * 0.9 + fps * 0.1

            # --- 10. Info overlay ---
            cv2.putText(display, f"FPS: {fps_smooth:.1f}", (20, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, COLOR_INFO, 2)
            cv2.putText(display, f"LAT: {lateral_m*100:.1f} cm", (20, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                        (0, 0, 255) if abs(lateral_m) > LATERAL_SAFETY_LIMIT_M else COLOR_INFO, 2)
            cv2.putText(display, f"Status: {nav['status']}", (20, 90),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 1)

            # --- 11. E-STOP warning ---
            if abs(lateral_m) > LATERAL_SAFETY_LIMIT_M:
                cv2.putText(display, "E-STOP", (WIDTH//2 - 60, HEIGHT//2),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 4)

            cv2.imshow("Peony Row Navigator", display)
            if cv2.waitKey(1) & 0xFF == 27:
                break

    stream.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
