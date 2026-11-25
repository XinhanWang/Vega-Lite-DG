"""Apply localized display text after the existing numerical/style sampler."""
import random
import re
from pathlib import Path

from .sampling_policy import CJK_FILE, THEMES, TITLE_PATTERNS
from .chart_text import sample_chart_text

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


def _set_chinese_font(cfg):
    font = Path(__file__).resolve().parents[1] / "assets/fonts" / CJK_FILE
    if not font.is_file():
        raise FileNotFoundError("Chinese font missing. Run python bootstrap.py --with-cjk")
    cfg["font_path"] = cfg["style"]["font_path"] = str(font)
    cfg.update(title_weight="normal", title_style="normal")


def _replace(values, new):
    mapping = dict(zip(dict.fromkeys(values), new, strict=True))
    return [mapping[value] for value in values]


def _with_original_unit(new, old):
    unit = re.search(r" +\([^()]+\)$", old or "")
    return new + unit[0] if unit else new


def _set_line_labels(cfg, new, translate_calendar=False):
    old = cfg["x_labels"]
    mapping = dict(zip(old, new))
    if translate_calendar:
        cfg["original_temporal_labels"] = old
    cfg["x_labels"] = new
    cfg["tick_labels"] = [mapping.get(label, label) for label in cfg.get("tick_labels", ())]
    cfg["_render_axes"]["xticklabels"] = new[:]


def _apply_expanded(cfg, kind, seed, sampling, percent_stack):
    language = sampling["language"]
    if language == "zh":
        _set_chinese_font(cfg)
    category_key = None
    if kind in {"pie", "boxplot"}:
        category_key = "categories"
    elif kind.startswith("bar"):
        category_key = "labels"
    elif cfg.get("x_mode") == "categorical":
        category_key = "x_labels"
    source_labels = cfg[category_key] if category_key else []
    source_series = cfg.get("series_names", ()) if cfg.get("show_legend") else ()
    text = sample_chart_text(kind, seed, language,
                             len(set(source_labels)), len(set(source_series)))
    cfg["title"] = text["title"]
    if source_series:
        cfg["series_names"] = _replace(source_series, text["series"])
        cfg["series_name"] = cfg["series_names"][0]
    if category_key:
        labels = _replace(source_labels, text["categories"])
        if category_key == "x_labels":
            _set_line_labels(cfg, labels)
        else:
            cfg[category_key] = labels
    if kind in {"pie", "boxplot"}:
        for row, label in zip(cfg["rows"], cfg["categories"], strict=True):
            row["category"] = label
        if kind == "boxplot":
            cfg["value_title"] = _with_original_unit(text["value_axis"], cfg.get("value_title"))
    elif kind.startswith("bar"):
        horizontal = kind.startswith("barh")
        value_axis = "x_title" if horizontal else "y_title"
        category_axis = "y_title" if horizontal else "x_title"
        if percent_stack:
            cfg[value_axis] = "占比 (%)" if language == "zh" else "Share (%)"
        else:
            cfg[value_axis] = _with_original_unit(text["value_axis"], cfg.get(value_axis))
        cfg[category_axis] = text["category_axis"]
    elif kind.startswith("line"):
        mode = cfg["x_mode"]
        x_title = text[{"numeric": "index_axis", "categorical": "category_axis", "temporal": "time_axis"}[mode]]
        cfg["x_title"] = _with_original_unit(x_title, cfg.get("x_title")) if mode == "numeric" else x_title
        cfg["y_title"] = _with_original_unit(text["value_axis"], cfg.get("y_title"))
        if mode == "temporal" and language == "zh":
            _set_line_labels(cfg, [local_date(label) for label in cfg["x_labels"]], translate_calendar=True)
    else:
        cfg["x_title"] = _with_original_unit(text["second_measure_axis"], cfg.get("x_title"))
        cfg["y_title"] = _with_original_unit(text["value_axis"], cfg.get("y_title"))
    return cfg


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
    percent_stack = kind.endswith("_stack") and cfg.get("stack_mode") == "percent"
    value_axis = "x_title" if kind.startswith("barh") else "y_title"
    if percent_stack:
        cfg[value_axis] = "Share (%)"
    if sampling.get("text_profile") == "expanded-v1":
        return _apply_expanded(cfg, kind, seed, sampling, percent_stack)
    if sampling.get("language") != "zh":
        return cfg
    topic, measure, category, vocabulary = THEMES[sampling["theme"]]
    pool = list(vocabulary)
    random.Random(seed).shuffle(pool)
    _set_chinese_font(cfg)
    cfg["title"] = TITLE_PATTERNS[sampling["title_pattern"]].format(topic)
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
            _set_line_labels(cfg, new, translate_calendar=mode == "temporal")
    else:
        cfg.update(x_title="观测指标", y_title=measure)
    return cfg
