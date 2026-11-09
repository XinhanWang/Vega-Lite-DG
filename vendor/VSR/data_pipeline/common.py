from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable, Sequence

TARGET_SIDE = 1036

TEMPLATE_ALIASES = {
    "barh_1": "barh1",
    "barh_n": "barhn",
    "barv_1": "barv1",
    "barv_n": "barvn",
    "barv_stack": "barvstack",
    "line_1": "line1",
    "line_n": "linen",
    "scatter_1": "scatter1",
    "scatter_n": "scattern",
}

SEED_RE = re.compile(r"seed_(\d+)")


def alias_from_template_dir(template_dir: str) -> str:
    normalized = template_dir.strip().replace("-", "_")
    return TEMPLATE_ALIASES.get(normalized, normalized.replace("_", ""))


def extract_seed(run_dir_name: str) -> int:
    match = SEED_RE.search(run_dir_name)
    if not match:
        raise ValueError(f"Cannot parse seed from run directory: {run_dir_name}")
    return int(match.group(1))


def scan_annotation_runs(input_root: str | Path) -> list[Path]:
    root = Path(input_root).resolve()
    if not root.exists():
        raise FileNotFoundError(f"Input root not found: {root}")
    return sorted(root.rglob("annotations.json"))


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def dump_json(path: str | Path, data: Any, *, indent: int = 2) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)


def round_points(points: Iterable[Sequence[Any]]) -> list[list[float]]:
    return [[float(x), float(y)] for x, y in points]


def build_chart_json(data_ori: Sequence[Sequence[Any]] | None, title: str | None = None) -> dict[str, Any]:
    values: dict[str, dict[str, str]] = {}
    for entry in data_ori or []:
        if not isinstance(entry, (list, tuple)) or len(entry) < 3:
            continue
        series, x_key, y_val = entry[:3]
        series_key = "None" if series in (None, "", "None") else str(series)
        values.setdefault(series_key, {})[str(x_key)] = str(y_val)
    if not values:
        values["None"] = {}
    return {
        "title": title or "N/A",
        "values": values,
    }
