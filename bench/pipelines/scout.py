"""Scouting L1 stand-in: stereo depth -> mapping -> local planner, at 30 Hz.

- depth:   semi-global block matching (OpenCV SGBM), 640 x 480, 64 disparities
- points:  reproject every 4th pixel to 3D (f = 400 px, baseline 0.1 m)
- mapping: rolling local occupancy grid, 0.2 m voxels, 20 x 20 x 5 m around
           the vehicle: decay, then insert the points
- planner: clearance map (distance transform of the occupied slab) and 49
           arc primitives x 20 samples, scored on clearance and goal progress
"""

import cv2
import numpy as np

from harness import Pipeline, Stage
from pipelines.common import StereoCamera

RATE_HZ = 30.0
F_PX, BASELINE_M, VOXEL_M = 400.0, 0.1, 0.2
GRID = (100, 100, 25)  # x, y, z cells


def primitives(n_yaw=7, n_climb=7, n_samples=20, length_m=8.0):
    """(n_yaw * n_climb, n_samples, 3) arc samples in the vehicle frame."""
    out = []
    s = np.linspace(0.5, length_m, n_samples)
    for k in np.linspace(-0.25, 0.25, n_yaw):            # curvature [1/m]
        for climb in np.linspace(-0.3, 0.3, n_climb):    # climb slope
            yaw = k * s
            x = np.where(abs(k) > 1e-6, np.sin(yaw) / (k if abs(k) > 1e-6 else 1), s)
            y = np.where(abs(k) > 1e-6, (1 - np.cos(yaw)) / (k if abs(k) > 1e-6 else 1), 0 * s)
            out.append(np.stack([x, y, climb * s], 1))
    return np.array(out)


def build(provider="auto", threads=0):
    cam = StereoCamera(480, 640)
    sgbm = cv2.StereoSGBM_create(minDisparity=0, numDisparities=64, blockSize=5,
                                 P1=8 * 25, P2=32 * 25, mode=cv2.STEREO_SGBM_MODE_SGBM)
    grid = np.zeros(GRID, np.float32)
    prims = primitives()
    goal = np.array([20.0, 5.0, 0.0])
    origin = np.array([GRID[0] // 2, GRID[1] // 2, GRID[2] // 2])
    ys, xs = np.mgrid[0:480:4, 0:640:4]

    def depth(pair):
        return sgbm.compute(pair[0], pair[1])

    def points(disp16):
        d = disp16[::4, ::4].astype(np.float32) / 16.0
        ok = d > 1.0
        z = F_PX * BASELINE_M / d[ok]
        x = (xs[ok] - 320) * z / F_PX
        y = (ys[ok] - 240) * z / F_PX
        # camera (x right, y down, z forward) -> vehicle (x forward, y left, z up)
        return np.stack([z, -x, -y], 1)

    def mapping(pts):
        grid[...] *= 0.95
        idx = np.floor(pts / VOXEL_M).astype(np.int64) + origin
        ok = np.all((idx >= 0) & (idx < GRID), 1)
        idx = idx[ok]
        np.add.at(grid, (idx[:, 0], idx[:, 1], idx[:, 2]), 0.4)
        return grid

    def planner(g):
        occupied = (g.max(2) > 0.5).astype(np.uint8)
        clearance = cv2.distanceTransform(1 - occupied, cv2.DIST_L2, 5) * VOXEL_M
        idx = np.floor(prims / VOXEL_M).astype(np.int64) + origin
        idx = np.clip(idx, 0, np.array(GRID) - 1)
        occ = g[idx[..., 0], idx[..., 1], idx[..., 2]] > 0.5
        clear = clearance[idx[..., 0], idx[..., 1]].min(1)
        progress = -np.linalg.norm(prims[:, -1] - goal, axis=1)
        cost = np.where(occ.any(1), np.inf, -progress - 2.0 * np.minimum(clear, 3.0))
        return int(np.argmin(cost))

    stages = [Stage("depth", depth), Stage("points", points), Stage("mapping", mapping), Stage("planner", planner)]
    return Pipeline("scout", RATE_HZ, cam, stages, __doc__.strip().splitlines()[0],
                    {"stereo": [640, 480, 64], "grid_cells": list(GRID), "primitives": len(prims)})
