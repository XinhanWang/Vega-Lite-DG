from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw
from tqdm import tqdm

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR.parent))

from data_pipeline.common import dump_json, load_json  # noqa: E402

MARKER_OFFSETS = [
    (-6, -6), (-5, -6), (-4, -6), (-3, -6), (-2, -6), (-1, -6), (0, -6), (1, -6), (2, -6), (3, -6), (4, -6), (5, -6), (6, -6),
    (-6, -5), (-5, -5), (-4, -5), (-3, -5), (-2, -5), (-1, -5), (0, -5), (1, -5), (2, -5), (3, -5), (4, -5), (5, -5), (6, -5),
    (-6, -4), (-5, -4), (-4, -4), (-3, -4), (-2, -4), (-1, -4), (0, -4), (1, -4), (2, -4), (3, -4), (4, -4), (5, -4), (6, -4),
    (-6, -3), (-5, -3), (-4, -3), (-3, -3), (-2, -3), (-1, -3), (0, -3), (1, -3), (2, -3), (3, -3), (4, -3), (5, -3), (6, -3),
    (-6, -2), (-5, -2), (-4, -2), (-3, -2), (-2, -2), (-1, -2), (0, -2), (1, -2), (2, -2), (3, -2), (4, -2), (5, -2), (6, -2),
    (-6, -1), (-5, -1), (-4, -1), (-3, -1), (-2, -1), (-1, -1), (0, -1), (1, -1), (2, -1), (3, -1), (4, -1), (5, -1), (6, -1),
    (-6,  0), (-5,  0), (-4,  0), (-3,  0), (-2,  0), (-1,  0), (0,  0), (1,  0), (2,  0), (3,  0), (4,  0), (5,  0), (6,  0),
    (-6,  1), (-5,  1), (-4,  1), (-3,  1), (-2,  1), (-1,  1), (0,  1), (1,  1), (2,  1), (3,  1), (4,  1), (5,  1), (6,  1),
    (-6,  2), (-5,  2), (-4,  2), (-3,  2), (-2,  2), (-1,  2), (0,  2), (1,  2), (2,  2), (3,  2), (4,  2), (5,  2), (6,  2),
    (-6,  3), (-5,  3), (-4,  3), (-3,  3), (-2,  3), (-1,  3), (0,  3), (1,  3), (2,  3), (3,  3), (4,  3), (5,  3), (6,  3),
    (-6,  4), (-5,  4), (-4,  4), (-3,  4), (-2,  4), (-1,  4), (0,  4), (1,  4), (2,  4), (3,  4), (4,  4), (5,  4), (6,  4),
    (-6,  5), (-5,  5), (-4,  5), (-3,  5), (-2,  5), (-1,  5), (0,  5), (1,  5), (2,  5), (3,  5), (4,  5), (5,  5), (6,  5),
    (-6,  6), (-5,  6), (-4,  6), (-3,  6), (-2,  6), (-1,  6), (0,  6), (1,  6), (2,  6), (3,  6), (4,  6), (5,  6), (6,  6),
]

MARKER_COLORS = [
    "#000000", "#000000", "#000000", "#000000", "#000000", "#000000", "#FF0000", "#000000", "#000000", "#000000", "#000000", "#000000", "#000000",
    "#000000", "#FFFFFF", "#FFFFFF", "#FFFFFF", "#000000", "#000000", "#FF0000", "#000000", "#000000", "#FFFFFF", "#FFFFFF", "#FFFFFF", "#000000",
    "#000000", "#FFFFFF", "#FFFFFF", "#FFFFFF", "#000000", "#000000", "#FF0000", "#000000", "#000000", "#FFFFFF", "#FFFFFF", "#FFFFFF", "#000000",
    "#000000", "#FFFFFF", "#FFFFFF", "#FFFFFF", "#000000", "#000000", "#FF0000", "#000000", "#000000", "#FFFFFF", "#FFFFFF", "#FFFFFF", "#000000",
    "#000000", "#000000", "#000000", "#000000", "#000000", "#000000", "#FF0000", "#000000", "#000000", "#000000", "#000000", "#000000", "#000000",
    "#000000", "#000000", "#000000", "#000000", "#000000", "#000000", "#FF0000", "#000000", "#000000", "#000000", "#000000", "#000000", "#000000",
    "#FF0000", "#FF0000", "#FF0000", "#FF0000", "#FF0000", "#FF0000", "#FF0000", "#FF0000", "#FF0000", "#FF0000", "#FF0000", "#FF0000", "#FF0000",
    "#000000", "#000000", "#000000", "#000000", "#000000", "#000000", "#FF0000", "#000000", "#000000", "#000000", "#000000", "#000000", "#000000",
    "#000000", "#000000", "#000000", "#000000", "#000000", "#000000", "#FF0000", "#000000", "#000000", "#000000", "#000000", "#000000", "#000000",
    "#000000", "#FFFFFF", "#FFFFFF", "#FFFFFF", "#000000", "#000000", "#FF0000", "#000000", "#000000", "#FFFFFF", "#FFFFFF", "#FFFFFF", "#000000",
    "#000000", "#FFFFFF", "#FFFFFF", "#FFFFFF", "#000000", "#000000", "#FF0000", "#000000", "#000000", "#FFFFFF", "#FFFFFF", "#FFFFFF", "#000000",
    "#000000", "#FFFFFF", "#FFFFFF", "#FFFFFF", "#000000", "#000000", "#FF0000", "#000000", "#000000", "#FFFFFF", "#FFFFFF", "#FFFFFF", "#000000",
    "#000000", "#000000", "#000000", "#000000", "#000000", "#000000", "#FF0000", "#000000", "#000000", "#000000", "#000000", "#000000", "#000000",
]


def draw_marker(draw: ImageDraw.ImageDraw, center_x: float, center_y: float, *, width: int, height: int) -> None:
    cx = int(round(center_x))
    cy = int(round(center_y))
    for (dx, dy), color in zip(MARKER_OFFSETS, MARKER_COLORS):
        x = cx + dx
        y = cy + dy
        if 0 <= x < width and 0 <= y < height:
            draw.point((x, y), fill=color)


def draw_anchor_image(image_path: str | Path, points: list[list[Any]]) -> Image.Image:
    with Image.open(image_path) as src:
        image = src.convert("RGB")

    draw = ImageDraw.Draw(image)
    width, height = image.size
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            continue
        draw_marker(draw, float(point[0]), height - float(point[1]), width=width, height=height)
    return image


def process_item(task: tuple[dict[str, Any], str, str]) -> dict[str, Any]:
    item, input_root_str, output_root_str = task
    input_root = Path(input_root_str)
    output_root = Path(output_root_str)

    resized_path = input_root / item["resized_image"]
    rendered_rel = Path("images") / "rendered" / item["template"] / f"seed_{item['seed']}" / Path(item["resized_image"]).name
    rendered_path = output_root / rendered_rel
    rendered_path.parent.mkdir(parents=True, exist_ok=True)

    image = draw_anchor_image(resized_path, item.get("pixel_coords", []))
    image.save(rendered_path)

    updated = dict(item)
    updated["rendered_image"] = str(rendered_rel)
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Render pixel anchors onto resized charts.")
    parser.add_argument("--manifest", default=str(SCRIPT_DIR / "outputs" / "resized.json"))
    parser.add_argument("--output-manifest", default=None)
    parser.add_argument("--input-root", default=str(SCRIPT_DIR / "outputs"))
    parser.add_argument("--output-root", default=str(SCRIPT_DIR / "outputs"))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 1) - 4))
    args = parser.parse_args()

    input_root = Path(args.input_root).expanduser().resolve()
    output_root = Path(args.output_root).expanduser().resolve()
    output_manifest = (
        Path(args.output_manifest).expanduser().resolve()
        if args.output_manifest
        else output_root / "final.json"
    )

    manifest = load_json(args.manifest)
    items = manifest["items"] if isinstance(manifest, dict) else manifest
    if args.limit is not None:
        items = items[: args.limit]

    tasks = [(item, str(input_root), str(output_root)) for item in items]

    rendered: list[dict[str, Any]] = []
    if args.workers <= 1 or len(tasks) <= 1:
        for task in tqdm(tasks, desc="Rendering anchors"):
            rendered.append(process_item(task))
    else:
        chunk_size = max(1, len(tasks) // max(1, args.workers * 4))
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            for item in tqdm(executor.map(process_item, tasks, chunksize=chunk_size), total=len(tasks), desc="Rendering anchors"):
                rendered.append(item)

    rendered.sort(key=lambda item: (item["template"], item["seed"], item["sample_index"]))
    dump_json(
        output_manifest,
        {
            "meta": {
                "source_manifest": str(Path(args.manifest).resolve()),
                "input_root": str(input_root),
                "output_root": str(output_root),
                "sample_count": len(rendered),
            },
            "items": rendered,
        },
        indent=2,
    )
    print(f"Saved {len(rendered)} rendered samples to {output_manifest}")


if __name__ == "__main__":
    main()
