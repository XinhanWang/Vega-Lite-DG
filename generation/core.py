"""Sampling orchestration and provenance; no plotting or subprocess side effects."""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import numpy as np

from . import GENERATOR_VERSION
from . import bars, lines, scatter
from .common import RandomSource, clean, save
from .controls import FAMILIES, normalize_controls
from .labels import series_names, titles
from .styles import canvas
from .style_rules import REQUIRED_FONT_FILES
from .template_styles import finish_canvas


def _counts(rng, kind, controls):
    p = rng.py
    max_series = 6 if kind == "barv_stack" else 5
    if kind == "scatter_n" and "point_count" in controls:
        max_series = min(max_series, (controls["point_count"] - 4) // 4)
    series = controls.get("series_count", 1 if kind.endswith("_1") else p.randint(2, max_series))
    if kind.startswith("bar"):
        maximum = 24 if series == 1 else 16 if kind != "barv_stack" else 18
        count = controls.get("category_count", p.randint(6, maximum))
    elif kind.startswith("line"):
        count = controls.get("point_count", p.randint(6, 28))
    else:
        count = controls.get("point_count", p.randint(max(12, series * 4 + 4), 48))
    return count, series


def _axis_values(kind, cfg, axis):
    if kind.startswith("bar"):
        category_axis = "y" if kind.startswith("barh") else "x"
        if axis == category_axis:
            return np.arange(len(cfg["labels"])), True
        values = np.asarray(cfg.get("values", cfg.get("matrix")), dtype=float)
        if kind == "barv_stack":
            values = values.sum(axis=0)
        return np.append(values, 0), False
    if kind.startswith("line"):
        if axis == "x":
            return np.asarray(cfg["x_values"]), cfg["x_mode"] != "numeric"
        return np.asarray(cfg["matrix"]), False
    return np.asarray(cfg[axis]), False


def _axes(rng, kind, cfg, controls):
    """Explicit native scale/inversion choices replace render-time randomness."""
    p = rng.py
    axes = {"presentation_version": 3, "source": "native_sampling", "aspect": "auto"}
    for axis in ("x", "y"):
        values, categorical = _axis_values(kind, cfg, axis)
        domain = list(cfg[f"{axis}lim"])
        scale = "linear"
        scale = controls.get(f"{axis}_scale", scale)
        if categorical and scale != "linear":
            raise ValueError(f"A categorical {axis} axis must have a linear position scale")
        if scale == "log":
            if np.any(values <= 0):
                raise ValueError(f"A log {axis} axis requires strictly positive observations and endpoints")
            low, high = float(values.min()), float(values.max())
            factor = math.exp(max(math.log(high / low), .2) * .1)
            domain = [low / factor, high * factor]
        elif scale == "sqrt":
            if np.any(values < 0):
                raise ValueError(f"A sqrt {axis} axis requires nonnegative observations")
            domain[0] = max(0, domain[0])
        inverted = False
        if (kind.startswith('barh') and axis == 'y') or (kind == 'barv_1' and axis == 'x'):
            # Original renderers short-circuit the family-dependent first draw.
            inverted = (cfg['family'] in {'ordered', 'heavy_tail', 'log_spread'} and p.random() < .65) or p.random() < .24
        inverted = controls.get(f'{axis}_inverted', inverted)
        if inverted:
            domain.reverse()
        axes.update({f"{axis}lim": domain, f"{axis}scale": scale, f"{axis}_inverted": inverted})
    if kind.startswith("scatter") and axes["xscale"] == axes["yscale"] == "linear" and ((kind == "scatter_1" and cfg["family"] in {"ring", "clustered", "multi_cluster", "bimodal"} and p.random() < .58) or (kind == "scatter_n" and cfg["family"] == "ring" and p.random() < .18)):
        axes["aspect"] = "equal"
    refs = controls.get("reference_lines")
    if refs is None:
        refs = []
        if kind.startswith('bar'):
            if np.any(np.asarray(cfg.get('values', cfg.get('matrix'))) < 0):
                refs.append({'axis': 'x' if kind.startswith('barh') else 'y', 'value': 0})
        elif kind.startswith('line') and p.random() < .22:
            refs.append({'axis': 'y', 'value': 0})
    if any(not math.isfinite(float(ref["value"])) for ref in refs):
        raise ValueError("Reference-line values must be finite")
    axes["reference_lines"] = copy.deepcopy(refs)
    style = cfg["style"]
    axes["grid_visible"] = {axis: bool(style["grid_visible"]) and cfg.get("grid_axis", style["grid_axis"]) in {axis, "both"} for axis in ("x", "y")}
    def tick(lengths=(3, 4, 5), max_width=1.2, direction=None):
        return {'length': p.choice(lengths), 'width': p.uniform(.7, max_width),
                'direction': direction or p.choice(('in', 'out')),
                'color': style['text_color'], 'visible': True}
    default = {'length': 3.5, 'width': .8, 'direction': 'out', 'color': style['text_color'], 'visible': True}
    if kind.startswith('scatter'):
        shared = tick()
        axes['tick_styles'] = {'x': dict(shared), 'y': dict(shared)}
    elif kind == 'barv_stack':
        axes['tick_styles'] = {'x': tick(), 'y': tick((3, 4))}
    elif kind.startswith('barh'):
        axes['tick_styles'] = {'x': tick(max_width=1.3), 'y': tick((3, 4), direction='out')}
    elif kind.startswith('barv'):
        axes['tick_styles'] = {'y': tick(max_width=1.3), 'x': tick((3, 4), direction='out') if kind.endswith('_1') else dict(default)}
    else:
        axes['tick_styles'] = {'x': dict(default), 'y': tick()}
    # All category labels live in the sampler output; Vega-Lite never chooses a subset.
    if kind.startswith("line") and cfg["x_mode"] != "numeric":
        axes["xticks"], axes["xticklabels"] = list(range(len(cfg["x_labels"]))), cfg["x_labels"][:]
    return axes


def sample_config(kind, seed, controls=None):
    """Sample a portable configuration with independent, deterministic RNGs."""
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    c = normalize_controls(kind, controls)
    rng = RandomSource(seed)
    count, series = _counts(rng, kind, c)
    family = c.get("family", rng.py.choice(FAMILIES[kind]))
    style = canvas(rng, kind, series, count, c)
    show_probability = (.24 if kind.startswith("bar") else .18 if kind.startswith("line") else .14) if series == 1 else (.78 if kind.startswith("scatter") else 1.0)
    show_legend = c.get("show_legend", rng.py.random() < show_probability)
    chart_font = style['font_path'] if 'font_path' in c.get('style', {}) else str(Path(__file__).resolve().parents[1] / 'assets/fonts' / rng.py.choice(REQUIRED_FONT_FILES))
    names = series_names(rng, series, show_legend)
    cfg = {"generator_version": GENERATOR_VERSION, "kind": kind, "family": family,
           "n_series": series, "font_path": chart_font, "style": style,
           "show_legend": show_legend, "series_names": names, "series_name": names[0], **titles(rng, kind)}
    sampler = bars if kind.startswith("bar") else lines if kind.startswith("line") else scatter
    cfg.update(sampler.sample(rng, kind, count, series, family, style, c))
    p = rng.py
    cfg['title_loc'] = p.choice(('left', 'center'))
    cfg['title_weight'] = p.choices(('normal', 'bold'), (.72, .28) if kind.startswith('bar') else (.74, .26) if kind.startswith('line') else (.76, .24))[0]
    cfg['title_style'] = p.choices(('normal', 'italic'), (.86, .14) if kind.startswith('line') else (.85, .15) if kind.startswith('bar') and series > 1 else (.84, .16))[0]
    finish_canvas(kind, cfg, c)
    cfg["_render_axes"] = _axes(rng, kind, cfg, c)
    return clean(cfg)


def sampling_diagnostics(kind, seed, cfg, controls=None):
    """Describe sampled parameters and bind provenance to the exact configuration."""
    c = normalize_controls(kind, controls)
    config_json = json.dumps(cfg, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False)
    config_sha256 = hashlib.sha256(config_json.encode("utf-8")).hexdigest()
    return {"generator_version": GENERATOR_VERSION, "kind": kind,
            "requested_seed": seed, "sample_seed": seed, "sampling_attempts": 1,
            "controls": clean(c), "family": cfg["family"], "profile": cfg["style"]["profile"],
            "axes": copy.deepcopy(cfg["_render_axes"]), "renderer": "vega-lite",
            "source": "native parameter/data samplers; family taxonomy inspired by VSR",
            "config_sha256": config_sha256}


def generate_chart(kind, seed, outdir, controls=None):
    """Persist sampling evidence, leaving JSON construction/rendering to the pipeline.

    The return dictionary retains config/sample_seed/diagnostics used by the
    former entry point. Rendering always proceeds through adapter + render.mjs.
    max_attempts is accepted for old run configs but no rejection loop is needed:
    forced counts, family, errors and style choices are applied directly.
    """
    c = normalize_controls(kind, controls)
    outdir = Path(outdir)
    for name in ("config.json", "sampling.json"):
        if (outdir / name).exists():
            raise FileExistsError(f"Refusing to overwrite existing sample: {outdir / name}")
    cfg = sample_config(kind, seed, c)
    diagnostics = sampling_diagnostics(kind, seed, cfg, c)
    outdir.mkdir(parents=True, exist_ok=True)
    save(outdir / "config.json", cfg)
    save(outdir / "sampling.json", diagnostics)
    return {"config": cfg, "sample_seed": seed, "diagnostics": diagnostics}

