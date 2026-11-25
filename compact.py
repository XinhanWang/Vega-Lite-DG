"""Compact v4 semantic GT; v3 decoding is retained for migration audits."""
from __future__ import annotations

from collections import Counter
import copy
from decimal import Decimal
import json
import math
import re
from typing import Any

from ordering import first_seen, needs_path_order, needs_stack_endpoints, visual_rows
from spec_format import format_spec
from identity import IDENTITIES, ROW_FIELDS, migrate_spec, order_row


KINDS = {"barh_1", "barh_n", "barv_1", "barv_n", "barv_stack", "barh_stack",
         "line_1", "line_n", "scatter_1", "scatter_n"}
_PERCENT_SUFFIX = re.compile(
    r'''(?:datum\.value|format\(\s*datum\.value\s*,\s*(['"])~g\1\s*\))\s*\+\s*(['"])%\2'''
)


def _semantic(spec: dict) -> dict | None:
    value = spec.get("usermeta", {}).get("semantic")
    return value if isinstance(value, dict) and "kind" in value else None


def _primary_encoding(full: dict) -> dict:
    if "encoding" in full:
        return full["encoding"]
    for layer in full.get("layer", []):
        if layer.get("name", "").startswith(("bars_", "line_", "scatter_")):
            return layer["encoding"]
    raise ValueError("Adapter full spec has no primary data encoding")


def _mapping(keys: list[Any], labels: list[str]) -> tuple[dict, bool]:
    mapping = dict(zip(keys, labels))
    return mapping, len(set(mapping.values())) != len(mapping)


def _expr(labels: list[str]) -> str:
    # JSON strings, rather than interpolated literal fragments, handle quotes,
    # backslashes and all Unicode category/series names in Vega expressions.
    return json.dumps(labels, ensure_ascii=False, separators=(",", ":")) + "[datum.value]"


def _decode(expr: str, value: Any) -> Any:
    suffix = "[datum.value]"
    if not expr.endswith(suffix):
        raise ValueError("Unknown label-expression contract in minimal target")
    return json.loads(expr[:-len(suffix)])[int(value)]


def _legacy_percent_axis(definition: dict) -> bool:
    """Recognize legacy numeric tick labels that append `%` without scaling."""
    axis = definition.get("axis") or {}
    expression = axis.get("labelExpr")
    return (axis.get("labels", True) and axis.get("format") is None
            and axis.get("formatType", "number") == "number"
            and isinstance(expression, str) and _PERCENT_SUFFIX.fullmatch(expression.strip()) is not None)


def _percent_fraction(value: float | int) -> float:
    return float(Decimal(str(value)) / 100)


def _context(full: dict, version: int = 4) -> dict:
    semantic = _semantic(full)
    if semantic is None or semantic["kind"] not in KINDS:
        raise ValueError("Expected an adapter full spec for one of the nine VSR chart kinds")
    source_rows = full["data"]["values"]
    if not source_rows:
        raise ValueError("An observation table must not be empty")
    kind = semantic["kind"]
    enc = _primary_encoding(full)
    rows = visual_rows(kind, source_rows,
                       x_reverse=bool((enc.get("x", {}).get("scale") or {}).get("reverse")),
                       y_reverse=bool((enc.get("y", {}).get("scale") or {}).get("reverse")))
    series_keys = first_seen(rows, "series_id")
    visible_legend = enc.get("color", {}).get("legend") not in (None, False)
    series_names = ({row["series_id"]: row["series_name"] for row in rows} if visible_legend else
                    {key: f"Series {i + 1}" for i, key in enumerate(series_keys)})
    _, repeated_series = _mapping(series_keys, [series_names[key] for key in series_keys])
    include_series = version == 3 or visible_legend or len(series_keys) > 1
    category_field = None
    if kind.startswith("bar"):
        category_field = "category"
    elif kind.startswith("line") and semantic.get("x_mode", "numeric") != "numeric":
        category_field = "x"
    line_y_discrete = kind.startswith("line") and semantic.get("y_mode", "numeric") != "numeric"
    if kind.startswith("bar"):
        value_axis = "x" if kind.startswith("barh") else "y"
        numeric_fields = {value_axis: ("value", "lower", "upper", "start", "end")}
    else:
        numeric_fields = {axis: (axis,) for axis in ("x", "y")
                          if axis != category_field and (axis != "y" or not line_y_discrete)}
    percent_axes = {axis for axis in numeric_fields if _legacy_percent_axis(enc.get(axis, {}))}
    percent_fields = {field for axis in percent_axes for field in numeric_fields[axis]}
    category_keys = first_seen(rows, "category_id") if category_field else []
    category_visual = first_seen(sorted(rows, key=lambda r: r["plot_x"] * (-1 if (enc.get("x", {}).get("scale") or {}).get("reverse") else 1)), "category_id") if kind.startswith("line") and category_field else category_keys
    categories = {row["category_id"]: row["category"] for row in rows} if category_field else {}
    _, repeated_category = _mapping(category_keys, [categories[key] for key in category_keys])
    return {"kind": kind, "semantic": semantic, "rows": rows, "encoding": enc,
            "percent_axes": percent_axes, "percent_fields": percent_fields,
            "semantic_labels": full.get("usermeta", {}).get("semantic_labels", {}),
            "series_keys": series_keys, "series_names": series_names,
            "series_index": {key: i for i, key in enumerate(series_keys)},
            "include_series": include_series, "repeated_series": repeated_series,
            "visible_legend": visible_legend, "line_y_discrete": line_y_discrete,
            "path_order": kind.startswith("line") and needs_path_order(rows, x_reverse=bool((enc.get("x", {}).get("scale") or {}).get("reverse"))),
            "stack_endpoints": kind in {"barv_stack", "barh_stack"} and needs_stack_endpoints(rows),
            "category_field": category_field, "category_keys": category_keys, "category_visual": category_visual,
            "categories": categories, "category_index": {key: i for i, key in enumerate(category_keys)},
            "repeated_category": repeated_category}


def _data(context: dict, canonical: bool = True) -> list[dict]:
    """Projection reads source values; it never extracts a plotted endpoint."""
    output = []
    for row in context["rows"]:
        if context["kind"].startswith("bar"):
            result = {"category": row["category"], "value": row["value"]}
        else:
            result = {"x": row["x"], "y": row["y"]}
        if context["include_series"]:
            result["series"] = context["series_names"][row["series_id"]]
            if context["repeated_series"]:
                index = context["series_index"][row["series_id"]]
                result["series_id" if canonical else "series"] = f"S{index + 1}" if canonical else index
        if context["repeated_category"]:
            field = context["category_field"]
            index = context["category_index"][row["category_id"]]
            result[field + "_id" if canonical else field] = ("C" if field == "category" else "X") + str(index + 1) if canonical else index
        if "error_lower" in row:
            result.update(lower=row["error_lower"], upper=row["error_upper"])
        if context["path_order"]:
            result["path_order"] = row["point_index"]
        if context["kind"] in {"barv_stack", "barh_stack"}:
            if context["stack_endpoints"]:
                result.update(start=row["value_lower"], end=row["value_upper"])
            else:
                result["stack_order"] = row["series_index"]
        for field in context["percent_fields"] & result.keys():
            result[field] = _percent_fraction(result[field])
        output.append(order_row(result))
    return output


def unit_format(value, format_type="number") -> bool:
    """D3 currency and percent formats carry units, unlike precision-only formats."""
    return format_type == "number" and isinstance(value, str) and ("$" in value or value.endswith(("%", "p")))


def _axis_encoding(context: dict, channel: str, field: str, data_type: str) -> dict:
    original = context["encoding"].get(channel, {})
    result = {"field": field, "type": data_type}
    title = context["semantic_labels"].get(channel + "_title", original.get("title", (original.get("axis") or {}).get("title")))
    if title not in (None, "", []):
        result["title"] = copy.deepcopy(title)
    if data_type in {"nominal", "ordinal"}:
        result["sort"] = None
        if context["kind"].startswith("line") and channel == "x" and context["path_order"]:
            result["sort"] = [("X" + str(context["category_index"][key] + 1)) if context["repeated_category"] else context["categories"][key]
                              for key in context["category_visual"]]
    else:
        axis = original.get("axis") or {}
        legacy_percent = channel in context["percent_axes"]
        if unit_format(axis.get("format"), axis.get("formatType", "number")):
            result["axis"] = {"format": axis["format"]}
        elif legacy_percent:
            result["axis"] = {"format": "~%"}
        scale = original.get("scale") or {}
        semantic_scale = {k: scale[k] for k in ("type", "base", "exponent", "constant")
                          if k in scale and (k != "type" or scale[k] != "linear")}
        if legacy_percent and semantic_scale.get("type") == "symlog":
            semantic_scale["constant"] = _percent_fraction(semantic_scale.get("constant", 1))
        if semantic_scale:
            result["scale"] = semantic_scale
        if context["kind"].startswith("line") and channel == "x" and scale.get("reverse"):
            result.setdefault("scale", {})["reverse"] = True
    if context["repeated_category"] and field == context["category_field"]:
        result["field"] = field + "_id"
    return result


def _series_encoding(context: dict) -> dict:
    return {"field": "series_id" if context["repeated_series"] else "series",
            "type": "nominal", "sort": None}


def _needs_input_order(context: dict) -> bool:
    # Vega-Lite defaults to sorting a horizontal line by nominal Y.
    if context["line_y_discrete"]:
        return True
    last = {}
    for row in context["rows"]:
        key = row["series_id"]
        x = row["x"] if context["semantic"].get("x_mode") == "numeric" else context["category_index"][row["category_id"]]
        if key in last and x <= last[key]:
            return True
        last[key] = x
    return False


def migrate_line_axes(spec: dict) -> dict:
    """Canonicalize legacy standalone line axes on a freshly copied target."""
    mark = spec.get("mark")
    if mark not in ("line", {"type": "line"}, {"type": "line", "order": False}):
        return spec
    enc = spec.get("encoding")
    if not isinstance(enc, dict):
        return spec
    for axis in ("x", "y"):
        definition = enc.get(axis)
        if isinstance(definition, dict) and definition.get("type") == "ordinal":
            definition["type"] = "nominal"
    y = enc.get("y")
    if isinstance(y, dict) and y.get("type") == "nominal" and "order" not in enc:
        spec["mark"] = {"type": "line", "order": False}
    return spec


def normalize(full: dict) -> dict:
    """Create minimal training GT; applying it again is idempotent."""
    if (_semantic(full) or {}).get("kind") in {"pie", "boxplot"}:
        from statistical import compact_spec
        result = compact_spec(full)
        validate_target(result)
        return result
    if _semantic(full) is None:
        from statistical import target_kind
        if not target_kind(full):
            full = migrate_line_axes(migrate_spec(full))
        validate_target(full)
        return format_spec(full)
    context = _context(full)
    kind = context["kind"]
    result: dict[str, Any] = {"data": {"values": _data(context)}}
    title = context["semantic_labels"].get("title", full.get("title"))
    if isinstance(title, dict):
        title = title.get("text")
    if title not in (None, "", []):
        result["title"] = copy.deepcopy(title)
    if kind.startswith("bar"):
        category_axis, value_axis = ("y", "x") if kind.startswith("barh") else ("x", "y")
        encoding = {
            category_axis: _axis_encoding(context, category_axis, "category", "nominal"),
            value_axis: _axis_encoding(context, value_axis, "value", "quantitative"),
        }
        if context["include_series"]:
            encoding["color"] = _series_encoding(context)
        if kind in {"barh_n", "barv_n"}:
            encoding[category_axis + "Offset"] = _series_encoding(context)
        if kind in {"barv_stack", "barh_stack"}:
            if context["stack_endpoints"]:
                # Arbitrary baselines and crossing signed stacks cannot be
                # recreated by Vega's zero-based diverging stack transform.
                encoding[value_axis].update(field="end", stack=None)
                encoding[value_axis + "2"] = {"field": "start"}
            else:
                encoding[value_axis]["stack"] = "zero"
                encoding["order"] = {"field": "stack_order", "type": "quantitative"}
        if any("lower" in row for row in result["data"]["values"]):
            interval = {"field": "lower", "type": "quantitative"}
            if kind in {"barv_stack", "barh_stack"}:
                interval["stack"] = None
            result["layer"] = [{"mark": {"type": "bar"}}, {"mark": {"type": "errorbar"}, "encoding": {
                value_axis: interval, value_axis + "2": {"field": "upper"}}}]
        else:
            result["mark"] = "bar"
    else:
        xtype = "nominal" if context["category_field"] else "quantitative"
        ytype = "nominal" if context["line_y_discrete"] else "quantitative"
        encoding = {"x": _axis_encoding(context, "x", "x", xtype),
                    "y": _axis_encoding(context, "y", "y", ytype)}
        if context["include_series"]:
            encoding["color"] = _series_encoding(context)
        result["mark"] = ({"type": "line", "order": False} if _needs_input_order(context) else "line") if kind.startswith("line") else "point"
        if context["path_order"]:
            result["mark"] = "line"
            encoding["order"] = {"field": "path_order", "type": "quantitative"}
    result["encoding"] = encoding
    from table_metadata import attach_tables
    attach_tables(result, kind)
    result = format_spec(result)
    validate_target(result)
    return result


def project_rows(full: dict, version: int = 4) -> list[dict]:
    """Canonical source rows; version=3 retains historical singleton policy."""
    if version not in (3, 4):
        raise ValueError("Unsupported compact version")
    if _semantic(full) is None:
        return semantic_rows(full, version=version)
    if _semantic(full)["kind"] in {"pie", "boxplot"}:
        from statistical import project_rows as project_statistical_rows
        return project_statistical_rows(full)
    return _data(_context(full, version=version), canonical=True)


def semantic_rows(spec: dict, version: int = 4) -> list[dict]:
    """Decode minimal rows into the same canonical list as project_rows(full)."""
    if version not in (3, 4):
        raise ValueError("Unsupported compact version")
    if _semantic(spec) is not None:
        return project_rows(spec, version=version)
    rows = copy.deepcopy(spec["data"]["values"])
    encoding = spec["encoding"]
    for channel in ("x", "y"):
        definition = encoding.get(channel, {})
        expr = (definition.get("axis") or {}).get("labelExpr")
        if expr:
            field = definition["field"]
            for row in rows:
                row[field + "_instance"] = row[field]
                row[field] = _decode(expr, row[field])
    color = encoding.get("color", {})
    expr = (color.get("legend") or {}).get("labelExpr")
    if expr:
        for row in rows:
            row["series_instance"] = row["series"]
            row["series"] = _decode(expr, row["series"])
    return migrate_spec({"data": {"values": rows}, "encoding": {}})["data"]["values"]


def validate_canonical(spec: dict) -> None:
    """Validate the bounded v4 grammar. Unsupported/legacy input raises ValueError."""
    from statistical import target_kind, validate_compact
    if target_kind(spec):
        validate_compact(spec)
        return
    def check(ok, message):
        if not ok:
            raise ValueError("Unsupported/noncanonical compact-v4: " + message)
    check(isinstance(spec, dict), "expected object")
    if "usermeta" in spec:
        from table_metadata import table_metadata
        check(spec["usermeta"] == {"table_export": table_metadata(spec)}, "incorrect table export mapping")
    check(set(spec) <= {"usermeta", "data", "title", "mark", "encoding", "layer"}, "top-level keys")
    check({"data", "encoding"} <= set(spec), "missing data/encoding")
    check(isinstance(spec["data"], dict) and set(spec["data"]) == {"values"}, "inline values only")
    rows = spec["data"]["values"]
    check(isinstance(rows, list) and bool(rows), "empty table")
    check(all(isinstance(r, dict) for r in rows), "row objects required")
    fields = set(rows[0])
    check(all(set(r) == fields for r in rows), "inconsistent row fields")
    bar = {"category", "value"} <= fields
    core = {"category", "value"} if bar else {"x", "y"}
    check(core <= fields, "missing core observations")
    check(fields <= core | {"series", "category_id", "x_id", "y_id", "series_id", "lower", "upper", "path_order", "stack_order", "start", "end"}, "unknown data fields")
    check(("lower" in fields) == ("upper" in fields), "incomplete error interval")
    check(("start" in fields) == ("end" in fields), "incomplete stack endpoints")
    for row in rows:
        for f, v in row.items():
            check(isinstance(v, (str, int, float)) and not isinstance(v, bool), "non-scalar observation")
            check(not isinstance(v, (int, float)) or math.isfinite(v), "nonfinite observation")
            if f in {"value", "lower", "upper", "start", "end", "path_order", "stack_order"}:
                check(isinstance(v, (int, float)), "numeric observation required")
    for f, (identity, prefix) in IDENTITIES.items():
        if identity not in fields:
            continue
        check(f in fields, "identity without human label")
        labels = {}
        for row in rows:
            i = row[identity]
            check(isinstance(i, str) and i.startswith(prefix) and i[len(prefix):].isdigit()
                  and str(int(i[len(prefix):])) == i[len(prefix):] and int(i[len(prefix):]) > 0,
                  "string identity required: " + prefix + "1, " + prefix + "2, ...")
            check(i not in labels or labels[i] == row[f], "identity label conflict")
            labels[i] = row[f]
        check(list(labels) == [prefix + str(i + 1) for i in range(len(labels))], "identities must follow first-seen order")
        check(len(set(labels.values())) < len(labels), "unnecessary identity field")
    check(all(list(r) == list(order_row(r)) for r in rows), "noncanonical row field order")
    def valid_title(value):
        return isinstance(value, str) and bool(value) or isinstance(value, list) and bool(value) and all(isinstance(v, str) for v in value)
    if "title" in spec:
        check(valid_title(spec["title"]), "invalid title")
    enc = spec["encoding"]
    line_mark = spec.get('mark') == 'line' or isinstance(spec.get('mark'), dict) and spec['mark'].get('type') == 'line'
    check(isinstance(enc, dict) and {"x", "y"} <= set(enc), "missing positional encoding")
    check(set(enc) <= {"x", "y", "x2", "y2", "xOffset", "yOffset", "color", "order"}, "unsupported channel")
    used = set()
    for channel, d in enc.items():
        check(isinstance(d, dict), "channel object required")
        check(set(d) <= {"field", "type", "title", "sort", "scale", "stack", "axis"}, "display/unsupported encoding property")
        check(isinstance(d.get("field"), str) and d["field"] in fields, "field missing from data")
        f = d["field"]
        check(f + "_id" not in fields, "encoding must use identity field")
        used.add(f)
        if channel in {"x2", "y2"}:
            check(set(d) == {"field"}, "secondary channel grammar")
        else:
            check(d.get("type") in {"nominal", "ordinal", "quantitative"}, "unsupported data type")
            if line_mark and channel in {"x", "y"}:
                check(d["type"] in {"nominal", "quantitative"}, "discrete line axes must be nominal")
        if d.get("type") in {"nominal", "ordinal"}:
            explicit_line = line_mark and channel == "x" and "path_order" in fields and isinstance(d.get("sort"), list)
            check("sort" in d and (d["sort"] is None or explicit_line), "discrete order must follow rows except retreating lines")
            if explicit_line:
                check(len(d['sort']) == len(set(d['sort'])) and set(d['sort']) == {r[f] for r in rows}, "explicit X order must cover observed positions exactly")
        else:
            check("sort" not in d, "unnecessary quantitative sort")
        if "title" in d:
            check(valid_title(d["title"]), "invalid variable title")
        if "axis" in d:
            axis = d["axis"]
            check(channel in {"x", "y"} and d.get("type") == "quantitative"
                  and isinstance(axis, dict) and set(axis) == {"format"}
                  and unit_format(axis["format"]), "only unit-bearing numeric axis formats")
        if "scale" in d:
            scale = d["scale"]
            check(channel in {"x", "y"} and isinstance(scale, dict), "invalid scale")
            allowed = {"log": {"type", "base"}, "pow": {"type", "exponent"}, "sqrt": {"type"}, "symlog": {"type", "constant"}}
            reversed_line = line_mark and channel == "x" and scale.get("reverse") is True
            scale_type = scale.get('type')
            check(scale_type in allowed or (reversed_line and scale_type is None), "only nonlinear scales or reversed line X")
            check(set(scale) <= allowed.get(scale_type, set()) | ({'reverse'} if reversed_line else set()), "inapplicable scale parameter")
            for k in set(scale) - {"type", "reverse"}:
                v = scale[k]
                check(type(v) in (int, float) and math.isfinite(v) and v > 0 and (k != "base" or v != 1), "invalid nonlinear parameter")
        if "stack" in d:
            check(channel in {"x", "y"} and d["stack"] in (None, "zero"), "invalid stack")
    for channel in ("color", "xOffset", "yOffset"):
        if channel in enc:
            check(enc[channel] == {"field": "series_id" if "series_id" in fields else "series", "type": "nominal", "sort": None}, "series channel grammar")
    check(("series" in fields) == ("color" in enc), "series grouping required")
    if "layer" in spec:
        check("mark" not in spec and bar and "lower" in fields, "only explicit bar error layers supported")
        axis = "x" if enc["x"]["field"] in {"value", "end"} else "y"
        interval = {"field": "lower", "type": "quantitative"}
        if {"stack_order", "start"} & fields:
            interval["stack"] = None
        expected = [{"mark": {"type": "bar"}}, {"mark": {"type": "errorbar"}, "encoding": {axis: interval, axis + "2": {"field": "upper"}}}]
        check(format_spec(spec)["layer"] == format_spec({"layer": expected})["layer"], "unsupported layer structure")
        used.update({"lower", "upper"})
        mark = "bar"
    else:
        mark = spec.get("mark")
        check(mark in ("bar", "line", "point") if isinstance(mark, str) else mark in ({"type": "bar"}, {"type": "line"}, {"type": "point"}, {"type": "line", "order": False}), "unsupported mark")
        mark = mark if isinstance(mark, str) else mark["type"]
        check("lower" not in fields, "errors need explicit layers")
    check((mark == "bar") == bar, "mark/data mismatch")
    if bar:
        category_axis = "y" if enc["x"]["field"] in {"value", "end"} else "x"
        value_axis = "x" if category_axis == "y" else "y"
        check(enc[category_axis]["field"] == ("category_id" if "category_id" in fields else "category") and enc[category_axis]["type"] == "nominal", "bar category encoding")
        check(enc[value_axis]["field"] == ("end" if "start" in fields else "value") and enc[value_axis]["type"] == "quantitative", "bar value encoding")
        check(not {"path_order", "x_id", "y_id"} & fields, "line fields in bar")
        check(not {"xOffset", "yOffset"} & set(enc) or category_axis + "Offset" in enc, "offset axis")
    else:
        check(all(enc[axis]["field"] == (axis + "_id" if axis + "_id" in fields else axis)
                  for axis in ("x", "y")), "xy encoding")
        if mark == "line" and enc["y"]["type"] == "nominal":
            check(enc["x"]["type"] == "quantitative", "discrete line Y requires quantitative X")
            check("path_order" in fields or spec.get("mark") == {"type": "line", "order": False},
                  "discrete line Y requires input path order")
        else:
            check(enc["y"]["type"] == "quantitative", "quantitative Y required")
        check(not {"start", "stack_order", "category_id"} & fields and not {"xOffset", "yOffset", "x2", "y2"} & set(enc), "bar fields in xy chart")
        for axis in ("x", "y"):
            if enc[axis]["type"] == "quantitative":
                check(enc[axis]["field"] == axis and all(type(r[axis]) in (int, float) for r in rows),
                      "numeric " + axis + " required")
    if "path_order" in fields:
        check(mark == "line" and enc.get("order") == {"field": "path_order", "type": "quantitative"}, "path ordering required")
    if "stack_order" in fields:
        check(bar and enc.get("order") == {"field": "stack_order", "type": "quantitative"} and enc[value_axis].get("stack") == "zero", "stack ordering required")
    if "start" in fields:
        check(bar and enc[value_axis].get("field") == "end" and enc[value_axis].get("stack", "missing") is None and enc.get(value_axis + "2") == {"field": "start"}, "stack endpoints required")
        used.add("value")
    if "order" in enc:
        check(enc["order"] == {"field": "path_order" if "path_order" in fields else "stack_order", "type": "quantitative"} and bool({"path_order", "stack_order"} & fields), "unsupported order")
    for f in fields:
        check(f in used or f + "_id" in used, "unconsumed data field " + f)


validate_target = validate_canonical
