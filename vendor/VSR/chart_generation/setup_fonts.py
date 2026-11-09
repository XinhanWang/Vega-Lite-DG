from __future__ import annotations

import argparse

from common import FONT_DIR, REQUIRED_FONT_FILES, ensure_fonts, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and cache the font bundle used by the chart generation scripts.")
    parser.add_argument("--force", action="store_true", help="Re-download and overwrite existing font files.")
    args = parser.parse_args()

    installed = ensure_fonts(force=args.force)
    write_json(
        FONT_DIR / "fonts_manifest.json",
        {
            "font_dir": str(FONT_DIR),
            "count": len(installed),
            "required_fonts": REQUIRED_FONT_FILES,
            "installed_fonts": [path.name for path in installed],
        },
    )

    print(f"Installed {len(installed)} fonts into {FONT_DIR}")


if __name__ == "__main__":
    main()
