"""Map VSR presentation choices to ordinary, portable Vega-Lite properties.

Presentation is independent of the observation/compact contract. Font metadata
comes from the actual font file, using Matplotlib (already a pipeline dependency).
No SVG postprocessing or renderer-specific style injection is used.
"""
from __future__ import annotations

import copy
from functools import lru_cache
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DASHES = {"-": [], "solid": [], "--": [6, 3], "dashed": [6, 3],
          ":": [1.5, 2.5], "dotted": [1.5, 2.5], "-.": [6, 3, 1.5, 3],
          "dashdot": [6, 3, 1.5, 3]}


@lru_cache(maxsize=128)
def _font_metadata(filename: str, mtime_ns: int, size: int) -> dict:
    from matplotlib.font_manager import get_font, ttfFontProperty, weight_dict
    entry = ttfFontProperty(get_font(filename))
    weight = entry.weight if isinstance(entry.weight, (int, float)) else weight_dict[entry.weight]
    return {"family": entry.name, "weight": int(weight), "style": entry.style}


def describe_font(filename: str | Path) -> dict:
    path = Path(filename).resolve()
    stat = path.stat()
    return dict(_font_metadata(str(path), stat.st_mtime_ns, stat.st_size))


def selected_font(cfg: dict) -> dict:
    # All nine pinned upstream renderers pass cfg['font_path'] to FontProperties.
    # style.font_path is independently sampled and is only a fallback for cfg-only inputs.
    name = cfg.get("font_path") or cfg.get("style", {}).get("font_path")
    if not name:
        return {"family": "sans-serif", "weight": 400, "style": "normal", "source": "default"}
    path = Path(name)
    if not path.is_file():
        # Saved configurations may originate on another machine or OS.
        basename = str(name).replace("\\", "/").rsplit("/", 1)[-1]
        path = ROOT / "vendor/VSR/chart_generation/assets/fonts" / basename
    if not path.is_file():
        raise FileNotFoundError(f"Selected VSR font is unavailable: {name}. Run python bootstrap.py or supply the font file.")
    return {**describe_font(path), "file": path.name, "source": "font_file"}


def _rgba(color, alpha: float) -> str:
    text = {"white": "#ffffff", "black": "#000000", "gray": "#808080", "grey": "#808080"}.get(color, color)
    if isinstance(text, str) and text.startswith("#") and len(text) in {4, 5, 7, 9}:
        digits = text[1:]
        if len(digits) in {3, 4}:
            digits = "".join(c * 2 for c in digits)
        parts = [int(digits[i:i + 2], 16) / 255 for i in range(0, len(digits), 2)]
        r, g, b = parts[:3]
        a = parts[3] if len(parts) == 4 else 1
    else:
        from matplotlib.colors import to_rgba
        r, g, b, a = to_rgba(color)
    return f"rgba({round(r * 255)},{round(g * 255)},{round(b * 255)},{a * alpha:.4f})"


def _expression(values: list) -> dict:
    mapping = {f"s{i:03d}": value for i, value in enumerate(values)}
    # Vega's legend layout evaluates size/stroke width with the raw domain
    # value; symbol encoding evaluates it again with an entry object. Support
    # both contexts so every legend label has a finite anchor.
    return {"expr": "(" + json.dumps(mapping, separators=(",", ":")) + ")[isObject(datum) ? datum.value : datum]"}


def _legend_symbols(full: dict, kind: str, count: int, size: float) -> dict:
    # Use the actual generated marks, including SVG-path markers, rather than a
    # second marker conversion table that could drift from the chart itself.
    properties = []
    for i in range(count):
        marks = {layer.get("name"): layer.get("mark", {}) for layer in full["layer"]}
        if kind.startswith("line") and f"line_{i}" in marks:
            mark = marks[f"line_{i}"]
            properties.append(("stroke", mark.get("strokeDash", []), mark.get("strokeWidth", 1.8)))
        elif kind.startswith("bar"):
            properties.append(("square", [], 1))
        else:
            mark = marks.get(f"scatter_{i}", marks.get(f"line_markers_{i}", {}))
            properties.append((mark.get("shape", "circle"), [], mark.get("strokeWidth", 1)))
    return {"symbolType": _expression([p[0] for p in properties]),
            "symbolDash": _expression([p[1] for p in properties]),
            "symbolStrokeWidth": _expression([p[2] for p in properties]),
            "symbolSize": size ** 2}


def _best_corner(full: dict, legend_width: float, legend_height: float) -> str:
    """Choose the least occupied corner in the final transformed plot space.

    Count bar rectangle intersections and point/line-segment bounding boxes.
    This is a deterministic placement heuristic, not Matplotlib's algorithm.
    """
    from plot_layout import _transform
    axes = full["layer"][0]["encoding"]
    projections = {}
    for axis, length in (("x", full["width"]), ("y", full["height"])):
        scale = axes[axis]["scale"]
        domain = scale["domain"]
        transform, _ = _transform(scale, domain, [], axis)
        low, high = [transform(v) for v in domain]
        reverse = bool(scale.get("reverse")) ^ (axis == "y")
        def project(value, t=transform, lo=low, hi=high, span=length, rev=reverse):
            fraction = (t(value) - lo) / (hi - lo)
            return (1 - fraction if rev else fraction) * span
        projections[axis] = project
    boxes, previous = [], {}
    kind = full["usermeta"]["semantic"]["kind"]
    for row in full["data"]["values"]:
        if kind.startswith("bar"):
            x = sorted(projections["x"](row[f"plot_x{k}"]) for k in (0, 1))
            y = sorted(projections["y"](row[f"plot_y{k}"]) for k in (0, 1))
            boxes.append((x[0], y[0], x[1], y[1]))
        else:
            x, y = projections["x"](row["plot_x"]), projections["y"](row["plot_y"])
            boxes.append((x - 4, y - 4, x + 4, y + 4))
            sid = row["series_id"]
            if kind.startswith("line") and sid in previous:
                px, py = previous[sid]
                boxes.append((min(px, x), min(py, y), max(px, x), max(py, y)))
            previous[sid] = x, y
    w, h = full["width"], full["height"]
    corners = [("top-right", w - legend_width, 0), ("top-left", 0, 0),
               ("bottom-right", w - legend_width, h - legend_height),
               ("bottom-left", 0, h - legend_height)]
    def score(corner):
        _, x, y = corner
        return sum(max(0, min(x + legend_width, b[2]) - max(x, b[0])) *
                   max(0, min(y + legend_height, b[3]) - max(y, b[1])) for b in boxes)
    return min(corners, key=score)[0]


def apply_presentation(full: dict, cfg: dict) -> dict:
    result = copy.deepcopy(full)
    style = cfg.get("style", {})
    font = selected_font(cfg)
    kind = full["usermeta"]["semantic"]["kind"]
    text_color = style.get("text_color", "#222222")
    axes_source = cfg.get("_render_axes", cfg.get("render_axes", {}))
    ticks_source = axes_source.get("tick_styles", {})
    audit = result["usermeta"].setdefault("presentation", {})
    audit.update(version="vsr-presentation/1.0", font=font,
                 tick_style_source="native_render" if ticks_source else "configured_or_default",
                 legend_shadow="not_supported" if style.get("legend_shadow") else "not_requested")
    # Matplotlib draws all four spines. A view border avoids painting bottom/left
    # twice and is a guide, not extra observation geometry.
    border = bool(style.get("spine_visible", True))
    result["config"]["view"].update(stroke=style.get("spine_color", text_color) if border else None,
                                     strokeWidth=style.get("spine_width", 1))
    title = result["title"]
    title.update(font=font["family"], fontWeight=cfg.get("title_weight", font["weight"]),
                 fontStyle=cfg.get("title_style", font["style"]),
                 anchor={"left": "start", "center": "middle", "right": "end"}.get(cfg.get("title_loc"), "middle"))
    legend_options = None
    for layer in result["layer"]:
        for axis in ("x", "y"):
            guide = layer.get("encoding", {}).get(axis, {}).get("axis")
            if not isinstance(guide, dict):
                continue
            ticks = ticks_source.get(axis, {})
            length = float(ticks.get("length", style.get("tick_length", 3.5)))
            direction = ticks.get("direction", style.get("tick_direction", "out"))
            if direction not in {"in", "out"}:
                raise ValueError(f"Unsupported tick direction: {direction}")
            guide.update(labelFont=font["family"], titleFont=font["family"],
                         labelFontWeight=font["weight"], titleFontWeight=font["weight"],
                         labelFontStyle=font["style"], titleFontStyle=font["style"],
                         gridDash=DASHES[style.get("grid_style", "-")], domain=False,
                         tickColor=ticks.get("color", text_color),
                         tickWidth=ticks.get("width", style.get("tick_width", 0.8)),
                         ticks=ticks.get("visible", True))
            # An ExprRef is supported by VL for signed Vega tick lengths. Keep
            # label padding nonnegative so inward ticks cannot pull labels inside.
            guide["tickSize"] = {"expr": str(-length)} if direction == "in" else length
            guide["labelPadding"] = float(style.get("tick_pad", 3)) + (length if direction == "in" else 0)
        color = layer.get("encoding", {}).get("color", {})
        legend = color.get("legend")
        if not isinstance(legend, dict):
            continue
        if legend_options is None:
            size = float(style.get("legend_size", 10))
            count = len(color["scale"]["domain"])
            frame = bool(style.get("legend_frame", True))
            alpha = float(style.get("legend_framealpha", 0.9))
            columns = max(1, int(style.get("legend_ncol", 1)))
            legend_options = dict(
                labelFont=font["family"], titleFont=font["family"],
                labelFontWeight=font["weight"], titleFontWeight=font["weight"],
                labelFontStyle=font["style"], titleFontStyle=font["style"],
                fillColor=_rgba(style.get("axes_face", "white"), alpha) if frame else None,
                strokeColor=_rgba("#cccccc", alpha) if frame else None,
                cornerRadius=2 if frame else 0,
                padding=float(style.get("legend_borderpad", 0.35)) * size,
                offset=float(style.get("legend_borderaxespad", 0.2)) * size,
                rowPadding=float(style.get("legend_labelspacing", 0.3)) * size,
                columnPadding=float(style.get("legend_columnspacing", 1)) * size,
                labelOffset=float(style.get("legend_handletextpad", 0.5)) * size,
                columns=columns, direction="vertical", gridAlign="each",
                **_legend_symbols(full, kind, count, size * float(style.get("legend_handlelength", 1.5))))
            names = [s["series_name"] for s in full["data"]["values"] if s["point_index"] == 0]
            max_chars = max(map(len, names), default=8)
            lw = columns * (min(max_chars * size * 0.8, 240) + size * 2.5) + 2 * legend_options["padding"]
            lh = math.ceil(count / columns) * (size * 1.3 + legend_options["rowPadding"]) + 2 * legend_options["padding"]
            loc = style.get("legend_loc", "upper right")
            reason = "source_location"
            if style.get("legend_outside") or lw > full["width"] * 0.85 or lh > full["height"] * 0.85:
                orient = "right"
                reason = "source_outside" if style.get("legend_outside") else "space_for_complete_legend"
            elif loc == "best":
                orient = _best_corner(full, lw, lh)
                reason = "least_occupied_corner"
            elif loc in {"upper left", "upper right", "lower left", "lower right"}:
                orient = {"upper left": "top-left", "upper right": "top-right",
                          "lower left": "bottom-left", "lower right": "bottom-right"}[loc]
            else:
                orient = "none"
                xpos = 0 if loc == "center left" else full["width"] - lw if loc in {"center right", "right"} else (full["width"] - lw) / 2
                ypos = 0 if loc == "upper center" else full["height"] - lh if loc == "lower center" else (full["height"] - lh) / 2
                legend_options.update(legendX=max(0, xpos), legendY=max(0, ypos))
            legend_options["orient"] = orient
            audit["legend"] = {"requested": loc, "chosen": orient, "reason": reason, "frame": frame, "columns": columns}
        legend.update(copy.deepcopy(legend_options))
    return result
