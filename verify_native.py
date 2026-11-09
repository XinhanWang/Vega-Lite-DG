"""Verify adapter fidelity against actual upstream renders in a fresh directory."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

from native import KINDS, generate_native, jsonable, load_common, load_generator


def verify(outdir, seed=73101):
    outdir = Path(outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=False)
    checks = []
    for offset, kind in enumerate(KINDS):
        current_seed = seed + offset
        wrapped_dir = outdir / "wrapped" / kind
        wrapped = generate_native(kind, current_seed, wrapped_dir)
        generator = load_generator(kind)
        direct_dir = outdir / "direct" / kind
        direct_dir.mkdir(parents=True)
        direct = generator.render_one(0, runtime={"seed": current_seed, "RUN_ROOT": direct_dir, "save_dir": direct_dir})
        if direct is None:
            raise AssertionError(f"Direct upstream failed for {kind} seed {current_seed}")
        with Image.open(wrapped_dir / "native.png") as im:
            wrapped_pixels = np.asarray(im.convert("RGBA"))
        with Image.open(direct_dir / direct["image"]) as im:
            direct_pixels = np.asarray(im.convert("RGBA"))
        assert np.array_equal(wrapped_pixels, direct_pixels), f"Pixel parity failed: {kind}"
        native_annotation = dict(wrapped["annotation"])
        direct_annotation = dict(direct)
        native_annotation.pop("image")
        direct_annotation.pop("image")
        assert native_annotation == direct_annotation, f"Annotation parity failed: {kind}"
        common = load_common()
        common.seed_everything(current_seed)
        direct_config = jsonable(generator.sample_config())
        raw = json.loads((wrapped_dir / "native.raw.config.json").read_text(encoding="utf-8"))
        assert raw == direct_config, f"Config parity failed: {kind}"
        sampled = generate_native(kind, current_seed, outdir / "sampled" / kind, render=False)
        assert sampled["config"] == direct_config, f"Sampling-only parity failed: {kind}"
        checks.append({"kind": kind, "seed": current_seed, "rows": len(direct["data_ori"]), "pixel_parity": True, "annotation_parity": True, "config_parity": True, "sampling_only_parity": True})
        print(json.dumps(checks[-1]), flush=True)

    control_cases = [
        ("barv_1", {"category_count": 6, "family": "signed_mix", "profile": "dark_contrast", "show_error": True, "hatch": "x"}),
        ("barh_n", {"category_count": 5, "series_count": 3, "family": "crossing", "show_error": False}),
        ("barv_stack", {"category_count": 6, "series_count": 6, "family": "layered", "stack_mode": "percent"}),
        ("line_n", {"point_count": 8, "series_count": 4, "family": "oscillating", "x_mode": "numeric"}),
        ("scatter_n", {"point_count": 12, "series_count": 2, "family": "clustered"}),
    ]
    for i, (kind, controls) in enumerate(control_cases):
        result = generate_native(kind, seed + 100 + i, outdir / "controlled" / kind, controls, render=False)
        cfg = result["config"]
        for key in ("family", "x_mode", "stack_mode"):
            if key in controls:
                assert cfg[key] == controls[key], (kind, key)
        if "series_count" in controls:
            assert cfg["n_series"] == controls["series_count"]
        if "category_count" in controls:
            assert len(cfg["labels"]) == controls["category_count"]
        if "point_count" in controls:
            assert len(cfg.get("x_labels", cfg.get("x", []))) == controls["point_count"]
        if "profile" in controls:
            assert cfg["style"]["profile"] == controls["profile"]
        if "show_error" in controls:
            assert (cfg.get("xerr") is not None or cfg.get("yerr") is not None) == controls["show_error"]
        if "hatch" in controls:
            assert cfg["hatch"] == controls["hatch"]
        checks.append({"kind": kind, "controls": controls, "control_match": True, "sampling_attempts": result["diagnostics"]["sampling_attempts"]})

    try:
        generate_native("scatter_n", seed, outdir / "invalid", {"point_count": 12, "series_count": 3}, render=False)
    except ValueError:
        checks.append({"invalid_scatter_total_rejected": True})
    else:
        raise AssertionError("Impossible scatter total was not rejected")
    report = {"upstream_commit": "1fd040346add205ffbada9748273cad3bc9159e5", "passed": True, "checks": checks}
    (outdir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", required=True, help="A new directory; existing directories are rejected")
    parser.add_argument("--seed", type=int, default=73101)
    args = parser.parse_args()
    result = verify(args.outdir, args.seed)
    print(json.dumps({"passed": result["passed"], "check_count": len(result["checks"])}))
