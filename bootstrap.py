"""Prepare only project-local VSR fonts; never install or mutate global packages."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time
import urllib.request

from native import ROOT, VENDOR, load_common


def setup_fonts(retries=3, timeout=30):
    common = load_common()
    original_download = common._download_font

    def download(url, dest, force=False):
        dest = Path(dest)
        if dest.is_file() and not force:
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        last_error = None
        for attempt in range(retries):
            temp = dest.with_suffix(dest.suffix + ".tmp")
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "VSR-v1-font-bootstrap"})
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    data = response.read()
                if len(data) < 1024 or data[:4] not in (b"OTTO", b"\x00\x01\x00\x00", b"ttcf"):
                    raise ValueError(f"Downloaded font has invalid signature: {dest.name}")
                temp.write_bytes(data)
                temp.replace(dest)
                return
            except Exception as exc:
                last_error = exc
                temp.unlink(missing_ok=True)
                if attempt + 1 < retries:
                    time.sleep(min(2 ** attempt, 8))
        raise RuntimeError(f"Font download failed after {retries} attempts: {url}") from last_error

    try:
        common._download_font = download
        fonts = common.ensure_fonts()
    finally:
        common._download_font = original_download
    from matplotlib.font_manager import FontProperties
    records = []
    for font in fonts:
        records.append({"file": str(font.relative_to(ROOT)), "family": FontProperties(fname=str(font)).get_name(), "sha256": hashlib.sha256(font.read_bytes()).hexdigest(), "bytes": font.stat().st_size})
    manifest = {"vendor": str(VENDOR), "font_count": len(records), "fonts": records}
    (ROOT / "fonts.manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()
    result = setup_fonts(args.retries, args.timeout)
    print(json.dumps({"font_count": result["font_count"], "manifest": str(ROOT / "fonts.manifest.json")}))
