"""Native, independently renderable pie and precomputed box plot specifications."""
import copy
from decimal import Decimal
import json
import math

from generation.summaries import canonical_numbers, pie_label_mode
from precision import (PERCENT_FORMAT, PERCENT_SPECIFIER, PRECISION_VERSION,
                       box_projection, ordered_projection, percentage_fraction, percentage_parts)
from spec_format import format_spec
from table_metadata import attach_tables

SCHEMA = "https://vega.github.io/schema/vega-lite/v6.json"
LEGACY_PIE_METRIC_TITLES = {"Share (%)", "Value"}


def _pie_metric_title(title):
    if isinstance(title, str) and (not title.strip() or title.strip() in LEGACY_PIE_METRIC_TITLES):
        return None
    return title


def pie_value_error(values, percent_total=None):
    if not all(type(value) in (int, float) and math.isfinite(value) and value >= 0 for value in values):
        return "Pie values must be finite and nonnegative"
    if not any(value > 0 for value in values):
        return "Pie values must have a positive total"
    if percent_total is not None and not math.isclose(sum(values), percent_total):
        return f"Percentage pie must sum to {percent_total}"
    return None


def _pie_percent_format(theta):
    fmt = theta.get("format")
    if isinstance(fmt, str) and theta.get("formatType", "number") == "number" and PERCENT_SPECIFIER.fullmatch(fmt):
        return fmt
    return None


def _spec(kind, rows, options, axes):
    categories = [row["category"] for row in rows]
    size = options["size"]
    result = {"$schema": SCHEMA, "title": options["title"], "data": {"values": copy.deepcopy(rows)},
              "width": size, "height": size}
    color = {"field": "category", "type": "nominal", "sort": categories,
             "scale": {"domain": categories}, "legend": {"title": None, "orient": options["legend_position"]} if options["show_legend"] else None}
    if kind == "pie":
        radius = size * .34
        inner = radius * options["hole_ratio"] if options["donut"] else 0
        percentage = options["value_mode"] == "percent"
        percent_format = options.get("percent_format", PERCENT_FORMAT)
        numbers = {row["category"]: pie_label(row["value"], percentage, percent_format) for row in rows}
        label_mode = options["label_mode"]
        zero_categories = [row["category"] for row in rows if row["value"] == 0]
        category_values = {category: category + ": " + number for category, number in numbers.items()}
        if color["legend"] is not None and (label_mode == "legend_value" or zero_categories):
            labels = {category: category_values[category] if label_mode == "legend_value" or category in zero_categories
                      else category for category in categories}
            color["legend"]["labelExpr"] = "(" + json.dumps(labels) + ")[datum.label]"
        for index, row in enumerate(result["data"]["values"]):
            row["sector_order"] = index
        order = {"field": "sector_order", "type": "quantitative", "sort": "ascending"}
        theta = {"field": "value", "type": "quantitative", "stack": True,

                 "scale": {"range": [options["rotation"], options["rotation"] + 2 * math.pi]}}
        metric_title = _pie_metric_title(options.get("value_title"))
        if metric_title:
            theta["title"] = metric_title
        result.update(encoding={"theta": theta, "color": color, "order": order},
                      layer=[{"name": "sectors", "mark": {"type": "arc", "innerRadius": inner, "outerRadius": radius}}])
        if label_mode not in {"legend_value", "none"}:
            outside = label_mode in {"category", "category_value"}
            if label_mode == "category":
                expression = "datum.category"
            else:
                labels = category_values if outside else numbers
                expression = "(" + json.dumps(labels) + ")[datum.category]"
            label_mark = {"type": "text", "radius": radius + 30 if outside else max(radius * .78, (radius + inner) / 2),
                          "fontSize": 10 if len(rows) >= 7 else 11, "color": "#111827"}
            if outside:
                total = sum(row["value"] for row in rows)
                previous = 0
                alignments = {}
                for row in rows:
                    midpoint = options["rotation"] + 2 * math.pi * (previous + row["value"] / 2) / total
                    alignments[row["category"]] = "left" if math.sin(midpoint) >= 0 else "right"
                    previous += row["value"]
                label_mark["align"] = {"expr": "(" + json.dumps(alignments) + ")[datum.category]"}
            result["layer"].append({"name": "sector_labels", "mark": label_mark,
                                    "encoding": {"text": {"value": {"expr": expression}}, "color": {"value": "#111827"}}})
        if zero_categories:
            # Keep degenerate arcs from painting radial strokes, and avoid coincident numeric labels.
            for layer in result["layer"]:
                layer["transform"] = [{"filter": "datum.value > 0"}]
            if color["legend"] is None:
                # Autosize includes text below the plot without shifting the pie's center.
                positions = {category: size + 8 + 18 * index for index, category in enumerate(zero_categories)}
                result["layer"].append({
                    "name": "zero_labels", "transform": [{"filter": "datum.value === 0"}],
                    "mark": {"type": "text", "align": "center", "baseline": "top", "fontSize": 11,
                             "x": size / 2, "y": {"expr": "(" + json.dumps(positions) + ")[datum.category]"}},
                    "encoding": {"theta": {"value": 0}, "color": {"value": "#111827"},
                                 "text": {"value": {"expr": "(" + json.dumps(category_values) + ")[datum.category]"}}},
                })
    else:
        horizontal = options["orientation"] == "horizontal"
        category_axis, value_axis = ("y", "x") if horizontal else ("x", "y")
        result["encoding"] = {category_axis: {"field": "category", "type": "nominal", "sort": categories,
                                              "axis": {"title": None, "labelAngle": 0, "labelLimit": 0}}, "color": color}
        if horizontal:
            result["height"] = max(220, len(rows) * 55)
        else:
            result["width"] = max(size, len(rows) * 82)
        orient = "vertical" if horizontal else "horizontal"
        box_size = options["box_size"]
        guide = {"title": options["value_title"]}
        axis_format = axes.get(f"{value_axis}_format")
        if axis_format is not None:
            guide["format"] = axis_format
        def position(field):
            return {"field": field, "type": "quantitative", "scale": {"zero": False},
                    "axis": dict(guide)}
        result["layer"] = [
            {"name": "whiskers", "mark": {"type": "rule"}, "encoding": {value_axis: position("lower"), value_axis + "2": {"field": "upper"}}},
            {"name": "boxes", "mark": {"type": "bar", "size": box_size, "orient": options["orientation"]},
             "encoding": {value_axis: position("q1"), value_axis + "2": {"field": "q3"}}},
            *[{"name": "cap_" + field, "mark": {"type": "tick", "orient": orient, "size": box_size * .65, "thickness": 1.5},
               "encoding": {value_axis: position(field)}} for field in ("lower", "upper")],
            {"name": "medians", "mark": {"type": "tick", "orient": orient, "size": box_size, "thickness": 2.5, "color": "#111827"},
             "encoding": {value_axis: position("median"), "color": {"value": "#111827"}}},
            {"name": "outliers", "data": {"values": [{"category": row["category"], "value": value} for row in rows for value in row["outliers"]]},
             "mark": {"type": "point", "shape": options["point_shape"], "size": 45, "opacity": 1},
             "encoding": {value_axis: position("value")}}]
        for row in result["data"]["values"]:
            row.pop("outliers")
    return result


OPTION_KEYS = ("size", "title", "legend_position", "show_legend", "hole_ratio", "donut", "value_mode", "label_mode", "rotation",
               "orientation", "box_size", "point_shape", "value_title")


def project_rows(full):
    """Copy semantic columns in Full order, without rounding or recomputing data."""
    kind = full["usermeta"]["semantic"]["kind"]
    fields = ("category", "value") if kind == "pie" else ("category", "lower", "q1", "median", "q3", "upper")
    return [{field: copy.deepcopy(row[field]) for field in fields} for row in full["data"]["values"]]


def _field_semantics(full, channel):
    """Retain explicit scientific labels/formats from Full, never infer units."""
    from compact import unit_format
    result = {}
    for view in [full, *full.get("layer", [])]:
        definition = view.get("encoding", {}).get(channel, {})
        if "field" not in definition:
            continue
        guide = definition.get("legend" if channel == "color" else "axis") or {}
        title = guide.get("title", definition.get("title"))
        if "title" not in result and title not in (None, "", []):
            result["title"] = copy.deepcopy(title)
        if ("axis" not in result and channel in ("x", "y") and definition.get("type") == "quantitative"
                and unit_format(guide.get("format"), guide.get("formatType", "number"))):
            result["axis"] = {"format": guide["format"]}
    return result


def compact_spec(full):
    semantic = full["usermeta"]["semantic"]
    options = semantic["options"]
    rows = project_rows(full)
    result = {"data": {"values": rows}}
    title = full.get("title", options.get("title"))
    if isinstance(title, dict):
        title = title.get("text")
    if title:
        result["title"] = copy.deepcopy(title)
    if semantic["kind"] == "pie":
        fmt = _pie_percent_format(full.get("encoding", {}).get("theta", {}))
        theta_encoding = {"field": "value", "type": "quantitative", **_field_semantics(full, "theta")}
        if _pie_metric_title(theta_encoding.get("title")) is None:
            theta_encoding.pop("title", None)
        if fmt is not None:
            theta_encoding["format"] = fmt
        elif options.get("value_mode") == "percent":
            theta_encoding["format"] = options.get("percent_format", PERCENT_FORMAT)
        result.update(mark={"type": "arc"},
                      encoding={"theta": theta_encoding,
                                "color": {"field": "category", "type": "nominal", **_field_semantics(full, "color")}})
        return format_spec(attach_tables(result))
    horizontal = options["orientation"] == "horizontal"
    category_axis, value_axis = ("y", "x") if horizontal else ("x", "y")
    result["encoding"] = {
        category_axis: {"field": "category", "type": "nominal", "sort": None, **_field_semantics(full, category_axis)}}
    result["layer"] = [
        {"mark": {"type": "rule"}, "encoding": {value_axis: {"field": "lower", "type": "quantitative", **_field_semantics(full, value_axis)},
                                                value_axis + "2": {"field": "upper"}}},
        {"mark": {"type": "bar"},
         "encoding": {value_axis: {"field": "q1", "type": "quantitative"},
                      value_axis + "2": {"field": "q3"}}},
        {"mark": {"type": "tick"},
         "encoding": {value_axis: {"field": "median", "type": "quantitative"}}},
        {"data": {"values": outlier_rows(full)}, "mark": {"type": "point"},
         "encoding": {value_axis: {"field": "value", "type": "quantitative"}}}]
    return format_spec(attach_tables(result))


def outlier_rows(spec):
    for layer in spec.get("layer", []):
        mark = layer.get("mark")
        if isinstance(mark, dict) and mark.get("type") == "point" and "data" in layer:
            return copy.deepcopy(layer["data"]["values"])
    return [{"category": row["category"], "value": value}
            for row in spec["data"]["values"] for value in row.get("outliers", [])]


def target_kind(spec):
    """Identify statistical targets without depending on full-spec metadata."""
    if not isinstance(spec, dict):
        return None
    mark = spec.get("mark")
    if mark == "arc" or isinstance(mark, dict) and mark.get("type") == "arc":
        return "pie"
    data = spec.get("data")
    rows = data.get("values", []) if isinstance(data, dict) else []
    if isinstance(rows, list) and rows and isinstance(rows[0], dict) and {"q1", "median", "q3"} <= rows[0].keys():
        return "boxplot"
    return None


def validate_compact(spec):
    """Bounded compact-v4 extension: exact data fields and necessary geometry only."""
    def check(ok, message):
        if not ok:
            raise ValueError("Unsupported/noncanonical compact-v4 statistical target: " + message)
    kind = target_kind(spec)
    check(kind is not None, "unknown statistical chart")
    check(isinstance(spec.get("data"), dict) and set(spec["data"]) == {"values"}, "inline values only")
    rows = spec["data"]["values"]
    fields = {"category", "value"} if kind == "pie" else {"category", "lower", "q1", "median", "q3", "upper"}
    check(isinstance(rows, list) and bool(rows), "empty table")
    check(all(isinstance(row, dict) and set(row) == fields for row in rows), "statistic fields")
    check(all(isinstance(row["category"], str) and row["category"] for row in rows), "category names")
    check(len({row["category"] for row in rows}) == len(rows), "duplicate categories")
    if "title" in spec:
        title = spec["title"]
        check(isinstance(title, str) and bool(title) or isinstance(title, list) and bool(title)
              and all(isinstance(line, str) for line in title), "title")
    points = outlier_rows(spec) if kind == "boxplot" else []
    categories = {row["category"] for row in rows}
    check(all(set(point) == {"category", "value"} and point["category"] in categories
              and type(point["value"]) in (int, float) and math.isfinite(point["value"]) for point in points),
          "invalid outlier row")
    enc = spec.get("encoding", {})
    check(isinstance(enc, dict) and all(isinstance(value, dict) for value in enc.values()), "encoding objects")
    options = {"title": spec.get("title")}
    if kind == "pie":
        total = 1 if _pie_percent_format(enc.get("theta", {})) is not None else None
        error = pie_value_error([row["value"] for row in rows], total)
        check(error is None, error)
    else:
        for row in rows:
            values = [row[key] for key in ("lower", "q1", "median", "q3", "upper")]
            check(all(type(value) in (int, float) and math.isfinite(value) for value in values), "finite numbers required")
            lower, q1, median, q3, upper = [Decimal(str(row[key])) for key in ("lower", "q1", "median", "q3", "upper")]
            low, high = q1 - Decimal("1.5") * (q3 - q1), q3 + Decimal("1.5") * (q3 - q1)
            check(low <= lower <= q1 <= median <= q3 <= upper <= high, "five-number ordering/fences")
            check(all(Decimal(str(value)) < low or Decimal(str(value)) > high for value in (point["value"] for point in points if point["category"] == row["category"])), "outliers inside fences")
        horizontal = enc.get("y", {}).get("field") == "category"
        options["orientation"] = "horizontal" if horizontal else "vertical"
        layers = spec.get("layer")
        check(isinstance(layers, list) and len(layers) == 4, "four statistical layers required")
    full = {"data": {"values": rows}, "encoding": enc, "layer": spec.get("layer", []),
            "usermeta": {"semantic": {"kind": kind, "options": options}}}
    expected = compact_spec(full)
    if "usermeta" not in spec:
        expected.pop("usermeta")
    actual = format_spec(spec)
    if kind == "pie":
        theta = actual.get("encoding", {}).get("theta", {})
        title = theta.get("title")
        if isinstance(title, str) and title.strip() in LEGACY_PIE_METRIC_TITLES:
            # Compact-only archives remain readable without rewriting the original spec.
            del theta["title"]
    check(actual == expected, "unnecessary settings or incorrect statistical mapping")


def pie_label(value, percentage, percent_format=None):
    if percentage and not percent_format:
        return format(value, ".0%")
    decimal = Decimal(str(value))
    text = format(decimal.scaleb(2) if percentage else decimal, "f")
    return (text.rstrip("0").rstrip(".") if "." in text else text) + ("%" if percentage else "")


def final_rows(kind, cfg, precision_v1=False):
    rows = cfg["rows"] if precision_v1 else canonical_numbers(cfg["rows"])
    if precision_v1 and kind == "boxplot":
        return [box_projection(row) for row in rows]
    if precision_v1 and kind == "pie":
        values = [row["value"] for row in rows]
        percent = cfg["value_mode"] == "percent"
        error = pie_value_error(values, 100 if percent else None)
        if error is not None:
            raise ValueError(error)
        projected = percentage_parts(values) if percent else ordered_projection(values)
        return [dict(row, value=value) for row, value in zip(rows, projected)]
    return rows


def build_pair(kind, cfg, *, precision_v1=False, observation_rows=None):
    from presentation import apply_presentation
    from text_layout import apply_text_layout, fit_category_axis
    cfg = copy.deepcopy(cfg)
    options = {key: cfg[key] for key in OPTION_KEYS if key in cfg}
    if cfg.get("sampling", {}).get("language") == "zh":
        options["language"] = "zh"
    rows = copy.deepcopy(observation_rows) if observation_rows is not None else final_rows(kind, cfg, precision_v1)
    if kind == "pie":
        options["label_mode"] = pie_label_mode(options["value_mode"], options["show_legend"], options["label_mode"])
        percentage = options["value_mode"] == "percent"
        total = (100 if observation_rows is None else 1) if percentage else None
        error = pie_value_error([row["value"] for row in rows], total)
        if error is not None:
            raise ValueError(error)
        if percentage:
            if observation_rows is None:
                for row in rows:
                    row["value"] = percentage_fraction(row["value"])
            digits = max((len(Decimal(str(row["value"])).normalize().as_tuple().digits) for row in rows), default=4)
            options["percent_format"] = PERCENT_FORMAT if digits <= 4 else f".{digits}~p"
    full = _spec(kind, rows, options, cfg.get("_render_axes") or {})
    if ratio := cfg.get("layout_ratio"):
        full["width"] = max(full["width"], round(full["height"] * ratio))
    semantic = {"kind": kind, "options": options}
    full["usermeta"] = {"semantic": semantic}
    if precision_v1:
        full["usermeta"]["precision_version"] = PRECISION_VERSION
    full["title"] = {"text": cfg["title"], "fontSize": cfg["style"].get("title_size", 18),
                     "color": cfg["style"].get("text_color", "#111827")}
    full["config"] = {"view": {"stroke": None}}
    full["background"] = cfg["style"].get("facecolor", "white")
    full = apply_text_layout(apply_presentation(full, cfg))
    if kind == "pie" and options["label_mode"] in {"category", "category_value"}:
        # Long labels can cross the edge of the plotting rectangle.
        full["config"]["view"]["stroke"] = None
    if kind == "boxplot" and cfg.get("sampling", {}).get("text_profile") == "expanded-v1":
        channel = "y" if options["orientation"] == "horizontal" else "x"
        fit_category_axis(full, channel, [row["category"] for row in rows])
    colors = list(cfg["style"]["series_colors"])
    if len(colors) < len(rows):
        colors += ["#b279a2", "#ff9da6", "#9d755d", "#bab0ac", "#59a14f", "#edc949"]
    full["encoding"]["color"]["scale"]["range"] = colors[:len(rows)]
    legend = full["encoding"]["color"]["legend"]
    if legend is not None:
        legend.update(labelLimit=0, orient=cfg["legend_position"], columns=len(rows) if cfg["legend_position"] in {"top", "bottom"} and len(rows) <= 4 else 1)
    text_color = cfg["style"].get("text_color", "#111827")
    font = full["usermeta"]["presentation"]["font"]
    full["config"].update(axis={"labelColor": text_color, "titleColor": text_color, "grid": cfg["style"].get("grid_visible", True)},
                          legend={"labelColor": text_color})
    for role, prefixes in (("axis", ("label", "title")), ("legend", ("label", "title"))):
        for prefix in prefixes:
            full["config"][role].update({prefix + "Font": font["family"], prefix + "FontWeight": font["weight"], prefix + "FontStyle": font["style"]})
    for layer in full["layer"]:
        if layer["name"] == "medians":
            layer["encoding"]["color"] = {"value": text_color}
        if layer["name"] == "sectors":
            layer["mark"].update(stroke=full["background"], strokeWidth=cfg["style"].get("line_width", 1))
        if layer["name"] in {"sector_labels", "zero_labels"}:
            layer["mark"].update(font=font["family"], fontWeight=font["weight"], fontStyle=font["style"])
            layer["encoding"]["color"] = {"value": text_color}
            if layer["name"] == "sector_labels" and options["label_mode"] == "value":
                from PIL import ImageColor
                contrast = {}
                for row, color in zip(rows, colors):
                    red, green, blue = ImageColor.getrgb(color)[:3]
                    contrast[row["category"]] = "#111827" if .299 * red + .587 * green + .114 * blue > 150 else "#ffffff"
                layer["encoding"]["color"] = {"value": {"expr": "(" + json.dumps(contrast) + ")[datum.category]"}}
    layout = {"final_plot_size": [full["width"], full["height"]], "source": "native_statistical"}
    source = {"kind": kind, "family": cfg["family"], "rows": project_rows(full), "row_count": len(rows),
              "semantic": semantic, "plot_layout": layout, "presentation": full["usermeta"]["presentation"]}
    from compact import validate_target
    full = format_spec(attach_tables(full, kind))
    target = compact_spec(full)
    validate_target(target)
    return full, target, source
