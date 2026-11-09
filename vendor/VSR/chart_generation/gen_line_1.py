# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

import json
import os
import random
import traceback
import uuid
import warnings
from concurrent.futures import ProcessPoolExecutor
from itertools import repeat

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.font_manager import FontProperties
from tqdm import tqdm

from common import (
    MONTHS,
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
    bboxes_overlap,
    tick_label_bboxes,
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


def sample_point_count() -> int:
    low, high = choose_weighted(
        [(6, 8), (9, 12), (13, 16), (17, 22), (23, 30)],
        [0.12, 0.22, 0.24, 0.24, 0.18],
    )
    return random.randint(low, high)


def sample_series_count() -> int:
    return 1


def sample_x_mode() -> str:
    return choose_weighted(["categorical", "temporal", "numeric"], [0.48, 0.28, 0.24])


def sample_family() -> str:
    return choose_weighted(
        ["parallel_trend", "oscillating", "piecewise", "random_walk", "spike_event", "decay", "crossing", "seasonal", "mean_reverting", "logistic", "sawtooth"],
        [0.14, 0.16, 0.13, 0.13, 0.10, 0.08, 0.07, 0.05, 0.03, 0.03, 0.08],
    )


def sample_scale() -> float:
    return choose_weighted(
        [0.4, 1.0, 2.5, 6.0, 15.0, 35.0, 80.0],
        [0.05, 0.18, 0.20, 0.18, 0.16, 0.13, 0.10],
    ) * random.uniform(0.78, 1.28)


def finalize_series(series_list: list[np.ndarray]) -> list[list[float | int]]:
    out: list[list[float | int]] = []
    for series in series_list:
        values: list[float | int] = []
        for value in series:
            if abs(float(value)) < 1e-12:
                values.append(0)
                continue
            rounded = human_round(float(value))
            values.append(maybe_int_or_float(float(rounded)) if isinstance(rounded, float) else rounded)
        out.append(values)
    return out


def build_x_axis(n_points: int, mode: str) -> tuple[list[float], list[str], list[float], list[str]]:
    if mode == "categorical":
        x = list(range(n_points))
        label_kind = choose_weighted(
            ["word", "phrase", "month", "quarter", "year", "hybrid", "code", "compound", "abbr", "slug"],
            [0.17, 0.17, 0.16, 0.14, 0.12, 0.12, 0.04, 0.04, 0.02, 0.02],
        )
        labels = [sample_label(label_kind) for _ in range(n_points)]
        step = 1 if n_points <= 10 else 2 if n_points <= 16 else 3
        tick_positions = [x[i] for i in range(0, n_points, step)]
        tick_labels = [labels[i] for i in range(0, n_points, step)]
        if tick_positions[-1] != x[-1]:
            tick_positions.append(x[-1])
            tick_labels.append(labels[-1])
        return x, labels, tick_positions, tick_labels

    if mode == "temporal":
        granularity = choose_weighted(["month", "quarter", "year"], [0.56, 0.24, 0.20])
        if granularity == "month":
            start_year = random.randint(2018, 2026)
            start_month = random.randint(0, 11)
            x = list(range(n_points))
            labels = []
            for i in range(n_points):
                idx = start_month + i
                labels.append(f"{MONTHS[idx % 12]} {start_year + idx // 12}")
        elif granularity == "quarter":
            start_year = random.randint(2018, 2026)
            start_quarter = random.randint(0, 3)
            x = list(range(n_points))
            labels = []
            for i in range(n_points):
                idx = start_quarter + i
                labels.append(f"Q{idx % 4 + 1} {start_year + idx // 4}")
        else:
            start_year = random.randint(2012, 2022)
            x = list(range(n_points))
            labels = [str(start_year + i) for i in range(n_points)]
        step = 1 if n_points <= 10 else 2 if n_points <= 16 else 3
        tick_positions = [x[i] for i in range(0, n_points, step)]
        tick_labels = [labels[i] for i in range(0, n_points, step)]
        if tick_positions[-1] != x[-1]:
            tick_positions.append(x[-1])
            tick_labels.append(labels[-1])
        return x, labels, tick_positions, tick_labels

    start = sample_scale() * random.uniform(0.2, 1.4)
    steps = np.abs(np.random.lognormal(mean=0.0, sigma=random.uniform(0.08, 0.28), size=n_points - 1))
    steps *= sample_scale() * random.uniform(0.4, 2.2)
    x_values = [start]
    for step in steps:
        x_values.append(x_values[-1] + float(step))
    if random.random() < 0.24:
        offset = float(np.mean(x_values))
        x_values = [x - offset for x in x_values]
    x_values = [float(human_round(x)) if abs(x) < 1e4 else float(human_round(x)) for x in x_values]

    tick_count = min(n_points, random.randint(4, 7))
    tick_positions = np.linspace(min(x_values), max(x_values), tick_count).tolist()
    tick_labels = []
    for value in tick_positions:
        rounded = human_round(float(value))
        tick_labels.append(str(maybe_int_or_float(float(rounded)) if isinstance(rounded, float) else rounded))
    labels = [str(maybe_int_or_float(v) if abs(v - round(v)) < 1e-8 else round(v, 2)) for v in x_values]
    return x_values, labels, tick_positions, tick_labels


def _thin_ticks(positions: list[float], labels: list[str], step: int) -> tuple[list[float], list[str]]:
    step = max(1, int(step))
    if step <= 1 or len(positions) <= 2:
        return positions, labels
    indices = list(range(0, len(positions), step))
    if indices[-1] != len(positions) - 1:
        indices.append(len(positions) - 1)
    return [positions[i] for i in indices], [labels[i] for i in indices]


def _apply_xticks(ax, font_props, cfg: dict, positions: list[float], labels: list[str], rotation: int, ha: str, tick_size: int | None = None) -> None:
    ax.set_xticks(positions)
    ax.set_xticklabels(
        labels,
        fontproperties=font_props,
        fontsize=tick_size if tick_size is not None else cfg["style"]["tick_size"],
        rotation=rotation,
        ha=ha,
        color=cfg["style"]["text_color"],
    )


def _tight_layout(fig, rect=None) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        if rect is None:
            fig.tight_layout()
        else:
            fig.tight_layout(rect=rect)


def _layout_has_xtick_overlap(fig, ax) -> bool:
    return bboxes_overlap(tick_label_bboxes(ax, fig, axis="x"))


def resolve_xtick_layout(fig, ax, font_props, cfg: dict) -> tuple[list[float], list[str], int, str, int]:
    base_positions = list(cfg["tick_positions"])
    base_labels = list(cfg["tick_labels"])
    if not base_positions:
        return base_positions, base_labels, cfg["x_rotation"], cfg["x_ha"], cfg["style"]["tick_size"]

    max_label_len = max((len(str(label)) for label in base_labels), default=0)
    base_tick_size = cfg["style"]["tick_size"]

    step_candidates = [1]
    if len(base_labels) > 6 or max_label_len > 12:
        step_candidates.append(2)
    if len(base_labels) > 8 or max_label_len > 18:
        step_candidates.append(3)
    if len(base_labels) > 10 or max_label_len > 24:
        step_candidates.append(4)
    if len(base_labels) > 12 or max_label_len > 30:
        step_candidates.append(5)

    rotation_candidates: list[int] = []
    for rotation in [cfg["x_rotation"], 0, 15, 20, 30, 45, 60]:
        if rotation not in rotation_candidates:
            rotation_candidates.append(rotation)
    if max_label_len > 14 and 0 in rotation_candidates:
        rotation_candidates = [r for r in rotation_candidates if r != 0] + [0]

    for step in step_candidates:
        positions, labels = _thin_ticks(base_positions, base_labels, step)
        if not positions:
            continue
        tick_size = max(7, base_tick_size - 1) if step >= 3 else base_tick_size
        tick_size = max(7, tick_size - 1) if step >= 4 else tick_size
        for rotation in rotation_candidates:
            ha = "center" if rotation == 0 else "right"
            _apply_xticks(ax, font_props, cfg, positions, labels, rotation, ha, tick_size=tick_size)
            _tight_layout(fig, rect=cfg["style"]["layout_rect"])
            if not _layout_has_xtick_overlap(fig, ax):
                return positions, labels, rotation, ha, tick_size

    for fallback_count in [4, 3, 2, 1]:
        if len(base_positions) < fallback_count:
            continue
        if fallback_count == 1:
            indices = [len(base_positions) // 2]
        else:
            indices = np.linspace(0, len(base_positions) - 1, fallback_count, dtype=int).tolist()
        positions = [base_positions[i] for i in indices]
        labels = [base_labels[i] for i in indices]
        for rotation in [45, 60]:
            ha = "right"
            tick_size = max(7, base_tick_size - 2)
            _apply_xticks(ax, font_props, cfg, positions, labels, rotation, ha, tick_size=tick_size)
            _tight_layout(fig, rect=cfg["style"]["layout_rect"])
            if not _layout_has_xtick_overlap(fig, ax):
                return positions, labels, rotation, ha, tick_size

    return base_positions, base_labels, cfg["x_rotation"], cfg["x_ha"], base_tick_size


def make_base_curve(n: int, family: str) -> np.ndarray:
    t = np.linspace(0.0, 1.0, n)
    if family == "parallel_trend":
        mode = choose_weighted(["rise", "fall", "flat", "curve", "sawtooth"], [0.28, 0.22, 0.22, 0.18, 0.10])
        if mode == "rise":
            base = 0.7 + 1.6 * t
        elif mode == "fall":
            base = 2.0 - 1.3 * t
        elif mode == "flat":
            base = np.ones(n) * random.uniform(0.9, 1.6)
        else:
            base = 0.8 + 0.7 * np.sin(np.pi * t) ** 2 + 0.35 * t
        return base * sample_scale()

    if family == "crossing":
        base = (t - 0.5) * sample_scale() * 1.6
        base += np.sin(np.pi * t) * sample_scale() * 0.12
        return base

    if family == "oscillating":
        freq = random.uniform(0.9, 2.6)
        phase = random.uniform(0, np.pi)
        trend = (t - 0.5) * sample_scale() * random.uniform(-0.2, 0.4)
        return np.sin(2 * np.pi * freq * t + phase) * sample_scale() + trend

    if family == "piecewise":
        break_count = random.randint(1, min(3, max(1, n - 2)))
        breakpoints = sorted(random.sample(range(1, n - 1), break_count))
        control_x = [0] + breakpoints + [n - 1]
        control_y = []
        level = random.uniform(0.4, 1.2) * sample_scale()
        for idx in range(len(control_x)):
            if idx == 0:
                control_y.append(level)
            else:
                level += random.uniform(-0.45, 0.75) * sample_scale()
                control_y.append(level)
        base = np.interp(np.arange(n), control_x, control_y)
        return base

    if family == "random_walk":
        drift = random.uniform(-0.16, 0.18) * sample_scale()
        steps = np.random.normal(drift, sample_scale() * random.uniform(0.08, 0.22), n)
        return np.cumsum(steps)

    if family == "spike_event":
        baseline = np.ones(n) * random.uniform(0.5, 1.6) * sample_scale()
        baseline += (t - 0.5) * sample_scale() * random.uniform(-0.25, 0.25)
        spikes = np.zeros(n)
        for idx in random.sample(range(n), random.randint(1, max(1, n // 4))):
            spikes[idx] += sample_scale() * random.uniform(0.8, 2.6) * random.choice([-1, 1])
        return baseline + spikes

    if family == "sawtooth":
        cycles = random.uniform(2.0, 5.0)
        phase = random.uniform(0.0, 1.0)
        raw = np.mod(t * cycles + phase, 1.0)
        raw = raw if random.random() < 0.5 else 1.0 - raw
        base = 0.42 + raw * random.uniform(0.85, 1.25)
        if random.random() < 0.45:
            base += (t - 0.5) * random.uniform(-0.3, 0.35)
        return base * sample_scale()

    if family == "seasonal":
        freq = random.uniform(0.8, 2.4)
        phase = random.uniform(0, np.pi)
        base = 1.0 + 0.28 * np.sin(2 * np.pi * freq * t + phase) + 0.12 * np.sin(4 * np.pi * freq * t + phase / 2)
        if random.random() < 0.55:
            base += (t - 0.5) * random.uniform(-0.3, 0.5)
        return base * sample_scale()

    if family == "logistic":
        slope = random.uniform(4.0, 10.0)
        midpoint = random.uniform(0.25, 0.75)
        direction = random.choice([-1, 1])
        base = 1.0 / (1.0 + np.exp(-direction * slope * (t - midpoint)))
        return (0.35 + 1.25 * base) * sample_scale()

    if family == "mean_reverting":
        return np.ones(n) * sample_scale() * random.uniform(0.85, 1.45)

    if family == "sawtooth":
        cycles = random.uniform(2.0, 5.0)
        phase = random.uniform(0.0, 1.0)
        raw = np.mod(t * cycles + phase, 1.0)
        raw = raw if random.random() < 0.5 else 1.0 - raw
        base = 0.42 + raw * random.uniform(0.85, 1.25)
        if random.random() < 0.45:
            base += (t - 0.5) * random.uniform(-0.3, 0.35)
        return base * sample_scale()

    return np.ones(n) * sample_scale()


def generate_matrix(n_series: int, n_points: int, family: str) -> np.ndarray:
    t = np.linspace(0.0, 1.0, n_points)
    base = make_base_curve(n_points, family)
    matrix: list[np.ndarray] = []

    if family == "parallel_trend":
        for _ in range(n_series):
            scale = random.uniform(0.84, 1.18)
            offset = float(base.mean()) * random.uniform(-0.16, 0.18)
            noise = np.random.normal(0.0, max(float(np.std(base)) * random.uniform(0.03, 0.07), sample_scale() * 0.015), n_points)
            matrix.append(base * scale + offset + noise)
    elif family == "crossing":
        slopes = np.linspace(-1.0, 1.0, n_series) + np.random.normal(0.0, 0.12, n_series)
        amp = max(float(np.abs(base).mean()), sample_scale())
        centered = base - float(base.mean())
        for slope in slopes:
            intercept = amp * random.uniform(0.65, 1.35)
            noise = np.random.normal(0.0, amp * random.uniform(0.03, 0.08), n_points)
            matrix.append(intercept + slope * (t - 0.5) * amp * random.uniform(0.9, 1.7) + centered * random.uniform(0.25, 0.55) + noise)
    elif family == "oscillating":
        for s in range(n_series):
            phase = random.uniform(0, np.pi) + s * random.uniform(0.25, 0.9)
            amp = random.uniform(0.75, 1.35) * sample_scale()
            freq = random.uniform(0.8, 2.2)
            trend = (t - 0.5) * sample_scale() * random.uniform(-0.18, 0.35)
            noise = np.random.normal(0.0, amp * random.uniform(0.02, 0.07), n_points)
            matrix.append(np.sin(2 * np.pi * freq * t + phase) * amp + trend + noise)
    elif family == "piecewise":
        breakpoints = sorted(random.sample(range(1, n_points - 1), random.randint(1, min(3, n_points - 2))))
        control_x = [0] + breakpoints + [n_points - 1]
        for s in range(n_series):
            control_y = []
            level = random.uniform(0.5, 1.3) * sample_scale()
            for idx in range(len(control_x)):
                if idx == 0:
                    control_y.append(level)
                else:
                    level += random.uniform(-0.6, 0.8) * sample_scale()
                    control_y.append(level + s * random.uniform(-0.18, 0.18) * sample_scale())
            base_series = np.interp(np.arange(n_points), control_x, control_y)
            if random.random() < 0.4 and n_points >= 3:
                start = random.randint(0, max(0, n_points - 3))
                stop = random.randint(start + 2, n_points)
                plateau = slice(start, stop)
                base_series[plateau] = np.mean(base_series[plateau])
            matrix.append(base_series + np.random.normal(0.0, sample_scale() * random.uniform(0.02, 0.07), n_points))
    elif family == "random_walk":
        for _ in range(n_series):
            drift = random.uniform(-0.18, 0.18) * sample_scale()
            steps = np.random.normal(drift, sample_scale() * random.uniform(0.08, 0.20), n_points)
            series = np.cumsum(steps)
            if random.random() < 0.4:
                series += np.linspace(0, sample_scale() * random.uniform(-0.3, 0.3), n_points)
            matrix.append(series)
    elif family == "spike_event":
        spike_positions = sorted(random.sample(range(n_points), random.randint(1, max(1, n_points // 3))))
        for _ in range(n_series):
            baseline = np.ones(n_points) * random.uniform(0.4, 1.4) * sample_scale()
            baseline += (t - 0.5) * sample_scale() * random.uniform(-0.2, 0.3)
            series = baseline + np.random.normal(0.0, sample_scale() * random.uniform(0.03, 0.08), n_points)
            for pos in spike_positions:
                series[pos] += sample_scale() * random.uniform(0.7, 2.8) * random.choice([-1, 1])
            if random.random() < 0.35:
                extra_pos = random.randrange(n_points)
                series[extra_pos] += sample_scale() * random.uniform(1.5, 3.5)
            matrix.append(series)
    elif family == "sawtooth":
        cycles = random.uniform(2.0, 5.0)
        base_phase = random.uniform(0.0, 1.0)
        for s in range(n_series):
            phase = base_phase + s * random.uniform(0.08, 0.35)
            raw = np.mod(t * cycles + phase, 1.0)
            raw = raw if random.random() < 0.5 else 1.0 - raw
            series = (0.42 + raw * random.uniform(0.85, 1.25)) * sample_scale() * random.uniform(0.8, 1.25)
            if random.random() < 0.45:
                series += (t - 0.5) * sample_scale() * random.uniform(-0.15, 0.3)
            matrix.append(series + np.random.normal(0.0, sample_scale() * random.uniform(0.02, 0.06), n_points))
    elif family == "seasonal":
        for s in range(n_series):
            freq = random.uniform(0.8, 2.5)
            phase = random.uniform(0, np.pi) + s * random.uniform(0.18, 0.8)
            amp = random.uniform(0.75, 1.35) * sample_scale()
            series = np.sin(2 * np.pi * freq * t + phase) * amp
            series += 0.35 * np.sin(4 * np.pi * freq * t + phase / 2) * amp
            if random.random() < 0.6:
                series += (t - 0.5) * sample_scale() * random.uniform(-0.25, 0.45)
            matrix.append(series + np.random.normal(0.0, amp * random.uniform(0.02, 0.07), n_points))
    elif family == "mean_reverting":
        for _ in range(n_series):
            mean_level = sample_scale() * random.uniform(0.6, 1.8)
            theta = random.uniform(0.12, 0.28)
            noise_scale = sample_scale() * random.uniform(0.05, 0.16)
            series = np.empty(n_points)
            series[0] = mean_level + random.uniform(-0.6, 0.6) * mean_level
            for idx in range(1, n_points):
                series[idx] = series[idx - 1] + theta * (mean_level - series[idx - 1]) + np.random.normal(0.0, noise_scale)
            if random.random() < 0.35:
                series += np.linspace(0.0, sample_scale() * random.uniform(-0.25, 0.25), n_points)
            matrix.append(series)
    elif family == "logistic":
        for _ in range(n_series):
            slope = random.uniform(4.0, 10.0)
            midpoint = random.uniform(0.25, 0.75)
            direction = random.choice([-1, 1])
            curve = 1.0 / (1.0 + np.exp(-direction * slope * (t - midpoint)))
            curve = (0.35 + 1.25 * curve) * sample_scale()
            if random.random() < 0.4:
                curve += np.sin(2 * np.pi * random.uniform(0.8, 2.2) * t + random.uniform(0, np.pi)) * sample_scale() * random.uniform(0.04, 0.14)
            matrix.append(curve + np.random.normal(0.0, sample_scale() * random.uniform(0.02, 0.06), n_points))
    elif family == "decay":
        for _ in range(n_series):
            start = sample_scale() * random.uniform(0.8, 1.8)
            decay_rate = random.uniform(1.2, 4.5)
            series = start * np.exp(-decay_rate * t)
            if random.random() < 0.5:
                series = series[::-1]
            if random.random() < 0.45:
                series += np.sin(2 * np.pi * random.uniform(0.8, 2.6) * t + random.uniform(0, np.pi)) * sample_scale() * random.uniform(0.05, 0.18)
            if random.random() < 0.3:
                series += np.linspace(0.0, sample_scale() * random.uniform(-0.25, 0.25), n_points)
            matrix.append(series + np.random.normal(0.0, sample_scale() * random.uniform(0.02, 0.07), n_points))
    else:
        return generate_matrix(n_series, n_points, "parallel_trend")

    return np.array(matrix)


def finalize_x_numeric(x_values: list[float]) -> list[float | int]:
    out: list[float | int] = []
    for value in x_values:
        if abs(value) < 1e-12:
            out.append(0)
            continue
        rounded = human_round(float(value))
        out.append(maybe_int_or_float(float(rounded)) if isinstance(rounded, float) else rounded)
    return out


def sample_config() -> dict:
    n_points = sample_point_count()
    n_series = sample_series_count()
    family = sample_family()
    x_mode = sample_x_mode()

    x_values, x_labels, tick_positions, tick_labels = build_x_axis(n_points, x_mode)
    max_tick_label_len = max((len(label) for label in tick_labels), default=0)
    if x_mode != "numeric":
        extra_step = 1
        if max_tick_label_len > 12 or len(tick_labels) > 6:
            extra_step = 2
        if max_tick_label_len > 18 or len(tick_labels) > 8:
            extra_step = 3
        if max_tick_label_len > 24 or len(tick_labels) > 10:
            extra_step = 4
        if extra_step > 1:
            tick_positions, tick_labels = _thin_ticks(tick_positions, tick_labels, extra_step)
    matrix = generate_matrix(n_series, n_points, family)
    matrix = finalize_series(matrix)

    style = sample_canvas("line", series_count=n_series)
    fig_w, fig_h = style["figsize"]
    fig_w = min(max(fig_w, 6.2 + 0.16 * n_points + 0.06 * max_tick_label_len), 12.2)
    fig_h = min(max(fig_h, 4.4 + 0.08 * n_series), 8.4)
    style["figsize"] = (fig_w, fig_h)

    flat_values = [float(v) for row in matrix for v in row]
    ylim = padded_limits(flat_values, include_zero=False, pad=(0.06, 0.14))
    if all(v >= 0 for v in flat_values) and family in {"parallel_trend", "piecewise", "spike_event"} and random.random() < 0.42:
        ylim = (0.0, ylim[1])

    if x_mode == "numeric":
        xlim = padded_limits(x_values, include_zero=False, pad=(0.05, 0.12))
    else:
        xlim = (-0.5, n_points - 0.5)

    marker_choices = [None, "o", "s", "^", "D", "v", "<", ">", "p", "*", "x", "."]
    line_styles = ["-", "-", "-", "-", "--", "-.", ":"]
    markers = []
    styles = []
    marker_sizes = []
    markevery = []
    alphas = []
    widths = []
    for _ in range(n_series):
        marker = choose_weighted(marker_choices, [0.40, 0.16, 0.10, 0.08, 0.07, 0.07, 0.04, 0.03, 0.02, 0.01, 0.01, 0.01])
        if marker is None and random.random() < 0.35:
            marker = None
        markers.append(marker)
        styles.append(random.choice(line_styles))
        marker_sizes.append(random.uniform(4.0, 8.5) if n_points <= 16 else random.uniform(3.5, 6.5))
        markevery.append(None if marker is None or n_points <= 9 else random.randint(2, 4))
        alphas.append(random.uniform(0.82, 0.98))
        widths.append(random.uniform(1.25, 2.3))

    if x_mode == "numeric":
        x_rotation = choose_weighted([0, 15, 30, 45], [0.4, 0.25, 0.2, 0.15])
    elif max_tick_label_len > 18 or len(tick_labels) > 8:
        x_rotation = choose_weighted([30, 45, 60], [0.18, 0.34, 0.48])
    elif max_tick_label_len > 12 or len(tick_labels) > 6:
        x_rotation = choose_weighted([15, 30, 45], [0.22, 0.38, 0.40])
    else:
        x_rotation = choose_weighted([0, 15, 30], [0.46, 0.32, 0.22])
    x_ha = "center" if x_rotation == 0 else "right"

    return {
        "font_path": random.choice(FONT_POOL),
        "style": style,
        "family": family,
        "x_mode": x_mode,
        "n_series": n_series,
        "show_legend": random.random() < 0.18,
        "x_values": finalize_x_numeric(x_values) if x_mode == "numeric" else x_values,
        "x_labels": x_labels,
        "tick_positions": tick_positions,
        "tick_labels": tick_labels,
        "matrix": matrix,
        "x_title": sample_axis_title("x", "line"),
        "y_title": sample_axis_title("y", "line"),
        "title": sample_title("line"),
        "title_loc": random.choice(["left", "center"]),
        "title_weight": choose_weighted(["normal", "bold"], [0.74, 0.26]),
        "title_style": choose_weighted(["normal", "italic"], [0.86, 0.14]),
        "series_names": [sample_series_name(i) for i in range(n_series)],
        "colors": [series_color(style["series_colors"], i) for i in range(n_series)],
        "markers": markers,
        "linestyles": styles,
        "marker_sizes": marker_sizes,
        "markevery": markevery,
        "alphas": alphas,
        "widths": widths,
        "ylim": ylim,
        "xlim": xlim,
        "x_rotation": x_rotation,
        "x_ha": x_ha,
        "grid_axis": choose_weighted(["y", "both", "x"], [0.50, 0.35, 0.15]) if x_mode == "numeric" else choose_weighted(["y", "both", "x"], [0.62, 0.25, 0.13]),
    }


def collect_metadata(ax, cfg: dict, fig) -> tuple[list[int], list, list, list, list]:
    data_ori: list = []
    data_pixel: list = []
    data_pixel_proj_x: list = []
    data_pixel_proj_y: list = []

    origin = ax.transData.inverted().transform(ax.transAxes.transform((0, 0)))
    axes_x = origin[0]
    axes_y = origin[1]

    if cfg["x_mode"] == "numeric":
        x_values = cfg["x_values"]
    else:
        x_values = list(range(len(cfg["x_labels"])))

    for i in range(len(cfg["x_labels"])):
        x_item = cfg["x_labels"][i] if cfg["x_mode"] != "numeric" else x_values[i]
        for j in range(cfg["n_series"]):
            y_item = cfg["matrix"][j][i]
            data_ori.append([cfg["series_names"][j], x_item, y_item])
            point = ax.transData.transform([x_values[i], y_item]).tolist()
            data_pixel.append(point)
            data_pixel_proj_x.append(ax.transData.transform([x_values[i], axes_y]).tolist())
            data_pixel_proj_y.append(ax.transData.transform([axes_x, y_item]).tolist())

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

        if cfg["x_mode"] == "numeric":
            x_plot = np.array(cfg["x_values"], dtype=float)
        else:
            x_plot = np.arange(len(cfg["x_labels"]), dtype=float)

        for i in range(cfg["n_series"]):
            ax.plot(
                x_plot,
                cfg["matrix"][i],
                color=cfg["colors"][i],
                linewidth=cfg["widths"][i],
                linestyle=cfg["linestyles"][i],
                alpha=cfg["alphas"][i],
                marker=cfg["markers"][i],
                markersize=cfg["marker_sizes"][i],
                markevery=cfg["markevery"][i],
                label=cfg["series_names"][i],
            )

        ax.set_xlabel(cfg["x_title"], fontproperties=font_props, fontsize=cfg["style"]["label_size"], color=cfg["style"]["text_color"], labelpad=cfg["style"]["label_pad"])
        ax.set_ylabel(cfg["y_title"], fontproperties=font_props, fontsize=cfg["style"]["label_size"], color=cfg["style"]["text_color"], labelpad=cfg["style"]["label_pad"])

        if cfg["x_mode"] == "numeric":
            ax.set_xlim(cfg["xlim"])
            ax.set_xticks(cfg["tick_positions"])
            ax.set_xticklabels(cfg["tick_labels"], fontproperties=font_props, fontsize=cfg["style"]["tick_size"], rotation=cfg["x_rotation"], ha=cfg["x_ha"], color=cfg["style"]["text_color"])
            nonzero_x = [abs(float(v)) for v in cfg["x_values"] if float(v) != 0]
            if max(abs(cfg["xlim"][0]), abs(cfg["xlim"][1])) >= 1e4 or (nonzero_x and min(nonzero_x) < 1e-2):
                ax.ticklabel_format(axis="x", style="sci", scilimits=(0, 0))
        else:
            ax.set_xlim(cfg["xlim"])
            ax.set_xticks(cfg["tick_positions"])
            ax.set_xticklabels(cfg["tick_labels"], fontproperties=font_props, fontsize=cfg["style"]["tick_size"], rotation=cfg["x_rotation"], ha=cfg["x_ha"], color=cfg["style"]["text_color"])

        ax.set_ylim(cfg["ylim"])
        yticks = np.linspace(cfg["ylim"][0], cfg["ylim"][1], random.randint(4, 7))
        ax.set_yticks(yticks)
        nonzero_y = [abs(v) for row in cfg["matrix"] for v in row if v != 0]
        if max(abs(cfg["ylim"][0]), abs(cfg["ylim"][1])) >= 1e4 or (nonzero_y and min(nonzero_y) < 1e-2):
            ax.ticklabel_format(axis="y", style="sci", scilimits=(0, 0))

        ax.tick_params(
            axis="y",
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

        if random.random() < 0.22:
            ax.axhline(0, color=cfg["style"]["text_color"], linewidth=1.0, alpha=0.35)

        resolve_xtick_layout(fig, ax, font_props, cfg)

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
