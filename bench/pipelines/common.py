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
    """Runs a stand-in ONNX detector; decoding (sigmoid, threshold, NMS) is part of the timed work.

    provider:
      auto      onnxruntime with its best available provider, else OpenCV dnn
      cpu       onnxruntime CPU provider
      opencv    OpenCV dnn
      tensorrt  TensorRT FP16 engine (Jetson); built once and cached next to the ONNX file
      qnn       onnxruntime-qnn plugin on the Qualcomm HTP (NPU) at FP16, no CPU fallback;
                QNN_BACKEND overrides the HTP backend library (default: the system
                QAIRT /usr/lib/libQnnHtp.so when present)
      any other onnxruntime provider name
    """

    def __init__(self, size, provider="auto", threads=0):
        self.size = size
        path = os.path.join(ASSETS, "det%d.onnx" % size)
        if not os.path.exists(path):
            raise IOError("%s not found: run python3 bench/make_detector.py and copy bench/assets/ "
                          "to this machine" % path)
        if provider == "tensorrt":
            self.trt = TensorRTRunner(path)
            self.runtime = "tensorrt-%s:fp16" % self.trt.version
            return
        if provider == "opencv":
            self._opencv(path)
            return
        try:
            import onnxruntime as ort
        except ImportError:
            if provider not in ("auto",):
                raise
            self._opencv(path)
            return
        so = ort.SessionOptions()
        if threads:
            so.intra_op_num_threads = threads
        if provider == "qnn":
            import onnxruntime_qnn as oq
            ort.register_execution_provider_library("QNNExecutionProvider", oq.get_library_path())
            devices = [d for d in ort.get_ep_devices() if d.ep_name == "QNNExecutionProvider"]
            backend = os.environ.get("QNN_BACKEND") or (
                "/usr/lib/libQnnHtp.so" if os.path.exists("/usr/lib/libQnnHtp.so") else oq.get_qnn_htp_path())
            so.add_session_config_entry("session.disable_cpu_ep_fallback", "1")
            so.add_provider_for_devices(devices, {"backend_path": backend, "htp_performance_mode": "burst",
                                                  "enable_htp_fp16_precision": "1"})
            self.sess = ort.InferenceSession(path, so)
            self.runtime = "onnxruntime-qnn:HTP:fp16"
            return
        avail = ort.get_available_providers()
        if provider == "auto":
            order = ["TensorrtExecutionProvider", "CUDAExecutionProvider", "CPUExecutionProvider"]
            providers = [p for p in order if p in avail]
        elif provider == "cpu":
            providers = ["CPUExecutionProvider"]
        else:
            providers = [provider]
        self.sess = ort.InferenceSession(path, so, providers=providers)
        self.runtime = "onnxruntime:" + self.sess.get_providers()[0]

    def _opencv(self, path):
        self.net = cv2.dnn.readNetFromONNX(path)
        self.runtime = "opencv-dnn"

    def infer(self, bgr):
        blob = cv2.dnn.blobFromImage(bgr, 1 / 255.0, (self.size, self.size), swapRB=True)
        if self.runtime.startswith("tensorrt"):
            return self.trt.run(blob)[0]
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


class _CudaRuntime(object):
    """The few libcudart calls TensorRT inference needs, through ctypes (no pycuda or cuda-python)."""

    H2D, D2H = 1, 2

    def __init__(self):
        import ctypes
        import ctypes.util
        self.ct = ctypes
        names = ["libcudart.so", "libcudart.so.12", ctypes.util.find_library("cudart") or "",
                 "/usr/local/cuda/lib64/libcudart.so"]
        self.lib = None
        for n in names:
            try:
                self.lib = ctypes.CDLL(n)
                break
            except OSError:
                continue
        if self.lib is None:
            raise OSError("libcudart not found")
        # Declare every signature: without argtypes, ctypes passes Python ints as
        # 32-bit C ints and truncates 64-bit host pointers.
        vp, sz = ctypes.c_void_p, ctypes.c_size_t
        self.lib.cudaStreamCreate.argtypes = [ctypes.POINTER(vp)]
        self.lib.cudaMalloc.argtypes = [ctypes.POINTER(vp), sz]
        self.lib.cudaMemcpyAsync.argtypes = [vp, vp, sz, ctypes.c_int, vp]
        self.lib.cudaStreamSynchronize.argtypes = [vp]
        for f in (self.lib.cudaStreamCreate, self.lib.cudaMalloc, self.lib.cudaMemcpyAsync,
                  self.lib.cudaStreamSynchronize):
            f.restype = ctypes.c_int
        self.stream = vp()
        self.check(self.lib.cudaStreamCreate(ctypes.byref(self.stream)), "cudaStreamCreate")

    def check(self, err, what):
        if err != 0:
            raise RuntimeError("%s failed with CUDA error %d" % (what, err))

    def malloc(self, nbytes):
        p = self.ct.c_void_p()
        self.check(self.lib.cudaMalloc(self.ct.byref(p), nbytes), "cudaMalloc")
        return p

    def copy(self, dst, src, nbytes, kind):
        self.check(self.lib.cudaMemcpyAsync(dst, src, nbytes, kind, self.stream), "cudaMemcpyAsync")

    def sync(self):
        self.check(self.lib.cudaStreamSynchronize(self.stream), "cudaStreamSynchronize")


class TensorRTRunner(object):
    """FP16 TensorRT engine for a fixed-shape ONNX model; the engine is cached per TensorRT version."""

    def __init__(self, onnx_path):
        import tensorrt as trt
        self.version = trt.__version__
        logger = trt.Logger(trt.Logger.WARNING)
        cache = "%s.fp16.trt%s.engine" % (os.path.splitext(onnx_path)[0], self.version)
        if not os.path.exists(cache):
            builder = trt.Builder(logger)
            net = builder.create_network(0)
            parser = trt.OnnxParser(net, logger)
            with open(onnx_path, "rb") as f:
                if not parser.parse(f.read()):
                    raise RuntimeError("TensorRT could not parse %s: %s" % (
                        onnx_path, [str(parser.get_error(i)) for i in range(parser.num_errors)]))
            cfg = builder.create_builder_config()
            cfg.set_flag(trt.BuilderFlag.FP16)
            plan = builder.build_serialized_network(net, cfg)
            with open(cache, "wb") as f:
                f.write(plan)
        with open(cache, "rb") as f:
            self.engine = trt.Runtime(logger).deserialize_cuda_engine(f.read())
        self.ctx = self.engine.create_execution_context()
        self.cuda = _CudaRuntime()
        self.inputs, self.outputs = [], []
        for i in range(self.engine.num_io_tensors):
            name = self.engine.get_tensor_name(i)
            shape = tuple(self.engine.get_tensor_shape(name))
            host = np.empty(shape, trt.nptype(self.engine.get_tensor_dtype(name)))
            dev = self.cuda.malloc(host.nbytes)
            self.ctx.set_tensor_address(name, dev.value)
            io = (self.inputs if self.engine.get_tensor_mode(name) == trt.TensorIOMode.INPUT else self.outputs)
            io.append((name, host, dev))

    def run(self, *arrays):
        """Copy inputs to the GPU, run, copy outputs back; returns the output arrays."""
        for (_, host, dev), a in zip(self.inputs, arrays):
            host[...] = a
            self.cuda.copy(dev, host.ctypes.data, host.nbytes, _CudaRuntime.H2D)
        self.ctx.execute_async_v3(self.cuda.stream.value)
        for _, host, dev in self.outputs:
            self.cuda.copy(host.ctypes.data, dev, host.nbytes, _CudaRuntime.D2H)
        self.cuda.sync()
        return [host[0] if host.shape[0] == 1 else host for _, host, _ in self.outputs]
