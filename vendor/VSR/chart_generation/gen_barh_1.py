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
        [(6, 8), (9, 12), (13, 17), (18, 24)],
        [0.26, 0.31, 0.25, 0.18],
    )
    return random.randint(low, high)


def sample_category_label() -> str:
    kind = choose_weighted(
        ["word", "phrase", "year", "month", "quarter", "hybrid", "numeric", "code", "compound", "abbr", "slug", "ordinal", "paired"],
        [0.15, 0.19, 0.10, 0.10, 0.08, 0.15, 0.06, 0.05, 0.04, 0.03, 0.03, 0.01, 0.01],
    )
    text = sample_label(kind)
    if kind == "word" and random.random() < 0.28:
        return text.upper() if len(text) <= 4 else text.capitalize()
    if kind == "phrase" and random.random() < 0.30:
        parts = text.split()
        return " ".join(part.capitalize() for part in parts[:3])
    return text


def sample_scale() -> float:
    return choose_weighted(
        [0.1, 0.3, 1.0, 3.0, 10.0, 30.0, 100.0, 300.0, 1000.0],
        [0.03, 0.06, 0.18, 0.18, 0.18, 0.14, 0.12, 0.07, 0.04],
    ) * random.uniform(0.75, 1.35)


def finalize_values(values: list[float]) -> list[float | int]:
    out: list[float | int] = []
    for value in values:
        if abs(value) < 1e-12:
            out.append(0)
            continue
        rounded = human_round(float(value))
        out.append(maybe_int_or_float(float(rounded)) if isinstance(rounded, float) else rounded)
    return out


def make_balanced(n: int) -> list[float]:
    base = sample_scale()
    spread = random.uniform(0.12, 0.32)
    values = base * np.exp(np.random.normal(0.0, spread, n))
    if random.random() < 0.25:
        values[random.randrange(n)] *= random.uniform(1.8, 3.5)
    if random.random() < 0.18:
        values[random.randrange(n)] *= random.uniform(0.35, 0.7)
    return values.tolist()


def make_heavy_tail(n: int) -> list[float]:
    base = sample_scale()
    alpha = random.uniform(1.15, 2.0)
    values = base * (np.random.pareto(alpha, n) + 1.0)
    if random.random() < 0.7:
        values = np.sort(values)[::-1]
    if random.random() < 0.22:
        values[random.randrange(n)] *= random.uniform(2.5, 5.5)
    return values.tolist()


def make_ordered(n: int) -> list[float]:
    start = sample_scale() * random.uniform(0.45, 1.15)
    stop = start * random.uniform(1.8, 6.0)
    ascending = random.random() < 0.55
    values = np.linspace(start, stop, n)
    values += np.sin(np.linspace(0, np.pi, n)) * start * random.uniform(0.02, 0.10)
    values += np.random.normal(0.0, (stop - start) * random.uniform(0.01, 0.04), n)
    if not ascending:
        values = values[::-1]
    if random.random() < 0.12:
        values = -values
    return values.tolist()


def make_signed_mix(n: int) -> list[float]:
    scale = sample_scale()
    positive = scale * np.random.uniform(0.6, 2.0, n)
    negative = -scale * np.random.uniform(0.6, 2.0, n)
    mask = np.random.rand(n) < random.uniform(0.40, 0.65)
    values = np.where(mask, positive, negative)
    if random.random() < 0.28:
        zero_count = random.randint(1, max(1, n // 4))
        for idx in random.sample(range(n), zero_count):
            values[idx] = 0.0
    if not np.any(values > 0):
        values[random.randrange(n)] = abs(values[random.randrange(n)])
    if not np.any(values < 0):
        values[random.randrange(n)] = -abs(values[random.randrange(n)])
    return values.tolist()


def make_sparse(n: int) -> list[float]:
    scale = sample_scale()
    values = [0.0 for _ in range(n)]
    spike_count = max(2, min(n, random.randint(max(2, n // 5), max(3, n // 3))))
    for idx in random.sample(range(n), spike_count):
        mag = scale * random.uniform(0.45, 3.5)
        if random.random() < 0.35:
            mag *= random.uniform(1.8, 4.5)
        if random.random() < 0.22:
            mag = -mag
        values[idx] = mag
    for idx in range(n):
        if values[idx] == 0.0 and random.random() < 0.14:
            values[idx] = scale * random.uniform(0.04, 0.35) * random.choice([-1, 1])
    if not any(v != 0 for v in values):
        values[random.randrange(n)] = scale * random.uniform(0.8, 2.0)
    return values


def make_log_spread(n: int) -> list[float]:
    start_exp = random.uniform(-2.1, 0.0)
    stop_exp = random.uniform(1.6, 4.0)
    exps = np.linspace(start_exp, stop_exp, n)
    if random.random() < 0.5:
        exps = exps[::-1]
    values = [10 ** (exp + random.uniform(-0.12, 0.12)) for exp in exps]
    if random.random() < 0.18:
        values[random.randrange(n)] *= random.uniform(2.0, 4.5)
    if random.random() < 0.10:
        values[random.randrange(n)] *= -1
    return values


def make_clustered(n: int) -> list[float]:
    cluster_count = choose_weighted([2, 3], [0.72, 0.28])
    boundaries = sorted(random.sample(range(1, n), cluster_count - 1)) if cluster_count > 1 else []
    sizes = []
    last = 0
    for boundary in boundaries + [n]:
        sizes.append(boundary - last)
        last = boundary
    base = sample_scale()
    centers = sorted(
        base * random.uniform(0.45, 2.25) * random.choice([1, 1, 1, -1 if random.random() < 0.18 else 1])
        for _ in range(cluster_count)
    )
    values: list[float] = []
    for center, size in zip(centers, sizes):
        spread = random.uniform(0.08, 0.24)
        cluster = center * np.exp(np.random.normal(0.0, spread, size))
        if random.random() < 0.25:
            cluster[random.randrange(size)] *= random.uniform(1.4, 2.8)
        values.extend(cluster.tolist())
    return values


def make_alternating(n: int) -> list[float]:
    base = sample_scale()
    values: list[float] = []
    polarity = 1 if random.random() < 0.5 else -1
    for idx in range(n):
        magnitude = base * random.uniform(0.55, 2.1) * (1.0 + 0.16 * idx / max(1, n - 1))
        if idx % 2 == 0:
            values.append(polarity * magnitude)
        else:
            values.append(-polarity * magnitude * random.uniform(0.55, 1.0))
    if random.random() < 0.28:
        spike_idx = random.randrange(n)
        values[spike_idx] *= random.uniform(2.0, 4.2)
    return values


def make_bimodal(n: int) -> list[float]:
    split = random.randint(1, n - 1)
    left = sample_scale() * random.uniform(0.45, 1.15) * np.exp(np.random.normal(0.0, random.uniform(0.08, 0.20), split))
    right = sample_scale() * random.uniform(1.35, 3.25) * np.exp(np.random.normal(0.0, random.uniform(0.08, 0.20), n - split))
    values = np.concatenate([left, right]) if random.random() < 0.5 else np.concatenate([right, left])
    if random.random() < 0.3:
        values[random.randrange(n)] *= random.uniform(2.0, 4.5)
    return values.tolist()


def make_staircase(n: int) -> list[float]:
    step_count = choose_weighted([2, 3, 4, 5], [0.22, 0.34, 0.28, 0.16])
    step_count = min(step_count, n)
    boundaries = sorted(random.sample(range(1, n), step_count - 1)) if step_count > 1 else []
    sizes = []
    last = 0
    for boundary in boundaries + [n]:
        sizes.append(boundary - last)
        last = boundary
    ascending = random.random() < 0.55
    level = sample_scale() * random.uniform(0.35, 1.0)
    values: list[float] = []
    for idx, size in enumerate(sizes):
        if idx > 0:
            delta = sample_scale() * random.uniform(0.18, 0.95)
            level = level + delta if ascending else level - delta
        block = np.ones(size) * level + np.random.normal(0.0, max(abs(level) * 0.05, sample_scale() * 0.015), size)
        values.extend(block.tolist())
    if random.random() < 0.22:
        values[random.randrange(n)] += sample_scale() * random.uniform(0.8, 2.8)
    return values


def make_plateau(n: int) -> list[float]:
    left = sample_scale() * random.uniform(0.45, 1.05)
    plateau = left * random.uniform(1.4, 3.0)
    right = left * random.uniform(0.7, 1.4)
    start = random.randint(1, max(1, n // 3))
    end = random.randint(start + 1, n - 1) if n > 2 else n
    values = np.interp(np.arange(n), [0, start, end - 1, n - 1], [left, plateau, plateau, right])
    values += np.random.normal(0.0, sample_scale() * random.uniform(0.02, 0.07), n)
    if random.random() < 0.22:
        values[random.randrange(n)] *= random.uniform(1.6, 3.2)
    return values.tolist()


def generate_family_values(n: int, family: str) -> list[float]:
    if family == "balanced":
        values = make_balanced(n)
    elif family == "heavy_tail":
        values = make_heavy_tail(n)
    elif family == "ordered":
        values = make_ordered(n)
    elif family == "signed_mix":
        values = make_signed_mix(n)
    elif family == "sparse":
        values = make_sparse(n)
    elif family == "log_spread":
        values = make_log_spread(n)
    elif family == "clustered":
        values = make_clustered(n)
    elif family == "alternating":
        values = make_alternating(n)
    elif family == "bimodal":
        values = make_bimodal(n)
    elif family == "staircase":
        values = make_staircase(n)
    elif family == "plateau":
        values = make_plateau(n)
    else:
        values = make_balanced(n)
    return finalize_values(values)


def arrange_items(labels: list[str], values: list[float | int], family: str) -> tuple[list[str], list[float | int]]:
    items = list(zip(labels, values))
    if family in {"heavy_tail", "log_spread"}:
        if random.random() < 0.8:
            items.sort(key=lambda item: abs(float(item[1])), reverse=True)
        else:
            random.shuffle(items)
    elif family == "bimodal":
        if random.random() < 0.55:
            items.sort(key=lambda item: float(item[1]), reverse=random.random() < 0.5)
        else:
            random.shuffle(items)
    elif family == "staircase":
        items.sort(key=lambda item: float(item[1]), reverse=random.random() < 0.5)
    elif family == "plateau":
        if random.random() < 0.4:
            items.sort(key=lambda item: abs(float(item[1])), reverse=True)
    elif family == "alternating":
        if random.random() < 0.18:
            items.sort(key=lambda item: abs(float(item[1])), reverse=random.random() < 0.5)
    elif family == "ordered":
        items.sort(key=lambda item: float(item[1]), reverse=random.random() < 0.5)
    elif family == "signed_mix":
        if random.random() < 0.65:
            items.sort(key=lambda item: (float(item[1]) >= 0, abs(float(item[1]))))
        else:
            random.shuffle(items)
    elif family == "clustered":
        if random.random() < 0.3:
            items.sort(key=lambda item: abs(float(item[1])), reverse=True)
    else:
        if random.random() < 0.28:
            items.sort(key=lambda item: abs(float(item[1])), reverse=True)
        else:
            random.shuffle(items)

    if items:
        labels_out, values_out = zip(*items)
        return list(labels_out), list(values_out)
    return labels, values


def sample_config() -> dict:
    n_categories = sample_category_count()
    family = choose_weighted(
        ["balanced", "heavy_tail", "ordered", "signed_mix", "sparse", "log_spread", "clustered", "alternating", "bimodal", "staircase", "plateau"],
        [0.18, 0.15, 0.12, 0.11, 0.08, 0.08, 0.07, 0.08, 0.05, 0.04, 0.04],
    )

    labels = [sample_category_label() for _ in range(n_categories)]
    values = generate_family_values(n_categories, family)
    labels, values = arrange_items(labels, values, family)

    show_legend = random.random() < 0.24
    series_name = sample_series_name(0) if show_legend else "None"

    x_title = sample_axis_title("y", "barh")
    y_title = sample_axis_title("x", "barh")

    style = sample_canvas("barh", series_count=1)
    fig_w, fig_h = style["figsize"]
    max_label_len = max((len(label) for label in labels), default=8)
    fig_w = min(max(fig_w, 6.6 + max(0, max_label_len - 8) * 0.08), 11.6)
    fig_h = min(max(fig_h, 4.2 + 0.20 * n_categories), 9.8)
    style["figsize"] = (fig_w, fig_h)
    style["title_size"] = min(style["title_size"], 18)

    bar_height = random.uniform(0.58, 0.82)
    if n_categories > 18:
        bar_height = random.uniform(0.48, 0.68)

    flat_values = [float(v) for v in values]
    xlim = padded_limits(flat_values, include_zero=True, pad=(0.07, 0.18))
    if all(v >= 0 for v in flat_values):
        xlim = (0.0, xlim[1])
    if all(v <= 0 for v in flat_values):
        xlim = (xlim[0], 0.0)

    xerr = None
    if random.random() < 0.14:
        xerr = [abs(v) * random.uniform(0.05, 0.16) + random.uniform(0.0, 0.2) for v in flat_values]

    return {
        "font_path": random.choice(FONT_POOL),
        "style": style,
        "family": family,
        "series_name": series_name,
        "show_legend": show_legend,
        "title": sample_title("bar"),
        "title_loc": random.choice(["left", "center"]),
        "title_weight": choose_weighted(["normal", "bold"], [0.72, 0.28]),
        "title_style": choose_weighted(["normal", "italic"], [0.84, 0.16]),
        "x_title": x_title,
        "y_title": y_title,
        "labels": labels,
        "values": values,
        "bar_height": bar_height,
        "bar_color": series_color(style["series_colors"], 0),
        "edgecolor": style["text_color"] if random.random() < 0.35 else series_color(style["series_colors"], 0),
        "linewidth": random.uniform(0.65, 1.45),
        "alpha": random.uniform(0.78, 0.98),
        "hatch": None if random.random() < 0.68 else random.choice(["/", "\\", "|", "-", "+", "x", "o", "O", ".", "*"]),
        "xerr": xerr,
        "ecolor": style["text_color"] if xerr is not None and random.random() < 0.5 else series_color(style["series_colors"], 0),
        "capsize": random.randint(2, 5) if xerr is not None else None,
        "error_kw": {
            "elinewidth": random.uniform(0.8, 1.6),
            "capthick": random.uniform(0.8, 1.6),
        }
        if xerr is not None
        else None,
        "xlim": xlim,
    }


def collect_metadata(ax, cfg: dict, fig) -> tuple[list, list, list, list]:
    data_ori: list = []
    data_pixel: list = []
    data_pixel_proj_x: list = []
    data_pixel_proj_y: list = []

    origin = ax.transData.inverted().transform(ax.transAxes.transform((0, 0)))
    axes_x = origin[0]
    axes_y = origin[1]

    for idx, (label, value) in enumerate(zip(cfg["labels"], cfg["values"])):
        data_ori.append([cfg["series_name"], label, value])
        point = ax.transData.transform([value, idx]).tolist()
        data_pixel.append(point)
        data_pixel_proj_x.append(ax.transData.transform([value, axes_y]).tolist())
        data_pixel_proj_y.append(ax.transData.transform([axes_x, idx]).tolist())

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

        y = np.arange(len(cfg["values"]))
        bar_kwargs = dict(
            height=cfg["bar_height"],
            align="center",
            color=cfg["bar_color"],
            edgecolor=cfg["edgecolor"],
            linewidth=cfg["linewidth"],
            alpha=cfg["alpha"],
            hatch=cfg["hatch"],
            label=None if cfg["series_name"] == "None" else cfg["series_name"],
        )
        if cfg["xerr"] is not None:
            bar_kwargs.update(
                xerr=cfg["xerr"],
                ecolor=cfg["ecolor"],
                capsize=cfg["capsize"],
                error_kw=cfg["error_kw"],
            )
        ax.barh(y, cfg["values"], **bar_kwargs)

        ax.set_xlabel(cfg["x_title"], fontproperties=font_props, fontsize=cfg["style"]["label_size"], color=cfg["style"]["text_color"], labelpad=cfg["style"]["label_pad"])
        ax.set_ylabel(cfg["y_title"], fontproperties=font_props, fontsize=cfg["style"]["label_size"], color=cfg["style"]["text_color"], labelpad=cfg["style"]["label_pad"])
        ax.set_yticks(y)
        ax.set_yticklabels(
            cfg["labels"],
            fontproperties=font_props,
            fontsize=cfg["style"]["tick_size"],
            color=cfg["style"]["text_color"],
        )

        ax.tick_params(
            axis="x",
            which="major",
            labelsize=cfg["style"]["tick_size"],
            color=cfg["style"]["text_color"],
            length=random.choice([3, 4, 5]),
            width=random.uniform(0.7, 1.3),
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
            direction="out",
            pad=cfg["style"]["tick_pad"],
        )

        if cfg["xlim"] is not None:
            ax.set_xlim(cfg["xlim"])
            xticks = np.linspace(cfg["xlim"][0], cfg["xlim"][1], random.randint(4, 7))
            ax.set_xticks(xticks)
            if max(abs(cfg["xlim"][0]), abs(cfg["xlim"][1])) >= 1e4 or (
                0 < min(abs(v) for v in cfg["values"] if v != 0) < 1e-2
            ):
                ax.ticklabel_format(axis="x", style="sci", scilimits=(0, 0))

        if any(float(v) < 0 for v in cfg["values"]):
            ax.axvline(0, color=cfg["style"]["text_color"], linewidth=1.0, alpha=0.45)

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
                axis=choose_weighted(["x", "both", "y"], [0.68, 0.22, 0.10]),
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

        if cfg["family"] in {"ordered", "heavy_tail", "log_spread"} and random.random() < 0.65:
            ax.invert_yaxis()
        elif random.random() < 0.24:
            ax.invert_yaxis()

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
