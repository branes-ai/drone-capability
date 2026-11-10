"""Inspection L1 stand-in: VIO -> standoff estimation -> position control, at 30 Hz.

- vio_front: KLT tracking of up to 200 corners on 640 x 480 grey frames,
             replenished with Shi-Tomasi corners when fewer than 120 remain
- vio_back:  essential matrix (RANSAC) and relative pose, then a 15-state
             filter update with the pose
- standoff:  RANSAC plane fit (100 hypotheses) to 2000 points of a 160 x 120
             depth image (ToF class), giving distance and normal to the surface
- control:   cascaded PID, position -> velocity -> attitude
"""

import cv2
import numpy as np

from harness import Pipeline, Stage
from pipelines.common import KalmanFilter, MovingCamera

RATE_HZ = 30.0
K_CAM = np.array([[400, 0, 320], [0, 400, 240], [0, 0, 1]], np.float64)


def build(provider="auto", threads=0):
    cam = MovingCamera(480, 640)
    rng = np.random.RandomState(1)
    # A wall 3 m ahead, slightly tilted, with sensor noise.
    vs, us = np.mgrid[0:120, 0:160].astype(np.float32)
    depth_img = (3.0 + 0.004 * (us - 80) + rng.normal(0, 0.01, (120, 160))).astype(np.float32)
    pix = np.stack([(us - 80) / 100.0, (vs - 60) / 100.0], -1)
    state = {"prev": None, "pts": None}
    n = 15
    f = np.eye(n)
    f[0:3, 3:6] = (1.0 / RATE_HZ) * np.eye(3)
    h = np.zeros((6, n))
    h[:, :6] = np.eye(6)
    kf = KalmanFilter(f, h, 1e-3 * np.eye(n), 1e-2 * np.eye(6))
    gains = np.array([1.2, 0.8, 4.0])
    integ = np.zeros(3)

    def vio_front(frame):
        prev, pts = state["prev"], state["pts"]
        if prev is None:
            prev = frame
        if pts is None or len(pts) < 120:
            new = cv2.goodFeaturesToTrack(prev, 200, 0.01, 8)
            pts = new if pts is None or len(pts) == 0 else np.vstack([pts, new])[:200]
        nxt, st, _ = cv2.calcOpticalFlowPyrLK(prev, frame, pts, None, winSize=(21, 21), maxLevel=3)
        good = st.ravel() == 1
        p0, p1 = pts[good], nxt[good]
        state["prev"], state["pts"] = frame, p1.reshape(-1, 1, 2)
        return p0, p1

    def vio_back(tracks):
        p0, p1 = tracks
        z = kf.h @ kf.x
        if len(p0) >= 8:
            e, mask = cv2.findEssentialMat(p0, p1, K_CAM, cv2.RANSAC, 0.999, 1.0)
            if e is not None and e.shape == (3, 3):
                _, r, t, _ = cv2.recoverPose(e, p0, p1, K_CAM, mask=mask)
                z = np.concatenate([cv2.Rodrigues(r)[0].ravel(), t.ravel()])
        return kf.step(z)

    def standoff(x):
        sel = rng.randint(0, depth_img.size, 2000)
        d = depth_img.ravel()[sel]
        p = np.column_stack([pix.reshape(-1, 2)[sel] * d[:, None], d])
        best, best_n = None, -1
        for _ in range(100):
            a, b, c = p[rng.randint(0, len(p), 3)]
            nrm = np.cross(b - a, c - a)
            norm = np.linalg.norm(nrm)
            if norm < 1e-9:
                continue
            nrm = nrm / norm
            n_in = int((np.abs((p - a) @ nrm) < 0.03).sum())
            if n_in > best_n:
                best, best_n = (nrm, a), n_in
        nrm, a = best
        return x, abs(a @ nrm), nrm

    def control(est):
        x, dist, _ = est
        err = np.array([dist - 2.0, x[1], x[2]])
        integ[...] += err / RATE_HZ
        v_cmd = gains[0] * err + 0.1 * integ
        att_cmd = gains[1] * (v_cmd - x[3:6])
        return gains[2] * att_cmd

    stages = [Stage("vio_front", vio_front), Stage("vio_back", vio_back),
              Stage("standoff", standoff), Stage("control", control)]
    return Pipeline("inspection", RATE_HZ, cam, stages, __doc__.strip().splitlines()[0],
                    {"camera": [640, 480], "max_features": 200, "depth": [160, 120]})
