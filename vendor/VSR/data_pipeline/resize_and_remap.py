from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from PIL import Image
from tqdm import tqdm

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR.parent))

from data_pipeline.common import (  # noqa: E402
    TARGET_SIDE,
    alias_from_template_dir,
    build_chart_json,
    dump_json,
    extract_seed,
    load_json,
    scan_annotation_runs,
)

RESAMPLE_LANCZOS = getattr(Image, "Resampling", Image).LANCZOS


def _safe_relpath(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _remap_point(point: list[Any], src_wh: list[int], scale: float, x_offset: int, y_offset: int, target_side: int) -> list[float]:
    x, y = float(point[0]), float(point[1])
    _, h = src_wh
    x_out = x * scale + x_offset
    y_out = target_side - ((h - y) * scale + y_offset)
    return [x_out, y_out]


def _remap_points(points: list[list[Any]], src_wh: list[int], scale: float, x_offset: int, y_offset: int, target_side: int) -> list[list[float]]:
    return [_remap_point(point, src_wh, scale, x_offset, y_offset, target_side) for point in points]


def process_annotation_file(task: tuple[str, str, str, int, int | None, bool]) -> list[dict[str, Any]]:
    annotation_path_str, input_root_str, output_root_str, target_side, max_samples, write_images = task
    annotation_path = Path(annotation_path_str)
    input_root = Path(input_root_str)
    output_root = Path(output_root_str)

    run_dir = annotation_path.parent
    template_dir = run_dir.parent.name
    template = alias_from_template_dir(template_dir)
    seed = extract_seed(run_dir.name)

    records = load_json(annotation_path)
    if not isinstance(records, list):
        raise ValueError(f"annotations.json must contain a list: {annotation_path}")

    items: list[dict[str, Any]] = []
    for sample_index, record in enumerate(records):
        if max_samples is not None and len(items) >= max_samples:
            break

        source_image_rel = Path(record["image"])
        source_image_path = (run_dir / source_image_rel).resolve()
        with Image.open(source_image_path) as src:
            src = src.convert("RGB")
            orig_w, orig_h = src.size
            background = src.getpixel((0, 0))

            scale = target_side / max(orig_w, orig_h)
            new_w = int(orig_w * scale)
            new_h = int(orig_h * scale)
            resized = src.resize((new_w, new_h), RESAMPLE_LANCZOS)

            x_offset = (target_side - new_w) // 2
            y_offset = (target_side - new_h) // 2
            canvas = Image.new("RGB", (target_side, target_side), background)
            canvas.paste(resized, (x_offset, y_offset))

            resized_rel = Path("images") / "resized" / template / f"seed_{seed}" / source_image_rel.name
            if write_images:
                resized_path = output_root / resized_rel
                resized_path.parent.mkdir(parents=True, exist_ok=True)
                canvas.save(resized_path)

        chart_coords = record.get("data_ori", [])
        pixel_coords = _remap_points(record.get("data_pixel", []), [orig_w, orig_h], scale, x_offset, y_offset, target_side)

        items.append(
            {
                "source_annotation": _safe_relpath(annotation_path, input_root),
                "source_image": _safe_relpath(source_image_path, input_root),
                "template": template,
                "seed": seed,
                "sample_index": sample_index,
                "orig_wh": [orig_w, orig_h],
                "wh": [target_side, target_side],
                "resized_image": str(resized_rel),
                "chart_coords": chart_coords,
                "pixel_coords": pixel_coords,
                "chart_json": build_chart_json(chart_coords, record.get("title")),
            }
        )

    return items


def main() -> None:
    parser = argparse.ArgumentParser(description="Resize chart images and remap chart pixel coordinates.")
    parser.add_argument("--input-root", default=str(SCRIPT_DIR.parent / "chart_generation" / "outputs"))
    parser.add_argument("--output-root", default=str(SCRIPT_DIR / "outputs"))
    parser.add_argument("--manifest", default=None, help="Output manifest path. Default: outputs/resized.json")
    parser.add_argument("--target-side", type=int, default=TARGET_SIDE)
    parser.add_argument("--templates", nargs="*", default=None, help="Optional template filters, e.g. barh1 line1 scatter1")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 1) - 4))
    parser.add_argument("--no-images", action="store_true", help="Write only the manifest without saving resized images.")
    args = parser.parse_args()

    input_root = Path(args.input_root).resolve()
    output_root = Path(args.output_root).resolve()
    manifest_path = Path(args.manifest) if args.manifest else output_root / "resized.json"

    if args.limit is not None:
        args.workers = 1

    annotation_files = [str(path) for path in scan_annotation_runs(input_root)]
    if args.templates:
        allowed = {alias_from_template_dir(template) for template in args.templates} | {template.strip() for template in args.templates}
        annotation_files = [
            path
            for path in annotation_files
            if alias_from_template_dir(Path(path).parent.parent.name) in allowed or Path(path).parent.parent.name in allowed
        ]

    items: list[dict[str, Any]] = []
    if args.limit is not None or args.workers <= 1 or len(annotation_files) <= 1:
        for annotation_file in tqdm(annotation_files, desc="Resizing runs"):
            remaining = None if args.limit is None else max(0, args.limit - len(items))
            task = (annotation_file, str(input_root), str(output_root), args.target_side, remaining, not args.no_images)
            batch = process_annotation_file(task)
            for item in batch:
                items.append(item)
                if args.limit is not None and len(items) >= args.limit:
                    break
            if args.limit is not None and len(items) >= args.limit:
                break
    else:
        tasks = [(path, str(input_root), str(output_root), args.target_side, None, not args.no_images) for path in annotation_files]
        chunk_size = max(1, len(tasks) // max(1, args.workers * 4))
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            for batch in tqdm(executor.map(process_annotation_file, tasks, chunksize=chunk_size), total=len(tasks), desc="Resizing runs"):
                items.extend(batch)

    items.sort(key=lambda item: (item["template"], item["seed"], item["sample_index"]))
    if args.limit is not None:
        items = items[: args.limit]

    dump_json(
        manifest_path,
        {
            "meta": {
                "source_root": str(input_root),
                "output_root": str(output_root),
                "target_side": args.target_side,
                "sample_count": len(items),
                "template_count": len({item["template"] for item in items}),
                "templates": sorted({item["template"] for item in items}),
            },
            "items": items,
        },
        indent=2,
    )
    print(f"Saved {len(items)} resized samples to {manifest_path}")


if __name__ == "__main__":
    main()
