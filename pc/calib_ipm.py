# -*- coding: utf-8 -*-
"""IPM calibration from ground markers (C3 / v0.4 §5.6).

Workflow:
  1. Place >=4 markers on the ground along the row direction with known
     physical coordinates (x lateral, y forward, origin under camera,
     y forward-positive).  e.g. 40/50 cm spacing pairs.
  2. Grab one undistorted frame with markers visible:
     python pc/calib_ipm.py grab --cam 0 --out results/ipm_calib/frame.jpg
  3. Click the markers in order, typing their (x,y) meters when prompted:
     python pc/calib_ipm.py pick results/ipm_calib/frame.jpg
     -> writes results/ipm_calib/ipm_points.json
  4. Solve and verify:
     python pc/calib_ipm.py solve results/ipm_calib/frame.jpg
     -> prints reprojection error (target <= 2 cm), writes ipm_params.json
        and updates pc/perception.py constants suggestion.

Math: image point p_h = H_ground -> bird's-eye is split into
  (u,v) = homography(image -> ground-plane metric) solved by DLT from the
  >=4 correspondences.  Far/near lookahead rows then follow from the
  desired lookahead distances.
"""
import json
import os
import sys

import cv2
import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)


def grab(cam_idx, out_path):
    import cv2
    cap = cv2.VideoCapture(cam_idx)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise IOError('camera grab failed')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    cv2.imwrite(out_path, frame)
    print('saved', out_path, frame.shape)


def pick(img_path, out_json):
    import cv2
    pts_px, pts_m = [], []

    state = {'n': 0}

    def on_mouse(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            pts_px.append((x, y))
            xy = input(f'marker #{state["n"]} at ({x},{y}) -> physical x,y '
                       'meters (lateral, forward), comma sep: ')
            xm, ym = (float(v) for v in xy.split(','))
            pts_m.append((xm, ym))
            state['n'] += 1
            print(f'  recorded {state["n"]} markers')

    img = cv2.imread(img_path)
    # undistort first (perception Calib handles lazily)
    from pc.perception import Calib
    try:
        calib = Calib()
        img = calib.undistort(img)
        print('undistorted with calib_params')
    except FileNotFoundError:
        print('WARNING: no calib file — using raw image (undistorted camera only)')

    cv2.namedWindow('pick')
    cv2.setMouseCallback('pick', on_mouse)
    while True:
        vis = img.copy()
        for (x, y) in pts_px:
            cv2.circle(vis, (x, y), 5, (0, 0, 255), -1)
        cv2.putText(vis, f'{len(pts_px)} pts, press s to solve-save, q to quit',
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.imshow('pick', vis)
        k = cv2.waitKey(30) & 0xFF
        if k == ord('s') and len(pts_px) >= 4:
            os.makedirs(os.path.dirname(out_json), exist_ok=True)
            with open(out_json, 'w', encoding='utf-8') as f:
                json.dump({'points_px': pts_px, 'points_m': pts_m}, f, indent=1)
            print('saved', out_json)
            break
        if k == ord('q'):
            break
    cv2.destroyAllWindows()


def solve(img_path, json_path, out_dir):
    data = json.load(open(json_path, encoding='utf-8'))
    px = np.float32(data['points_px'])
    m = np.float32(data['points_m'])

    # DLT homography image(px) -> ground(m)
    H, _ = cv2.findHomography(px, m)
    Hinv = np.linalg.inv(H)

    # reprojection error on training points
    proj = cv2.perspectiveTransform(px.reshape(-1, 1, 2), H).reshape(-1, 2)
    err = np.linalg.norm(proj - m, axis=1)
    print('reprojection error per point (m):', np.round(err, 4))
    print('mean %.4f m, max %.4f m  (target mean <= 0.02 m)' %
          (err.mean(), err.max()))

    # suggested bird's-eye parameters: map ground metrics to IPM pixel grid
    # choose 1 cm/px lateral, 1 cm/px longitudinal around origin (center-bottom)
    scale = 100.0  # px per meter
    # derive where lookahead rows land in image for given lookahead distances
    far_d, near_d = 1.8, 0.45   # m ahead — adjust per row spacing
    out = {
        'H_img2ground': H.tolist(),
        'scale_px_per_m': scale,
        'reproj_mean_m': float(err.mean()),
        'lookahead': {'far_m': far_d, 'near_m': near_d},
        'note': 'replace IPM_SRC/IPM_DST/Scales in pc/perception.py with this H '
                '(warp image with Hinv to render BEV, or sample line via H)'
    }
    os.makedirs(out_dir, exist_ok=True)
    out_json = os.path.join(out_dir, 'ipm_params.json')
    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=1)
    print('saved', out_json)

    # visualize: draw ground grid through Hinv onto the image
    vis = cv2.imread(img_path).copy()
    if vis is None:
        return
    for ym in np.arange(0.2, 3.01, 0.2):
        pts = np.float32([[(x, ym) for x in np.arange(-1.0, 1.01, 0.1)]])
        imgpts = cv2.perspectiveTransform(pts, Hinv).reshape(-1, 2)
        for a, b in zip(imgpts[:-1], imgpts[1:]):
            pa = (int(a[0]), int(a[1]))
            pb = (int(b[0]), int(b[1]))
            if all(0 <= v < 4000 for v in pa + pb):
                cv2.line(vis, pa, pb, (0, 255, 0), 1)
    for xm in np.arange(-1.0, 1.01, 0.2):
        pts = np.float32([[(xm, y) for y in np.arange(0.2, 3.01, 0.1)]])
        imgpts = cv2.perspectiveTransform(pts, Hinv).reshape(-1, 2)
        for a, b in zip(imgpts[:-1], imgpts[1:]):
            pa = (int(a[0]), int(a[1]))
            pb = (int(b[0]), int(b[1]))
            if all(0 <= v < 4000 for v in pa + pb):
                cv2.line(vis, pa, pb, (255, 0, 0), 1)
    out_img = os.path.join(out_dir, 'ipm_grid.jpg')
    cv2.imwrite(out_img, vis)
    print('grid overlay ->', out_img, '(green: rows every 0.2m forward, blue: lateral)')


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'grab':
        grab(int(sys.argv[2]), sys.argv[3])
    elif cmd == 'pick':
        pick(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else
             'results/ipm_calib/ipm_points.json')
    elif cmd == 'solve':
        solve(sys.argv[2],
              sys.argv[3] if len(sys.argv) > 3 else 'results/ipm_calib/ipm_points.json',
              sys.argv[4] if len(sys.argv) > 4 else 'results/ipm_calib')
    else:
        print(__doc__)
