"""Compact v4 semantic GT; v3 decoding is retained for migration audits."""
from __future__ import annotations

from collections import Counter
import copy
import json
import math
from typing import Any

from ordering import first_seen, needs_path_order, needs_stack_endpoints, visual_rows
from spec_format import format_spec


KINDS = {"barh_1", "barh_n", "barv_1", "barv_n", "barv_stack",
         "line_1", "line_n", "scatter_1", "scatter_n"}


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
    category_field = "category" if kind.startswith("bar") else "x" if kind.startswith("line") and semantic.get("x_mode") != "numeric" else None
    category_keys = list(dict.fromkeys(row["category_id"] for row in rows)) if category_field else []
    categories = {row["category_id"]: row["category"] for row in rows} if category_field else {}
    _, repeated_category = _mapping(category_keys, [categories[key] for key in category_keys])
    return {"kind": kind, "semantic": semantic, "rows": rows, "encoding": enc,
            "semantic_labels": full.get("usermeta", {}).get("semantic_labels", {}),
            "series_keys": series_keys, "series_names": series_names,
            "series_index": {key: i for i, key in enumerate(series_keys)},
            "include_series": include_series, "repeated_series": repeated_series,
            "visible_legend": visible_legend,
            "path_order": kind.startswith("line") and needs_path_order(rows),
            "stack_endpoints": kind == "barv_stack" and needs_stack_endpoints(rows),
            "category_field": category_field, "category_keys": category_keys,
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
                result["series_instance" if canonical else "series"] = index
        if context["repeated_category"]:
            field = context["category_field"]
            index = context["category_index"][row["category_id"]]
            result[field + "_instance" if canonical else field] = index
        if "error_lower" in row:
            result.update(lower=row["error_lower"], upper=row["error_upper"])
        if context["path_order"]:
            result["path_order"] = row["point_index"]
        if context["kind"] == "barv_stack":
            if context["stack_endpoints"]:
                result.update(start=row["value_lower"], end=row["value_upper"])
            else:
                result["stack_order"] = row["series_index"]
        output.append(result)
    return output


def _axis_encoding(context: dict, channel: str, field: str, data_type: str) -> dict:
    original = context["encoding"].get(channel, {})
    result = {"field": field, "type": data_type}
    title = context["semantic_labels"].get(channel + "_title", original.get("title", (original.get("axis") or {}).get("title")))
    if title not in (None, "", []):
        result["title"] = copy.deepcopy(title)
    if data_type in {"nominal", "ordinal"}:
        result["sort"] = None
    else:
        scale = original.get("scale") or {}
        semantic_scale = {k: scale[k] for k in ("type", "base", "exponent", "constant")
                          if k in scale and (k != "type" or scale[k] != "linear")}
        if semantic_scale:
            result["scale"] = semantic_scale
    if context["repeated_category"] and field == context["category_field"]:
        result["field"] = field + "_instance"
    return result


def _series_encoding(context: dict) -> dict:
    return {"field": "series_instance" if context["repeated_series"] else "series",
            "type": "nominal", "sort": None}


def _needs_input_order(context: dict) -> bool:
    last = {}
    for row in context["rows"]:
        key = row["series_id"]
        x = row["x"] if context["semantic"].get("x_mode") == "numeric" else context["category_index"][row["category_id"]]
        if key in last and x <= last[key]:
            return True
        last[key] = x
    return False


def normalize(full: dict) -> dict:
    """Create minimal training GT; applying it again is idempotent."""
    if _semantic(full) is None:
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
        if kind == "barv_stack":
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
            if kind == "barv_stack":
                interval["stack"] = None
            result["layer"] = [{"mark": "bar"}, {"mark": "rule", "encoding": {
                value_axis: interval, value_axis + "2": {"field": "upper"}}}]
        else:
            result["mark"] = "bar"
    else:
        xtype = "ordinal" if context["category_field"] else "quantitative"
        encoding = {"x": _axis_encoding(context, "x", "x", xtype),
                    "y": _axis_encoding(context, "y", "y", "quantitative")}
        if context["include_series"]:
            encoding["color"] = _series_encoding(context)
        result["mark"] = ({"type": "line", "order": False} if _needs_input_order(context) else "line") if kind.startswith("line") else "point"
        if context["path_order"]:
            result["mark"] = "line"
            encoding["order"] = {"field": "path_order", "type": "quantitative"}
    result["encoding"] = encoding
    result = format_spec(result)
    validate_target(result)
    return result


def project_rows(full: dict, version: int = 4) -> list[dict]:
    """Canonical source rows; version=3 retains historical singleton policy."""
    if version not in (3, 4):
        raise ValueError("Unsupported compact version")
    if _semantic(full) is None:
        return semantic_rows(full, version=version)
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
    return rows


def validate_canonical(spec: dict) -> None:
    """Validate the bounded v4 grammar. Unsupported/legacy input raises ValueError."""
    def check(ok, message):
        if not ok:
            raise ValueError("Unsupported/noncanonical compact-v4: " + message)
    check(isinstance(spec, dict), "expected object")
    check(set(spec) <= {"data", "title", "mark", "encoding", "layer"}, "top-level keys")
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
    check(fields <= core | {"series", "category_instance", "x_instance", "series_instance", "lower", "upper", "path_order", "stack_order", "start", "end"}, "unknown data fields")
    check(("lower" in fields) == ("upper" in fields), "incomplete error interval")
    check(("start" in fields) == ("end" in fields), "incomplete stack endpoints")
    for row in rows:
        for f, v in row.items():
            check(isinstance(v, (str, int, float)) and not isinstance(v, bool), "non-scalar observation")
            check(not isinstance(v, (int, float)) or math.isfinite(v), "nonfinite observation")
            if f in {"value", "y", "lower", "upper", "start", "end", "path_order", "stack_order"}:
                check(isinstance(v, (int, float)), "numeric observation required")
    for f in ("category", "x", "series"):
        identity = f + "_instance"
        if identity not in fields:
            continue
        check(f in fields, "identity without human label")
        labels = {}
        for row in rows:
            i = row[identity]
            check(type(i) is int and i >= 0, "integer identity required")
            check(i not in labels or labels[i] == row[f], "identity label conflict")
            labels[i] = row[f]
        check(list(labels) == list(range(len(labels))), "identities must follow first-seen order")
        check(len(set(labels.values())) < len(labels), "unnecessary identity field")
    def valid_title(value):
        return isinstance(value, str) and bool(value) or isinstance(value, list) and bool(value) and all(isinstance(v, str) for v in value)
    if "title" in spec:
        check(valid_title(spec["title"]), "invalid title")
    enc = spec["encoding"]
    check(isinstance(enc, dict) and {"x", "y"} <= set(enc), "missing positional encoding")
    check(set(enc) <= {"x", "y", "x2", "y2", "xOffset", "yOffset", "color", "order"}, "unsupported channel")
    used = set()
    for channel, d in enc.items():
        check(isinstance(d, dict), "channel object required")
        check(set(d) <= {"field", "type", "title", "sort", "scale", "stack"}, "display/unsupported encoding property")
        check(isinstance(d.get("field"), str) and d["field"] in fields, "field missing from data")
        f = d["field"]
        check(f + "_instance" not in fields, "encoding must use identity field")
        used.add(f)
        if channel in {"x2", "y2"}:
            check(set(d) == {"field"}, "secondary channel grammar")
        else:
            check(d.get("type") in {"nominal", "ordinal", "quantitative"}, "unsupported data type")
        if d.get("type") in {"nominal", "ordinal"}:
            check("sort" in d and d["sort"] is None, "discrete order must follow rows")
        else:
            check("sort" not in d, "unnecessary quantitative sort")
        if "title" in d:
            check(valid_title(d["title"]), "invalid variable title")
        if "scale" in d:
            scale = d["scale"]
            check(channel in {"x", "y"} and isinstance(scale, dict), "invalid scale")
            allowed = {"log": {"type", "base"}, "pow": {"type", "exponent"}, "sqrt": {"type"}, "symlog": {"type", "constant"}}
            check(isinstance(scale.get("type"), str) and scale["type"] in allowed, "only nonlinear semantic scales")
            check(set(scale) <= allowed[scale["type"]], "inapplicable scale parameter")
            for k in set(scale) - {"type"}:
                v = scale[k]
                check(type(v) in (int, float) and math.isfinite(v) and v > 0 and (k != "base" or v != 1), "invalid nonlinear parameter")
        if "stack" in d:
            check(channel in {"x", "y"} and d["stack"] in (None, "zero"), "invalid stack")
    for channel in ("color", "xOffset", "yOffset"):
        if channel in enc:
            check(enc[channel] == {"field": "series_instance" if "series_instance" in fields else "series", "type": "nominal", "sort": None}, "series channel grammar")
    check(("series" in fields) == ("color" in enc), "series grouping required")
    if "layer" in spec:
        check("mark" not in spec and bar and "lower" in fields, "only explicit bar error layers supported")
        axis = "x" if enc["x"]["field"] in {"value", "end"} else "y"
        interval = {"field": "lower", "type": "quantitative"}
        if {"stack_order", "start"} & fields:
            interval["stack"] = None
        expected = [{"mark": "bar"}, {"mark": "rule", "encoding": {axis: interval, axis + "2": {"field": "upper"}}}]
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
        category_axis = "y" if enc["x"]["field"] == "value" else "x"
        value_axis = "x" if category_axis == "y" else "y"
        check(enc[category_axis]["field"] == ("category_instance" if "category_instance" in fields else "category") and enc[category_axis]["type"] == "nominal", "bar category encoding")
        check(enc[value_axis]["field"] == ("end" if "start" in fields else "value") and enc[value_axis]["type"] == "quantitative", "bar value encoding")
        check(not {"path_order", "x_instance"} & fields, "line fields in bar")
        check(not {"xOffset", "yOffset"} & set(enc) or category_axis + "Offset" in enc, "offset axis")
    else:
        check(enc["x"]["field"] == ("x_instance" if "x_instance" in fields else "x") and enc["y"]["field"] == "y" and enc["y"]["type"] == "quantitative", "xy encoding")
        check(not {"start", "stack_order", "category_instance"} & fields and not {"xOffset", "yOffset", "x2", "y2"} & set(enc), "bar fields in xy chart")
        if enc["x"]["type"] == "quantitative":
            check(all(type(r["x"]) in (int, float) for r in rows), "numeric x required")
    if "path_order" in fields:
        check(mark == "line" and enc.get("order") == {"field": "path_order", "type": "quantitative"}, "path ordering required")
    if "stack_order" in fields:
        check(bar and enc.get("order") == {"field": "stack_order", "type": "quantitative"} and enc["y"].get("stack") == "zero", "stack ordering required")
    if "start" in fields:
        check(bar and enc["y"].get("field") == "end" and enc["y"].get("stack", "missing") is None and enc.get("y2") == {"field": "start"}, "stack endpoints required")
        used.add("value")
    if "order" in enc:
        check(enc["order"] == {"field": "path_order" if "path_order" in fields else "stack_order", "type": "quantitative"} and bool({"path_order", "stack_order"} & fields), "unsupported order")
    for f in fields:
        check(f in used or f + "_instance" in used, "unconsumed data field " + f)


validate_target = validate_canonical
