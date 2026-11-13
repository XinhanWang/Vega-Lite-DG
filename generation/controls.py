"""Supported chart families and explicit generation controls."""
from __future__ import annotations

KINDS = ("barh_1", "barh_n", "barv_1", "barv_n", "barv_stack", "line_1", "line_n", "scatter_1", "scatter_n", "barh_stack")
BAR_SINGLE_FAMILIES = ("balanced", "heavy_tail", "ordered", "signed_mix", "sparse", "log_spread", "clustered", "alternating", "bimodal", "staircase", "plateau")
BAR_MULTI_FAMILIES = ("parallel", "crossing", "dominant", "mixed_scale", "composition", "sparse", "signed", "alternating", "bimodal", "staircase", "plateau")
STACK_FAMILIES = ("balanced", "dominant", "sparse", "layered", "front_loaded", "back_loaded", "switchback", "fragmented")
LINE_FAMILIES = ("parallel_trend", "crossing", "oscillating", "piecewise", "random_walk", "spike_event", "decay", "seasonal", "mean_reverting", "logistic", "sawtooth")
SCATTER_FAMILIES = ("clustered", "multi_cluster", "correlated", "curved", "ring", "heteroskedastic", "fan", "stripe", "stepwise", "bimodal", "outliers", "spiral", "crescent", "grid", "bridge", "hourglass")
PROFILES = ("chromatic", "publication_clean", "colorful_analytic", "presentation_emphasis", "dashboard_dense", "monochrome_minimal", "editorial", "compact_report", "dark_contrast", "dense_scatter_family")
FAMILIES = {kind: (STACK_FAMILIES if kind in {"barv_stack", "barh_stack"} else BAR_SINGLE_FAMILIES if kind.startswith("bar") and kind.endswith("_1") else BAR_MULTI_FAMILIES if kind.startswith("bar") else LINE_FAMILIES if kind.startswith("line") else SCATTER_FAMILIES) for kind in KINDS}
HATCHES = (None, "/", "\\", "|", "-", "+", "x", "o", "O", ".", "*")


def normalize_controls(kind, controls):
    if kind not in KINDS:
        raise ValueError(f"Unknown chart type {kind!r}; expected one of {KINDS}")
    if controls is not None and not isinstance(controls, dict):
        raise ValueError("controls must be an object")
    c = dict(controls or {})
    if kind in {"barv_stack", "barh_stack"}:
        c.setdefault("stack_mode", "absolute")
        if kind == "barh_stack" and c["stack_mode"] != "absolute":
            raise ValueError("barh_stack supports absolute stacks only")
    for old, new in {"n_points": "point_count", "n_categories": "category_count", "n_series": "series_count", "style_profile": "profile"}.items():
        if old in c:
            if new in c and c[old] != c[new]:
                raise ValueError(f"Conflicting controls: {old} and {new}")
            c[new] = c.pop(old)
    accepted = {"point_count", "category_count", "series_count", "family", "x_mode", "stack_mode", "profile", "style", "show_error", "hatch", "max_attempts", "show_legend", "x_inverted", "y_inverted", "x_scale", "y_scale", "reference_lines"}
    unknown = set(c) - accepted
    if unknown:
        raise ValueError(f"Unknown generation controls: {sorted(unknown)}")
    if "family" in c and c["family"] not in FAMILIES[kind]:
        raise ValueError(f"Invalid family for {kind}: {c['family']!r}")
    if "category_count" in c and not kind.startswith("bar"):
        raise ValueError("category_count applies only to bar templates")
    if "point_count" in c and kind.startswith("bar"):
        raise ValueError("Use category_count for bar templates")
    for key in ("point_count", "category_count", "series_count", "max_attempts"):
        if key in c and (isinstance(c[key], bool) or not isinstance(c[key], int) or c[key] <= 0):
            raise ValueError(f"{key} must be a positive integer")
    if c.get("max_attempts", 1) > 10000:
        raise ValueError("max_attempts must be in [1, 10000]")
    if "series_count" in c:
        lo, hi = (1, 1) if kind.endswith("_1") else (2, 6 if kind in {"barv_stack", "barh_stack"} else 5)
        if not lo <= c["series_count"] <= hi:
            raise ValueError(f"{kind} requires series_count in [{lo}, {hi}]")
    if kind == "scatter_n" and "point_count" in c:
        minimum = 4 * c.get("series_count", 2) + 4
        if not minimum <= c["point_count"] <= 48:
            raise ValueError(f"scatter_n point_count is the total across series and must be in [{minimum}, 48]")
    if "x_mode" in c and (not kind.startswith("line") or c["x_mode"] not in {"numeric", "categorical", "temporal"}):
        raise ValueError("x_mode is numeric/categorical/temporal and applies only to line templates")
    if "stack_mode" in c and (kind not in {"barv_stack", "barh_stack"} or c["stack_mode"] not in {"absolute", "percent"}):
        raise ValueError("stack_mode is absolute/percent and applies only to barv_stack")
    if "profile" in c and (c["profile"] not in PROFILES or (c["profile"] == "dense_scatter_family" and not kind.startswith("scatter"))):
        raise ValueError(f"Invalid profile for {kind}")
    if "show_error" in c and (not kind.startswith("bar") or kind in {"barv_stack", "barh_stack"} or not isinstance(c["show_error"], bool)):
        raise ValueError("show_error is a boolean for non-stacked bars")
    if "hatch" in c and (not kind.startswith("bar") or c["hatch"] not in HATCHES):
        raise ValueError("hatch must be a supported bar pattern")
    if "style" in c and not isinstance(c["style"], dict):
        raise ValueError("style must be a dictionary of style overrides")
    for key in ("show_legend", "x_inverted", "y_inverted"):
        if key in c and not isinstance(c[key], bool):
            raise ValueError(f"{key} must be a boolean")
    for axis in ("x", "y"):
        if f"{axis}_scale" in c and c[f"{axis}_scale"] not in {"linear", "log", "symlog", "sqrt"}:
            raise ValueError(f"{axis}_scale must be linear, log, symlog or sqrt")
    if "reference_lines" in c:
        if not isinstance(c["reference_lines"], list):
            raise ValueError("reference_lines must be a list of {axis, value} objects")
        for ref in c["reference_lines"]:
            if not isinstance(ref, dict) or set(ref) != {"axis", "value"} or ref["axis"] not in {"x", "y"} or isinstance(ref["value"], bool) or not isinstance(ref["value"], (int, float)):
                raise ValueError("Each reference line requires axis x/y and numeric value")
    return c
