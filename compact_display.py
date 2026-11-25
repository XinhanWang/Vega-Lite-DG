"""Derive independently renderable previews from compact v4 semantic targets.

No file IO and no data mutation: callers may serialize the result as
compact.preview.vl.json. Display defaults never become training labels.
"""
from __future__ import annotations

from collections import Counter
import copy
import json

from compact import migrate_line_axes, validate_target
from identity import migrate_spec
from precision import PERCENT_SPECIFIER
from statistical import target_kind


def vega_lite_spec(compact: dict) -> dict:
    """Move the Compact Pie percentage format onto a Vega-Lite tooltip."""
    result = copy.deepcopy(compact)
    if result.get("mark") in ("arc", {"type": "arc"}):
        encoding = result["encoding"]
        theta = encoding["theta"]
        if "format" in theta:
            fmt = theta.pop("format")
            encoding["tooltip"] = {**theta, "format": fmt}
    return result


def render_spec(compact: dict, *, fit_boxplot=False) -> dict:
    """Return a fresh Vega-Lite preview with identical observation data/order."""
    compact = migrate_line_axes(migrate_spec(compact))
    validate_target(compact)
    result = vega_lite_spec(compact)
    rows = result["data"]["values"]
    enc = result["encoding"]
    if target_kind(result) == "boxplot":
        value_axis = "x" if enc.get("y", {}).get("field") == "category" else "y"
        whisker = result["layer"][0]["encoding"][value_axis]
        whisker.setdefault("title", None)
        if PERCENT_SPECIFIER.fullmatch(whisker.get("axis", {}).get("format", "")):
            # The whisker and outlier extent defines the preview range.
            whisker["scale"] = {"zero": False}
    for channel, d in enc.items():
        if channel not in {"x2", "y2", "order", "xOffset", "yOffset"}:
            d.setdefault("title", None)
        f = d["field"]
        discrete = d.get("type") in {"nominal", "ordinal"}
        if channel in {"x", "y"} and discrete:
            d["axis"] = {"values": list(dict.fromkeys(r[f] for r in rows)),
                         "labelOverlap": False, "labelLimit": 0, "labelBound": False}
        if f.endswith("_id") and channel in {"x", "y", "color"}:
            labels = {r[f]: r[f.removesuffix("_id")] for r in rows}
            expr = json.dumps(labels, ensure_ascii=False, separators=(",", ":")) + "[datum.value]"
            d.setdefault("legend" if channel == "color" else "axis", {})["labelExpr"] = expr
        if channel == "color":
            d.setdefault("legend", {}).update(title=None, labelLimit=0)
    mark = result.get("mark")
    if mark == "line" or isinstance(mark, dict) and mark.get("type") == "line":
        series = enc.get("color", {}).get("field")
        counts = Counter(r[series] if series else None for r in rows)
        if 1 in counts.values():
            result["mark"] = {"type": "line"} if isinstance(mark, str) else mark
            result["mark"]["point"] = True
    # Keep the compact target presentation-free while giving Chinese previews
    # the exact embedded font face used by the native SVG renderer.
    if any("\u3400" <= char <= "\u9fff" for char in json.dumps(compact, ensure_ascii=False)):
        from generation.sampling_policy import CJK_NAME
        result["config"] = {
            "font": CJK_NAME, "title": {"fontWeight": 400},
            "axis": {"titleFontWeight": 400, "labelFontWeight": 400},
            "legend": {"titleFontWeight": 400, "labelFontWeight": 400},
        }
    if fit_boxplot and isinstance(result.get("layer"), list):
        from text_layout import fit_category_axis
        if target_kind(compact) == "boxplot":
            channel = "y" if enc.get("y", {}).get("field") == "category" else "x"
            fit_category_axis(result, channel, list(dict.fromkeys(row["category"] for row in rows)))
    return result
