"""Shared stand-in components: synthetic camera, detector runtime, filters.

Every input is synthetic and deterministic (seeded), so a run measures the
cost of the computation, not of a dataset or a camera driver. Frames are
pre-generated, so producing a frame costs nothing inside the timed loop.
"""

import os

import cv2
import numpy as np

ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")


def texture(h, w, seed=0):
    """Blurred noise with edges and corners, so feature trackers and stereo have something to lock on."""
    rng = np.random.RandomState(seed)
    img = rng.randint(0, 256, (h // 8, w // 8)).astype(np.uint8)
    img = cv2.resize(img, (w, h), interpolation=cv2.INTER_NEAREST)
    img = cv2.GaussianBlur(img, (5, 5), 1.5)
    noise = rng.randint(0, 24, (h, w)).astype(np.uint8)
    return cv2.add(img, noise)


class MovingCamera(object):
    """A camera translating over a large texture: frame k is a shifted crop."""

    def __init__(self, h, w, n_frames=64, step=(2, 3), color=False, seed=0):
        big = texture(h + n_frames * step[0] + 8, w + n_frames * step[1] + 8, seed)
        if color:
            big = cv2.cvtColor(big, cv2.COLOR_GRAY2BGR)
        self.frames = [np.ascontiguousarray(big[k * step[0]:k * step[0] + h, k * step[1]:k * step[1] + w])
                       for k in range(n_frames)]

    def __call__(self, k):
        # Ping-pong through the sequence, so motion never jumps (a jump breaks feature tracks).
        n = len(self.frames)
        k %= 2 * n - 2
        return self.frames[k if k < n else 2 * n - 2 - k]


class StereoCamera(object):
    """Rectified stereo pairs of a slanted plane: disparity grows down the image."""

    def __init__(self, h, w, n_frames=16, d_min=8, d_max=48, seed=0):
        self.pairs = []
        xs, ys = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
        disp = (d_min + (d_max - d_min) * ys / (h - 1)).astype(np.float32)
        for k in range(n_frames):
            # Right(x) = Left(x + d): a point at column x in the left image is at x - d in the right.
            full = texture(h, w + d_max + 1, seed + k)
            left = np.ascontiguousarray(full[:, :w])
            right = cv2.remap(full, xs + disp, ys, cv2.INTER_LINEAR)
            self.pairs.append((left, right))

    def __call__(self, k):
        return self.pairs[k % len(self.pairs)]


class Detector(object):
    """Runs a stand-in ONNX detector with onnxruntime, or OpenCV dnn if onnxruntime is missing.

    provider: 'auto' picks TensorRT, then CUDA, then CPU (onnxruntime), or the
    OpenCV backend. Decoding (sigmoid, score threshold, NMS) is part of the
    timed work, as it is on a real detector.
    """

    def __init__(self, size, provider="auto", threads=0):
        self.size = size
        path = os.path.join(ASSETS, "det%d.onnx" % size)
        if not os.path.exists(path):
            raise IOError("%s not found: run python3 bench/make_detector.py and copy bench/assets/ "
                          "to this machine" % path)
        self.runtime = None
        try:
            import onnxruntime as ort
            avail = ort.get_available_providers()
            if provider == "auto":
                order = ["TensorrtExecutionProvider", "CUDAExecutionProvider", "CPUExecutionProvider"]
                providers = [p for p in order if p in avail]
            elif provider == "opencv":
                raise ImportError
            else:
                providers = [provider]
            so = ort.SessionOptions()
            if threads:
                so.intra_op_num_threads = threads
            self.sess = ort.InferenceSession(path, so, providers=providers)
            self.runtime = "onnxruntime:" + self.sess.get_providers()[0]
        except ImportError:
            self.net = cv2.dnn.readNetFromONNX(path)
            self.runtime = "opencv-dnn"

    def infer(self, bgr):
        blob = cv2.dnn.blobFromImage(bgr, 1 / 255.0, (self.size, self.size), swapRB=True)
        if self.runtime.startswith("onnxruntime"):
            return self.sess.run(None, {"images": blob})[0][0]
        self.net.setInput(blob)
        return self.net.forward()[0]

    @staticmethod
    def decode(preds, score_thr=0.25, nms_thr=0.45, top_k=100):
        """preds (cells, 5 + nc) -> list of (x, y, w, h, score, cls)."""
        logits = preds[:, 4:]
        scores = 1 / (1 + np.exp(-logits))
        obj = scores[:, 0]
        cls = scores[:, 1:].argmax(1)
        conf = obj * scores[np.arange(len(scores)), 1 + cls]
        keep = np.nonzero(conf > score_thr)[0]
        if len(keep) > 4 * top_k:
            keep = keep[np.argsort(-conf[keep])[:4 * top_k]]
        boxes = preds[keep, :4]
        rects = [[float(x), float(y), float(abs(w)) + 1, float(abs(h)) + 1] for x, y, w, h in boxes]
        idx = cv2.dnn.NMSBoxes(rects, conf[keep].tolist(), score_thr, nms_thr, top_k=top_k) if rects else []
        idx = np.array(idx).reshape(-1)
        return [tuple(rects[i]) + (float(conf[keep[i]]), int(cls[keep[i]])) for i in idx]


class KalmanFilter(object):
    """Linear Kalman filter; predict + update per frame, dense numpy (as an EKF step costs)."""

    def __init__(self, f, h, q, r):
        n = f.shape[0]
        self.f, self.h, self.q, self.r = f, h, q, r
        self.x, self.p = np.zeros(n), np.eye(n)

    def step(self, z):
        self.x = self.f @ self.x
        self.p = self.f @ self.p @ self.f.T + self.q
        s = self.h @ self.p @ self.h.T + self.r
        k = np.linalg.solve(s, self.h @ self.p).T
        self.x = self.x + k @ (z - self.h @ self.x)
        self.p = (np.eye(len(self.x)) - k @ self.h) @ self.p
        return self.x


def constant_velocity(dim, dt, n_meas=None, q=1e-2, r=1e-1):
    """State [pos(dim), vel(dim)]; measures the first n_meas states (default: positions)."""
    n_meas = dim if n_meas is None else n_meas
    f = np.eye(2 * dim)
    f[:dim, dim:] = dt * np.eye(dim)
    h = np.zeros((n_meas, 2 * dim))
    h[:, :n_meas] = np.eye(n_meas)
    return KalmanFilter(f, h, q * np.eye(2 * dim), r * np.eye(n_meas))
