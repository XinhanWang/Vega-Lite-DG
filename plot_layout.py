"""Fit complete observation geometry inside the plot before rendering.

This policy changes presentation only: source observations, uncertainty and
series identity are never edited.  Native limits are lower bounds on the visible
domain, rather than permission to hide data.  The adapter calls this before
creating hatch/reference geometry so those layers use the fitted coordinates.
"""
from __future__ import annotations

import copy
import math
from typing import Callable


POLICY = "complete-observation-domain-v1"
MAX_PLOT_SIDE = 16384.0
SAFETY_PX = 2.0


def _finite(value, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    return float(value)


def _scale_for_axis(cfg: dict, layers: list[dict], axis: str) -> dict:
    definitions = []
    for layer in layers:
        channel = layer.get("encoding", {}).get(axis, {})
        scale = channel.get("scale")
        if isinstance(scale, dict):
            definitions.append({key: scale[key] for key in ("type", "base", "exponent", "constant") if key in scale})
    if definitions:
        first = definitions[0]
        if any(item != first for item in definitions[1:]):
            raise ValueError(f"Cannot fit inconsistent {axis} scale transforms across layers")
        return {"type": "linear", **first}
    native = cfg.get("_render_axes") or {}
    return {"type": native.get(f"{axis}scale", native.get(f"{axis}_scale", "linear"))}


def _transform(scale: dict, domain: list[float], values: list[float], axis: str) -> tuple[Callable, Callable]:
    kind = scale.get("type", "linear")
    if kind in {"linear", "time", "utc"}:
        return lambda x: x, lambda x: x
    if kind == "log":
        if "base" in scale and (_finite(scale["base"], f"{axis} log base") <= 0 or scale["base"] == 1):
            raise ValueError(f"{axis} log base must be positive and different from 1")
        positive = all(value > 0 for value in domain)
        negative = all(value < 0 for value in domain)
        if not positive and not negative:
            raise ValueError(f"{axis} log domain must be entirely positive or entirely negative; zero is not representable")
        if any(value <= 0 if positive else value >= 0 for value in values):
            raise ValueError(f"{axis} observation/interval geometry crosses zero or has the wrong sign for the log domain")
        if positive:
            return math.log, math.exp
        return lambda x: -math.log(-x), lambda x: -math.exp(-x)
    if kind == "symlog":
        constant = _finite(scale.get("constant", 1), f"{axis} symlog constant")
        if constant <= 0:
            raise ValueError(f"{axis} symlog constant must be positive")
        return (lambda x: math.copysign(math.log1p(abs(x) / constant), x),
                lambda x: math.copysign(math.expm1(abs(x)) * constant, x))
    if kind in {"pow", "sqrt"}:
        exponent = 0.5 if kind == "sqrt" else _finite(scale.get("exponent", 1), f"{axis} power exponent")
        if exponent <= 0:
            raise ValueError(f"{axis} power exponent must be positive")
        return (lambda x: math.copysign(abs(x) ** exponent, x),
                lambda x: math.copysign(abs(x) ** (1 / exponent), x))
    raise ValueError(f"Cannot safely fit unsupported {axis} scale type {kind!r}")


def _extent_values(kind: str, rows: list[dict], axis: str) -> list[float]:
    values = []
    horizontal = kind.startswith("barh")
    for row in rows:
        fields = [f"plot_{axis}0", f"plot_{axis}1"] if kind.startswith("bar") else [f"plot_{axis}"]
        if kind.startswith("bar") and axis == ("x" if horizontal else "y"):
            fields += [key for key in ("error_lower", "error_upper") if key in row]
        values.extend(_finite(row[field], f"{axis} geometry {field}") for field in fields)
    if not values:
        raise ValueError("Cannot fit a chart without observations")
    return values


def _at(cfg: dict, plural: str, single: str, index: int, default):
    sequence = cfg.get(plural)
    return sequence[index] if sequence is not None else cfg.get(single, default)


def _fallback_marks(kind: str, cfg: dict, rows: list[dict]) -> list[dict]:
    """Permit direct use without importing adapter internals or changing RNG."""
    if kind.startswith("bar"):
        marks = [{"type": "bar", "strokeWidth": cfg.get("linewidth", 1)}]
        if any("error_lower" in row for row in rows):
            error = cfg.get("error_kw") or {}
            marks += [{"type": "rule", "strokeWidth": error.get("elinewidth", 1)},
                      {"type": "tick", "orient": "vertical" if kind.startswith("barh") else "horizontal",
                       "size": 2 * (cfg.get("capsize") or 3), "thickness": error.get("capthick", 1)}]
        return marks
    count = 1 + max(int(row.get("series_index", 0)) for row in rows)
    marks = []
    for index in range(count):
        if kind.startswith("line"):
            if _at(cfg, "linestyles", "linestyle", index, "-") not in {None, "None", "none", "", " "}:
                marks.append({"type": "line", "strokeWidth": _at(cfg, "widths", "linewidth", index, 1.8)})
            if _at(cfg, "markers", "marker", index, None) not in {None, "None", "none", "", " "}:
                marks.append({"type": "point", "size": _at(cfg, "marker_sizes", "markersize", index, 6) ** 2})
        else:
            marks.append({"type": "point", "size": _at(cfg, "sizes", "size", index, 25),
                          "strokeWidth": _at(cfg, "linewidths", "linewidth", index, 0.5)})
    return marks


def _pixel_margins(kind: str, cfg: dict, rows: list[dict], layers: list[dict]) -> tuple[dict, list[dict]]:
    marks = [layer.get("mark", {}) for layer in layers] if layers else _fallback_marks(kind, cfg, rows)
    margins = {"x": SAFETY_PX, "y": SAFETY_PX}
    details = []
    for value in marks:
        mark = {"type": value} if isinstance(value, str) else value
        mark_type = mark.get("type")
        stroke = _finite(mark.get("strokeWidth", 1), "mark stroke width")
        if stroke < 0:
            raise ValueError("Mark stroke width cannot be negative")
        # Vega paint bounds include the default miter limit (4) times half
        # the stroke width.  Keep it even for filled symbols to cover the
        # conservative scenegraph bounds used by our post-render quality gate.
        x = y = 2 * stroke + SAFETY_PX
        if mark_type in {"point", "circle", "square"}:
            size = _finite(mark.get("size", 30), "point size")
            if size < 0:
                raise ValueError("Point size cannot be negative")
            # All adapter symbols are built-ins or paths inside [-1, 1].
            # 1.5 sqrt(size) safely covers their asymmetric triangle, star,
            # cross and custom-path extents as well as circles and squares.
            x = y = 1.5 * math.sqrt(size) + 2 * stroke + SAFETY_PX
        elif mark_type == "tick":
            size = _finite(mark.get("size", 20), "error cap size")
            thickness = _finite(mark.get("thickness", 1), "error cap thickness")
            if min(size, thickness) < 0:
                raise ValueError("Error cap dimensions cannot be negative")
            across, along = thickness / 2 + SAFETY_PX, size / 2 + SAFETY_PX
            if mark.get("orient") == "vertical":
                x, y = across, along
            elif mark.get("orient") == "horizontal":
                x, y = along, across
            else:
                x = y = max(across, along)
        margins["x"], margins["y"] = max(margins["x"], x), max(margins["y"], y)
        details.append({"mark": mark_type, "x_px": x, "y_px": y})
    return margins, details


def _fit_transformed(old_lo: float, old_hi: float, data_lo: float, data_hi: float,
                     fraction: float) -> tuple[float, float]:
    """Smallest domain containing old bounds with fractional data clearances."""
    span = max(old_hi - old_lo, (data_hi - data_lo) / (1 - 2 * fraction),
               (old_hi - data_lo) / (1 - fraction), (data_hi - old_lo) / (1 - fraction))
    lower = max(data_hi - (1 - fraction) * span, old_hi - span)
    upper = min(data_lo - fraction * span, old_lo)
    midpoint_choice = (old_lo + old_hi - span) / 2
    lo = min(upper, max(lower, midpoint_choice))
    hi = lo + span
    # Return the original floats exactly when they already provide clearance.
    if data_lo - old_lo >= fraction * (old_hi - old_lo) and old_hi - data_hi >= fraction * (old_hi - old_lo):
        return old_lo, old_hi
    epsilon = max(abs(span), 1.0) * 1e-12
    return min(old_lo, lo - epsilon), max(old_hi, hi + epsilon)


def fit_plot_layout(kind: str, cfg: dict, rows: list[dict], limits: dict,
                    width: float, height: float, *, layers: list[dict] | None = None) -> tuple[dict, float, float, dict]:
    """Expand domains and, if needed, the plot so every observation can fit.

    ``layers`` should contain the main observation/error layers before hatch or
    reference construction.  It supplies the exact scale transform and visual
    mark sizes; ``rows`` supplies interval ends including signed stack geometry.
    Subsequent text layout may enlarge the canvas, but must not shrink it.
    """
    layers = layers or []
    original_dimensions = {"width": _finite(width, "plot width"), "height": _finite(height, "plot height")}
    if min(original_dimensions.values()) <= 0:
        raise ValueError("Plot dimensions must be positive")
    original_limits = copy.deepcopy(limits)
    margins, mark_details = _pixel_margins(kind, cfg, rows, layers)
    # A large glyph can require more room than the existing canvas.  Growing
    # the canvas keeps each margin below one quarter of the plot dimension.
    width = max(float(width), 4 * margins["x"] + 4)
    height = max(float(height), 4 * margins["y"] + 4)
    spans, fitted, axes_audit = {}, {}, {}
    for axis, pixels in (("x", width), ("y", height)):
        if axis not in limits or len(limits[axis]) != 2:
            raise ValueError(f"{axis} limits must have two endpoints")
        domain = [_finite(value, f"{axis} domain") for value in limits[axis]]
        if domain[0] == domain[1]:
            raise ValueError(f"{axis} domain must have nonzero extent")
        values = _extent_values(kind, rows, axis)
        scale = _scale_for_axis(cfg, layers, axis)
        transform, inverse = _transform(scale, domain, values, axis)
        try:
            old_lo, old_hi = sorted(transform(value) for value in domain)
            data_lo, data_hi = min(map(transform, values)), max(map(transform, values))
            fraction = margins[axis] / pixels
            original_clearance = (data_lo - old_lo >= fraction * (old_hi - old_lo)
                                  and old_hi - data_hi >= fraction * (old_hi - old_lo))
            lo, hi = _fit_transformed(old_lo, old_hi, data_lo, data_hi, fraction)
            if original_clearance:
                new_domain = sorted(domain)
            else:
                new_domain = [inverse(lo), inverse(hi)]
                # A mathematically adequate expansion can round straight back
                # onto an endpoint (e.g. a unit range near 1e15).  Round outward
                # in the actual data coordinates and verify the representable
                # transformed bounds, instead of claiming invisible padding.
                for _ in range(8):
                    new_domain = [math.nextafter(new_domain[0], -math.inf),
                                  math.nextafter(new_domain[1], math.inf)]
                    lo, hi = (transform(value) for value in new_domain)
                    if (data_lo - lo >= fraction * (hi - lo)
                            and hi - data_hi >= fraction * (hi - lo)):
                        break
                else:
                    raise ValueError("floating-point precision cannot preserve the requested pixel clearance")
        except (ValueError, OverflowError, ZeroDivisionError) as error:
            raise ValueError(f"Cannot fit finite {axis} {scale.get('type')} coordinates: {error}") from error
        if not all(math.isfinite(value) for value in [lo, hi, *new_domain]) or hi <= lo:
            raise ValueError(f"Fitted {axis} scale is not finite and nondegenerate")
        if domain[0] > domain[1]:
            new_domain.reverse()
        fitted[axis], spans[axis] = new_domain, hi - lo
        axes_audit[axis] = {"scale": scale, "source_limits": domain, "fitted_limits": new_domain,
                            "geometry_extent": [min(values), max(values)], "margin_px": margins[axis],
                            "changed": new_domain != domain}
    native = cfg.get("_render_axes") or {}
    aspect = native.get("aspect", "auto")
    equal_aspect = aspect == "equal" or isinstance(aspect, (int, float)) and not isinstance(aspect, bool) and aspect > 0
    if equal_aspect:
        unit_aspect = 1.0 if aspect == "equal" else _finite(aspect, "unit aspect")
        required_ratio = spans["y"] / spans["x"] * unit_aspect
        if height / width < required_ratio:
            height = width * required_ratio
        else:
            width = height / required_ratio
    if not all(math.isfinite(value) and 0 < value <= MAX_PLOT_SIDE for value in (width, height)):
        raise ValueError(f"Complete data/mark bounds require a plot larger than {int(MAX_PLOT_SIDE)} pixels")
    # Round up: rounding down could remove a promised subpixel clearance.
    width, height = math.ceil(width * 1000) / 1000, math.ceil(height * 1000) / 1000
    dimensions = {"width": width, "height": height}
    audit = {"policy": POLICY, "source_limits": original_limits, "fitted_limits": copy.deepcopy(fitted),
             "source_dimensions": original_dimensions, "fitted_dimensions": dimensions,
             "changed": fitted != original_limits or dimensions != original_dimensions,
             "axes": axes_audit, "mark_padding": mark_details,
             "padding_rationale": "Observation/interval endpoints plus conservative symbol, cap and stroke paint bounds with 2px safety; fit in scale-transform space.",
             "equal_aspect": bool(equal_aspect), "aspect_policy": "Enlarge plot dimensions; never narrow data domains.",
             "observations_changed": False}
    return fitted, width, height, audit
