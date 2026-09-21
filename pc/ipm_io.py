# -*- coding: utf-8 -*-
"""带来源校验的 IPM 外参加载器（E2③，2026-09-21）。

为什么不是"把 ipm_params.json 接进去"就完事：
`results/smoke_ipm/ipm_params.json` 的源图 `frame.jpg` 像素 mean=0.0/std=0.0
（全黑），点不是对着真实地面标的，`reproj_mean_m` 只反映"求解器能把自己的
合成输入解回去"。仓库现存零个真实外参标定。所以本模块的第一职责是
**把不合格标定挡在生产链路之外**，第二才是算变换。

拒绝条件（任一即拒，抛 IpmRejected）：
  * 缺来源字段：source_image / points_source / vehicle_profile / calib_date / n_points
  * points_source != 'field'            —— 合成、仿真、冒烟都不算
  * 源图不存在，或像素标准差 < MIN_IMAGE_STD —— 全黑/纯色图不可能支撑标定
  * reproj_mean_m > max_reproj_m（默认 0.02 m，即 calib_ipm.py 自己写的目标）
  * n_points < 4                        —— 单应最少 4 点，且 4 点无冗余
  * vehicle_profile 与请求档案不符       —— 见 v1.0 §4.1 跨车迁移边界、§4.3 档案握手
  * H 非 3x3 / 含非有限值 / h22 == 0

坐标约定（与 pc/perception.py 现有 BEV 网格一致）：
  地面系：X 向右为正（m），Y 向前为正（m），原点在相机正下方地面。
  BEV 像素：x_bev = X*s + W/2，y_bev = H_img - Y*s，s = scale_px_per_m（各向同性）。
  因此 m/px = 1/s，**横纵向同一个数**——旧占位用的 0.0015/0.0030 各向异性是
  占位产物，不是物理事实。
"""
import json
import os

import cv2
import numpy as np

MIN_IMAGE_STD = 5.0          # 全黑/纯色图挡在门外（smoke 那份就是这个毛病）
MIN_POINTS = 4
MAX_REPROJ_M = 0.02          # calib_ipm.py 自定的目标：mean <= 0.02 m
REQUIRED = ('H_img2ground', 'scale_px_per_m', 'reproj_mean_m', 'lookahead',
            'source_image', 'points_source', 'vehicle_profile', 'calib_date',
            'n_points')


class IpmRejected(Exception):
    """标定不合格——不是警告，是拒绝使用。"""


class IpmCalib(object):
    """一份通过校验的外参标定及其派生变换。"""

    def __init__(self, H, scale_px_per_m, model_wh, far_m, near_m, prov):
        w, h = model_wh
        self.H_img2ground = H
        self.H_ground2img = np.linalg.inv(H)
        self.scale_px_per_m = float(scale_px_per_m)
        self.m_per_px = 1.0 / self.scale_px_per_m
        # 地面米 -> BEV 像素（各向同性，原点在底边中心）
        A = np.array([[self.scale_px_per_m, 0.0, w / 2.0],
                      [0.0, -self.scale_px_per_m, h],
                      [0.0, 0.0, 1.0]])
        self.A_ground2bev = A
        self.M_img2bev = A @ H
        self.M_bev2img = np.linalg.inv(self.M_img2bev)
        self.model_wh = (w, h)
        self.far_row_px = h - far_m * self.scale_px_per_m
        self.near_row_px = h - near_m * self.scale_px_per_m
        self.provenance = prov

    def ground_to_bev(self, x_m, y_m):
        """地面米 -> BEV 像素（只用仿射部分，不要混进 H）。"""
        p = self.A_ground2bev @ np.array([x_m, y_m, 1.0])
        return p[0] / p[2], p[1] / p[2]

    def describe(self):
        p = self.provenance
        return ('IPM 标定已加载：车档案=%s 日期=%s 点源=%s 点数=%d '
                '重投影=%.4f m m/px=%.5f(各向同性) 源图=%s' % (
                    p['vehicle_profile'], p['calib_date'], p['points_source'],
                    p['n_points'], p['reproj_mean_m'], self.m_per_px,
                    p['source_image']))


def _image_std(path):
    im = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if im is None:
        raise IpmRejected('源图读不了：%s' % path)
    return float(im.std())


def load_ipm_params(path, vehicle_profile, model_wh=(960, 720),
                    max_reproj_m=MAX_REPROJ_M):
    """加载并校验一份外参标定；任何一项不合格就抛 IpmRejected。"""
    if not os.path.isfile(path):
        raise IpmRejected('标定文件不存在：%s' % path)
    with open(path, encoding='utf-8') as f:
        d = json.load(f)

    missing = [k for k in REQUIRED if k not in d]
    if missing:
        raise IpmRejected('缺来源字段 %s —— 无来源的标定不得进入生产链路' % missing)

    if d['points_source'] != 'field':
        raise IpmRejected("points_source=%r 不是 'field'：合成/仿真/冒烟输出不是标定"
                          % d['points_source'])
    if d['vehicle_profile'] != vehicle_profile:
        raise IpmRejected('标定属于车档案 %r，当前请求 %r —— 横向指标禁止跨车引用'
                          % (d['vehicle_profile'], vehicle_profile))
    if int(d['n_points']) < MIN_POINTS:
        raise IpmRejected('标定点只有 %s 个，<%d 无法解单应' % (d['n_points'], MIN_POINTS))
    reproj = float(d['reproj_mean_m'])
    if not np.isfinite(reproj) or reproj < 0.0:
        raise IpmRejected('重投影误差 %r m 非法（必须是非负有限值）' % d['reproj_mean_m'])
    if reproj > max_reproj_m:
        raise IpmRejected('重投影误差 %.4f m 超过上限 %.4f m' % (reproj, max_reproj_m))

    src = d['source_image']
    if not os.path.isfile(src):
        raise IpmRejected('标定时用的源图不存在，无法复核：%s' % src)
    std = _image_std(src)
    if std < MIN_IMAGE_STD:
        raise IpmRejected('源图像素标准差 %.2f < %.1f（近乎纯色/全黑），'
                          '不可能是真实地面标定图' % (std, MIN_IMAGE_STD))

    H = np.array(d['H_img2ground'], dtype=np.float64)
    if H.shape != (3, 3) or not np.isfinite(H).all():
        raise IpmRejected('H_img2ground 必须是 3x3 有限矩阵')
    # 退化判定用秩，不能只看 h22：diag(1,0,1) 的 h22=1 但矩阵不可逆（复审 §4.2）
    if np.linalg.matrix_rank(H) < 3 or abs(np.linalg.det(H)) < 1e-18:
        raise IpmRejected('H 退化（秩<3 或行列式≈0），无法求逆')
    scale = float(d['scale_px_per_m'])
    if not np.isfinite(scale) or scale <= 0:
        raise IpmRejected('scale_px_per_m 必须为正')

    la = d['lookahead']
    if 'far_m' not in la or 'near_m' not in la:
        raise IpmRejected('lookahead 缺 far_m/near_m')
    far_m, near_m = float(la['far_m']), float(la['near_m'])
    if not (np.isfinite(far_m) and np.isfinite(near_m)) or not (0 < near_m < far_m <= 10.0):
        raise IpmRejected('lookahead 需满足 0<near<far≤10 m 且有限，实得 near=%r far=%r'
                          % (la['near_m'], la['far_m']))
    # 前视距离必须落在 BEV 画布内，否则"矩阵正确但采样区在图外"
    if far_m * float(d['scale_px_per_m']) > max(model_wh) * 1.5:
        raise IpmRejected('far_m=%s 在 scale=%s px/m 下超出 BEV 画布，采样区不可用'
                          % (far_m, d['scale_px_per_m']))
    prov = dict(d)
    prov['image_std'] = std
    return IpmCalib(H, scale, model_wh, far_m, near_m, prov)
