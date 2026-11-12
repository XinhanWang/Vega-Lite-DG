"""Compact GT identities. Display labels are never used to merge explicit objects."""
from __future__ import annotations
import copy

ROW_FIELDS = ("category", "category_id", "value", "x", "x_id", "y", "lower", "upper",
              "path_order", "stack_order", "start", "end", "series", "series_id")
IDENTITIES = {"category": ("category_id", "C"), "x": ("x_id", "X"), "series": ("series_id", "S")}


def order_row(row: dict) -> dict:
    return {k: row[k] for k in (*ROW_FIELDS, *(k for k in row if k not in ROW_FIELDS)) if k in row}


def migrate_spec(spec: dict) -> dict:
    """Import-only migration of legacy *_instance and old ID spellings.

    Existing identities, not labels, define objects. IDs are canonicalized by
    first row occurrence. If labels are unique, redundant ID columns disappear.
    No inference of separate objects from repeated observation text is attempted.
    """
    out = copy.deepcopy(spec)
    rows = out.get("data", {}).get("values", [])
    renames = {}
    for field, (new, prefix) in IDENTITIES.items():
        old = field + "_instance"
        active = any(new in r or old in r for r in rows)
        if not active:
            continue
        labels = {}
        for r in rows:
            if new not in r and old not in r or field not in r:
                raise ValueError("Partial identity column: " + new)
            if new in r and old in r and r[new] != r[old]:
                raise ValueError("Conflicting identity columns: " + new)
            key = r.get(new, r.get(old))
            if key in labels and labels[key] != r[field]:
                raise ValueError("Identity label conflict: " + new)
            labels[key] = r[field]
        repeated = len(set(labels.values())) < len(labels)
        ids = {key: prefix + str(i + 1) for i, key in enumerate(labels)}
        for r in rows:
            key = r.get(new, r.get(old))
            r.pop(old, None)
            r.pop(new, None)
            if repeated:
                r[new] = ids[key]
        renames[old] = new if repeated else field
        renames[new] = new if repeated else field
    def view(node):
        for d in node.get("encoding", {}).values():
            if isinstance(d, dict) and d.get("field") in renames:
                d["field"] = renames[d["field"]]
        for k in ("layer", "concat", "hconcat", "vconcat"):
            for child in node.get(k, []):
                view(child)
        if isinstance(node.get("spec"), dict):
            view(node["spec"])
    view(out)
    if rows:
        out["data"]["values"] = [order_row(r) for r in rows]
    return out
