# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

import json
import os
import random
import traceback
import uuid
from concurrent.futures import ProcessPoolExecutor
from itertools import repeat

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.font_manager import FontProperties
from tqdm import tqdm

from common import (
    build_output_layout,
    clear_dir,
    choose_weighted,
    human_round,
    load_font_pool,
    load_words,
    maybe_int_or_float,
    padded_limits,
    legend_kwargs,
    sample_axis_title,
    sample_canvas,
    sample_label,
    sample_title,
    sample_series_name,
    safe_max_workers,
    seed_everything,
    series_color,
    write_manifest,
)

BASE_DIR = Path(__file__).resolve().parent
RUN_NAME = Path(__file__).stem.replace("gen_", "", 1)
GEN_NUM = int(os.environ.get("VSR_GEN_NUM", "50"))

WORDS = load_words()
FONT_POOL = load_font_pool()

seed = None
RUN_ROOT = None
SAVE_DIR = None
OUTPUT_JSON = None
MANIFEST_PATH = None


SCATTER_POINT_BANDS = {
    "clustered": [
        ((16, 22), 0.18),
        ((23, 28), 0.24),
        ((29, 34), 0.24),
        ((35, 41), 0.18),
        ((42, 48), 0.16),
    ],
    "multi_cluster": [
        ((18, 24), 0.16),
        ((25, 30), 0.24),
        ((31, 36), 0.24),
        ((37, 42), 0.20),
        ((43, 48), 0.16),
    ],
    "correlated": [
        ((14, 20), 0.20),
        ((21, 26), 0.24),
        ((27, 32), 0.24),
        ((33, 39), 0.20),
        ((40, 48), 0.12),
    ],
    "curved": [
        ((12, 18), 0.22),
        ((19, 24), 0.26),
        ((25, 30), 0.22),
        ((31, 38), 0.18),
        ((39, 48), 0.12),
    ],
    "ring": [
        ((14, 20), 0.22),
        ((21, 26), 0.24),
        ((27, 32), 0.24),
        ((33, 40), 0.18),
        ((41, 48), 0.12),
    ],
    "heteroskedastic": [
        ((14, 20), 0.22),
        ((21, 26), 0.24),
        ((27, 32), 0.24),
        ((33, 40), 0.18),
        ((41, 48), 0.12),
    ],
    "fan": [
        ((12, 18), 0.24),
        ((19, 24), 0.26),
        ((25, 30), 0.22),
        ((31, 36), 0.18),
        ((37, 48), 0.10),
    ],
    "stripe": [
        ((16, 22), 0.18),
        ((23, 28), 0.24),
        ((29, 34), 0.24),
        ((35, 41), 0.20),
        ((42, 48), 0.14),
    ],
    "stepwise": [
        ((12, 18), 0.24),
        ((19, 24), 0.26),
        ((25, 30), 0.22),
        ((31, 38), 0.18),
        ((39, 48), 0.10),
    ],
    "bimodal": [
        ((14, 18), 0.20),
        ((19, 24), 0.26),
        ((25, 30), 0.24),
        ((31, 36), 0.18),
        ((37, 48), 0.12),
    ],
    "outliers": [
        ((10, 15), 0.28),
        ((16, 22), 0.26),
        ((23, 28), 0.22),
        ((29, 36), 0.16),
        ((37, 48), 0.08),
    ],
    "spiral": [
        ((14, 18), 0.20),
        ((19, 24), 0.26),
        ((25, 30), 0.24),
        ((31, 38), 0.18),
        ((39, 48), 0.12),
    ],
    "crescent": [
        ((12, 18), 0.20),
        ((19, 24), 0.26),
        ((25, 30), 0.24),
        ((31, 38), 0.18),
        ((39, 48), 0.12),
    ],
    "grid": [
        ((12, 18), 0.18),
        ((19, 24), 0.24),
        ((25, 30), 0.24),
        ((31, 38), 0.20),
        ((39, 48), 0.14),
    ],
    "bridge": [
        ((12, 18), 0.22),
        ((19, 24), 0.24),
        ((25, 30), 0.24),
        ((31, 38), 0.18),
        ((39, 48), 0.12),
    ],
    "hourglass": [
        ((12, 18), 0.18),
        ((19, 24), 0.22),
        ((25, 30), 0.24),
        ((31, 38), 0.20),
        ((39, 48), 0.16),
    ],
}

DEFAULT_SCATTER_POINT_BANDS = [
    ((12, 18), 0.22),
    ((19, 24), 0.26),
    ((25, 30), 0.22),
    ((31, 38), 0.18),
    ((39, 48), 0.12),
]


def sample_point_count(family: str) -> int:
    bands = SCATTER_POINT_BANDS.get(family, DEFAULT_SCATTER_POINT_BANDS)
    low, high = choose_weighted([band for band, _ in bands], [weight for _, weight in bands])
    return random.randint(low, high)


def sample_family() -> str:
    return choose_weighted(
        ["clustered", "multi_cluster", "correlated", "curved", "ring", "heteroskedastic", "fan", "stripe", "stepwise", "bimodal", "outliers", "spiral", "crescent", "grid", "bridge", "hourglass"],
        [0.12, 0.08, 0.12, 0.11, 0.08, 0.10, 0.07, 0.06, 0.05, 0.04, 0.03, 0.05, 0.04, 0.04, 0.04, 0.03],
    )


def sample_scale() -> float:
    return choose_weighted(
        [0.5, 1.0, 2.0, 4.0, 8.0, 15.0, 30.0, 60.0],
        [0.08, 0.16, 0.20, 0.18, 0.14, 0.11, 0.08, 0.05],
    ) * random.uniform(0.80, 1.30)


def sample_marker(n_points: int) -> tuple[str, float, float]:
    if n_points > 36:
        marker = choose_weighted([".", "o", "s", "X"], [0.50, 0.26, 0.16, 0.08])
        size = random.uniform(10.0, 18.0)
        alpha = random.uniform(0.58, 0.82)
    elif n_points > 24:
        marker = choose_weighted(["o", ".", "s", "^", "D", "v", "P", "X"], [0.22, 0.18, 0.16, 0.12, 0.10, 0.08, 0.08, 0.06])
        size = random.uniform(14.0, 26.0)
        alpha = random.uniform(0.66, 0.90)
    else:
        marker = choose_weighted(["o", "s", "^", "D", "v", "<", ">", "P", "X", "*", "."], [0.18, 0.14, 0.12, 0.10, 0.09, 0.07, 0.07, 0.08, 0.08, 0.04, 0.03])
        size = random.uniform(18.0, 40.0)
        alpha = random.uniform(0.72, 0.96)
    return marker, size, alpha


def finalize_values(values: np.ndarray) -> np.ndarray:
    out = []
    for value in values:
        if abs(float(value)) < 1e-12:
            out.append(0.0)
        else:
            rounded = human_round(float(value))
            out.append(float(rounded) if isinstance(rounded, int) else float(rounded))
    return np.array(out, dtype=float)


def allocate_counts(n_points: int, k: int) -> list[int]:
    if k <= 1:
        return [n_points]
    if k >= n_points:
        return [1] * n_points
    weights = np.random.dirichlet(np.full(k, random.uniform(0.8, 2.2)))
    counts = np.maximum(1, np.floor(weights * n_points).astype(int))
    while counts.sum() < n_points:
        counts[random.randrange(k)] += 1
    while counts.sum() > n_points:
        idx = random.randrange(k)
        if counts[idx] > 1:
            counts[idx] -= 1
    return counts.tolist()


def rotated_covariance(major: float, minor: float) -> np.ndarray:
    angle = random.uniform(0, np.pi)
    c, s = np.cos(angle), np.sin(angle)
    rot = np.array([[c, -s], [s, c]])
    scale = np.diag([major**2, minor**2])
    return rot @ scale @ rot.T


def make_clustered(n_points: int) -> tuple[np.ndarray, np.ndarray]:
    cluster_count = choose_weighted([2, 3, 4, 5], [0.34, 0.32, 0.22, 0.12])
    counts = allocate_counts(n_points, cluster_count)
    coord_scale = sample_scale()
    centers = []
    for _ in range(cluster_count):
        angle = random.uniform(0, 2 * np.pi)
        radius = coord_scale * random.uniform(0.25, 1.45)
        centers.append(
            np.array(
                [
                    np.cos(angle) * radius + random.uniform(-0.2, 0.2) * coord_scale,
                    np.sin(angle) * radius + random.uniform(-0.2, 0.2) * coord_scale,
                ]
            )
        )

    points = []
    cluster_ids = []
    for idx, (center, count) in enumerate(zip(centers, counts)):
        cov = rotated_covariance(
            major=coord_scale * random.uniform(0.08, 0.28),
            minor=coord_scale * random.uniform(0.04, 0.16),
        )
        cloud = np.random.multivariate_normal(center, cov, count)
        if random.random() < 0.22 and count > 3:
            cloud[random.randrange(count)] += np.random.normal(0.0, coord_scale * random.uniform(0.8, 1.8), 2)
        points.append(cloud)
        cluster_ids.extend([idx] * count)
    pts = np.concatenate(points, axis=0)
    return pts[:, 0], pts[:, 1]


def make_multi_cluster(n_points: int) -> tuple[np.ndarray, np.ndarray]:
    cluster_count = choose_weighted([3, 4, 5, 6], [0.24, 0.30, 0.26, 0.20])
    counts = allocate_counts(n_points, cluster_count)
    coord_scale = sample_scale()
    anchors = []
    for _ in range(cluster_count):
        angle = random.uniform(0, 2 * np.pi)
        radius = coord_scale * random.uniform(0.30, 1.55)
        center = np.array([
            np.cos(angle) * radius,
            np.sin(angle) * radius,
        ])
        if random.random() < 0.5:
            center += np.array([random.uniform(-0.22, 0.22), random.uniform(-0.22, 0.22)]) * coord_scale
        anchors.append(center)

    if random.random() < 0.35:
        anchors.sort(key=lambda pt: pt[0])

    points = []
    for center, count in zip(anchors, counts):
        cov = rotated_covariance(
            major=coord_scale * random.uniform(0.06, 0.22),
            minor=coord_scale * random.uniform(0.03, 0.12),
        )
        cloud = np.random.multivariate_normal(center, cov, count)
        if random.random() < 0.2 and count > 4:
            cloud[random.randrange(count)] += np.random.normal(0.0, coord_scale * random.uniform(0.6, 1.6), 2)
        points.append(cloud)
    pts = np.concatenate(points, axis=0)
    return pts[:, 0], pts[:, 1]


def make_bimodal(n_points: int) -> tuple[np.ndarray, np.ndarray]:
    counts = allocate_counts(n_points, 2)
    coord_scale = sample_scale()
    angle = random.uniform(0, 2 * np.pi)
    distance = coord_scale * random.uniform(1.0, 2.4)
    direction = np.array([np.cos(angle), np.sin(angle)])
    center_a = direction * distance
    center_b = -direction * distance * random.uniform(0.65, 1.15)
    centers = [center_a, center_b]
    if random.random() < 0.45:
        centers[1] += np.array([random.uniform(-0.35, 0.35), random.uniform(-0.35, 0.35)]) * coord_scale

    points = []
    for idx, (center, count) in enumerate(zip(centers, counts)):
        cov = rotated_covariance(
            major=coord_scale * random.uniform(0.08, 0.24) * (1.0 + 0.25 * idx),
            minor=coord_scale * random.uniform(0.04, 0.14),
        )
        cloud = np.random.multivariate_normal(center, cov, count)
        if random.random() < 0.25 and count > 3:
            cloud[random.randrange(count)] += np.random.normal(0.0, coord_scale * random.uniform(0.7, 1.7), 2)
        points.append(cloud)
    pts = np.concatenate(points, axis=0)
    return pts[:, 0], pts[:, 1]


def make_fan(n_points: int) -> tuple[np.ndarray, np.ndarray]:
    coord_scale = sample_scale()
    x = np.random.uniform(-coord_scale * random.uniform(0.7, 2.2), coord_scale * random.uniform(0.7, 2.2), n_points)
    if random.random() < 0.45:
        x = np.sort(x)
    slope = random.choice([-1, 1]) * random.uniform(0.25, 1.1)
    intercept = random.uniform(-0.30, 0.30) * coord_scale
    x_scale = np.abs(x) / max(float(np.max(np.abs(x))), 1e-6)
    sigma = coord_scale * (random.uniform(0.03, 0.07) + random.uniform(0.05, 0.18) * x_scale ** random.uniform(0.8, 1.6))
    y = slope * x + intercept + np.random.normal(0.0, sigma, n_points)
    if random.random() < 0.34:
        y += np.sign(x) * coord_scale * random.uniform(0.05, 0.16)
    return x, y


def make_stepwise(n_points: int) -> tuple[np.ndarray, np.ndarray]:
    coord_scale = sample_scale()
    x = np.random.uniform(-coord_scale * random.uniform(1.0, 2.0), coord_scale * random.uniform(1.0, 2.0), n_points)
    x.sort()
    step_count = choose_weighted([2, 3, 4, 5], [0.20, 0.32, 0.28, 0.20])
    breakpoints = sorted(random.sample(range(1, n_points), min(step_count, max(1, n_points - 1))))
    edges = [0] + breakpoints + [n_points]
    levels = []
    level = random.uniform(-0.3, 0.3) * coord_scale
    for _ in range(len(edges) - 1):
        levels.append(level)
        level += random.uniform(-0.8, 0.9) * coord_scale
    y = np.empty(n_points, dtype=float)
    for start, stop, level in zip(edges[:-1], edges[1:], levels):
        segment = slice(start, stop)
        if random.random() < 0.5:
            y[segment] = level + (x[segment] - float(np.mean(x[segment]))) * random.uniform(-0.18, 0.18)
        else:
            y[segment] = level
    y += np.random.normal(0.0, coord_scale * random.uniform(0.04, 0.13), n_points)
    if random.random() < 0.3:
        y[random.randrange(n_points)] += coord_scale * random.uniform(0.7, 2.2) * random.choice([-1, 1])
    return x, y


def make_correlated(n_points: int) -> tuple[np.ndarray, np.ndarray]:
    coord_scale = sample_scale()
    x = np.random.normal(0.0, coord_scale, n_points)
    slope = random.choice([-1, 1]) * random.uniform(0.45, 1.55)
    intercept = random.uniform(-0.35, 0.35) * coord_scale
    noise = np.random.normal(0.0, coord_scale * random.uniform(0.10, 0.30), n_points)
    y = slope * x + intercept + noise
    if random.random() < 0.30:
        y += np.sin(x / max(coord_scale, 1e-6)) * coord_scale * random.uniform(0.12, 0.35)
    return x, y


def make_curved(n_points: int) -> tuple[np.ndarray, np.ndarray]:
    coord_scale = sample_scale()
    x = np.random.uniform(-coord_scale * random.uniform(1.1, 2.4), coord_scale * random.uniform(1.1, 2.4), n_points)
    mode = choose_weighted(["parabola", "arc", "s_curve"], [0.46, 0.28, 0.26])
    if mode == "parabola":
        a = random.choice([-1, 1]) * random.uniform(0.18, 0.55) / max(coord_scale, 1e-6)
        b = random.uniform(-0.4, 0.4)
        c = random.uniform(-0.35, 0.35) * coord_scale
        y = a * x**2 + b * x + c
    elif mode == "arc":
        x = np.random.uniform(-coord_scale, coord_scale, n_points)
        y = np.sqrt(np.maximum(coord_scale**2 - x**2, 0)) * random.choice([-1, 1]) + random.uniform(-0.25, 0.25) * coord_scale
    else:
        y = np.tanh(x / max(coord_scale, 1e-6)) * coord_scale * random.uniform(0.9, 1.8)
    y += np.random.normal(0.0, coord_scale * random.uniform(0.08, 0.22), n_points)
    return x, y


def make_ring(n_points: int) -> tuple[np.ndarray, np.ndarray]:
    coord_scale = sample_scale()
    full_circle = random.random() < 0.62
    if full_circle:
        theta = np.random.uniform(0, 2 * np.pi, n_points)
    else:
        start = random.uniform(0, 2 * np.pi)
        theta = np.random.uniform(start, start + random.uniform(np.pi / 2, 1.75 * np.pi), n_points)
    radius = coord_scale * random.uniform(0.8, 1.8)
    r = radius + np.random.normal(0.0, coord_scale * random.uniform(0.05, 0.18), n_points)
    x = r * np.cos(theta) + random.uniform(-0.25, 0.25) * coord_scale
    y = r * np.sin(theta) + random.uniform(-0.25, 0.25) * coord_scale
    return x, y


def make_heteroskedastic(n_points: int) -> tuple[np.ndarray, np.ndarray]:
    coord_scale = sample_scale()
    x = np.random.uniform(-coord_scale * random.uniform(1.2, 2.5), coord_scale * random.uniform(1.2, 2.5), n_points)
    slope = random.choice([-1, 1]) * random.uniform(0.25, 1.1)
    intercept = random.uniform(-0.25, 0.25) * coord_scale
    sigma = coord_scale * (random.uniform(0.04, 0.10) + random.uniform(0.02, 0.08) * np.abs(x) / max(np.max(np.abs(x)), 1e-6))
    y = slope * x + intercept + np.random.normal(0.0, sigma, n_points)
    return x, y


def make_stripe(n_points: int) -> tuple[np.ndarray, np.ndarray]:
    coord_scale = sample_scale()
    mode = choose_weighted(["vertical", "horizontal", "diagonal"], [0.42, 0.32, 0.26])
    stripe_count = choose_weighted([3, 4, 5, 6], [0.24, 0.34, 0.24, 0.18])
    if mode == "vertical":
        centers = np.linspace(-coord_scale, coord_scale, stripe_count) + np.random.normal(0.0, coord_scale * 0.12, stripe_count)
        x = np.random.choice(centers, size=n_points) + np.random.normal(0.0, coord_scale * random.uniform(0.03, 0.10), n_points)
        y = np.random.uniform(-coord_scale * random.uniform(1.1, 2.0), coord_scale * random.uniform(1.1, 2.0), n_points)
    elif mode == "horizontal":
        centers = np.linspace(-coord_scale, coord_scale, stripe_count) + np.random.normal(0.0, coord_scale * 0.12, stripe_count)
        y = np.random.choice(centers, size=n_points) + np.random.normal(0.0, coord_scale * random.uniform(0.03, 0.10), n_points)
        x = np.random.uniform(-coord_scale * random.uniform(1.1, 2.0), coord_scale * random.uniform(1.1, 2.0), n_points)
    else:
        x = np.random.uniform(-coord_scale * random.uniform(1.0, 2.0), coord_scale * random.uniform(1.0, 2.0), n_points)
        offsets = np.linspace(-coord_scale, coord_scale, stripe_count) + np.random.normal(0.0, coord_scale * 0.12, stripe_count)
        offset = np.random.choice(offsets, size=n_points)
        slope = random.choice([-1, 1]) * random.uniform(0.55, 1.35)
        y = slope * x + offset + np.random.normal(0.0, coord_scale * random.uniform(0.04, 0.12), n_points)
    return x, y


def make_outliers(n_points: int) -> tuple[np.ndarray, np.ndarray]:
    core_n = max(3, int(n_points * random.uniform(0.82, 0.94)))
    out_n = n_points - core_n
    core_x = np.random.normal(0.0, sample_scale(), core_n)
    slope = random.choice([-1, 1]) * random.uniform(0.4, 1.3)
    core_y = slope * core_x + np.random.normal(0.0, sample_scale() * random.uniform(0.12, 0.22), core_n)
    coord_scale = max(sample_scale(), float(np.max(np.abs(core_x))) if core_x.size else 1.0)
    out_x = np.random.uniform(-coord_scale * random.uniform(2.0, 4.5), coord_scale * random.uniform(2.0, 4.5), out_n)
    out_y = np.random.uniform(-coord_scale * random.uniform(2.0, 4.5), coord_scale * random.uniform(2.0, 4.5), out_n)
    x = np.concatenate([core_x, out_x])
    y = np.concatenate([core_y, out_y])
    return x, y


def make_spiral(n_points: int) -> tuple[np.ndarray, np.ndarray]:
    coord_scale = sample_scale()
    turns = random.uniform(2.5, 5.2)
    theta = np.linspace(0.0, turns * 2 * np.pi, n_points)
    radius = np.linspace(coord_scale * 0.18, coord_scale * random.uniform(1.1, 1.8), n_points)
    radius += np.random.normal(0.0, coord_scale * random.uniform(0.02, 0.08), n_points)
    x = radius * np.cos(theta)
    y = radius * np.sin(theta)
    if random.random() < 0.7:
        rot = random.uniform(-np.pi, np.pi)
        c, s = np.cos(rot), np.sin(rot)
        x, y = c * x - s * y, s * x + c * y
    return x, y


def make_crescent(n_points: int) -> tuple[np.ndarray, np.ndarray]:
    coord_scale = sample_scale()
    start = random.uniform(0, 2 * np.pi)
    span = random.uniform(np.pi * 0.85, np.pi * 1.35)
    theta = np.random.uniform(start, start + span, n_points)
    radius = coord_scale * random.uniform(0.85, 1.65)
    radial = radius + np.random.normal(0.0, coord_scale * random.uniform(0.05, 0.16), n_points)
    x = radial * np.cos(theta)
    y = radial * np.sin(theta) * random.uniform(0.55, 0.92)
    y += np.cos(theta * 1.7) * coord_scale * random.uniform(0.05, 0.16)
    return x, y


def make_grid(n_points: int) -> tuple[np.ndarray, np.ndarray]:
    coord_scale = sample_scale()
    rows = choose_weighted([2, 3, 4, 5], [0.12, 0.32, 0.32, 0.24])
    cols = max(2, int(np.ceil(n_points / rows)))
    xs = np.linspace(-coord_scale, coord_scale, cols)
    ys = np.linspace(-coord_scale, coord_scale, rows)
    grid_x, grid_y = np.meshgrid(xs, ys)
    coords = np.column_stack([grid_x.ravel(), grid_y.ravel()])
    if len(coords) > n_points:
        idx = np.random.choice(len(coords), n_points, replace=False)
        coords = coords[idx]
    else:
        extra = n_points - len(coords)
        if extra > 0:
            jitter = np.column_stack([
                np.random.choice(xs, extra, replace=True) + np.random.normal(0.0, coord_scale * 0.08, extra),
                np.random.choice(ys, extra, replace=True) + np.random.normal(0.0, coord_scale * 0.08, extra),
            ])
            coords = np.vstack([coords, jitter])
    coords += np.random.normal(0.0, coord_scale * random.uniform(0.03, 0.10), coords.shape)
    return coords[:, 0], coords[:, 1]


def make_bridge(n_points: int) -> tuple[np.ndarray, np.ndarray]:
    coord_scale = sample_scale()
    left_n = max(3, int(n_points * random.uniform(0.34, 0.46)))
    right_n = max(3, int(n_points * random.uniform(0.34, 0.46)))
    bridge_n = max(2, n_points - left_n - right_n)
    left = np.random.normal([-coord_scale, coord_scale * random.uniform(-0.25, 0.25)], [coord_scale * 0.18, coord_scale * 0.18], (left_n, 2))
    right = np.random.normal([coord_scale, coord_scale * random.uniform(-0.25, 0.25)], [coord_scale * 0.18, coord_scale * 0.18], (right_n, 2))
    bridge_t = np.linspace(0.0, 1.0, bridge_n)
    bridge = np.column_stack([
        np.interp(bridge_t, [0.0, 1.0], [-coord_scale * 0.7, coord_scale * 0.7]),
        np.interp(bridge_t, [0.0, 1.0], [0.0, coord_scale * random.uniform(-0.12, 0.12)]),
    ])
    bridge += np.random.normal(0.0, coord_scale * random.uniform(0.03, 0.09), bridge.shape)
    coords = np.vstack([left, bridge, right])
    if len(coords) > n_points:
        coords = coords[np.random.choice(len(coords), n_points, replace=False)]
    elif len(coords) < n_points:
        extra = n_points - len(coords)
        coords = np.vstack([coords, coords[np.random.choice(len(coords), extra, replace=True)]])
    return coords[:, 0], coords[:, 1]


def make_hourglass(n_points: int) -> tuple[np.ndarray, np.ndarray]:
    coord_scale = sample_scale()
    x = np.random.uniform(-coord_scale * random.uniform(1.0, 1.8), coord_scale * random.uniform(1.0, 1.8), n_points)
    if random.random() < 0.42:
        x = np.sort(x)
    x_norm = np.abs(x) / max(float(np.max(np.abs(x))), 1e-6)
    branch = np.where(np.random.rand(n_points) < 0.5, 1.0, -1.0)
    power = random.uniform(0.8, 1.4)
    y = branch * (0.18 + 0.95 * x_norm**power) * coord_scale
    y += np.random.normal(0.0, coord_scale * random.uniform(0.03, 0.10), n_points)
    if random.random() < 0.42:
        rot = random.uniform(-0.35, 0.35)
        c, s = np.cos(rot), np.sin(rot)
        x, y = c * x - s * y, s * x + c * y
    return x, y


def build_points(n_points: int, family: str) -> tuple[np.ndarray, np.ndarray]:
    if family == "clustered":
        return make_clustered(n_points)
    if family == "multi_cluster":
        return make_multi_cluster(n_points)
    if family == "correlated":
        return make_correlated(n_points)
    if family == "curved":
        return make_curved(n_points)
    if family == "ring":
        return make_ring(n_points)
    if family == "heteroskedastic":
        return make_heteroskedastic(n_points)
    if family == "fan":
        return make_fan(n_points)
    if family == "stripe":
        return make_stripe(n_points)
    if family == "stepwise":
        return make_stepwise(n_points)
    if family == "bimodal":
        return make_bimodal(n_points)
    if family == "outliers":
        return make_outliers(n_points)
    if family == "spiral":
        return make_spiral(n_points)
    if family == "crescent":
        return make_crescent(n_points)
    if family == "grid":
        return make_grid(n_points)
    if family == "bridge":
        return make_bridge(n_points)
    if family == "hourglass":
        return make_hourglass(n_points)
    return make_clustered(n_points)


def sample_config() -> dict:
    family = sample_family()
    n_points = sample_point_count(family)
    x, y = build_points(n_points, family)
    x = finalize_values(x)
    y = finalize_values(y)

    style = sample_canvas("scatter", series_count=1)
    fig_w, fig_h = style["figsize"]
    if family in {"ring", "clustered"}:
        fig_w = max(fig_w, 6.0)
        fig_h = max(fig_h, 6.0)
    else:
        fig_w = min(max(fig_w, 5.8 + 0.01 * n_points), 10.5)
        fig_h = min(max(fig_h, 5.0 + 0.01 * n_points), 9.0)
    style["figsize"] = (fig_w, fig_h)

    show_legend = random.random() < 0.14
    series_name = sample_series_name(0) if show_legend else "None"
    label_color = series_color(style["series_colors"], 0)
    marker, size, alpha = sample_marker(n_points)

    flat_x = [float(v) for v in x]
    flat_y = [float(v) for v in y]
    symmetric = family in {"clustered", "multi_cluster", "ring", "bimodal", "hourglass"} and random.random() < 0.80
    xlim = padded_limits(flat_x, include_zero=(not symmetric and random.random() < 0.28), symmetric=symmetric, pad=(0.07, 0.16))
    ylim = padded_limits(flat_y, include_zero=(not symmetric and random.random() < 0.28), symmetric=symmetric, pad=(0.07, 0.16))

    x_title = sample_axis_title("x", "scatter")
    y_title = sample_axis_title("y", "scatter")

    return {
        "font_path": random.choice(FONT_POOL),
        "style": style,
        "family": family,
        "n_points": n_points,
        "x": x,
        "y": y,
        "series_name": series_name,
        "show_legend": show_legend,
        "title": sample_title("scatter"),
        "title_loc": random.choice(["left", "center"]),
        "title_weight": choose_weighted(["normal", "bold"], [0.76, 0.24]),
        "title_style": choose_weighted(["normal", "italic"], [0.84, 0.16]),
        "x_title": x_title,
        "y_title": y_title,
        "color": label_color,
        "marker": marker,
        "size": size,
        "alpha": alpha,
        "edgecolor": "none" if marker == "." or n_points > 42 else (style["text_color"] if random.random() < 0.45 else label_color),
        "linewidth": random.uniform(0.3, 0.9),
        "xlim": xlim,
        "ylim": ylim,
        "grid_axis": choose_weighted(["both", "y", "x"], [0.52, 0.28, 0.20]),
    }


def collect_metadata(ax, cfg: dict, fig) -> tuple[list[int], list, list, list, list]:
    data_ori: list = []
    data_pixel: list = []
    data_pixel_proj_x: list = []
    data_pixel_proj_y: list = []

    origin = ax.transData.inverted().transform(ax.transAxes.transform((0, 0)))
    axes_x = origin[0]
    axes_y = origin[1]

    for x, y in zip(cfg["x"], cfg["y"]):
        data_ori.append([cfg["series_name"], x, y])
        data_pixel.append(ax.transData.transform([x, y]).tolist())
        data_pixel_proj_x.append(ax.transData.transform([x, axes_y]).tolist())
        data_pixel_proj_y.append(ax.transData.transform([axes_x, y]).tolist())

    width = int(fig.get_figwidth() * fig.dpi)
    height = int(fig.get_figheight() * fig.dpi)
    return [width, height], data_ori, data_pixel, data_pixel_proj_x, data_pixel_proj_y


def render_one(index: int, runtime=None):
    try:
        global seed, RUN_ROOT, SAVE_DIR
        if runtime is not None:
            seed = runtime["seed"]
            RUN_ROOT = runtime["RUN_ROOT"]
            SAVE_DIR = runtime["save_dir"]

        seed_everything(seed + int(index))
        cfg = sample_config()

        plt.rcdefaults()
        plt.rcParams["text.usetex"] = False

        font_props = FontProperties(fname=cfg["font_path"])
        fig, ax = plt.subplots(figsize=cfg["style"]["figsize"], dpi=cfg["style"]["dpi"])
        fig.patch.set_facecolor(cfg["style"]["facecolor"])
        ax.set_facecolor(cfg["style"]["axes_face"])
        ax.set_frame_on(True)

        ax.scatter(
            cfg["x"],
            cfg["y"],
            s=cfg["size"],
            c=cfg["color"],
            marker=cfg["marker"],
            alpha=cfg["alpha"],
            edgecolors=cfg["edgecolor"],
            linewidths=cfg["linewidth"],
            label=None if cfg["series_name"] == "None" else cfg["series_name"],
        )

        ax.set_xlabel(cfg["x_title"], fontproperties=font_props, fontsize=cfg["style"]["label_size"], color=cfg["style"]["text_color"], labelpad=cfg["style"]["label_pad"])
        ax.set_ylabel(cfg["y_title"], fontproperties=font_props, fontsize=cfg["style"]["label_size"], color=cfg["style"]["text_color"], labelpad=cfg["style"]["label_pad"])
        ax.set_xlim(cfg["xlim"])
        ax.set_ylim(cfg["ylim"])

        ax.set_xticks(np.linspace(cfg["xlim"][0], cfg["xlim"][1], random.randint(4, 7)))
        ax.set_yticks(np.linspace(cfg["ylim"][0], cfg["ylim"][1], random.randint(4, 7)))
        nonzero_x = [abs(float(v)) for v in cfg["x"] if float(v) != 0]
        if max(abs(cfg["xlim"][0]), abs(cfg["xlim"][1])) >= 1e4 or (nonzero_x and min(nonzero_x) < 1e-2):
            ax.ticklabel_format(axis="x", style="sci", scilimits=(0, 0))
        nonzero_y = [abs(float(v)) for v in cfg["y"] if float(v) != 0]
        if max(abs(cfg["ylim"][0]), abs(cfg["ylim"][1])) >= 1e4 or (nonzero_y and min(nonzero_y) < 1e-2):
            ax.ticklabel_format(axis="y", style="sci", scilimits=(0, 0))

        ax.tick_params(
            axis="both",
            which="major",
            labelsize=cfg["style"]["tick_size"],
            color=cfg["style"]["text_color"],
            length=random.choice([3, 4, 5]),
            width=random.uniform(0.7, 1.2),
            direction=random.choice(["in", "out"]),
            pad=cfg["style"]["tick_pad"],
        )

        if cfg["show_legend"]:
            ax.legend(**legend_kwargs(cfg["style"]))

        ax.set_title(
            cfg["title"],
            fontproperties=font_props,
            size=cfg["style"]["title_size"],
            color=cfg["style"]["text_color"],
            pad=cfg["style"]["title_pad"],
            loc=cfg["title_loc"],
            style=cfg["title_style"],
            weight=cfg["title_weight"],
        )

        if cfg["style"]["grid_visible"]:
            ax.grid(
                visible=True,
                axis=cfg["grid_axis"],
                which="major",
                linestyle=cfg["style"]["grid_style"],
                linewidth=cfg["style"]["grid_width"],
                alpha=cfg["style"]["grid_alpha"],
                color=cfg["style"]["grid_color"],
            )
        else:
            ax.grid(visible=False)

        for spine in ax.spines.values():
            spine.set_visible(cfg["style"]["spine_visible"])
            spine.set_color(cfg["style"]["spine_color"])
            spine.set_linewidth(cfg["style"]["spine_width"])

        if cfg["family"] in {"ring", "clustered", "multi_cluster", "bimodal"} and random.random() < 0.58:
            ax.set_aspect("equal", adjustable="datalim")

        if cfg["style"]["layout_rect"] is None:
            fig.tight_layout()
        else:
            fig.tight_layout(rect=cfg["style"]["layout_rect"])

        wh, data_ori, data_pixel, proj_x, proj_y = collect_metadata(ax, cfg, fig)
        output_path = SAVE_DIR / f"chart_{uuid.uuid4().hex}.png"
        plt.savefig(output_path, facecolor=cfg["style"]["facecolor"])
        plt.close(fig)

        return {
            "image": str(Path(output_path).relative_to(RUN_ROOT)),
            "wh": wh,
            "data_ori": data_ori,
            "data_pixel": data_pixel,
            "data_pixel_proj_x": proj_x,
            "data_pixel_proj_y": proj_y,
            "title": cfg["title"],
            "x_title": cfg["x_title"],
            "y_title": cfg["y_title"],
        }
    except Exception:
        print("[ERROR]", traceback.format_exc())
        plt.close("all")
        return None


if __name__ == "__main__":
    seed = seed_everything()
    RUN_ROOT, SAVE_DIR, OUTPUT_JSON, MANIFEST_PATH = build_output_layout(RUN_NAME, seed)
    clear_dir(SAVE_DIR)
    runtime = dict(seed=seed, RUN_ROOT=RUN_ROOT, save_dir=SAVE_DIR)

    max_workers = safe_max_workers()
    chunk_size = max(10, GEN_NUM // (max_workers * 10))

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        raw_results = list(
            tqdm(
                executor.map(render_one, range(GEN_NUM), repeat(runtime), chunksize=chunk_size),
                total=GEN_NUM,
                desc="Generating",
            )
        )
        results = [result for result in raw_results if result is not None]

    with OUTPUT_JSON.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, ensure_ascii=False)

    write_manifest(
        MANIFEST_PATH,
        script=RUN_NAME,
        seed=seed,
        gen_num=GEN_NUM,
        sample_count=len(results),
        save_dir=str(SAVE_DIR),
        font_count=len(FONT_POOL),
        fonts=[Path(path).name for path in FONT_POOL],
    )

    print(f"完成生成 {len(results)} 张图表，目录：{SAVE_DIR}")
