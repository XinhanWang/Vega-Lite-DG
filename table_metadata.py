"""Describe semantic observation tables by their actual inline Vega-Lite paths."""


def table_metadata(spec, kind=None):
    rows = spec["data"]["values"]
    box = kind == "boxplot" or bool(rows and {"q1", "median", "q3"} <= rows[0].keys())
    tables = [{"id": "box_plot_summaries" if box else "data", "path": "/data/values"}]
    if box:
        for index, layer in enumerate(spec.get("layer", [])):
            if layer.get("mark", {}).get("type") == "point" and "data" in layer:
                tables.append({"id": "outliers", "path": f"/layer/{index}/data/values"})
    return {"tables": tables}


def attach_tables(spec, kind=None):
    spec.setdefault("usermeta", {})["table_export"] = table_metadata(spec, kind)
    return spec
