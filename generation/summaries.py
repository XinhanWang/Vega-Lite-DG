"""Pie observations and precomputed Tukey summaries from independent RNGs."""
from pathlib import Path
from decimal import Decimal
import math
import re

import numpy as np

from . import GENERATOR_VERSION
from .controls import FAMILIES
from .style_rules import REQUIRED_FONT_FILES
from .styles import canvas


def canonical_numbers(value):
    """Clean repeated binary tails within one ULP, without a precision ceiling."""
    if isinstance(value, dict):
        return {key: canonical_numbers(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [canonical_numbers(item) for item in value]
    if isinstance(value, (float, np.floating)):
        if not math.isfinite(value):
            raise ValueError("Statistical values must be finite")
        number = float(value)
        fractional = repr(number).split("e")[0].partition(".")[2]
        if re.search(r"(?:0{6,}|9{6,})\d{0,2}$", fractional):
            for precision in range(1, 18):
                candidate = float(format(number, f".{precision}g"))
                if abs(candidate - number) <= math.ulp(number):
                    number = candidate
                    break
        return int(number) if number.is_integer() else number
    return value


def tukey_summary(observations):
    values = np.asarray(observations, dtype=float)
    if values.ndim != 1 or len(values) < 4 or not np.all(np.isfinite(values)):
        raise ValueError("Tukey summaries require at least four finite observations")
    # Observations are sampled to two decimals. Exact decimal Type-7 interpolation
    # retains their legitimate quarter-step precision without binary float tails.
    values = sorted(Decimal(str(value)) for value in values.tolist())
    def quantile(probability):
        position = (len(values) - 1) * Decimal(probability)
        index = int(position)
        fraction = position - index
        return values[index] + fraction * (values[min(index + 1, len(values) - 1)] - values[index])
    q1, median, q3 = [quantile(p) for p in (".25", ".5", ".75")]
    iqr = q3 - q1
    fence_low, fence_high = q1 - Decimal("1.5") * iqr, q3 + Decimal("1.5") * iqr
    inside = [value for value in values if fence_low <= value <= fence_high]
    outliers = [value for value in values if value < fence_low or value > fence_high]
    def number(value):
        return int(value) if value == value.to_integral_value() else float(value)
    return dict(lower=number(min(inside)), q1=number(q1), median=number(median),
                q3=number(q3), upper=number(max(inside)), outliers=[number(value) for value in outliers])


def _box_observations(rng, family, mode):
    observations = {"normal": lambda: rng.np.normal(0, 1, 64),
                    "uniform": lambda: rng.np.uniform(-2, 2, 64),
                    "skewed": lambda: rng.np.lognormal(0, .65, 64),
                    "bimodal": lambda: np.concatenate((rng.np.normal(-1.5, .4, 32), rng.np.normal(1.5, .4, 32))),
                    "heavy_tail": lambda: rng.np.standard_t(3, 64)}[family]()
    observations = np.round(observations * rng.py.choice((2, 5, 10, 20)) + rng.py.randint(10, 100), 2)
    if mode == "none":
        for attempt in range(len(observations)):
            summary = tukey_summary(observations)
            if not summary["outliers"]:
                break
            observations = np.clip(observations, summary["lower"], summary["upper"])
        else:
            raise ValueError("Could not obtain a bounded distribution")
    elif mode == "injected":
        summary = tukey_summary(observations)
        q1, q3 = Decimal(str(summary["q1"])), Decimal(str(summary["q3"]))
        span = max(q3 - q1, Decimal(1))
        observations = np.append(observations, [float(q1 - 4 * span), float(q3 + 4 * span)])
    return observations


def sample(rng, kind, controls):
    count = controls.get("category_count", rng.py.randint(2, 8))
    family = controls.get("family", rng.py.choice(FAMILIES[kind]))
    style = canvas(rng, kind, min(count, 5), count, controls)
    font = style["font_path"] if "font_path" in controls.get("style", {}) else str(
        Path(__file__).resolve().parents[1] / "assets/fonts" / rng.py.choice(REQUIRED_FONT_FILES))
    names = rng.py.choice(("Group", "Region", "Product", "Team", "Channel", "Cohort"))
    categories = [f"{names} {chr(65 + index)}" for index in range(count)]
    rng.py.shuffle(categories)
    cfg = dict(generator_version=GENERATOR_VERSION, kind=kind, family=family,
               n_series=1, font_path=font, style=style, categories=categories,
               show_legend=controls.get("show_legend", True if kind == "pie" else rng.py.choice((True, False))),
               legend_position=controls.get("legend_position", rng.py.choice(("left", "right", "top", "bottom"))),
               title_loc=rng.py.choice(("left", "center")), title_weight="normal", title_style="normal",
               _render_axes={}, size=rng.py.choice((400, 440, 480, 520)))
    if kind == "pie":
        weights = {"balanced": lambda: rng.np.uniform(.8, 1.2, count),
                   "dominant": lambda: np.array([8] + [1] * (count - 1)),
                   "long_tail": lambda: np.geomspace(5, .3, count),
                   "bimodal": lambda: np.array([4, 4] + [1] * (count - 2))}[family]()
        weights = rng.np.permutation(weights)
        fractions = weights / weights.sum()
        mode = controls.get("value_mode", rng.py.choice(("percent", "absolute")))
        if mode == "percent":
            quotas = fractions * (100 - 4 * count)
            values = np.floor(quotas).astype(int) + 4
            remainder = 100 - int(values.sum())
            values[np.argsort(-(quotas - np.floor(quotas)), kind="stable")[:remainder]] += 1
        else:
            values = np.round((fractions + .035) * rng.py.choice((100, 500, 1000, 5000)), rng.py.choice((0, 1)))
        cfg.update(value_mode=mode, donut=controls.get("donut", rng.py.choice((True, False))),
                   label_mode=controls.get("label_mode", rng.py.choice(("legend_value", "value", "category_value"))),
                   rotation=rng.py.choice((0, .5, 1, 1.5)) * np.pi,
                   hole_ratio=rng.py.choice((.35, .5, .6)), title=rng.py.choice(("Category share", "Allocation", "Market composition")))
        if not cfg["show_legend"]:
            cfg["label_mode"] = "category_value"
        if count >= 7:
            cfg["size"] = max(cfg["size"], 640 if mode == "absolute" and cfg["label_mode"] == "value" else 520)
        cfg["rows"] = [dict(category=category, value=float(value)) for category, value in zip(categories, values)]
    else:
        mode = controls.get("outlier_mode", rng.py.choice(("none", "natural", "injected")))
        cfg.update(orientation=controls.get("orientation", rng.py.choice(("horizontal", "vertical"))),
                   outlier_mode=mode, box_size=rng.py.choice((18, 25, 32, 40)),
                   point_shape=rng.py.choice(("circle", "diamond", "square", "cross")),
                   title=rng.py.choice(("Measurements by group", "Response distribution", "Group comparison")),
                   value_title=rng.py.choice(("Score", "Duration (ms)", "Measurement")), rows=[], observations=[])
        for category in categories:
            observations = _box_observations(rng, family, mode)
            cfg["observations"].append(observations.tolist())
            cfg["rows"].append(dict(category=category, **tukey_summary(observations)))
    cfg["rows"] = canonical_numbers(cfg["rows"])
    if "observations" in cfg:
        cfg["observations"] = canonical_numbers(cfg["observations"])
    return cfg
