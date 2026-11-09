from __future__ import annotations

import json
import math
import os
import random
import shutil
import colorsys
import urllib.request
from pathlib import Path
from typing import Iterable

import matplotlib
from matplotlib import colors as mcolors

matplotlib.use("Agg", force=True)

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
FONT_DIR = ASSETS_DIR / "fonts"
OUTPUT_DIR = BASE_DIR / "outputs"

WORDS_CANDIDATES = [
    BASE_DIR / "words.txt",
]

FONT_DIR_CANDIDATES = [
    FONT_DIR,
]

REQUIRED_FONT_FILES = [
    "DejaVuSans-Bold.ttf",
    "DejaVuSans.ttf",
    "DejaVuSerif.ttf",
    "DejaVuSerif-Bold.ttf",
    "DejaVuSansMono.ttf",
    "DejaVuSansMono-Bold.ttf",
    "NimbusSans-Regular.otf",
    "NimbusSans-Bold.otf",
    "NimbusRoman-Regular.otf",
    "NimbusRoman-Bold.otf",
    "NimbusMonoPS-Regular.otf",
    "NimbusMonoPS-Bold.otf",
    "URWBookman-Demi.otf",
    "URWBookman-Light.otf",
    "URWGothic-Book.otf",
    "NotoMono-Regular.otf",
]

_WORDS_CACHE: dict[tuple[str, int], list[str]] = {}

DEJAVU_FONT_DIR = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
DEJAVU_FONT_FILES = {
    "DejaVuSans-Bold.ttf",
    "DejaVuSans.ttf",
    "DejaVuSerif.ttf",
    "DejaVuSerif-Bold.ttf",
    "DejaVuSansMono.ttf",
    "DejaVuSansMono-Bold.ttf",
}

FONT_URLS = {
    "NimbusSans-Regular.otf": "https://raw.githubusercontent.com/ArtifexSoftware/urw-base35-fonts/master/fonts/NimbusSans-Regular.otf",
    "NimbusSans-Bold.otf": "https://raw.githubusercontent.com/ArtifexSoftware/urw-base35-fonts/master/fonts/NimbusSans-Bold.otf",
    "NimbusRoman-Regular.otf": "https://raw.githubusercontent.com/ArtifexSoftware/urw-base35-fonts/master/fonts/NimbusRoman-Regular.otf",
    "NimbusRoman-Bold.otf": "https://raw.githubusercontent.com/ArtifexSoftware/urw-base35-fonts/master/fonts/NimbusRoman-Bold.otf",
    "NimbusMonoPS-Regular.otf": "https://raw.githubusercontent.com/ArtifexSoftware/urw-base35-fonts/master/fonts/NimbusMonoPS-Regular.otf",
    "NimbusMonoPS-Bold.otf": "https://raw.githubusercontent.com/ArtifexSoftware/urw-base35-fonts/master/fonts/NimbusMonoPS-Bold.otf",
    "URWBookman-Demi.otf": "https://raw.githubusercontent.com/ArtifexSoftware/urw-base35-fonts/master/fonts/URWBookman-Demi.otf",
    "URWBookman-Light.otf": "https://raw.githubusercontent.com/ArtifexSoftware/urw-base35-fonts/master/fonts/URWBookman-Light.otf",
    "URWGothic-Book.otf": "https://raw.githubusercontent.com/ArtifexSoftware/urw-base35-fonts/master/fonts/URWGothic-Book.otf",
    "NotoMono-Regular.otf": "https://raw.githubusercontent.com/googlefonts/noto-fonts/bf20559450ec75aec7a646b208343540a4496262/phaseIII_only/unhinted/otf/NotoMono/NotoMono-Regular.otf",
}

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
QUARTERS = ["Q1", "Q2", "Q3", "Q4"]
SERIES_TAGS = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L"]
UNITS = [
    "",
    " (%)",
    " (ms)",
    " (k)",
    " (USD)",
    " (GB)",
    " (°C)",
    " (rpm)",
    " (ops/s)",
    " (Hz)",
    " (kg)",
    " (km)",
    " (samples)",
    " (events)",
    " (req/s)",
    " (MB)",
    " (ppm)",
    " (px)",
]

PALETTES = {
    "paper": {
        "face": "#ffffff",
        "axes": "#fbfbf9",
        "grid": "#d7dce2",
        "text": "#1f2937",
        "series": ["#1f77b4", "#2ca02c", "#d62728", "#ff7f0e", "#17becf"],
    },
    "cool": {
        "face": "#f8fbff",
        "axes": "#ffffff",
        "grid": "#d6e1ea",
        "text": "#111827",
        "series": ["#2563eb", "#0ea5e9", "#14b8a6", "#f97316", "#ef4444"],
    },
    "warm": {
        "face": "#fcfbf6",
        "axes": "#ffffff",
        "grid": "#e3dccf",
        "text": "#26211e",
        "series": ["#c2410c", "#ca8a04", "#b45309", "#0f766e", "#7c3aed"],
    },
    "muted": {
        "face": "#f7f7f4",
        "axes": "#ffffff",
        "grid": "#ced4da",
        "text": "#1f1f1f",
        "series": ["#374151", "#64748b", "#0f766e", "#b91c1c", "#1d4ed8"],
    },
    "dark": {
        "face": "#111827",
        "axes": "#111827",
        "grid": "#334155",
        "text": "#f8fafc",
        "series": ["#22d3ee", "#f59e0b", "#34d399", "#f43f5e", "#60a5fa"],
    },
    "studio": {
        "face": "#f6f7fb",
        "axes": "#ffffff",
        "grid": "#d8dde8",
        "text": "#1d2433",
        "series": ["#4c6ef5", "#12b886", "#fa5252", "#f59f00", "#7950f2"],
    },
    "vibrant": {
        "face": "#fcfcfb",
        "axes": "#ffffff",
        "grid": "#d8dee7",
        "text": "#1f2430",
        "series": ["#e45756", "#4c78a8", "#72b7b2", "#f58518", "#54a24b"],
    },
    "forest": {
        "face": "#f7faf7",
        "axes": "#ffffff",
        "grid": "#d6e2d6",
        "text": "#1f2d22",
        "series": ["#2f6f4e", "#6aa84f", "#93c47d", "#2c7da0", "#c27ba0"],
    },
    "royal": {
        "face": "#f7f8ff",
        "axes": "#ffffff",
        "grid": "#dbe1f0",
        "text": "#1b2340",
        "series": ["#1d4ed8", "#7c3aed", "#0f766e", "#d97706", "#ef4444"],
    },
    "earth": {
        "face": "#fbf8f2",
        "axes": "#ffffff",
        "grid": "#e4d8c8",
        "text": "#31261d",
        "series": ["#8d6e63", "#4e7c7b", "#c97c5d", "#849483", "#b08968"],
    },
    "paper2": {
        "face": "#fffef8",
        "axes": "#ffffff",
        "grid": "#dfe6ea",
        "text": "#1f2937",
        "series": ["#0f766e", "#2563eb", "#d97706", "#7c3aed", "#dc2626"],
    },
    "pastel": {
        "face": "#fffaf8",
        "axes": "#ffffff",
        "grid": "#eadfe7",
        "text": "#243240",
        "series": ["#5b8def", "#f28f3b", "#6cce8f", "#d95f5f", "#9d7ec7"],
    },
    "sunset": {
        "face": "#fff8f2",
        "axes": "#ffffff",
        "grid": "#e8ddd2",
        "text": "#2b211a",
        "series": ["#d1495b", "#edae49", "#00798c", "#30638e", "#8a5a44"],
    },
    "mono": {
        "face": "#fafafa",
        "axes": "#ffffff",
        "grid": "#d4d4d4",
        "text": "#1f1f1f",
        "series": ["#111111", "#404040", "#6b7280", "#9ca3af", "#0f766e"],
    },
    "berry": {
        "face": "#fff7fb",
        "axes": "#ffffff",
        "grid": "#ead7e4",
        "text": "#2b1f33",
        "series": ["#a61e4d", "#6d28d9", "#d9480f", "#0f766e", "#f59f00"],
    },
    "lagoon": {
        "face": "#f6fbfb",
        "axes": "#ffffff",
        "grid": "#d5e7ea",
        "text": "#15313a",
        "series": ["#0f766e", "#0891b2", "#2563eb", "#14b8a6", "#f97316"],
    },
    "desert": {
        "face": "#fbf6ef",
        "axes": "#ffffff",
        "grid": "#e5d8c7",
        "text": "#33261c",
        "series": ["#8c5a3c", "#c97c5d", "#7a8450", "#d97706", "#2f6f4e"],
    },
    "retro": {
        "face": "#fffdf4",
        "axes": "#ffffff",
        "grid": "#e6dcc0",
        "text": "#2f261d",
        "series": ["#b45309", "#0f766e", "#4338ca", "#ca8a04", "#be185d"],
    },
    "glacier": {
        "face": "#f6fbfd",
        "axes": "#ffffff",
        "grid": "#d6e7ef",
        "text": "#173042",
        "series": ["#0ea5e9", "#22c55e", "#14b8a6", "#64748b", "#38bdf8"],
    },
    "ember": {
        "face": "#fff8f4",
        "axes": "#ffffff",
        "grid": "#ead7cf",
        "text": "#301b15",
        "series": ["#ea580c", "#ef4444", "#f97316", "#b45309", "#fb7185"],
    },
    "sage": {
        "face": "#f7fbf5",
        "axes": "#ffffff",
        "grid": "#dbe6d6",
        "text": "#233126",
        "series": ["#6b8f71", "#8fb996", "#a3b18a", "#386641", "#bc6c25"],
    },
    "indigo": {
        "face": "#f7f8ff",
        "axes": "#ffffff",
        "grid": "#dbe1f4",
        "text": "#1e2337",
        "series": ["#4f46e5", "#7c3aed", "#06b6d4", "#0f766e", "#d97706"],
    },
    "slate": {
        "face": "#f8fafc",
        "axes": "#ffffff",
        "grid": "#d8e0ea",
        "text": "#1f2937",
        "series": ["#475569", "#64748b", "#0f766e", "#2563eb", "#94a3b8"],
    },
    "citrus": {
        "face": "#fffdf1",
        "axes": "#ffffff",
        "grid": "#e8e1c0",
        "text": "#2d2a1f",
        "series": ["#d97706", "#84cc16", "#eab308", "#f97316", "#10b981"],
    },
    "aurora": {
        "face": "#f8fbff",
        "axes": "#ffffff",
        "grid": "#d8e4ef",
        "text": "#152238",
        "series": ["#00b4d8", "#8e5cf7", "#f72585", "#2ec4b6", "#f9c74f"],
    },
    "coral": {
        "face": "#fff8f5",
        "axes": "#ffffff",
        "grid": "#ead8d3",
        "text": "#2c1f1b",
        "series": ["#ff6b6b", "#ff922b", "#2a9d8f", "#457b9d", "#e76f51"],
    },
    "mint": {
        "face": "#f7fffb",
        "axes": "#ffffff",
        "grid": "#d6ebdf",
        "text": "#1e3127",
        "series": ["#1b9aaa", "#2ec4b6", "#52b788", "#40916c", "#3a86ff"],
    },
    "midnight": {
        "face": "#0b1220",
        "axes": "#0f172a",
        "grid": "#243047",
        "text": "#e5eef9",
        "series": ["#38bdf8", "#f472b6", "#f59e0b", "#4ade80", "#a78bfa"],
    },
    "graphite": {
        "face": "#f8fafc",
        "axes": "#ffffff",
        "grid": "#cbd5e1",
        "text": "#111827",
        "series": ["#0f172a", "#334155", "#2563eb", "#dc2626", "#0f766e"],
    },
    "opal": {
        "face": "#f6fbfa",
        "axes": "#ffffff",
        "grid": "#d7e8e3",
        "text": "#18312c",
        "series": ["#0ea5e9", "#14b8a6", "#22c55e", "#60a5fa", "#84cc16"],
    },
}

PALETTE_EXTRAS = {
    "paper": ["#9467bd"],
    "cool": ["#8b5cf6"],
    "warm": ["#e11d48"],
    "muted": ["#a855f7"],
    "dark": ["#a78bfa"],
    "studio": ["#f59e0b"],
    "vibrant": ["#b07aa1"],
    "forest": ["#f4a261"],
    "royal": ["#06b6d4"],
    "earth": ["#7f5539"],
    "paper2": ["#ef4444"],
    "pastel": ["#4db6ac"],
    "sunset": ["#f3722c"],
    "mono": ["#7c3aed"],
    "berry": ["#f59f00"],
    "lagoon": ["#8b5cf6"],
    "desert": ["#2a9d8f"],
    "retro": ["#8a5a44"],
    "glacier": ["#2dd4bf"],
    "ember": ["#fb7185"],
    "sage": ["#4d7c0f"],
    "indigo": ["#22d3ee"],
    "slate": ["#94a3b8"],
    "citrus": ["#22c55e"],
    "aurora": ["#06b6d4", "#a855f7"],
    "coral": ["#fb7185", "#ffd166"],
    "mint": ["#2dd4bf", "#22c55e"],
    "midnight": ["#22d3ee", "#f59e0b", "#fb7185"],
    "graphite": ["#475569", "#0ea5e9"],
    "opal": ["#06b6d4", "#8b5cf6"],
}


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def clear_dir(path: Path) -> None:
    path = Path(path)
    if not path.exists():
        return
    for child in path.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def _copy_font(source: Path, dest: Path, force: bool = False) -> None:
    if dest.exists() and not force:
        return
    ensure_dir(dest.parent)
    shutil.copy2(source, dest)


def _download_font(url: str, dest: Path, force: bool = False) -> None:
    if dest.exists() and not force:
        return
    ensure_dir(dest.parent)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    with urllib.request.urlopen(url) as response, tmp.open("wb") as f:
        shutil.copyfileobj(response, f)
    tmp.replace(dest)


def resolve_existing(candidates: Iterable[Path]) -> Path:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return next(iter(candidates))


def seed_everything(seed: int | None = None, env_var: str = "VSR_SEED") -> int:
    if seed is None:
        env_seed = os.environ.get(env_var)
        if env_seed:
            seed = int(env_seed)
        else:
            seed = int.from_bytes(os.urandom(4), byteorder="big")
    random.seed(seed)
    try:
        import numpy as np

        np.random.seed(seed % (2**32 - 1))
    except Exception:
        pass
    return seed


def load_words(path: Path | None = None, max_length: int = 12) -> list[str]:
    if path is None:
        path = resolve_existing(WORDS_CANDIDATES)
    cache_key = (str(path), max_length)
    cached = _WORDS_CACHE.get(cache_key)
    if cached is not None:
        return cached
    with Path(path).open("r", encoding="utf-8") as f:
        words = [line.strip() for line in f if 0 < len(line.strip()) <= max_length]
    _WORDS_CACHE[cache_key] = words
    return words


def ensure_fonts(font_dir: Path | None = None, force: bool = False) -> list[Path]:
    if font_dir is None:
        font_dir = FONT_DIR
    font_dir = Path(font_dir)
    ensure_dir(font_dir)

    if not force:
        installed = [font_dir / name for name in REQUIRED_FONT_FILES if (font_dir / name).exists()]
        if len(installed) == len(REQUIRED_FONT_FILES):
            return installed

    installed: list[Path] = []
    for font_name in sorted(DEJAVU_FONT_FILES):
        source = DEJAVU_FONT_DIR / font_name
        if not source.exists():
            raise FileNotFoundError(
                f"Missing bundled Matplotlib font: {source}. "
                "Please install a full Matplotlib package."
            )
        dest = font_dir / font_name
        _copy_font(source, dest, force=force)
        installed.append(dest)

    for font_name, url in FONT_URLS.items():
        dest = font_dir / font_name
        _download_font(url, dest, force=force)
        installed.append(dest)

    missing = [name for name in REQUIRED_FONT_FILES if not (font_dir / name).exists()]
    if missing:
        raise RuntimeError(f"Font setup incomplete, missing: {', '.join(missing)}")
    return installed


def load_font_pool(font_dir: Path | None = None) -> list[str]:
    if font_dir is None:
        font_dir = resolve_existing(FONT_DIR_CANDIDATES)
    font_dir = Path(font_dir)
    fonts = [str(font_dir / name) for name in REQUIRED_FONT_FILES if (font_dir / name).exists()]
    if not fonts:
        raise FileNotFoundError(
            f"No usable fonts found in {font_dir}. "
            "Please make sure the shared font bundle exists."
        )
    return fonts


def build_output_layout(script_name: str, seed: int, output_root: Path = OUTPUT_DIR) -> tuple[Path, Path, Path, Path]:
    output_root = Path(os.environ.get("VSR_OUTPUT_ROOT", output_root))
    run_root = output_root / script_name / f"seed_{seed:08d}"
    image_dir = ensure_dir(run_root / "images")
    annotations_path = run_root / "annotations.json"
    manifest_path = run_root / "manifest.json"
    ensure_dir(run_root)
    return run_root, image_dir, annotations_path, manifest_path


def safe_max_workers(reserve: int = 4) -> int:
    cpu_count = os.cpu_count() or 1
    return max(1, cpu_count - reserve)


def write_json(path: Path, payload) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=4, ensure_ascii=False)


def write_manifest(path: Path, **meta) -> None:
    write_json(path, meta)


def choose_weighted(items: list, weights: list[float]):
    return random.choices(items, weights=weights, k=1)[0]


def _clamp_unit(value: float) -> float:
    return max(0.0, min(1.0, value))


def _mix_colors(color_a: str, color_b: str, ratio: float) -> str:
    ratio = _clamp_unit(ratio)
    ra, ga, ba = mcolors.to_rgb(color_a)
    rb, gb, bb = mcolors.to_rgb(color_b)
    return mcolors.to_hex(
        (
            ra * (1.0 - ratio) + rb * ratio,
            ga * (1.0 - ratio) + gb * ratio,
            ba * (1.0 - ratio) + bb * ratio,
        )
    )


def _shift_hue(color: str, delta: float) -> str:
    r, g, b = mcolors.to_rgb(color)
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    h = (h + delta) % 1.0
    return mcolors.to_hex(colorsys.hls_to_rgb(h, l, s))


def _adjust_lightness(color: str, delta: float) -> str:
    r, g, b = mcolors.to_rgb(color)
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    l = _clamp_unit(l + delta)
    l = max(0.10, min(0.90, l))
    return mcolors.to_hex(colorsys.hls_to_rgb(h, l, s))


def _adjust_saturation(color: str, scale: float) -> str:
    r, g, b = mcolors.to_rgb(color)
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    s = _clamp_unit(s * scale)
    return mcolors.to_hex(colorsys.hls_to_rgb(h, l, s))


def _relative_luminance(color: str) -> float:
    r, g, b = mcolors.to_rgb(color)

    def to_linear(value: float) -> float:
        if value <= 0.04045:
            return value / 12.92
        return ((value + 0.055) / 1.055) ** 2.4

    r = to_linear(r)
    g = to_linear(g)
    b = to_linear(b)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_ratio(color_a: str, color_b: str) -> float:
    la = _relative_luminance(color_a)
    lb = _relative_luminance(color_b)
    lighter = max(la, lb)
    darker = min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def _hls_triplet(color: str) -> tuple[float, float, float]:
    r, g, b = mcolors.to_rgb(color)
    return colorsys.rgb_to_hls(r, g, b)


def _colors_too_close(color_a: str, color_b: str) -> bool:
    ha, la, sa = _hls_triplet(color_a)
    hb, lb, sb = _hls_triplet(color_b)
    hue_delta = abs(ha - hb)
    hue_delta = min(hue_delta, 1.0 - hue_delta)
    return hue_delta < 0.06 and abs(la - lb) < 0.16 and abs(sa - sb) < 0.18


def _sample_random_series_color(
    theme: str,
    facecolor: str,
    chart_kind: str,
    avoid: Iterable[str] | None = None,
) -> str:
    if theme in {"dark", "midnight"}:
        flavors = [
            ("glow", 0.34),
            ("vivid", 0.26),
            ("cool", 0.18),
            ("deep", 0.12),
            ("pastel", 0.10),
        ]
    elif theme in {"mono", "slate", "graphite"}:
        flavors = [
            ("balanced", 0.30),
            ("deep", 0.22),
            ("vivid", 0.20),
            ("pastel", 0.18),
            ("neon", 0.10),
        ]
    else:
        flavors = [
            ("vivid", 0.28),
            ("balanced", 0.22),
            ("deep", 0.18),
            ("pastel", 0.18),
            ("neon", 0.14),
        ]

    flavor = choose_weighted([name for name, _ in flavors], [weight for _, weight in flavors])
    if flavor == "pastel":
        saturation_range = (0.24, 0.58)
        lightness_range = (0.68, 0.92)
    elif flavor == "deep":
        saturation_range = (0.58, 0.98)
        lightness_range = (0.22, 0.50)
    elif flavor == "neon":
        saturation_range = (0.82, 1.00)
        lightness_range = (0.42, 0.74)
    elif flavor == "glow":
        saturation_range = (0.60, 1.00)
        lightness_range = (0.64, 0.90)
    elif flavor == "cool":
        saturation_range = (0.52, 0.92)
        lightness_range = (0.36, 0.78)
    else:
        saturation_range = (0.50, 0.98)
        lightness_range = (0.30, 0.78)

    if chart_kind == "scatter":
        saturation_range = (max(0.20, saturation_range[0] - 0.05), min(1.00, saturation_range[1] + 0.04))
        lightness_range = (max(0.24, lightness_range[0] - 0.04), min(0.92, lightness_range[1] + 0.04))
    elif chart_kind == "line":
        saturation_range = (max(0.24, saturation_range[0] - 0.03), min(1.00, saturation_range[1] + 0.02))
        lightness_range = (max(0.24, lightness_range[0] - 0.02), min(0.88, lightness_range[1] + 0.02))
    elif chart_kind.startswith("bar"):
        saturation_range = (max(0.22, saturation_range[0] - 0.02), min(1.00, saturation_range[1] + 0.02))
        lightness_range = (max(0.24, lightness_range[0] - 0.01), min(0.86, lightness_range[1]))

    avoid_list = list(avoid or [])
    min_contrast = 2.0 if chart_kind in {"line", "scatter"} else 1.8

    for _ in range(40):
        hue = random.random()
        saturation = random.uniform(*saturation_range)
        lightness = random.uniform(*lightness_range)
        color = mcolors.to_hex(colorsys.hls_to_rgb(hue, lightness, saturation))
        if _contrast_ratio(color, facecolor) < min_contrast:
            continue
        if any(_colors_too_close(color, other) for other in avoid_list):
            continue
        return color

    # Fallback: keep the hue random but push it away from the background.
    hue = random.random()
    saturation = min(1.0, max(0.35, random.uniform(*saturation_range)))
    lightness = 0.42 if _relative_luminance(facecolor) > 0.5 else 0.72
    if theme in {"dark", "midnight"}:
        lightness = 0.76
    elif theme in {"mono", "slate", "graphite"}:
        lightness = 0.48
    return mcolors.to_hex(colorsys.hls_to_rgb(hue, lightness, saturation))


def _distinct_anchor_colors(palette: dict, count: int) -> list[str]:
    candidates = list(dict.fromkeys([*palette["series"], *PALETTE_EXTRAS.get(palette["theme"], [])]))
    if not candidates:
        candidates = [palette["text"], palette["grid"], palette["axes"]]
    if len(candidates) >= count:
        return random.sample(candidates, count)
    anchors = list(candidates)
    while len(anchors) < count:
        anchors.append(random.choice(candidates))
    return anchors


def _series_color_mode(chart_kind: str, series_count: int, profile: str) -> str:
    if profile == "monochrome_minimal":
        modes = ["muted", "sequential", "direct", "random"]
        weights = [0.36, 0.26, 0.16, 0.22]
    elif profile == "dark_contrast":
        modes = ["direct", "expanded", "paired", "chromatic", "sequential", "random"]
        weights = [0.24, 0.19, 0.16, 0.16, 0.11, 0.14]
    elif profile == "chromatic":
        modes = ["chromatic", "triadic", "expanded", "paired", "sequential", "random"]
        weights = [0.27, 0.18, 0.15, 0.12, 0.10, 0.18]
    elif profile == "compact_report":
        modes = ["direct", "muted", "sequential", "paired", "random"]
        weights = [0.28, 0.22, 0.16, 0.12, 0.22]
    elif chart_kind == "scatter":
        modes = ["chromatic", "expanded", "triadic", "paired", "direct", "sequential", "random"]
        weights = [0.16, 0.19, 0.13, 0.13, 0.11, 0.08, 0.20]
    elif chart_kind == "line":
        modes = ["direct", "paired", "triadic", "chromatic", "sequential", "expanded", "random"]
        weights = [0.18, 0.14, 0.13, 0.15, 0.11, 0.09, 0.20]
    elif chart_kind.startswith("bar"):
        modes = ["direct", "expanded", "paired", "chromatic", "sequential", "muted", "random"]
        weights = [0.21, 0.18, 0.15, 0.11, 0.10, 0.08, 0.17]
    else:
        modes = ["direct", "expanded", "paired", "chromatic", "sequential", "random"]
        weights = [0.21, 0.18, 0.15, 0.15, 0.11, 0.20]

    if series_count <= 1:
        if "chromatic" in modes:
            base = {m: 0.0 for m in modes}
            base["chromatic"] = 0.22
            if "random" in base:
                base["random"] = 0.24
            if "direct" in base:
                base["direct"] = 0.16
            if "sequential" in base:
                base["sequential"] = 0.14
            if "expanded" in base:
                base["expanded"] = 0.10
            if "paired" in base:
                base["paired"] = 0.08
            if "triadic" in base:
                base["triadic"] = 0.06
            weights = [base[m] for m in modes]
            total = sum(weights)
            weights = [w / total for w in weights]
        else:
            total = sum(weights)
            weights = [w / total for w in weights]
    elif series_count >= 4:
        if "expanded" in modes:
            weights = [w + 0.06 if m == "expanded" else w for m, w in zip(modes, weights)]
        if "chromatic" in modes:
            weights = [w + 0.05 if m == "chromatic" else w for m, w in zip(modes, weights)]
        if "random" in modes:
            weights = [w + 0.10 if m == "random" else w for m, w in zip(modes, weights)]
        total = sum(weights)
        weights = [w / total for w in weights]

    return choose_weighted(modes, weights)


def build_series_colors(
    palette: dict,
    series_count: int,
    chart_kind: str,
    profile: str,
    color_mode: str | None = None,
) -> list[str]:
    theme = palette["theme"]
    base_colors = list(dict.fromkeys(palette["series"]))
    anchor_count = min(5, max(1, series_count))
    anchors = _distinct_anchor_colors(palette, anchor_count)
    if color_mode is None:
        color_mode = _series_color_mode(chart_kind, series_count, profile)
    chart_random_chance = 0.0
    if color_mode != "random":
        if profile == "chromatic":
            chart_random_chance = 0.16 if series_count >= 4 else 0.12 if series_count >= 3 else 0.08
        elif profile in {"colorful_analytic", "dense_scatter_family"}:
            chart_random_chance = 0.14 if series_count >= 4 else 0.10 if series_count >= 3 else 0.06
        elif profile in {"presentation_emphasis", "dashboard_dense"}:
            chart_random_chance = 0.10 if series_count >= 4 else 0.07 if series_count >= 3 else 0.04
        elif profile in {"compact_report", "monochrome_minimal"}:
            chart_random_chance = 0.06 if series_count >= 4 else 0.04 if series_count >= 3 else 0.02
        elif chart_kind == "scatter":
            chart_random_chance = 0.15 if series_count >= 4 else 0.11 if series_count >= 3 else 0.07
        elif chart_kind == "line":
            chart_random_chance = 0.13 if series_count >= 4 else 0.09 if series_count >= 3 else 0.06
        elif chart_kind.startswith("bar"):
            chart_random_chance = 0.11 if series_count >= 4 else 0.08 if series_count >= 3 else 0.05
        else:
            chart_random_chance = 0.10 if series_count >= 4 else 0.07 if series_count >= 3 else 0.05
        if random.random() < chart_random_chance:
            color_mode = "random"
    series_colors: list[str] = []
    neutral_targets = [palette["axes"], palette["text"], palette["grid"]]
    accent_pool = [*base_colors, *PALETTE_EXTRAS.get(theme, [])]
    if not accent_pool:
        accent_pool = [palette["text"]]
    random_tail = 0.0
    if color_mode != "random":
        if profile == "chromatic":
            random_tail = 0.30 if series_count >= 3 else 0.18
        elif profile in {"colorful_analytic", "dense_scatter_family"}:
            random_tail = 0.24 if series_count >= 3 else 0.14
        elif profile in {"presentation_emphasis", "dashboard_dense"}:
            random_tail = 0.16 if series_count >= 3 else 0.10
        elif profile in {"compact_report", "monochrome_minimal"}:
            random_tail = 0.08 if series_count >= 3 else 0.04
        elif chart_kind == "scatter":
            random_tail = 0.22 if series_count >= 3 else 0.14
        elif chart_kind == "line":
            random_tail = 0.18 if series_count >= 3 else 0.12
        elif chart_kind.startswith("bar"):
            random_tail = 0.16 if series_count >= 3 else 0.10
        if series_count >= 5:
            random_tail += 0.04

    for idx in range(series_count):
        cycle = idx // max(1, len(anchors))
        anchor = anchors[idx % len(anchors)]
        if color_mode == "random":
            color = _sample_random_series_color(theme, palette["face"], chart_kind, avoid=series_colors)
        elif color_mode == "muted":
            target = neutral_targets[idx % len(neutral_targets)]
            color = _mix_colors(anchor, target, 0.16 + 0.08 * (idx % 3))
            color = _adjust_saturation(color, 0.82 if idx % 2 == 0 else 0.90)
        elif color_mode == "sequential":
            step = idx - (series_count - 1) / 2.0
            color = _shift_hue(anchor, step * 0.018)
            color = _adjust_lightness(color, step * 0.045)
            color = _adjust_saturation(color, 1.05)
        elif color_mode == "paired":
            pair_anchor = anchors[idx % min(2, len(anchors))]
            step = idx // 2
            color = _shift_hue(pair_anchor, (0.04 if idx % 2 == 0 else -0.04) * (1 + 0.35 * step))
            color = _adjust_lightness(color, (0.06 if idx % 2 == 0 else -0.03) * min(step, 2))
            color = _adjust_saturation(color, 1.06)
        elif color_mode == "triadic":
            tri_anchor = anchors[idx % len(anchors)]
            color = _shift_hue(tri_anchor, random.choice([-0.09, 0.0, 0.09]))
            color = _adjust_lightness(color, (cycle * 0.05) * (1 if idx % 2 == 0 else -1))
            color = _adjust_saturation(color, 1.08)
        elif color_mode == "chromatic":
            source = accent_pool[idx % len(accent_pool)]
            hue_shift = random.choice([-0.16, -0.10, -0.05, 0.0, 0.05, 0.10, 0.16])
            color = _shift_hue(source, hue_shift + cycle * 0.03)
            color = _adjust_lightness(color, random.choice([-0.05, 0.0, 0.04, 0.08]) - cycle * 0.02)
            color = _adjust_saturation(color, 1.10 if theme not in {"mono", "slate", "graphite"} else 0.92)
        elif color_mode == "expanded":
            source = accent_pool[idx % len(accent_pool)]
            if cycle == 0:
                color = source
            else:
                color = _shift_hue(source, (0.04 * cycle) * (1 if idx % 2 == 0 else -1))
                color = _adjust_lightness(color, 0.03 * cycle * (1 if idx % 3 == 0 else -1))
                color = _adjust_saturation(color, 1.04)
        elif color_mode == "direct":
            source = accent_pool[idx % len(accent_pool)]
            if cycle == 0:
                color = source
            else:
                color = _shift_hue(source, random.choice([0.02, -0.02, 0.04, -0.04]))
                color = _adjust_lightness(color, random.choice([0.01, -0.01, 0.03, -0.03]))
                color = _adjust_saturation(color, 1.02)
        else:
            source = accent_pool[idx % len(accent_pool)]
            if cycle == 0:
                color = source
            else:
                color = _shift_hue(source, random.choice([0.03, -0.03, 0.06, -0.06]))
                color = _adjust_lightness(color, random.choice([0.02, -0.02, 0.05, -0.05]))
                color = _adjust_saturation(color, 1.03)

        if color_mode != "random" and random_tail and random.random() < random_tail:
            color = _sample_random_series_color(theme, palette["face"], chart_kind, avoid=series_colors)
        if theme in {"mono", "slate", "graphite"} and color_mode not in {"chromatic", "expanded", "random"}:
            color = _adjust_saturation(color, 0.92)
        series_colors.append(color)

    if series_count == 1 and color_mode not in {"chromatic", "expanded"}:
        series_colors[0] = _adjust_saturation(series_colors[0], 1.12)
        series_colors[0] = _adjust_lightness(series_colors[0], 0.02 if theme != "dark" else 0.06)
    return series_colors


def human_round(value: float) -> float | int:
    if value == 0:
        return 0

    abs_value = abs(value)
    if abs_value >= 1000:
        step = random.choice([1, 2, 5, 10, 20, 50, 100])
    elif abs_value >= 100:
        step = random.choice([1, 2, 5, 10])
    elif abs_value >= 10:
        step = random.choice([0.1, 0.2, 0.5, 1, 2])
    elif abs_value >= 1:
        step = random.choice([0.01, 0.05, 0.1, 0.2, 0.5])
    else:
        step = random.choice([0.001, 0.005, 0.01, 0.02])

    rounded = round(value / step) * step
    if step >= 1 and random.random() < 0.8:
        return int(round(rounded))
    if step < 1:
        decimals = max(0, int(round(-math.log10(step))))
        return round(rounded, decimals)
    return round(rounded, 0)


def sample_word() -> str:
    words = load_words()
    return random.choice(words)


def sample_phrase(min_words: int = 1, max_words: int = 3) -> str:
    count = random.randint(min_words, max_words)
    return " ".join(sample_word().capitalize() for _ in range(count))


def sample_label(kind: str | None = None) -> str:
    if kind is None:
        kind = choose_weighted(
            ["word", "phrase", "year", "quarter", "month", "hybrid", "numeric", "code", "compound", "abbr", "slug", "ordinal", "paired"],
            [0.19, 0.16, 0.09, 0.08, 0.09, 0.13, 0.06, 0.07, 0.07, 0.05, 0.04, 0.02, 0.05],
        )

    if kind == "word":
        word = sample_word()
        return word.capitalize() if random.random() < 0.45 else word
    if kind == "phrase":
        return sample_phrase(2, 4)
    if kind == "year":
        return str(random.randint(2016, 2026))
    if kind == "quarter":
        return f"{random.choice(QUARTERS)} {random.randint(2019, 2026)}"
    if kind == "month":
        month = random.choice(MONTHS)
        if random.random() < 0.5:
            return month
        return f"{month}-{random.randint(19, 26):02d}"
    if kind == "hybrid":
        return f"{sample_word().capitalize()} {random.randint(1, 99)}"
    if kind == "numeric":
        v = random.choice([random.randint(0, 99), random.uniform(0, 99), random.uniform(100, 999)])
        return str(human_round(v))
    if kind == "code":
        return f"{random.choice(SERIES_TAGS)}{random.randint(1, 99)}"
    if kind == "compound":
        left = sample_word().capitalize()
        right = sample_word().capitalize()
        return f"{left}-{right}" if random.random() < 0.55 else f"{left} / {right}"
    if kind == "abbr":
        parts = [sample_word() for _ in range(random.randint(2, 4))]
        return "".join(part[0].upper() for part in parts if part)
    if kind == "slug":
        parts = [sample_word().lower() for _ in range(random.randint(2, 3))]
        sep = random.choice(["-", "_"])
        suffix = str(random.randint(1, 99)) if random.random() < 0.35 else ""
        return sep.join(parts) + suffix
    if kind == "ordinal":
        value = random.randint(1, 24)
        suffix = "th" if 10 <= value % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")
        return f"{value}{suffix}"
    if kind == "paired":
        left = sample_word().capitalize()
        right = sample_word().capitalize()
        return f"{left} {random.choice(['vs', '&', 'and'])} {right}"
    return sample_word()


def sample_series_name(index: int) -> str:
    pool = [
        f"Series {index + 1}",
        SERIES_TAGS[index % len(SERIES_TAGS)],
        f"{sample_word().capitalize()} {index + 1}",
        f"{sample_word().capitalize()}",
        f"{sample_word().capitalize()}-{sample_word().capitalize()}",
        f"{sample_word().capitalize()} / {sample_word().capitalize()}",
        f"{sample_word().upper()}_{index + 1}",
        f"Group {index + 1}",
        f"Batch {index + 1}",
        f"Run {index + 1}",
        f"Trial {index + 1}",
        f"Layer {index + 1}",
    ]
    return random.choice(pool)


def sample_title(chart_kind: str | None = None) -> str:
    if chart_kind == "scatter":
        patterns = ["short", "paired", "phrase", "temporal", "code"]
        weights = [0.26, 0.22, 0.22, 0.16, 0.14]
    elif chart_kind == "line":
        patterns = ["phrase", "temporal", "paired", "trend", "short"]
        weights = [0.30, 0.18, 0.16, 0.20, 0.16]
    elif chart_kind and chart_kind.startswith("bar"):
        patterns = ["short", "phrase", "paired", "temporal", "compact"]
        weights = [0.25, 0.28, 0.18, 0.12, 0.17]
    else:
        patterns = ["phrase", "paired", "short", "temporal", "code"]
        weights = [0.28, 0.22, 0.22, 0.16, 0.12]

    pattern = choose_weighted(patterns, weights)
    if pattern == "short":
        return sample_label(kind=choose_weighted(["word", "hybrid", "abbr"], [0.62, 0.25, 0.13])).capitalize()
    if pattern == "phrase":
        return " ".join(sample_label(kind="word").capitalize() for _ in range(random.randint(2, 4)))
    if pattern == "paired":
        left = sample_label(kind=choose_weighted(["word", "phrase", "abbr"], [0.45, 0.35, 0.20]))
        right = sample_label(kind=choose_weighted(["word", "phrase", "abbr"], [0.45, 0.35, 0.20]))
        return f"{left.capitalize()} {random.choice(['/', 'vs', '&'])} {right.capitalize()}"
    if pattern == "temporal":
        return random.choice(
            [
                f"{random.randint(2016, 2026)}",
                f"{random.choice(MONTHS)} {random.randint(2018, 2026)}",
                f"{random.choice(QUARTERS)} {random.randint(2018, 2026)}",
                f"{random.randint(2018, 2026)}-{random.randint(18, 26):02d}",
            ]
        )
    if pattern == "code":
        return f"{sample_label('abbr')} {random.randint(1, 99)}"
    if pattern == "trend":
        head = sample_label(kind=choose_weighted(["word", "phrase"], [0.72, 0.28])).capitalize()
        tail = random.choice(["Trend", "Profile", "Shift", "Pattern", "View"])
        return f"{head} {tail}"
    if pattern == "compact":
        return f"{sample_label(kind=choose_weighted(['word', 'code', 'hybrid'], [0.48, 0.34, 0.18])).capitalize()} {random.choice(['I', 'II', 'III', 'IV'])}"
    return sample_phrase(1, 3)


def sample_axis_title(axis: str, chart_kind: str) -> str | None:
    if random.random() < 0.12:
        return None

    if axis == "x":
        options = [
            "Time",
            "Index",
            "Category",
            "Year",
            "Month",
            "Batch",
            "Condition",
            "Iteration",
            "Phase",
            "Window",
            "Segment",
            "Sample",
            "Region",
            "Scenario",
            "Group",
            "Lane",
            "Step",
            "Feature",
            "Channel",
            "Bin",
            "Bucket",
            "Class",
            "Type",
            "Band",
            "Stage",
        ]
    else:
        options = [
            "Value",
            "Count",
            "Score",
            "Rate",
            "Throughput",
            "Latency",
            "Magnitude",
            "Frequency",
            "Volume",
            "Intensity",
            "Error",
            "Gap",
            "Load",
            "Demand",
            "Density",
            "Change",
            "Spread",
            "Signal",
            "Target",
            "Baseline",
            "Share",
            "Utilization",
            "Revenue",
            "Units",
            "Score",
        ]

    base = random.choice(options)
    unit = random.choice(UNITS)
    if chart_kind == "scatter" and axis == "y" and random.random() < 0.35:
        unit = random.choice([" (ms)", " (px)", " (dB)", " (%)", ""])
    if chart_kind.startswith("bar") and axis == "y" and random.random() < 0.35:
        unit = random.choice([" (k)", " (%)", " (USD)", ""])
    return f"{base}{unit}".strip()


def sample_profile(chart_kind: str, series_count: int = 1) -> str:
    if chart_kind == "scatter":
        profiles = [
            "chromatic",
            "dense_scatter_family",
            "colorful_analytic",
            "publication_clean",
            "dashboard_dense",
            "presentation_emphasis",
            "monochrome_minimal",
            "editorial",
            "compact_report",
            "dark_contrast",
        ]
        weights = [0.11, 0.18, 0.18, 0.10, 0.12, 0.08, 0.05, 0.07, 0.04, 0.07]
        if series_count >= 3:
            weights = [0.14, 0.19, 0.17, 0.08, 0.12, 0.07, 0.04, 0.07, 0.03, 0.09]
    elif chart_kind == "line":
        profiles = ["chromatic", "publication_clean", "colorful_analytic", "presentation_emphasis", "dashboard_dense", "monochrome_minimal", "editorial", "compact_report", "dark_contrast"]
        weights = [0.10, 0.12, 0.19, 0.13, 0.15, 0.05, 0.09, 0.04, 0.13]
        if series_count >= 3:
            weights = [0.12, 0.11, 0.20, 0.13, 0.15, 0.05, 0.09, 0.04, 0.11]
    elif chart_kind.startswith("bar"):
        profiles = ["chromatic", "publication_clean", "colorful_analytic", "dashboard_dense", "presentation_emphasis", "monochrome_minimal", "editorial", "compact_report", "dark_contrast"]
        weights = [0.09, 0.12, 0.18, 0.15, 0.14, 0.06, 0.11, 0.04, 0.11]
        if series_count >= 4:
            weights = [0.11, 0.11, 0.18, 0.15, 0.13, 0.06, 0.11, 0.04, 0.11]
        elif series_count == 1:
            weights = [0.14, 0.13, 0.11, 0.12, 0.14, 0.08, 0.10, 0.04, 0.14]
    else:
        profiles = ["chromatic", "publication_clean", "colorful_analytic", "presentation_emphasis", "dashboard_dense", "monochrome_minimal", "editorial", "compact_report", "dark_contrast"]
        weights = [0.10, 0.12, 0.18, 0.14, 0.14, 0.06, 0.10, 0.04, 0.12]
    return choose_weighted(profiles, weights)


def _palette_choices(profile: str | None, series_count: int = 1) -> tuple[list[str], list[float]]:
    if profile == "chromatic":
        if series_count <= 1:
            return (
                ["aurora", "coral", "mint", "opal", "vibrant", "midnight", "graphite", "glacier", "sunset", "citrus", "royal", "berry", "lagoon"],
                [0.15, 0.13, 0.13, 0.10, 0.10, 0.08, 0.08, 0.08, 0.08, 0.05, 0.04, 0.03, 0.03],
            )
        return (
            ["aurora", "coral", "mint", "opal", "vibrant", "midnight", "graphite", "glacier", "sunset", "citrus", "royal", "berry", "lagoon"],
            [0.14, 0.12, 0.12, 0.10, 0.10, 0.09, 0.08, 0.08, 0.08, 0.05, 0.04, 0.04, 0.04],
        )
    if profile == "publication_clean":
        if series_count <= 1:
            return (
                ["paper", "paper2", "earth", "sunset", "retro", "desert", "warm", "muted", "mono", "cool", "vibrant", "forest", "royal", "lagoon", "berry", "dark", "pastel", "studio", "aurora", "coral", "mint", "opal"],
                [0.12, 0.11, 0.11, 0.08, 0.07, 0.07, 0.06, 0.06, 0.05, 0.05, 0.04, 0.04, 0.03, 0.03, 0.03, 0.02, 0.02, 0.01, 0.01, 0.01, 0.01, 0.01],
            )
        return (
            ["paper", "paper2", "studio", "earth", "cool", "muted", "vibrant", "forest", "royal", "warm", "pastel", "sunset", "berry", "lagoon", "desert", "retro", "mono", "dark", "aurora", "coral", "mint", "opal"],
            [0.12, 0.10, 0.09, 0.08, 0.08, 0.07, 0.08, 0.08, 0.07, 0.05, 0.05, 0.05, 0.04, 0.04, 0.03, 0.03, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01],
        )
    if profile == "colorful_analytic":
        if series_count <= 1:
            return (
                ["aurora", "coral", "mint", "opal", "vibrant", "royal", "glacier", "citrus", "berry", "sunset", "forest", "lagoon", "studio", "paper2", "pastel", "dark"],
                [0.16, 0.12, 0.12, 0.10, 0.10, 0.09, 0.08, 0.08, 0.06, 0.06, 0.04, 0.03, 0.02, 0.01, 0.02, 0.01],
            )
        return (
            ["aurora", "coral", "mint", "opal", "vibrant", "royal", "glacier", "citrus", "berry", "sunset", "forest", "lagoon", "studio", "paper2", "pastel", "dark"],
            [0.15, 0.11, 0.11, 0.09, 0.10, 0.09, 0.08, 0.08, 0.06, 0.06, 0.05, 0.04, 0.02, 0.01, 0.03, 0.02],
        )
    if profile == "dashboard_dense":
        if series_count <= 1:
            return (
                ["paper2", "earth", "retro", "sunset", "desert", "berry", "cool", "forest", "vibrant", "royal", "lagoon", "pastel", "studio", "muted", "mono", "warm", "dark", "paper", "aurora", "coral", "mint", "opal"],
                [0.11, 0.11, 0.09, 0.08, 0.08, 0.08, 0.08, 0.08, 0.08, 0.07, 0.05, 0.04, 0.04, 0.03, 0.02, 0.01, 0.01, 0.02, 0.01, 0.01, 0.01, 0.01],
            )
        return (
            ["cool", "vibrant", "royal", "forest", "studio", "lagoon", "berry", "sunset", "paper2", "paper", "pastel", "earth", "retro", "desert", "muted", "mono", "warm", "dark", "aurora", "coral", "mint", "opal"],
            [0.11, 0.11, 0.10, 0.09, 0.09, 0.09, 0.08, 0.07, 0.06, 0.06, 0.05, 0.04, 0.04, 0.03, 0.01, 0.01, 0.01, 0.01, 0.02, 0.02, 0.01, 0.01],
        )
    if profile == "presentation_emphasis":
        if series_count <= 1:
            return (
                ["sunset", "berry", "retro", "paper2", "earth", "desert", "warm", "vibrant", "lagoon", "forest", "royal", "pastel", "studio", "cool", "mono", "muted", "dark", "paper"],
                [0.14, 0.12, 0.10, 0.10, 0.09, 0.09, 0.08, 0.08, 0.07, 0.06, 0.05, 0.04, 0.03, 0.02, 0.01, 0.01, 0.01, 0.0],
            )
        return (
            ["vibrant", "royal", "sunset", "forest", "studio", "berry", "lagoon", "paper2", "cool", "earth", "pastel", "warm", "retro", "desert", "dark", "paper", "mono", "muted"],
            [0.13, 0.12, 0.12, 0.10, 0.09, 0.09, 0.08, 0.08, 0.06, 0.06, 0.05, 0.04, 0.03, 0.03, 0.01, 0.01, 0.01, 0.0],
        )
    if profile == "monochrome_minimal":
        return (
            ["muted", "mono", "paper", "paper2", "dark", "earth", "studio"],
            [0.28, 0.26, 0.16, 0.12, 0.10, 0.05, 0.03],
        )
    if profile == "editorial":
        if series_count <= 1:
            return (
                ["paper", "earth", "retro", "sunset", "sage", "ember", "forest", "vibrant", "citrus", "paper2", "glacier", "slate", "indigo", "dark", "mono"],
                [0.16, 0.14, 0.12, 0.11, 0.09, 0.08, 0.08, 0.08, 0.07, 0.06, 0.04, 0.03, 0.02, 0.01, 0.01],
            )
        return (
            ["paper", "earth", "retro", "sunset", "sage", "ember", "forest", "vibrant", "citrus", "paper2", "glacier", "slate", "indigo", "dark", "mono"],
            [0.15, 0.13, 0.11, 0.10, 0.09, 0.09, 0.08, 0.08, 0.07, 0.07, 0.04, 0.03, 0.03, 0.01, 0.01],
        )
    if profile == "compact_report":
        if series_count <= 1:
            return (
                ["mono", "slate", "muted", "paper", "paper2", "cool", "glacier", "indigo", "dark"],
                [0.23, 0.19, 0.16, 0.14, 0.11, 0.08, 0.06, 0.02, 0.01],
            )
        return (
            ["mono", "slate", "muted", "paper", "paper2", "cool", "glacier", "indigo", "dark"],
            [0.22, 0.18, 0.16, 0.13, 0.11, 0.09, 0.06, 0.03, 0.02],
        )
    if profile == "dark_contrast":
        if series_count <= 1:
            return (
                ["midnight", "dark", "indigo", "slate", "lagoon", "royal", "ember", "berry", "forest", "glacier", "mono", "aurora", "coral"],
                [0.16, 0.16, 0.12, 0.10, 0.10, 0.10, 0.08, 0.07, 0.06, 0.05, 0.03, 0.01, 0.01],
            )
        return (
            ["midnight", "dark", "indigo", "slate", "lagoon", "royal", "ember", "berry", "forest", "glacier", "mono", "aurora", "coral"],
            [0.15, 0.15, 0.12, 0.10, 0.10, 0.09, 0.08, 0.08, 0.06, 0.05, 0.02, 0.01, 0.01],
        )
    if profile == "dense_scatter_family":
        if series_count <= 1:
            return (
                ["aurora", "coral", "mint", "opal", "vibrant", "cool", "forest", "royal", "sunset", "berry", "lagoon", "studio", "pastel", "earth", "retro", "dark", "paper2", "warm", "desert", "muted", "mono", "paper"],
                [0.12, 0.10, 0.10, 0.09, 0.10, 0.08, 0.08, 0.08, 0.07, 0.07, 0.07, 0.05, 0.05, 0.04, 0.04, 0.02, 0.02, 0.01, 0.01, 0.01, 0.01, 0.01],
            )
        return (
            ["aurora", "coral", "mint", "opal", "vibrant", "cool", "forest", "royal", "studio", "pastel", "sunset", "lagoon", "berry", "paper2", "earth", "retro", "dark", "warm", "desert", "muted", "mono", "paper"],
            [0.11, 0.10, 0.09, 0.09, 0.09, 0.07, 0.07, 0.07, 0.06, 0.07, 0.07, 0.07, 0.07, 0.05, 0.04, 0.04, 0.02, 0.01, 0.01, 0.01, 0.01, 0.0],
        )
    if series_count <= 1:
        return (
            ["paper", "paper2", "earth", "sunset", "retro", "desert", "warm", "muted", "mono", "cool", "vibrant", "forest", "royal", "lagoon", "berry", "dark", "pastel", "studio", "aurora", "coral", "mint", "opal", "midnight", "graphite"],
            [0.10, 0.09, 0.09, 0.08, 0.07, 0.07, 0.06, 0.06, 0.05, 0.06, 0.05, 0.05, 0.04, 0.04, 0.04, 0.02, 0.02, 0.02, 0.02, 0.02, 0.02, 0.02, 0.02, 0.02],
        )
    if series_count >= 4:
        return (
            ["aurora", "coral", "mint", "opal", "vibrant", "forest", "royal", "sunset", "lagoon", "berry", "studio", "paper2", "pastel", "cool", "earth", "retro", "warm", "desert", "muted", "mono", "dark", "midnight", "graphite"],
            [0.11, 0.10, 0.10, 0.09, 0.10, 0.08, 0.08, 0.08, 0.07, 0.07, 0.06, 0.06, 0.05, 0.04, 0.04, 0.03, 0.02, 0.02, 0.01, 0.01, 0.01, 0.01, 0.0],
        )
    return (
        ["paper", "cool", "muted", "vibrant", "forest", "royal", "studio", "earth", "warm", "dark", "paper2", "pastel", "sunset", "berry", "lagoon", "desert", "retro", "mono", "aurora", "coral", "mint", "opal", "midnight", "graphite"],
        [0.08, 0.08, 0.07, 0.09, 0.08, 0.08, 0.08, 0.07, 0.05, 0.05, 0.06, 0.05, 0.05, 0.05, 0.04, 0.04, 0.03, 0.02, 0.04, 0.04, 0.04, 0.04, 0.03, 0.02],
    )

def sample_palette(chart_kind: str, profile: str | None = None, series_count: int = 1) -> dict:
    themes, weights = _palette_choices(profile, series_count=series_count)
    theme = choose_weighted(themes, weights)
    palette = dict(PALETTES[theme])
    palette["theme"] = theme
    color_mode = _series_color_mode(chart_kind, series_count, profile or "publication_clean")
    palette["color_mode"] = color_mode
    palette["series"] = build_series_colors(
        palette,
        series_count=series_count,
        chart_kind=chart_kind,
        profile=profile or "publication_clean",
        color_mode=color_mode,
    )
    return palette


def sample_canvas(chart_kind: str, series_count: int = 1) -> dict:
    profile = sample_profile(chart_kind, series_count)
    palette = sample_palette(chart_kind, profile=profile, series_count=series_count)
    font_dir = resolve_existing(FONT_DIR_CANDIDATES)
    font_pool = load_font_pool(font_dir)

    if chart_kind == "barh":
        figsize = (random.uniform(6.8, 10.2), random.uniform(4.4, 7.4))
    elif chart_kind == "barv":
        figsize = (random.uniform(6.0, 9.2), random.uniform(4.8, 7.8))
    elif chart_kind == "line":
        figsize = (random.uniform(6.2, 10.4), random.uniform(4.2, 7.4))
    else:
        figsize = (random.uniform(5.6, 9.2), random.uniform(5.0, 8.5))

    if profile == "dashboard_dense":
        figsize = (figsize[0] * 0.92, figsize[1] * 0.92)
    elif profile == "presentation_emphasis":
        figsize = (figsize[0] * 1.06, figsize[1] * 1.06)
    elif profile == "monochrome_minimal":
        figsize = (figsize[0] * 0.98, figsize[1] * 0.98)
    elif profile == "dense_scatter_family":
        figsize = (figsize[0] * 1.02, figsize[1] * 1.02)

    dense = series_count >= 4
    dpi = choose_weighted([180, 200, 220, 240, 300], [0.18, 0.24, 0.22, 0.20, 0.16])
    legend_ncol = 1
    if series_count == 2:
        legend_ncol = choose_weighted([1, 2], [0.78, 0.22])
    elif series_count == 3:
        legend_ncol = choose_weighted([1, 2], [0.68, 0.32])
    elif series_count == 4:
        legend_ncol = choose_weighted([1, 2], [0.58, 0.42])
    elif series_count >= 5:
        legend_ncol = choose_weighted([1, 2, 3], [0.42, 0.42, 0.16])

    style = {
        "palette": palette,
        "font_path": random.choice(font_pool),
        "figsize": figsize,
        "dpi": dpi,
        "profile": profile,
        "color_mode": palette.get("color_mode"),
        "facecolor": palette["face"],
        "axes_face": palette["axes"],
        "text_color": palette["text"],
        "grid_color": palette["grid"],
        "series_colors": palette["series"],
        "title_size": random.randint(11, 24) if not dense else random.randint(10, 20),
        "label_size": random.randint(9, 16),
        "tick_size": random.randint(8, 13),
        "legend_size": random.randint(8, 12),
        "label_pad": random.uniform(3.2, 7.5) if chart_kind != "scatter" else random.uniform(2.6, 6.0),
        "tick_pad": random.uniform(1.8, 4.5),
        "grid_visible": random.random() < (0.70 if chart_kind in {"line", "scatter"} else 0.55),
        "grid_axis": random.choice(["x", "y", "both"]),
        "grid_style": random.choice(["-", "--", ":"]),
        "grid_width": random.uniform(0.5, 1.2),
        "grid_alpha": random.uniform(0.25, 0.6),
        "legend_loc": random.choice(["best", "upper right", "upper left", "center left", "lower right"]),
        "legend_outside": random.random() < (0.18 if series_count >= 4 else 0.12),
        "legend_frame": random.random() < 0.75,
        "legend_shadow": random.random() < 0.12,
        "legend_ncol": legend_ncol,
        "legend_borderpad": random.uniform(0.25, 0.75),
        "legend_borderaxespad": random.uniform(0.0, 0.35),
        "legend_handlelength": random.uniform(1.0, 2.0),
        "legend_handletextpad": random.uniform(0.4, 0.9),
        "legend_columnspacing": random.uniform(0.8, 1.6),
        "legend_labelspacing": random.uniform(0.2, 0.55),
        "legend_framealpha": random.uniform(0.78, 0.96),
        "spine_visible": random.random() < 0.84,
        "spine_width": random.uniform(0.8, 1.8),
        "spine_color": palette["text"],
        "title_pad": random.uniform(8, 22),
    }

    if style["legend_outside"]:
        style["legend_loc"] = random.choice(["upper left", "center left", "lower left"])
        style["legend_bbox_to_anchor"] = (1.02, 1.0)
        style["layout_rect"] = (0.0, 0.0, 0.84, 1.0)
    else:
        style["legend_bbox_to_anchor"] = None
        style["layout_rect"] = None

    if profile == "dashboard_dense":
        style["title_size"] = max(10, style["title_size"] - 2)
        style["label_size"] = max(8, style["label_size"] - 1)
        style["tick_size"] = max(7, style["tick_size"] - 1)
        style["legend_size"] = max(7, style["legend_size"] - 1)
        style["label_pad"] *= 0.86
        style["tick_pad"] *= 0.82
        style["grid_visible"] = random.random() < (0.78 if chart_kind in {"line", "scatter"} else 0.66)
        style["legend_outside"] = random.random() < (0.28 if series_count >= 3 else 0.16)
        style["legend_frame"] = random.random() < 0.72
        style["legend_shadow"] = random.random() < 0.06
        if series_count >= 3:
            style["legend_ncol"] = choose_weighted([1, 2, 3], [0.28, 0.48, 0.24])
    elif profile == "presentation_emphasis":
        style["title_size"] = min(28, style["title_size"] + 2)
        style["label_size"] = min(18, style["label_size"] + 1)
        style["tick_size"] = min(14, style["tick_size"] + 1)
        style["legend_size"] = min(13, style["legend_size"] + 1)
        style["label_pad"] *= 1.08
        style["tick_pad"] *= 1.05
        style["title_pad"] *= 1.12
        style["grid_visible"] = random.random() < (0.66 if chart_kind in {"line", "scatter"} else 0.58)
        style["legend_outside"] = random.random() < (0.12 if series_count >= 3 else 0.08)
        style["legend_frame"] = random.random() < 0.82
        style["legend_shadow"] = random.random() < 0.10
    elif profile == "monochrome_minimal":
        style["grid_visible"] = random.random() < (0.48 if chart_kind in {"line", "scatter"} else 0.40)
        style["grid_alpha"] *= 0.78
        style["legend_frame"] = random.random() < 0.60
        style["legend_shadow"] = False
        style["legend_outside"] = random.random() < 0.08
        style["title_size"] = max(10, style["title_size"] - 1)
        style["tick_size"] = max(7, style["tick_size"] - 1)
    elif profile == "editorial":
        style["title_size"] = min(28, style["title_size"] + 1)
        style["label_size"] = min(18, style["label_size"] + 1)
        style["tick_size"] = min(14, style["tick_size"] + 1)
        style["legend_size"] = min(13, style["legend_size"] + 1)
        style["grid_visible"] = random.random() < (0.62 if chart_kind in {"line", "scatter"} else 0.54)
        style["legend_outside"] = random.random() < (0.14 if series_count >= 3 else 0.10)
        style["legend_frame"] = random.random() < 0.82
        style["legend_shadow"] = random.random() < 0.08
        style["grid_alpha"] *= 0.9
    elif profile == "compact_report":
        style["title_size"] = max(9, style["title_size"] - 2)
        style["label_size"] = max(8, style["label_size"] - 1)
        style["tick_size"] = max(7, style["tick_size"] - 1)
        style["legend_size"] = max(7, style["legend_size"] - 1)
        style["label_pad"] *= 0.82
        style["tick_pad"] *= 0.8
        style["grid_visible"] = random.random() < (0.56 if chart_kind in {"line", "scatter"} else 0.46)
        style["grid_style"] = random.choice(["--", ":"])
        style["legend_outside"] = random.random() < (0.28 if series_count >= 3 else 0.18)
        style["legend_frame"] = random.random() < 0.70
        style["legend_shadow"] = False
    elif profile == "dark_contrast":
        style["grid_visible"] = random.random() < (0.72 if chart_kind in {"line", "scatter"} else 0.60)
        style["grid_alpha"] = min(0.65, style["grid_alpha"] * 1.12)
        style["legend_frame"] = random.random() < 0.88
        style["legend_shadow"] = random.random() < 0.08
        style["legend_outside"] = random.random() < (0.10 if series_count >= 3 else 0.06)
        style["spine_width"] = min(2.2, style["spine_width"] + 0.2)
        style["title_size"] = min(26, style["title_size"] + 1)
        style["label_size"] = min(17, style["label_size"] + 1)
        style["tick_size"] = min(13, style["tick_size"] + 1)
    elif profile == "dense_scatter_family":
        style["title_size"] = max(10, style["title_size"] - 1)
        style["label_size"] = max(8, style["label_size"] - 1)
        style["tick_size"] = max(7, style["tick_size"] - 1)
        style["label_pad"] *= 0.92
        style["tick_pad"] *= 0.90
        style["grid_visible"] = random.random() < 0.84
        style["legend_outside"] = random.random() < (0.18 if series_count >= 3 else 0.10)
        style["legend_frame"] = random.random() < 0.76
        style["legend_shadow"] = random.random() < 0.05
    elif profile == "colorful_analytic":
        style["grid_visible"] = random.random() < (0.74 if chart_kind in {"line", "scatter"} else 0.62)
        style["legend_frame"] = random.random() < 0.80
        style["legend_outside"] = random.random() < (0.16 if series_count >= 4 else 0.10)

    if style["legend_outside"]:
        style["legend_loc"] = random.choice(["upper left", "center left", "lower left"])
        style["legend_bbox_to_anchor"] = (1.02, 1.0)
        style["layout_rect"] = (0.0, 0.0, 0.84, 1.0)
    else:
        style["legend_bbox_to_anchor"] = None
        style["layout_rect"] = None

    return style


def legend_kwargs(style: dict) -> dict:
    kwargs = {
        "loc": style["legend_loc"],
        "prop": {"size": style["legend_size"]},
        "frameon": style["legend_frame"],
        "shadow": style["legend_shadow"],
        "ncol": style.get("legend_ncol", 1),
        "borderpad": style.get("legend_borderpad", 0.35),
        "handlelength": style.get("legend_handlelength", 1.5),
        "handletextpad": style.get("legend_handletextpad", 0.5),
        "columnspacing": style.get("legend_columnspacing", 1.0),
        "labelspacing": style.get("legend_labelspacing", 0.3),
        "framealpha": style.get("legend_framealpha", 0.9),
    }
    if style.get("legend_outside") and style.get("legend_bbox_to_anchor") is not None:
        kwargs["bbox_to_anchor"] = style["legend_bbox_to_anchor"]
        kwargs["borderaxespad"] = style.get("legend_borderaxespad", 0.2)
    return kwargs


def tick_label_bboxes(ax, fig, axis: str = "x"):
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    labels = ax.get_xticklabels() if axis == "x" else ax.get_yticklabels()
    bboxes = []
    for label in labels:
        if not label.get_visible():
            continue
        if not label.get_text():
            continue
        try:
            bbox = label.get_window_extent(renderer=renderer)
        except Exception:
            continue
        bboxes.append(bbox)
    return bboxes


def bboxes_overlap(bboxes) -> bool:
    boxes = sorted(bboxes, key=lambda box: (box.x0, box.y0))
    for prev, curr in zip(boxes, boxes[1:]):
        if prev.overlaps(curr):
            return True
    return False


def padded_limits(
    values: Iterable[float],
    include_zero: bool = False,
    symmetric: bool = False,
    pad: tuple[float, float] = (0.06, 0.15),
) -> tuple[float, float]:
    clean = [float(v) for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))]
    if not clean:
        return (-1.0, 1.0)

    lo = min(clean)
    hi = max(clean)
    span = hi - lo
    if span == 0:
        span = max(abs(lo), abs(hi), 1.0)
    margin = span * random.uniform(*pad)
    lo -= margin
    hi += margin

    if include_zero:
        lo = min(lo, 0.0)
        hi = max(hi, 0.0)

    if symmetric:
        bound = max(abs(lo), abs(hi))
        lo = -bound
        hi = bound

    return lo, hi


def series_color(series_colors: list[str], index: int) -> str:
    if not series_colors:
        return "#1f77b4"
    return series_colors[index % len(series_colors)]


def maybe_int_or_float(value: float) -> float | int:
    if abs(value - round(value)) < 1e-10 and random.random() < 0.8:
        return int(round(value))
    return value
