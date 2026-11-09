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


def sample_category_count() -> int:
    low, high = choose_weighted(
        [(4, 6), (7, 9), (10, 12), (13, 16)],
        [0.27, 0.32, 0.25, 0.16],
    )
    return random.randint(low, high)


def sample_series_count() -> int:
    return choose_weighted([2, 3, 4, 5], [0.32, 0.33, 0.22, 0.13])


def sample_category_label() -> str:
    kind = choose_weighted(
        ["word", "phrase", "month", "quarter", "year", "hybrid", "numeric", "code", "compound", "abbr", "slug", "ordinal", "paired"],
        [0.16, 0.17, 0.14, 0.11, 0.09, 0.15, 0.06, 0.05, 0.04, 0.03, 0.03, 0.01, 0.01],
    )
    return sample_label(kind)


def sample_scale() -> float:
    return choose_weighted(
        [0.2, 0.6, 1.0, 2.0, 4.0, 8.0, 15.0, 30.0, 60.0],
        [0.04, 0.08, 0.18, 0.18, 0.16, 0.13, 0.10, 0.08, 0.05],
    ) * random.uniform(0.8, 1.25)


def finalize_values(values: list[float]) -> list[float | int]:
    out: list[float | int] = []
    for value in values:
        if abs(value) < 1e-12:
            out.append(0)
            continue
        rounded = human_round(float(value))
        out.append(maybe_int_or_float(float(rounded)) if isinstance(rounded, float) else rounded)
    return out


def base_curve(n: int, centered: bool = False) -> np.ndarray:
    t = np.linspace(0.0, 1.0, n)
    mode = choose_weighted(
        ["flat", "rise", "fall", "wave", "hump", "step"],
        [0.18, 0.22, 0.18, 0.18, 0.14, 0.10],
    )
    scale = sample_scale()

    if centered:
        baseline = np.zeros(n)
        if mode == "flat":
            curve = baseline + np.random.normal(0.0, scale * 0.10, n)
        elif mode == "rise":
            curve = (t - 0.5) * scale * 1.8
        elif mode == "fall":
            curve = (0.5 - t) * scale * 1.8
        elif mode == "wave":
            curve = np.sin(2 * np.pi * random.uniform(0.8, 2.0) * t + random.uniform(0, np.pi)) * scale * 0.9
        elif mode == "hump":
            curve = np.exp(-((t - 0.5) / random.uniform(0.18, 0.28)) ** 2) * scale - scale * 0.45
        else:
            step_at = random.randint(1, max(1, n - 2))
            curve = np.where(np.arange(n) >= step_at, scale * 0.9, -scale * 0.35)
        return curve

    if mode == "flat":
        curve = np.ones(n) * scale * random.uniform(0.75, 1.15)
    elif mode == "rise":
        curve = (0.7 + 1.2 * t) * scale
    elif mode == "fall":
        curve = (1.9 - 1.1 * t) * scale
    elif mode == "wave":
        curve = (1.0 + 0.25 * np.sin(2 * np.pi * random.uniform(0.8, 2.2) * t + random.uniform(0, np.pi))) * scale
    elif mode == "hump":
        curve = (0.7 + 0.7 * np.exp(-((t - 0.45) / random.uniform(0.18, 0.28)) ** 2)) * scale
    else:
        step_at = random.randint(1, max(1, n - 2))
        curve = np.where(np.arange(n) >= step_at, scale * 1.35, scale * 0.75)
    return curve


def generate_matrix(n_series: int, n_categories: int, family: str) -> np.ndarray:
    t = np.linspace(-1.0, 1.0, n_categories)
    centered = family == "signed"
    base = base_curve(n_categories, centered=centered)

    if family == "composition":
        total = np.maximum(base, 0) + sample_scale() * 0.2
        alpha = random.uniform(0.8, 2.2)
        columns = []
        for total_value in total:
            fractions = np.random.dirichlet(np.full(n_series, alpha))
            column = total_value * fractions
            if random.random() < 0.2:
                column += np.random.normal(0.0, max(total_value * 0.02, 0.02), n_series)
            column = np.clip(column, 0, None)
            if float(column.sum()) <= 0:
                column = np.full(n_series, total_value / n_series)
            columns.append(column)
        return np.array(columns).T

    matrix: list[np.ndarray] = []
    if family == "parallel":
        for _ in range(n_series):
            scale = random.uniform(0.84, 1.22)
            offset = float(base.mean()) * random.uniform(-0.12, 0.18)
            noise = np.random.normal(0.0, np.maximum(np.abs(base) * random.uniform(0.02, 0.06), sample_scale() * 0.012), n_categories)
            matrix.append(base * scale + offset + noise)
    elif family == "crossing":
        slopes = np.linspace(-0.95, 0.95, n_series) + np.random.normal(0.0, 0.12, n_series)
        central = float(np.abs(base).mean() or sample_scale())
        for slope in slopes:
            intercept = central * random.uniform(0.65, 1.35)
            noise = np.random.normal(0.0, central * random.uniform(0.03, 0.08), n_categories)
            series = intercept + slope * t * central * random.uniform(0.8, 1.6) + 0.25 * (base - float(base.mean())) + noise
            matrix.append(series)
    elif family == "dominant":
        dominant_idx = random.randrange(n_series)
        for s in range(n_series):
            if s == dominant_idx:
                scale = random.uniform(2.5, 5.5)
            else:
                scale = random.uniform(0.35, 1.05)
            offset = float(base.mean()) * random.uniform(-0.08, 0.12)
            noise = np.random.normal(0.0, np.maximum(np.abs(base) * random.uniform(0.02, 0.06), sample_scale() * 0.01), n_categories)
            matrix.append(base * scale + offset + noise)
    elif family == "mixed_scale":
        scales = sorted(random.uniform(0.55, 4.5) for _ in range(n_series))
        for scale in scales:
            offset = float(base.mean()) * random.uniform(-0.08, 0.12)
            noise = np.random.normal(0.0, np.maximum(np.abs(base) * random.uniform(0.02, 0.05), sample_scale() * 0.01), n_categories)
            matrix.append(base * scale + offset + noise)
    elif family == "sparse":
        for _ in range(n_series):
            scale = random.uniform(0.75, 1.45)
            series = base * scale + np.random.normal(0.0, np.maximum(np.abs(base) * random.uniform(0.02, 0.05), sample_scale() * 0.01), n_categories)
            mask = np.random.rand(n_categories) < random.uniform(0.18, 0.42)
            series = np.where(mask, 0.0, series)
            if random.random() < 0.25:
                spike_idx = random.randrange(n_categories)
                series[spike_idx] += sample_scale() * random.uniform(0.8, 3.0)
            matrix.append(series)
    elif family == "signed":
        center = sample_scale() * random.uniform(0.35, 0.9)
        base_centered = base_curve(n_categories, centered=True) * random.uniform(0.8, 1.3)
        for _ in range(n_series):
            offset = random.uniform(-center * 0.55, center * 0.55)
            slope = random.uniform(-1.0, 1.0)
            noise = np.random.normal(0.0, center * random.uniform(0.05, 0.12), n_categories)
            matrix.append(base_centered * random.uniform(0.6, 1.35) + slope * t * center * 0.9 + offset + noise)
    elif family == "alternating":
        center = sample_scale() * random.uniform(0.65, 1.5)
        shift = random.randint(0, 1)
        pattern = np.where((np.arange(n_categories) + shift) % 2 == 0, 1.0, -1.0)
        for s in range(n_series):
            scale = random.uniform(0.65, 1.35)
            offset = random.uniform(-0.25, 0.25) * center
            slope = random.uniform(-0.25, 0.25) * center
            noise = np.random.normal(0.0, center * random.uniform(0.03, 0.08), n_categories)
            matrix.append(pattern * center * random.uniform(0.45, 1.05) * scale + slope * t + offset + noise)
    else:
        return generate_matrix(n_series, n_categories, "parallel")

    return np.array(matrix)


def reorder_categories(labels: list[str], matrix: np.ndarray, family: str) -> tuple[list[str], np.ndarray]:
    totals = matrix.sum(axis=0)
    order = list(range(matrix.shape[1]))

    if family in {"parallel", "dominant"}:
        if random.random() < 0.35:
            order.sort(key=lambda idx: totals[idx], reverse=True)
    elif family == "crossing":
        if random.random() < 0.5:
            order.sort(key=lambda idx: matrix[0, idx], reverse=True)
    elif family == "mixed_scale":
        order.sort(key=lambda idx: abs(totals[idx]), reverse=random.random() < 0.5)
    elif family == "composition":
        if random.random() < 0.72:
            order.sort(key=lambda idx: totals[idx], reverse=True)
    elif family == "sparse":
        order.sort(key=lambda idx: (totals[idx] <= 0, abs(totals[idx])), reverse=False)
    elif family == "signed":
        if random.random() < 0.5:
            order.sort(key=lambda idx: (totals[idx] < 0, abs(totals[idx])))
    elif family == "alternating":
        pass
    else:
        if random.random() < 0.25:
            random.shuffle(order)

    labels_out = [labels[i] for i in order]
    matrix_out = matrix[:, order]
    return labels_out, matrix_out


def sample_stack_family() -> str:
    return choose_weighted(
        ["balanced", "dominant", "sparse", "layered", "front_loaded", "back_loaded", "switchback", "fragmented"],
        [0.24, 0.20, 0.14, 0.16, 0.09, 0.07, 0.05, 0.05],
    )


def sample_stack_mode() -> str:
    return choose_weighted(["absolute", "percent"], [0.72, 0.28])


def generate_stack_matrix(n_series: int, n_categories: int, family: str, mode: str) -> np.ndarray:
    totals = np.abs(base_curve(n_categories, centered=False))
    totals += sample_scale() * random.uniform(0.15, 0.55)
    if mode == "percent":
        totals = np.ones(n_categories, dtype=float) * 100.0
    else:
        if random.random() < 0.45:
            totals = totals * np.linspace(random.uniform(0.75, 0.95), random.uniform(1.05, 1.55), n_categories)
        if random.random() < 0.25:
            totals = totals[::-1]

    if family == "layered":
        start = np.random.dirichlet(np.full(n_series, random.uniform(0.9, 2.0)))
        end = np.random.dirichlet(np.full(n_series, random.uniform(0.9, 2.0)))
        matrix: list[np.ndarray] = []
        for idx, total in enumerate(totals):
            t = idx / max(1, n_categories - 1)
            fractions = (1.0 - t) * start + t * end
            fractions += np.random.normal(0.0, random.uniform(0.01, 0.05), n_series)
            fractions = np.clip(fractions, 0, None)
            if float(fractions.sum()) <= 0:
                fractions = np.full(n_series, 1.0 / n_series)
            fractions /= fractions.sum()
            matrix.append(fractions * total)
        return np.array(matrix).T

    if family == "front_loaded":
        start_alpha = np.linspace(2.4, 0.7, n_series)
        end_alpha = np.linspace(0.7, 1.8, n_series)
        matrix = []
        for idx, total in enumerate(totals):
            mix = idx / max(1, n_categories - 1)
            alpha = (1.0 - mix) * start_alpha + mix * end_alpha
            alpha = np.clip(alpha * random.uniform(0.85, 1.25), 0.18, None)
            fractions = np.random.dirichlet(alpha)
            if random.random() < 0.18:
                fractions[random.randrange(n_series)] += random.uniform(0.05, 0.18)
                fractions = np.clip(fractions, 0, None)
                fractions /= fractions.sum()
            matrix.append(fractions * total)
        return np.array(matrix).T

    if family == "back_loaded":
        start_alpha = np.linspace(0.7, 1.8, n_series)
        end_alpha = np.linspace(2.4, 0.7, n_series)
        matrix = []
        for idx, total in enumerate(totals):
            mix = idx / max(1, n_categories - 1)
            alpha = (1.0 - mix) * start_alpha + mix * end_alpha
            alpha = np.clip(alpha * random.uniform(0.85, 1.25), 0.18, None)
            fractions = np.random.dirichlet(alpha)
            if random.random() < 0.18:
                fractions[random.randrange(n_series)] += random.uniform(0.05, 0.18)
                fractions = np.clip(fractions, 0, None)
                fractions /= fractions.sum()
            matrix.append(fractions * total)
        return np.array(matrix).T

    if family == "switchback":
        start_alpha = np.linspace(2.0, 0.8, n_series)
        mid_alpha = np.roll(start_alpha[::-1], 1)
        end_alpha = np.linspace(0.8, 2.0, n_series)
        matrix = []
        for idx, total in enumerate(totals):
            mix = idx / max(1, n_categories - 1)
            if mix < 0.5:
                alpha = (1.0 - mix * 2.0) * start_alpha + (mix * 2.0) * mid_alpha
            else:
                alpha = (1.0 - (mix - 0.5) * 2.0) * mid_alpha + ((mix - 0.5) * 2.0) * end_alpha
            alpha = np.clip(alpha * random.uniform(0.85, 1.20), 0.18, None)
            fractions = np.random.dirichlet(alpha)
            if random.random() < 0.22:
                pivot = random.randrange(n_series)
                fractions[pivot] += random.uniform(0.06, 0.20)
                fractions = np.clip(fractions, 0, None)
                fractions /= fractions.sum()
            matrix.append(fractions * total)
        return np.array(matrix).T

    if family == "fragmented":
        matrix = []
        for total in totals:
            alpha = random.uniform(0.35, 0.95)
            fractions = np.random.dirichlet(np.full(n_series, alpha))
            mask = np.random.rand(n_series) < random.uniform(0.30, 0.65)
            if mask.any():
                fractions = fractions * mask
            if float(fractions.sum()) <= 0:
                fractions[random.randrange(n_series)] = 1.0
            fractions = fractions / fractions.sum()
            if random.random() < 0.38:
                fractions[random.randrange(n_series)] += random.uniform(0.10, 0.28)
                fractions = np.clip(fractions, 0, None)
                fractions /= fractions.sum()
            column = total * fractions
            if random.random() < 0.22:
                column += np.random.normal(0.0, max(float(total) * 0.01, 0.01), n_series)
                column = np.clip(column, 0, None)
            matrix.append(column)
        return np.array(matrix).T

    matrix = []
    for total in totals:
        if family == "balanced":
            alpha = random.uniform(1.5, 3.6)
            fractions = np.random.dirichlet(np.full(n_series, alpha))
        elif family == "dominant":
            alpha = random.uniform(0.40, 0.95)
            fractions = np.random.dirichlet(np.full(n_series, alpha))
            dominant_idx = random.randrange(n_series)
            fractions[dominant_idx] += random.uniform(0.20, 0.55)
            if random.random() < 0.34:
                fractions[random.randrange(n_series)] *= random.uniform(0.20, 0.60)
            fractions = np.clip(fractions, 0, None)
            fractions /= fractions.sum()
        else:
            alpha = random.uniform(0.35, 0.90)
            fractions = np.random.dirichlet(np.full(n_series, alpha))
            mask = np.random.rand(n_series) < random.uniform(0.45, 0.75)
            if mask.any():
                fractions = fractions * mask
            if float(fractions.sum()) <= 0:
                fractions[random.randrange(n_series)] = 1.0
            fractions = fractions / fractions.sum()
            if random.random() < 0.28:
                fractions[random.randrange(n_series)] += random.uniform(0.08, 0.22)
                fractions = np.clip(fractions, 0, None)
                fractions /= fractions.sum()

        column = total * fractions
        if random.random() < 0.18:
            column += np.random.normal(0.0, max(float(total) * 0.01, 0.01), n_series)
            column = np.clip(column, 0, None)
            if float(column.sum()) <= 0:
                column = np.full(n_series, float(total) / n_series)
        matrix.append(column)

    return np.array(matrix).T


def reorder_stack_categories(labels: list[str], matrix: np.ndarray, family: str, mode: str) -> tuple[list[str], np.ndarray]:
    totals = matrix.sum(axis=0)
    order = list(range(matrix.shape[1]))
    if mode == "percent":
        if random.random() < 0.45:
            order.sort(key=lambda idx: totals[idx], reverse=random.random() < 0.5)
        elif random.random() < 0.2:
            random.shuffle(order)
    else:
        if family in {"balanced", "dominant", "front_loaded", "back_loaded", "switchback"} and random.random() < 0.55:
            order.sort(key=lambda idx: totals[idx], reverse=True)
        elif family in {"layered", "fragmented"} and random.random() < 0.35:
            order.sort(key=lambda idx: totals[idx], reverse=random.random() < 0.5)
        elif random.random() < 0.18:
            random.shuffle(order)
    return [labels[i] for i in order], matrix[:, order]


def sample_config() -> dict:
    n_categories = sample_category_count()
    n_series = choose_weighted([2, 3, 4, 5, 6], [0.22, 0.27, 0.24, 0.17, 0.10])
    family = sample_stack_family()
    mode = sample_stack_mode()

    labels = [sample_category_label() for _ in range(n_categories)]
    matrix = generate_stack_matrix(n_series, n_categories, family, mode)
    labels, matrix = reorder_stack_categories(labels, matrix, family, mode)

    style = sample_canvas("barv", series_count=n_series)
    fig_w, fig_h = style["figsize"]
    max_label_len = max((len(label) for label in labels), default=8)
    fig_w = min(max(fig_w, 6.0 + 0.12 * n_categories + 0.05 * max_label_len), 11.8)
    fig_h = min(max(fig_h, 4.8 + 0.14 * n_series), 8.6)
    style["figsize"] = (fig_w, fig_h)

    bar_width = random.uniform(0.58, 0.80)
    if n_categories > 10:
        bar_width = random.uniform(0.52, 0.72)
    matrix_final = finalize_matrix(matrix)
    matrix_final_arr = np.array(matrix_final, dtype=float)
    stack_totals = matrix_final_arr.sum(axis=0)
    ylim = padded_limits(stack_totals.tolist(), include_zero=True, pad=(0.06, 0.16))
    ylim = (0.0, max(ylim[1], float(np.max(stack_totals)) * 1.06))

    if n_categories > 10 or max_label_len > 10:
        x_rotation = choose_weighted([20, 30, 40, 50, 60], [0.10, 0.22, 0.24, 0.22, 0.22])
    else:
        x_rotation = choose_weighted([0, 10, 15, 25], [0.38, 0.22, 0.20, 0.20])
    x_ha = "center" if x_rotation == 0 else "right"

    bottoms = np.cumsum(np.vstack([np.zeros(n_categories), matrix_final_arr[:-1]]), axis=0)

    return {
        "font_path": random.choice(FONT_POOL),
        "style": style,
        "family": family,
        "stack_mode": mode,
        "n_series": n_series,
        "labels": labels,
        "matrix": matrix_final,
        "bottoms": bottoms.tolist(),
        "bar_width": bar_width,
        "x_title": sample_axis_title("x", "barv"),
        "y_title": "Share (%)" if mode == "percent" else sample_axis_title("y", "barv"),
        "title": sample_title("bar"),
        "title_loc": random.choice(["left", "center"]),
        "title_weight": choose_weighted(["normal", "bold"], [0.72, 0.28]),
        "title_style": choose_weighted(["normal", "italic"], [0.85, 0.15]),
        "series_names": [sample_series_name(i) for i in range(n_series)],
        "colors": [series_color(style["series_colors"], i) for i in range(n_series)],
        "edgecolors": [
            style["text_color"] if random.random() < 0.28 else series_color(style["series_colors"], i)
            for i in range(n_series)
        ],
        "alphas": [random.uniform(0.78, 0.98) for _ in range(n_series)],
        "hatches": [None if random.random() < 0.72 else random.choice(["/", "\\", "|", "-", "+", "x", "o", "O", ".", "*"]) for _ in range(n_series)],
        "ylims": ylim,
        "x_rotation": x_rotation,
        "x_ha": x_ha,
    }


def finalize_matrix(matrix: np.ndarray) -> list[list[float | int]]:
    out: list[list[float | int]] = []
    for row in matrix:
        series: list[float | int] = []
        for value in row:
            if abs(float(value)) < 1e-12:
                series.append(0)
                continue
            rounded = human_round(float(value))
            series.append(maybe_int_or_float(float(rounded)) if isinstance(rounded, float) else rounded)
        out.append(series)
    return out


def collect_metadata(ax, cfg: dict, fig) -> tuple[list[int], list, list, list, list]:
    data_ori: list = []
    data_pixel: list = []
    data_pixel_proj_x: list = []
    data_pixel_proj_y: list = []

    origin = ax.transData.inverted().transform(ax.transAxes.transform((0, 0)))
    axes_x = origin[0]
    axes_y = origin[1]

    x = np.arange(len(cfg["labels"]))
    for i, label in enumerate(cfg["labels"]):
        for j in range(cfg["n_series"]):
            value = cfg["matrix"][j][i]
            bottom = cfg["bottoms"][j][i]
            center = bottom + value / 2.0
            data_ori.append([cfg["series_names"][j], label, value])
            point = ax.transData.transform([x[i], center]).tolist()
            data_pixel.append(point)
            data_pixel_proj_x.append(ax.transData.transform([x[i], axes_y]).tolist())
            data_pixel_proj_y.append(ax.transData.transform([axes_x, center]).tolist())

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

        x = np.arange(len(cfg["labels"]))
        for i in range(cfg["n_series"]):
            bar_kwargs = dict(
                width=cfg["bar_width"],
                color=cfg["colors"][i],
                edgecolor=cfg["edgecolors"][i],
                linewidth=random.uniform(0.6, 1.4),
                alpha=cfg["alphas"][i],
                hatch=cfg["hatches"][i],
                label=cfg["series_names"][i],
            )
            ax.bar(
                x,
                cfg["matrix"][i],
                bottom=cfg["bottoms"][i],
                align="center",
                **bar_kwargs,
            )

        ax.set_xlabel(cfg["x_title"], fontproperties=font_props, fontsize=cfg["style"]["label_size"], color=cfg["style"]["text_color"], labelpad=cfg["style"]["label_pad"])
        ax.set_ylabel(cfg["y_title"], fontproperties=font_props, fontsize=cfg["style"]["label_size"], color=cfg["style"]["text_color"], labelpad=cfg["style"]["label_pad"])
        ax.set_xticks(x)
        ax.set_xticklabels(
            cfg["labels"],
            fontproperties=font_props,
            fontsize=cfg["style"]["tick_size"],
            rotation=cfg["x_rotation"],
            ha=cfg["x_ha"],
            color=cfg["style"]["text_color"],
        )

        ax.tick_params(
            axis="x",
            which="major",
            labelsize=cfg["style"]["tick_size"],
            color=cfg["style"]["text_color"],
            length=random.choice([3, 4, 5]),
            width=random.uniform(0.7, 1.2),
            direction=random.choice(["in", "out"]),
            pad=cfg["style"]["tick_pad"],
        )
        ax.tick_params(
            axis="y",
            which="major",
            labelsize=cfg["style"]["tick_size"],
            color=cfg["style"]["text_color"],
            length=random.choice([3, 4]),
            width=random.uniform(0.7, 1.2),
            direction=random.choice(["in", "out"]),
            pad=cfg["style"]["tick_pad"],
        )

        ax.set_ylim(cfg["ylims"])
        yticks = np.linspace(cfg["ylims"][0], cfg["ylims"][1], random.randint(4, 7))
        ax.set_yticks(yticks)
        flat_abs = [abs(v) for row in cfg["matrix"] for v in row if v != 0]
        if max(abs(cfg["ylims"][0]), abs(cfg["ylims"][1])) >= 1e4 or (flat_abs and min(flat_abs) < 1e-2):
            ax.ticklabel_format(axis="y", style="sci", scilimits=(0, 0))

        if any(v < 0 for row in cfg["matrix"] for v in row):
            ax.axhline(0, color=cfg["style"]["text_color"], linewidth=1.0, alpha=0.45)

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
                axis=choose_weighted(["y", "both", "x"], [0.68, 0.22, 0.10]),
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
