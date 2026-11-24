"""Apply localized display text after the existing numerical/style sampler."""
import random
import re
from pathlib import Path

from .sampling_policy import CJK_FILE, THEMES, TITLE_PATTERNS

MONTHS = dict(zip(("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), range(1, 13)))


def local_date(label):
    if match := re.fullmatch(r"Q([1-4]) (\d{4})", label):
        return f"{match[2]}年第{match[1]}季度"
    if match := re.fullmatch(r"([A-Za-z]{3})[- /](\d{2,4})", label):
        if match[1] in MONTHS:
            return f"{match[2]}年{MONTHS[match[1]]}月"
    if match := re.fullmatch(r"([A-Za-z]{3})", label):
        if match[1] in MONTHS:
            return f"{MONTHS[match[1]]}月"
    return label


def _labels(values, pool, prefix):
    mapping = {}
    for value in values:
        if value not in mapping:
            index = len(mapping)
            mapping[value] = pool[index] if index < len(pool) else f"{prefix}{index+1}"
    return [mapping[value] for value in values]


def apply(cfg, kind, seed, sampling):
    if not sampling:
        return cfg
    cfg["sampling"] = sampling
    style = cfg["style"]
    if "aspect_ratio" in sampling:
        ratio = sampling["aspect_ratio"]
        if kind in {"pie", "boxplot"}:
            cfg["layout_ratio"] = ratio
        else:
            width, height = style["figsize"]
            area = width * height
            style["figsize"] = [(area * ratio) ** .5, (area / ratio) ** .5]
    if kind == "pie" and sampling.get("value_labels") is False:
        cfg.update(label_mode="none", show_legend=True)
    percent_stack = kind.endswith("_stack") and cfg.get("stack_mode") == "percent"
    value_axis = "x_title" if kind.startswith("barh") else "y_title"
    if percent_stack:
        cfg[value_axis] = "Share (%)"
    if sampling.get("language") != "zh":
        return cfg
    topic, measure, category, vocabulary = THEMES[sampling["theme"]]
    pool = list(vocabulary)
    random.Random(seed).shuffle(pool)
    font = Path(__file__).resolve().parents[1] / "assets/fonts" / CJK_FILE
    if not font.is_file():
        raise FileNotFoundError("Chinese font missing. Run python bootstrap.py --with-cjk")
    cfg["font_path"] = style["font_path"] = str(font)
    cfg.update(title=TITLE_PATTERNS[sampling["title_pattern"]].format(topic),
               title_weight="normal", title_style="normal")
    if kind in {"pie", "boxplot"}:
        labels = _labels(cfg["categories"], pool, category)
        cfg["categories"] = labels
        for row, label in zip(cfg["rows"], labels):
            row["category"] = label
        if kind == "boxplot":
            cfg["value_title"] = measure
        return cfg
    if cfg.get("show_legend"):
        groups = ("本期", "上期", "目标", "基准", "试验组", "对照组")
        cfg["series_names"] = _labels(cfg["series_names"], groups, "系列")
        cfg["series_name"] = cfg["series_names"][0]
    if kind.startswith("bar"):
        if percent_stack:
            measure = "\u5360\u6bd4 (%)"
        cfg["labels"] = _labels(cfg["labels"], pool, category)
        cfg["x_title"], cfg["y_title"] = (measure, category) if kind.startswith("barh") else (category, measure)
    elif kind.startswith("line"):
        mode = cfg["x_mode"]
        cfg["x_title"] = {"numeric": "观测序号", "categorical": category, "temporal": "时间"}[mode]
        cfg["y_title"] = measure
        if mode != "numeric":
            old = cfg["x_labels"]
            new = [local_date(label) for label in old] if mode == "temporal" else _labels(old, pool, category)
            translated = dict(zip(old, new))
            if mode == "temporal":
                cfg["original_temporal_labels"] = old
            cfg["x_labels"] = new
            cfg["tick_labels"] = [translated.get(label, label) for label in cfg.get("tick_labels", ())]
            cfg["_render_axes"]["xticklabels"] = new[:]
    else:
        cfg.update(x_title="观测指标", y_title=measure)
    return cfg
