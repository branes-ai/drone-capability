"""Generate the stand-in detector models (ONNX) used by the racing pipeline.

    python3 bench/make_detector.py            # writes bench/assets/det320.onnx

The network is a YOLOv8n-shaped single-stage detector: conv-BN-SiLU stem, four
downsampling stages with CSP blocks at YOLOv8n widths (16-32-64-128-256), and a
three-scale head (stride 8/16/32), about 80% of YOLOv8n's compute, that emits 4 box + 1 objectness + NC class
channels per cell. The weights are random (seeded): latency and power depend on
the architecture and the input size, not on what the network has learnt.
Detection quality is therefore NOT measured with these models.

Needs torch and onnx on the machine that generates the files; the targets need
only onnxruntime or OpenCV's dnn module. Copy bench/assets/ to the target.
"""

import argparse
import json
from pathlib import Path

import torch
import torch.nn as nn

ASSETS = Path(__file__).resolve().parent / "assets"
NUM_CLASSES = 2  # gate / target, and a background-like second class


def conv(c_in, c_out, k=3, s=1):
    return nn.Sequential(nn.Conv2d(c_in, c_out, k, s, k // 2, bias=False), nn.BatchNorm2d(c_out), nn.SiLU())


class Bottleneck(nn.Module):
    def __init__(self, c):
        super().__init__()
        self.a, self.b = conv(c, c), conv(c, c)

    def forward(self, x):
        return x + self.b(self.a(x))


class CSP(nn.Module):
    """C2f-style block: split, n bottlenecks on one half, concatenate every output."""

    def __init__(self, c_in, c_out, n):
        super().__init__()
        self.h = c_out // 2
        self.cv1 = conv(c_in, 2 * self.h, 1)
        self.m = nn.ModuleList(Bottleneck(self.h) for _ in range(n))
        self.cv2 = conv((2 + n) * self.h, c_out, 1)

    def forward(self, x):
        y = list(self.cv1(x).chunk(2, 1))
        for m in self.m:
            y.append(m(y[-1]))
        return self.cv2(torch.cat(y, 1))


class Detector(nn.Module):
    def __init__(self, nc=NUM_CLASSES, w=(16, 32, 64, 128, 256), n=(2, 4, 4, 2)):
        super().__init__()
        self.stem = conv(3, w[0], 3, 2)                                       # /2
        self.s1 = nn.Sequential(conv(w[0], w[1], 3, 2), CSP(w[1], w[1], n[0]))  # /4
        self.s2 = nn.Sequential(conv(w[1], w[2], 3, 2), CSP(w[2], w[2], n[1]))  # /8
        self.s3 = nn.Sequential(conv(w[2], w[3], 3, 2), CSP(w[3], w[3], n[2]))  # /16
        self.s4 = nn.Sequential(conv(w[3], w[4], 3, 2), CSP(w[4], w[4], n[3]))  # /32
        self.up = nn.Upsample(scale_factor=2, mode="nearest")
        self.f3 = CSP(w[4] + w[3], w[3], 1)
        self.f2 = CSP(w[3] + w[2], w[2], 1)
        no = 5 + nc
        self.h2, self.h3, self.h4 = (nn.Sequential(conv(c, c), nn.Conv2d(c, no, 1)) for c in (w[2], w[3], w[4]))
        self.no = no

    def forward(self, x):
        x2 = self.s2(self.s1(self.stem(x)))
        x3 = self.s3(x2)
        x4 = self.s4(x3)
        p3 = self.f3(torch.cat([self.up(x4), x3], 1))
        p2 = self.f2(torch.cat([self.up(p3), x2], 1))
        outs = [h(p).flatten(2) for h, p in ((self.h2, p2), (self.h3, p3), (self.h4, x4))]
        return torch.cat(outs, 2).transpose(1, 2)  # (1, cells, 5 + nc)


def count(model, size):
    """Parameters and multiply-accumulates for one forward pass at size x size."""
    macs = [0]

    def hook(mod, inp, out):
        if isinstance(mod, nn.Conv2d):
            macs[0] += out.numel() * mod.in_channels // mod.groups * mod.kernel_size[0] * mod.kernel_size[1]

    hs = [m.register_forward_hook(hook) for m in model.modules()]
    with torch.no_grad():
        model(torch.zeros(1, 3, size, size))
    for h in hs:
        h.remove()
    return sum(p.numel() for p in model.parameters()), macs[0]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sizes", type=int, nargs="+", default=[320])
    ap.add_argument("--out", type=Path, default=ASSETS)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    torch.manual_seed(0)
    model = Detector().eval()
    for size in args.sizes:
        path = args.out / f"det{size}.onnx"
        torch.onnx.export(model, torch.zeros(1, 3, size, size), str(path), opset_version=13,
                          input_names=["images"], output_names=["preds"], dynamo=False)
        params, macs = count(model, size)
        meta = {"architecture": "YOLOv8n-shaped CSP detector, random weights", "input": [1, 3, size, size],
                "params": params, "gmacs": round(macs / 1e9, 3), "num_classes": NUM_CLASSES}
        path.with_suffix(".json").write_text(json.dumps(meta, indent=2) + "\n")
        print(f"{path}: {params / 1e6:.2f} M params, {macs / 1e9:.2f} GMACs")


if __name__ == "__main__":
    main()
