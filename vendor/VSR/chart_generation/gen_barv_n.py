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
    elif family == "bimodal":
        centers = np.sort(np.random.uniform(-0.7, 0.7, 2))
        bump_width = random.uniform(0.18, 0.34)
        shape = np.zeros(n_categories)
        for center in centers:
            shape += np.exp(-((t - center) / bump_width) ** 2)
        shape /= max(float(shape.max()), 1e-6)
        for _ in range(n_series):
            scale = random.uniform(0.55, 1.55)
            offset = float(base.mean()) * random.uniform(-0.10, 0.14)
            series = shape * sample_scale() * random.uniform(0.9, 1.6) * scale + offset
            series += np.random.normal(0.0, sample_scale() * random.uniform(0.02, 0.06), n_categories)
            if random.random() < 0.30:
                series = np.roll(series, random.randint(-1, 1))
            matrix.append(series)
    elif family == "staircase":
        step_count = min(choose_weighted([2, 3, 4, 5], [0.24, 0.32, 0.26, 0.18]), n_categories)
        boundaries = sorted(random.sample(range(1, n_categories), step_count - 1)) if step_count > 1 else []
        sizes = []
        last = 0
        for boundary in boundaries + [n_categories]:
            sizes.append(boundary - last)
            last = boundary
        start_level = sample_scale() * random.uniform(0.35, 1.0)
        end_level = start_level + sample_scale() * random.uniform(0.8, 3.2)
        levels = np.linspace(start_level, end_level, step_count)
        if random.random() < 0.5:
            levels = levels[::-1]
        for _ in range(n_series):
            series: list[float] = []
            for level, size in zip(levels, sizes):
                block = np.ones(size) * level + np.random.normal(0.0, max(abs(level) * 0.05, sample_scale() * 0.015), size)
                series.extend(block.tolist())
            if len(series) < n_categories:
                series.extend([series[-1]] * (n_categories - len(series)))
            series = series[:n_categories]
            if random.random() < 0.26:
                series[random.randrange(n_categories)] += sample_scale() * random.uniform(0.8, 2.8)
            matrix.append(np.array(series))
    elif family == "plateau":
        left = sample_scale() * random.uniform(0.45, 1.05)
        plateau = left * random.uniform(1.4, 3.0)
        right = left * random.uniform(0.7, 1.4)
        start = random.randint(1, max(1, n_categories // 3))
        end = random.randint(max(start + 1, n_categories // 2), max(start + 1, n_categories - 1)) if n_categories > 2 else n_categories
        shape = np.interp(np.arange(n_categories), [0, start, max(start + 1, end - 1), n_categories - 1], [left, plateau, plateau, right])
        for _ in range(n_series):
            scale = random.uniform(0.65, 1.35)
            offset = float(base.mean()) * random.uniform(-0.10, 0.10)
            series = shape * scale + offset + np.random.normal(0.0, sample_scale() * random.uniform(0.02, 0.06), n_categories)
            if random.random() < 0.22:
                series[random.randrange(n_categories)] += sample_scale() * random.uniform(0.7, 2.2)
            matrix.append(series)
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
    elif family in {"bimodal", "staircase", "plateau"}:
        if random.random() < 0.45:
            order.sort(key=lambda idx: totals[idx], reverse=random.random() < 0.5)
        elif random.random() < 0.2:
            random.shuffle(order)
    else:
        if random.random() < 0.25:
            random.shuffle(order)

    labels_out = [labels[i] for i in order]
    matrix_out = matrix[:, order]
    return labels_out, matrix_out


def sample_config() -> dict:
    n_categories = sample_category_count()
    n_series = sample_series_count()
    family = choose_weighted(
        ["parallel", "crossing", "dominant", "mixed_scale", "composition", "sparse", "signed", "alternating", "bimodal", "staircase", "plateau"],
        [0.18, 0.15, 0.12, 0.11, 0.10, 0.08, 0.08, 0.08, 0.04, 0.03, 0.03],
    )

    labels = [sample_category_label() for _ in range(n_categories)]
    matrix = generate_matrix(n_series, n_categories, family)
    labels, matrix = reorder_categories(labels, matrix, family)

    style = sample_canvas("barv", series_count=n_series)
    fig_w, fig_h = style["figsize"]
    max_label_len = max((len(label) for label in labels), default=8)
    fig_w = min(max(fig_w, 6.0 + 0.18 * n_categories + 0.05 * max_label_len), 11.5)
    fig_h = min(max(fig_h, 4.8 + 0.10 * n_series), 8.2)
    style["figsize"] = (fig_w, fig_h)

    group_width = random.uniform(0.68, 0.84)
    bar_width = group_width / (n_series + 0.25)
    offsets = [(i - (n_series - 1) / 2) * bar_width for i in range(n_series)]

    flat_values = [float(v) for v in matrix.flatten()]
    ylim = padded_limits(flat_values, include_zero=True, pad=(0.07, 0.18))
    if all(v >= 0 for v in flat_values):
        ylim = (0.0, ylim[1])
    if all(v <= 0 for v in flat_values):
        ylim = (ylim[0], 0.0)

    if n_categories > 8 or max_label_len > 8:
        x_rotation = choose_weighted([20, 30, 40, 50, 60], [0.14, 0.22, 0.24, 0.22, 0.18])
    else:
        x_rotation = choose_weighted([0, 10, 15, 25], [0.34, 0.22, 0.22, 0.22])
    x_ha = "center" if x_rotation == 0 else "right"

    yerr = None
    error_kw = None
    if random.random() < 0.16:
        yerr = []
        for series in matrix:
            errs = [abs(v) * random.uniform(0.05, 0.14) + random.uniform(0.0, 0.25) for v in series]
            yerr.append(errs)
        error_kw = {
            "elinewidth": random.uniform(0.8, 1.5),
            "capthick": random.uniform(0.8, 1.5),
        }

    return {
        "font_path": random.choice(FONT_POOL),
        "style": style,
        "family": family,
        "n_series": n_series,
        "labels": labels,
        "matrix": finalize_matrix(matrix),
        "group_width": group_width,
        "bar_width": bar_width,
        "offsets": offsets,
        "x_title": sample_axis_title("x", "barv"),
        "y_title": sample_axis_title("y", "barv"),
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
        "show_error": yerr is not None,
        "yerr": yerr,
        "error_kw": error_kw,
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
            data_ori.append([cfg["series_names"][j], label, value])
            point = ax.transData.transform([x[i] + cfg["offsets"][j], value]).tolist()
            data_pixel.append(point)
            data_pixel_proj_x.append(ax.transData.transform([x[i] + cfg["offsets"][j], axes_y]).tolist())
            data_pixel_proj_y.append(ax.transData.transform([axes_x, value]).tolist())

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
            if cfg["show_error"]:
                bar_kwargs.update(
                    yerr=cfg["yerr"][i],
                    error_kw=cfg["error_kw"],
                    capsize=random.randint(2, 5),
                    ecolor=cfg["style"]["text_color"] if random.random() < 0.55 else cfg["colors"][i],
                )
            ax.bar(
                x + cfg["offsets"][i],
                cfg["matrix"][i],
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
            axis="y",
            which="major",
            labelsize=cfg["style"]["tick_size"],
            color=cfg["style"]["text_color"],
            length=random.choice([3, 4, 5]),
            width=random.uniform(0.7, 1.3),
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
