"""Compact, independently renderable training targets for nine chart kinds.

Observation tables follow image reading order. Categorical and series encodings
use sort:null; numerical scale reversal remains explicit. All categorical line
labels are required, and hidden legends use stable English Series 1, Series 2,
... identifiers instead of labels that cannot be read in the image.

Bars contain category/value/series and lines/scatter contain x/y/series. Error
intervals add lower/upper. Ordinary stacks use stack_order to preserve their
baselines after top-to-bottom table ordering; arbitrary or crossing stacks use
measured start/end instead. Nonmonotonic paths add path_order only when visible
x order would otherwise connect different observations. These are semantic
fields, not pixels or styling.

Repeated display names use integer keys and literal label expressions without
merging identities. project_rows(full) and semantic_rows(compact) return equal
ordered canonical rows, with *_instance audit fields only for ambiguous names.
Duplicate observations are retained. Already-compact inputs are copied unchanged.
"""
from __future__ import annotations

from collections import Counter
import copy
import json
from typing import Any

from ordering import first_seen, needs_path_order, needs_stack_endpoints, visual_rows


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


def _context(full: dict) -> dict:
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
    include_series = True
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


def _data(context: dict, canonical: bool = False) -> list[dict]:
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
    # Null preserves an explicitly absent scientific axis title; otherwise
    # Vega would invent "category", "x", "y" or "value" as visible content.
    result["title"] = title
    if data_type in {"nominal", "ordinal"}:
        result["sort"] = None
        labels = [context["categories"][key] for key in context["category_keys"]]
        values = list(range(len(labels))) if context["repeated_category"] else labels
        result["axis"] = {"values": values, "labelOverlap": False, "labelLimit": 0, "labelBound": False}
    else:
        scale = original.get("scale") or {}
        semantic_scale = {k: scale[k] for k in ("type", "base", "exponent", "constant")
                          if k in scale and (k != "type" or scale[k] != "linear")}
        if scale.get("reverse"):
            semantic_scale["reverse"] = True
        if semantic_scale:
            result["scale"] = semantic_scale
    if context["repeated_category"] and field == context["category_field"]:
        result["axis"]["labelExpr"] = _expr([context["categories"][key] for key in context["category_keys"]])
    return result


def _series_encoding(context: dict) -> dict:
    result = {"field": "series", "type": "nominal", "sort": None,
              "legend": {"title": None} if context["visible_legend"] else None}
    if context["repeated_series"]:
        result["legend"]["labelExpr"] = _expr([context["series_names"][key] for key in context["series_keys"]])
    return result


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
        return copy.deepcopy(full)
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
            encoding[category_axis + "Offset"] = {"field": "series", "type": "nominal", "sort": None}
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
        if kind.startswith("line") and 1 in Counter(row["series_id"] for row in context["rows"]).values():
            # A one-vertex path paints no segment. Keep the primary line mark
            # for geometry auditing and expose its observations with points.
            if isinstance(result["mark"], str):
                result["mark"] = {"type": "line"}
            result["mark"]["point"] = True
    result["encoding"] = encoding
    return result


def project_rows(full: dict) -> list[dict]:
    """Canonical source observations, retaining order and ambiguous identities.

    Ordinary bars use category/value[/series][/lower/upper]; lines/scatter use
    x/y[/series]. Only duplicate-name identities add *_instance in this audit
    return value. Those audit-only keys never enter the minimal GT data table.
    """
    return _data(_context(full), canonical=True)


def semantic_rows(spec: dict) -> list[dict]:
    """Decode minimal rows into the same canonical list as project_rows(full)."""
    if _semantic(spec) is not None:
        return project_rows(spec)
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
