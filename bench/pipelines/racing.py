"""Racing L1 stand-in: gate detection -> gate pose -> state estimation -> MPC, at 60 Hz.

- detect:   YOLOv8n-shaped detector at 320 x 320 on a 640 x 480 colour frame
- decode:   score threshold and NMS
- gate_pnp: PnP on the four corners of the best gates (up to 3)
- estimate: IMU propagation at 1 kHz between frames (16 steps) and an 18-state
            filter update with the gate poses
- mpc:      condensed linear MPC, 12 states x 4 inputs, horizon 20, box-
            constrained, 40 projected-gradient iterations, warm-started
"""

import cv2
import numpy as np

from harness import Pipeline, Stage
from pipelines.common import Detector, KalmanFilter, MovingCamera

RATE_HZ = 60.0
GATE = np.array([[-0.75, -0.75, 0], [0.75, -0.75, 0], [0.75, 0.75, 0], [-0.75, 0.75, 0]], np.float32)
K_CAM = np.array([[400, 0, 320], [0, 400, 240], [0, 0, 1]], np.float32)


class LinearMPC(object):
    """min sum ||x_k - r||_Q + ||u_k||_R over N steps, |u| <= u_max, x_{k+1} = A x_k + B u_k."""

    def __init__(self, a, b, n=20, q=1.0, r=0.1, u_max=1.0, iters=40):
        nx, nu = b.shape
        self.n, self.nu, self.u_max, self.iters = n, nu, u_max, iters
        # Prediction matrices: X = Sx x0 + Su U.
        sx = np.zeros((n * nx, nx))
        su = np.zeros((n * nx, n * nu))
        ak = np.eye(nx)
        for k in range(n):
            ak = a @ ak
            sx[k * nx:(k + 1) * nx] = ak
            for j in range(k + 1):
                su[k * nx:(k + 1) * nx, j * nu:(j + 1) * nu] = np.linalg.matrix_power(a, k - j) @ b
        self.sx, self.su, self.q = sx, su, q
        self.h = q * su.T @ su + r * np.eye(n * nu)
        self.step = 1.0 / np.linalg.eigvalsh(self.h).max()
        self.u = np.zeros(n * nu)

    def solve(self, x0, ref):
        g = self.q * self.su.T @ (self.sx @ x0 - np.tile(ref, self.n))
        u = np.concatenate([self.u[self.nu:], self.u[-self.nu:]])  # shift warm start
        for _ in range(self.iters):
            u = np.clip(u - self.step * (self.h @ u + g), -self.u_max, self.u_max)
        self.u = u
        return u[:self.nu]


def hover_model(dt):
    """Quadrotor linearised at hover: [p, v, att, rate] (12), inputs [thrust, 3 torques]."""
    a = np.eye(12)
    a[0:3, 3:6] = dt * np.eye(3)
    a[6:9, 9:12] = dt * np.eye(3)
    a[3, 7], a[4, 6] = 9.81 * dt, -9.81 * dt  # tilt -> horizontal acceleration
    b = np.zeros((12, 4))
    b[5, 0] = dt
    b[9:12, 1:4] = 20 * dt * np.eye(3)
    return a, b


def build(provider="auto", threads=0, **opts):
    cam = MovingCamera(480, 640, color=True)
    det = Detector(320, provider, threads)
    dt = 1.0 / RATE_HZ
    n = 18
    f = np.eye(n)
    f[0:3, 3:6] = dt * np.eye(3)
    h = np.zeros((6, n))
    h[:, :6] = np.eye(6)
    kf = KalmanFilter(f, h, 1e-3 * np.eye(n), 1e-2 * np.eye(6))
    imu_f = np.eye(n)
    imu_f[0:3, 3:6] = 1e-3 * np.eye(3)
    mpc = LinearMPC(*hover_model(dt))
    ref = np.zeros(12)
    ref[0] = 5.0
    img_scale = np.array([640 / 320.0, 480 / 320.0], np.float32)

    def gate_pnp(dets):
        poses = []
        for x, y, w, hh, _, _ in sorted(dets, key=lambda d: -d[4])[:3]:
            cx, cy = np.array([x % 320, y % 320], np.float32) * img_scale
            s = np.float32(20 + w % 100)
            img_pts = np.array([[cx - s, cy - s], [cx + s, cy - s], [cx + s, cy + s], [cx - s, cy + s]], np.float32)
            ok, rvec, tvec = cv2.solvePnP(GATE, img_pts, K_CAM, None, flags=cv2.SOLVEPNP_IPPE_SQUARE)
            if ok:
                poses.append(np.concatenate([rvec.ravel(), tvec.ravel()]))
        return poses

    def estimate(poses):
        for _ in range(16):  # IMU propagation between camera frames
            kf.x = imu_f @ kf.x
        z = poses[0] if poses else kf.h @ kf.x
        x = kf.step(z)
        return x[:12]

    stages = [
        Stage("detect", det.infer),
        Stage("decode", Detector.decode),
        Stage("gate_pnp", gate_pnp),
        Stage("estimate", estimate),
        Stage("mpc", lambda x: mpc.solve(x, ref)),
    ]
    return Pipeline("racing", RATE_HZ, cam, stages, __doc__.strip().splitlines()[0],
                    {"detector_input": 320, "detector_runtime": det.runtime, "camera": [640, 480]})
