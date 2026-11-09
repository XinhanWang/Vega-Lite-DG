"""Minimal, independently renderable training GT for VSR's nine chart kinds.

Contract
--------
``normalize(full)`` projects the adapter's rich observation table into ordinary
Vega-Lite: category/value[/series] for bars and x/y[/series] for lines/scatter.
Only measured error endpoints add lower/upper. No IDs, pixel geometry, source
domains, typography, per-series layers, or provenance enter training targets.
Calendar-period line labels remain an ordered discrete axis, as in VSR.

Repeated display names are the one identity exception: the ambiguous field uses
an integer key, with a labelExpr containing its original labels. This uses no
extra data column, never changes the labels, and keeps distinct source slots.
``project_rows(full)`` and ``semantic_rows(minimal)`` return equal ordered lists
of canonical observation dictionaries. They decode these keys back to labels,
adding category_instance/x_instance/series_instance only for ambiguous names.
Thus callers can compare lists to audit source order, or Counters of canonical
JSON to audit multisets. Duplicate scatter observations are never deduplicated.

Source data order is retained verbatim. A non-increasing numeric line or a line
whose series visit categories in different orders uses mark.order=false, so
Vega connects the original per-series sequence without an extra row index.
Stack order uses category as an ordinal key: all keys within a category are
equal, so Vega's stable sort keeps the source series order without a new column.

Already-minimal inputs are returned as independent copies. This function is an
adapter projection, not a general optimizer for arbitrary Vega-Lite programs.
"""
from __future__ import annotations

import copy
import json
from typing import Any


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
    rows = full["data"]["values"]
    if not rows:
        raise ValueError("An observation table must not be empty")
    kind = semantic["kind"]
    enc = _primary_encoding(full)
    series_keys = list(dict.fromkeys(row["series_id"] for row in rows))
    series_names = {row["series_id"]: row["series_name"] for row in rows}
    _, repeated_series = _mapping(series_keys, [series_names[key] for key in series_keys])
    visible_legend = enc.get("color", {}).get("legend") is not None
    include_series = len(series_keys) > 1 or visible_legend
    category_field = "category" if kind.startswith("bar") else "x" if kind.startswith("line") and semantic.get("x_mode") != "numeric" else None
    category_keys = list(dict.fromkeys(row["category_id"] for row in rows)) if category_field else []
    categories = {row["category_id"]: row["category"] for row in rows} if category_field else {}
    _, repeated_category = _mapping(category_keys, [categories[key] for key in category_keys])
    return {"kind": kind, "semantic": semantic, "rows": rows, "encoding": enc,
            "semantic_labels": full.get("usermeta", {}).get("semantic_labels", {}),
            "series_keys": series_keys, "series_names": series_names,
            "series_index": {key: i for i, key in enumerate(series_keys)},
            "include_series": include_series, "repeated_series": repeated_series,
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
            result["series"] = row["series_name"]
            if context["repeated_series"]:
                index = context["series_index"][row["series_id"]]
                result["series_instance" if canonical else "series"] = index
        if context["repeated_category"]:
            field = context["category_field"]
            index = context["category_index"][row["category_id"]]
            result[field + "_instance" if canonical else field] = index
        if "error_lower" in row:
            result.update(lower=row["error_lower"], upper=row["error_upper"])
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
    else:
        scale = original.get("scale") or {}
        if scale.get("type", "linear") != "linear":
            result["scale"] = {k: scale[k] for k in ("type", "base", "exponent", "constant") if k in scale}
    if context["repeated_category"] and field == context["category_field"]:
        result["axis"] = {"labelExpr": _expr([context["categories"][key] for key in context["category_keys"]])}
    return result


def _series_encoding(context: dict) -> dict:
    result = {"field": "series", "type": "nominal", "sort": None}
    if context["repeated_series"]:
        result["legend"] = {"labelExpr": _expr([context["series_names"][key] for key in context["series_keys"]])}
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
            encoding[value_axis]["stack"] = "zero"
            # Every stack group has one category. Sorting these equal keys is
            # stable, preserving input series order without a per-row index.
            encoding["order"] = {"field": "category", "type": "ordinal"}
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
