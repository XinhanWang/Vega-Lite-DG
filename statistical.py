"""Native, independently renderable pie and precomputed box plot specifications."""
import copy
import json
import math
from decimal import Decimal

from generation.summaries import canonical_numbers
from spec_format import format_spec

SCHEMA = "https://vega.github.io/schema/vega-lite/v6.json"


def _spec(kind, rows, options):
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
        suffix = " + '%'" if percentage else ""
        number = "format(datum.value, '~g')" + suffix
        label_mode = options["label_mode"]
        if label_mode == "legend_value" and color["legend"] is not None:
            labels = {row["category"]: f'{row["category"]}: {row["value"]:g}' + ("%" if percentage else "") for row in rows}
            color["legend"]["labelExpr"] = "(" + json.dumps(labels) + ")[datum.label]"
        order = {"field": "sector_order", "type": "quantitative", "sort": "ascending"}
        theta = {"field": "value", "type": "quantitative", "stack": True,
                 "title": "Share (%)" if percentage else "Value",
                 "scale": {"range": [options["rotation"], options["rotation"] + 2 * math.pi]}}
        result.update(transform=[{"calculate": "indexof(" + json.dumps(categories) + ", datum.category)", "as": "sector_order"}],
                      encoding={"theta": theta, "color": color, "order": order},
                      layer=[{"name": "sectors", "mark": {"type": "arc", "innerRadius": inner, "outerRadius": radius}}])
        if label_mode != "legend_value":
            outside = label_mode == "category_value"
            expression = "datum.category + ': ' + " + number if outside else number
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
        def position(field):
            return {"field": field, "type": "quantitative", "scale": {"zero": False},
                    "axis": {"title": options["value_title"]}}
        result["layer"] = [
            {"name": "whiskers", "mark": {"type": "rule"}, "encoding": {value_axis: position("lower"), value_axis + "2": {"field": "upper"}}},
            {"name": "boxes", "mark": {"type": "bar", "size": box_size, "orient": options["orientation"]},
             "encoding": {value_axis: position("q1"), value_axis + "2": {"field": "q3"}}},
            *[{"name": "cap_" + field, "mark": {"type": "tick", "orient": orient, "size": box_size * .65, "thickness": 1.5},
               "encoding": {value_axis: position(field)}} for field in ("lower", "upper")],
            {"name": "medians", "mark": {"type": "tick", "orient": orient, "size": box_size, "thickness": 2.5, "color": "#111827"},
             "encoding": {value_axis: position("median"), "color": {"value": "#111827"}}},
            {"name": "outliers", "transform": [{"flatten": ["outliers"], "as": ["outlier"]}, {"filter": "isValid(datum.outlier)"}],
             "mark": {"type": "point", "shape": options["point_shape"], "size": 45, "opacity": 1},
             "encoding": {value_axis: position("outlier")}}]
        if not any(row["outliers"] for row in rows):
            result["layer"].pop()
    return result


OPTION_KEYS = ("size", "title", "legend_position", "show_legend", "hole_ratio", "donut", "value_mode", "label_mode", "rotation",
               "orientation", "box_size", "point_shape", "value_title")


def project_rows(full):
    """Copy semantic columns in Full order, without rounding or recomputing data."""
    kind = full["usermeta"]["semantic"]["kind"]
    fields = ("category", "value") if kind == "pie" else ("category", "lower", "q1", "median", "q3", "upper", "outliers")
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
        result.update(mark={"type": "arc"},
                      encoding={"theta": {"field": "value", "type": "quantitative", **_field_semantics(full, "theta")},
                                "color": {"field": "category", "type": "nominal", **_field_semantics(full, "color")}})
        return format_spec(result)
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
        {"transform": [{"flatten": ["outliers"]}], "mark": {"type": "point"},
         "encoding": {value_axis: {"field": "outliers", "type": "quantitative"}}}]
    return format_spec(result)


def target_kind(spec):
    """Identify statistical targets without depending on full-spec metadata."""
    if not isinstance(spec, dict):
        return None
    mark = spec.get("mark")
    if mark == "arc" or isinstance(mark, dict) and mark.get("type") == "arc":
        return "pie"
    data = spec.get("data")
    rows = data.get("values", []) if isinstance(data, dict) else []
    if isinstance(rows, list) and rows and isinstance(rows[0], dict) and "outliers" in rows[0]:
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
    fields = {"category", "value"} if kind == "pie" else {"category", "lower", "q1", "median", "q3", "upper", "outliers"}
    check(isinstance(rows, list) and bool(rows), "empty table")
    check(all(isinstance(row, dict) and set(row) == fields for row in rows), "statistic fields")
    check(all(isinstance(row["category"], str) and row["category"] for row in rows), "category names")
    check(len({row["category"] for row in rows}) == len(rows), "duplicate categories")
    if "title" in spec:
        title = spec["title"]
        check(isinstance(title, str) and bool(title) or isinstance(title, list) and bool(title)
              and all(isinstance(line, str) for line in title), "title")
    for row in rows:
        values = [row["value"]] if kind == "pie" else [row[key] for key in ("lower", "q1", "median", "q3", "upper")]
        if kind == "boxplot":
            check(isinstance(row["outliers"], list), "outlier array")
            values += row["outliers"]
        check(all(type(value) in (int, float) and math.isfinite(value) for value in values), "finite numbers required")
        if kind == "pie":
            check(row["value"] > 0, "positive sector values")
        else:
            lower, q1, median, q3, upper = [Decimal(str(row[key])) for key in ("lower", "q1", "median", "q3", "upper")]
            low, high = q1 - Decimal("1.5") * (q3 - q1), q3 + Decimal("1.5") * (q3 - q1)
            check(low <= lower <= q1 <= median <= q3 <= upper <= high, "five-number ordering/fences")
            check(all(Decimal(str(value)) < low or Decimal(str(value)) > high for value in row["outliers"]), "outliers inside fences")
    enc = spec.get("encoding", {})
    check(isinstance(enc, dict) and all(isinstance(value, dict) for value in enc.values()), "encoding objects")
    options = {"title": spec.get("title")}
    if kind == "boxplot":
        horizontal = enc.get("y", {}).get("field") == "category"
        options["orientation"] = "horizontal" if horizontal else "vertical"
        layers = spec.get("layer")
        check(isinstance(layers, list) and len(layers) == 4, "four statistical layers required")
    full = {"data": {"values": rows}, "encoding": enc, "layer": spec.get("layer", []),
            "usermeta": {"semantic": {"kind": kind, "options": options}}}
    check(format_spec(spec) == compact_spec(full), "unnecessary settings or incorrect statistical mapping")


def build_pair(kind, cfg):
    from presentation import apply_presentation
    from text_layout import apply_text_layout
    cfg = copy.deepcopy(cfg)
    cfg["rows"] = canonical_numbers(cfg["rows"])
    options = {key: cfg[key] for key in OPTION_KEYS if key in cfg}
    rows = [dict(row_id=f"r{index:03d}", **row) for index, row in enumerate(cfg["rows"])]
    full = _spec(kind, rows, options)
    semantic = {"kind": kind, "options": options}
    full["usermeta"] = {"semantic": semantic}
    full["title"] = {"text": cfg["title"], "fontSize": cfg["style"].get("title_size", 18),
                     "color": cfg["style"].get("text_color", "#111827")}
    full["config"] = {"view": {"stroke": None}}
    full["background"] = cfg["style"].get("facecolor", "white")
    full = apply_text_layout(apply_presentation(full, cfg))
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
        if layer["name"] == "sector_labels":
            layer["mark"].update(font=font["family"], fontWeight=font["weight"], fontStyle=font["style"])
            layer["encoding"]["color"] = {"value": text_color}
            if cfg["label_mode"] == "value":
                from PIL import ImageColor
                contrast = {}
                for row, color in zip(rows, colors):
                    red, green, blue = ImageColor.getrgb(color)[:3]
                    contrast[row["category"]] = "#111827" if .299 * red + .587 * green + .114 * blue > 150 else "#ffffff"
                layer["encoding"]["color"] = {"value": {"expr": "(" + json.dumps(contrast) + ")[datum.category]"}}
    layout = {"final_plot_size": [full["width"], full["height"]], "source": "native_statistical"}
    source = {"kind": kind, "family": cfg["family"], "rows": rows, "row_count": len(rows),
              "semantic": semantic, "plot_layout": layout, "presentation": full["usermeta"]["presentation"]}
    from compact import validate_target
    full = format_spec(full)
    target = compact_spec(full)
    validate_target(target)
    return full, target, source
