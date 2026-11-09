"""Small, non-destructive adapter around the pinned upstream VSR generators.

Uncontrolled sampling calls the original sample_config without modifying its RNG
stream. Controlled sampling replaces only requested samplers and records those
interventions. Parallel callers must use processes (Matplotlib is not thread safe).
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import threading
from contextlib import contextmanager

ROOT = Path(__file__).resolve().parent
VENDOR = ROOT / "vendor" / "VSR" / "chart_generation"
os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".cache" / "matplotlib"))
KINDS = ("barh_1", "barh_n", "barv_1", "barv_n", "barv_stack", "line_1", "line_n", "scatter_1", "scatter_n")
BAR_SINGLE_FAMILIES = ("balanced", "heavy_tail", "ordered", "signed_mix", "sparse", "log_spread", "clustered", "alternating", "bimodal", "staircase", "plateau")
BAR_MULTI_FAMILIES = ("parallel", "crossing", "dominant", "mixed_scale", "composition", "sparse", "signed", "alternating", "bimodal", "staircase", "plateau")
STACK_FAMILIES = ("balanced", "dominant", "sparse", "layered", "front_loaded", "back_loaded", "switchback", "fragmented")
LINE_FAMILIES = ("parallel_trend", "crossing", "oscillating", "piecewise", "random_walk", "spike_event", "decay", "seasonal", "mean_reverting", "logistic", "sawtooth")
SCATTER_FAMILIES = ("clustered", "multi_cluster", "correlated", "curved", "ring", "heteroskedastic", "fan", "stripe", "stepwise", "bimodal", "outliers", "spiral", "crescent", "grid", "bridge", "hourglass")
PROFILES = ("chromatic", "publication_clean", "colorful_analytic", "presentation_emphasis", "dashboard_dense", "monochrome_minimal", "editorial", "compact_report", "dark_contrast", "dense_scatter_family")
FAMILIES = {kind: (STACK_FAMILIES if kind == "barv_stack" else BAR_SINGLE_FAMILIES if kind.startswith("bar") and kind.endswith("_1") else BAR_MULTI_FAMILIES if kind.startswith("bar") else LINE_FAMILIES if kind.startswith("line") else SCATTER_FAMILIES) for kind in KINDS}
_MODULES = {}
_COMMON = None
_LOCK = threading.RLock()


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_common():
    global _COMMON
    if _COMMON is None:
        if not (VENDOR / "common.py").is_file():
            raise FileNotFoundError(f"Pinned VSR sources missing: {VENDOR}; run bootstrap.py first")
        _COMMON = _load(VENDOR / "common.py", "_vsr_v1_upstream_common")
    return _COMMON


def load_generator(kind):
    if kind not in KINDS:
        raise ValueError(f"Unknown chart type {kind!r}; expected one of {KINDS}")
    if kind not in _MODULES:
        common = load_common()
        previous = sys.modules.get("common")
        try:
            sys.modules["common"] = common
            _MODULES[kind] = _load(VENDOR / f"gen_{kind}.py", f"_vsr_v1_{kind}")
        finally:
            if previous is None:
                sys.modules.pop("common", None)
            else:
                sys.modules["common"] = previous
    return _MODULES[kind]


def jsonable(value):
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "tolist"):
        return jsonable(value.tolist())
    if hasattr(value, "item"):
        return value.item()
    return value


def _save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(jsonable(value), ensure_ascii=False, allow_nan=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _normalize_controls(kind, controls):
    c = dict(controls or {})
    aliases = {"n_points": "point_count", "n_categories": "category_count", "n_series": "series_count", "style_profile": "profile"}
    for old, new in aliases.items():
        if old in c:
            if new in c and c[old] != c[new]:
                raise ValueError(f"Conflicting controls: {old} and {new}")
            c[new] = c.pop(old)
    accepted = {"point_count", "category_count", "series_count", "family", "x_mode", "stack_mode", "profile", "style", "show_error", "hatch", "max_attempts"}
    unknown = set(c) - accepted
    if unknown:
        raise ValueError(f"Unknown native controls: {sorted(unknown)}")
    if "family" in c and c["family"] not in FAMILIES[kind]:
        raise ValueError(f"Invalid family for {kind}: {c['family']!r}")
    if "category_count" in c and not kind.startswith("bar"):
        raise ValueError("category_count applies only to bar templates")
    if "point_count" in c and kind.startswith("bar"):
        raise ValueError("Use category_count for bar templates")
    for key in ("point_count", "category_count", "series_count"):
        if key in c and (isinstance(c[key], bool) or not isinstance(c[key], int) or c[key] <= 0):
            raise ValueError(f"{key} must be a positive integer")
    if "series_count" in c:
        lo, hi = (1, 1) if kind.endswith("_1") else (2, 6 if kind == "barv_stack" else 5)
        if not lo <= c["series_count"] <= hi:
            raise ValueError(f"{kind} requires series_count in [{lo}, {hi}]")
    if kind == "scatter_n" and "point_count" in c:
        minimum = 4 * c.get("series_count", 2) + 4
        if not minimum <= c["point_count"] <= 48:
            raise ValueError(f"scatter_n point_count is the total across series and must be in [{minimum}, 48]")
    if "x_mode" in c and (not kind.startswith("line") or c["x_mode"] not in {"numeric", "categorical", "temporal"}):
        raise ValueError("x_mode is numeric/categorical/temporal and applies only to line templates")
    if "stack_mode" in c and (kind != "barv_stack" or c["stack_mode"] not in {"absolute", "percent"}):
        raise ValueError("stack_mode is absolute/percent and applies only to barv_stack")
    if "profile" in c and (c["profile"] not in PROFILES or (c["profile"] == "dense_scatter_family" and not kind.startswith("scatter"))):
        raise ValueError(f"Invalid profile for {kind}")
    if "show_error" in c and (not kind.startswith("bar") or kind == "barv_stack" or not isinstance(c["show_error"], bool)):
        raise ValueError("show_error is a boolean for non-stacked bars")
    if "hatch" in c and (not kind.startswith("bar") or c["hatch"] not in (None, "/", "\\", "|", "-", "+", "x", "o", "O", ".", "*")):
        raise ValueError("hatch must be an upstream bar hatch value")
    if "style" in c and not isinstance(c["style"], dict):
        raise ValueError("style must be a dictionary of native style overrides")
    return c


@contextmanager
def _controlled_samplers(module, kind, controls):
    """Patch only samplers in memory; restore all functions even on failure."""
    common = load_common()
    patches = []
    def patch(obj, key, value):
        patches.append((obj, key, getattr(obj, key)))
        setattr(obj, key, value)
    def constant(value):
        return lambda *args, **kwargs: value
    try:
        for key, sampler in (("category_count", "sample_category_count"), ("point_count", "sample_point_count"), ("series_count", "sample_series_count"), ("x_mode", "sample_x_mode"), ("stack_mode", "sample_stack_mode")):
            if key in controls and hasattr(module, sampler):
                patch(module, sampler, constant(controls[key]))
        if "family" in controls:
            sampler = "sample_stack_family" if kind == "barv_stack" else "sample_family"
            if hasattr(module, sampler):
                patch(module, sampler, constant(controls["family"]))
        # The bar family and stacked series count are sampled inline upstream.
        old_choose = module.choose_weighted
        def choose(items, weights):
            if "family" in controls and tuple(items) == tuple(FAMILIES[kind]):
                return controls["family"]
            if kind == "barv_stack" and "series_count" in controls and list(items) == [2, 3, 4, 5, 6]:
                return controls["series_count"]
            return old_choose(items, weights)
        patch(module, "choose_weighted", choose)
        if "profile" in controls:
            patch(common, "sample_profile", constant(controls["profile"]))
        yield
    finally:
        for obj, key, original in reversed(patches):
            setattr(obj, key, original)


def _matches(cfg, c):
    count = len(cfg.get("x_labels", cfg.get("x", [])))
    if "point_count" in c and count != c["point_count"]:
        return False
    if "show_error" in c and bool(cfg.get("xerr") is not None or cfg.get("yerr") is not None) != c["show_error"]:
        return False
    return True


def _axes_snapshot(ax, fig):
    """Capture choices made inside render_one after sample_config returned."""
    reference_lines = []
    for line in ax.lines:
        if line.get_transform() == ax.get_xaxis_transform():
            values = list(line.get_xdata())
            if values and all(float(v) == float(values[0]) for v in values):
                reference_lines.append({"axis": "x", "value": float(values[0])})
        elif line.get_transform() == ax.get_yaxis_transform():
            values = list(line.get_ydata())
            if values and all(float(v) == float(values[0]) for v in values):
                reference_lines.append({"axis": "y", "value": float(values[0])})
    return jsonable({
        "xlim": ax.get_xlim(), "ylim": ax.get_ylim(),
        "x_inverted": ax.xaxis_inverted(), "y_inverted": ax.yaxis_inverted(),
        "xscale": ax.get_xscale(), "yscale": ax.get_yscale(), "aspect": ax.get_aspect(),
        "xticks": ax.get_xticks(), "yticks": ax.get_yticks(),
        "xticklabels": [t.get_text() for t in ax.get_xticklabels()],
        "yticklabels": [t.get_text() for t in ax.get_yticklabels()],
        "x_offset_text": ax.xaxis.get_offset_text().get_text(),
        "y_offset_text": ax.yaxis.get_offset_text().get_text(),
        "reference_lines": reference_lines,
        "axes_bbox_bottom_left": ax.bbox.bounds, "dpi": fig.dpi,
        "lines": [{"x": line.get_xdata(), "y": line.get_ydata(), "color": line.get_color(), "linewidth": line.get_linewidth(), "linestyle": line.get_linestyle(), "alpha": line.get_alpha(), "marker": line.get_marker(), "markersize": line.get_markersize(), "label": line.get_label()} for line in ax.lines],
    })


def generate_native(kind, seed, outdir, controls=None, render=True):
    """Return config/annotation/seed/diagnostics, retaining author RNG behavior.

    Files: config.json, native.raw.config.json, native.diagnostics.json and (when
    render=True) native.png, native.annotation.json, native.original.annotation.json.
    Native pixel coordinates retain VSR's bottom-left coordinate convention.
    Existing final outputs are rejected; use a new per-sample output directory.
    """
    c = _normalize_controls(kind, controls)
    outdir = Path(outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    for name in ("config.json", "native.png", "native.annotation.json"):
        if (outdir / name).exists():
            raise FileExistsError(f"Refusing to overwrite existing sample: {outdir / name}")
    attempts = int(c.get("max_attempts", 256))
    if not 1 <= attempts <= 10000:
        raise ValueError("max_attempts must be in [1, 10000]")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    with _LOCK:
        module = load_generator(kind)
        common = load_common()
        original_sample = module.sample_config
        original_collect = module.collect_metadata
        captured = {}
        diagnostics = {"kind": kind, "requested_seed": seed, "controls": c, "pixel_origin": "bottom-left", "upstream_commit": "1fd040346add205ffbada9748273cad3bc9159e5"}
        with _controlled_samplers(module, kind, c):
            for attempt in range(attempts):
                sample_seed = seed + attempt
                common.seed_everything(sample_seed)
                cfg = original_sample()
                if _matches(cfg, c):
                    break
            else:
                raise ValueError(f"No native configuration met controls after {attempts} attempts: {c}")
            diagnostics.update(sample_seed=sample_seed, sampling_attempts=attempt + 1)

            def capture_config():
                # Called after render_one resets to sample_seed; repeat exactly the
                # accepted sampling so rendering continues at the correct RNG state.
                actual = original_sample()
                captured["raw"] = copy.deepcopy(actual)
                if "style" in c:
                    unknown = set(c["style"]) - set(actual["style"])
                    if unknown:
                        raise ValueError(f"Unknown style keys: {sorted(unknown)}")
                    actual["style"].update(copy.deepcopy(c["style"]))
                if "hatch" in c:
                    if "hatches" in actual:
                        actual["hatches"] = [c["hatch"]] * actual["n_series"]
                    else:
                        actual["hatch"] = c["hatch"]
                captured["config"] = actual
                return actual

            def collect(ax, cfg, fig):
                result = original_collect(ax, cfg, fig)
                diagnostics["axes"] = _axes_snapshot(ax, fig)
                return result

            annotation = None
            if render:
                try:
                    module.sample_config = capture_config
                    module.collect_metadata = collect
                    annotation = module.render_one(0, runtime={"seed": sample_seed, "RUN_ROOT": outdir, "save_dir": outdir})
                finally:
                    module.sample_config = original_sample
                    module.collect_metadata = original_collect
                if annotation is None:
                    raise RuntimeError(f"Upstream VSR rendering failed for {kind}, seed={sample_seed}; see upstream traceback")
                original_annotation = copy.deepcopy(annotation)
                source = outdir / annotation["image"]
                source.rename(outdir / "native.png")
                annotation["image"] = "native.png"
                _save(outdir / "native.original.annotation.json", original_annotation)
                _save(outdir / "native.annotation.json", annotation)
            else:
                common.seed_everything(sample_seed)
                capture_config()
            cfg = captured["config"]
            if "axes" in diagnostics:
                cfg["_render_axes"] = copy.deepcopy(diagnostics["axes"])
            _save(outdir / "native.raw.config.json", captured["raw"])
            _save(outdir / "config.json", cfg)
            _save(outdir / "native.diagnostics.json", diagnostics)
            return {"config": jsonable(cfg), "annotation": jsonable(annotation), "sample_seed": sample_seed, "diagnostics": jsonable(diagnostics)}
