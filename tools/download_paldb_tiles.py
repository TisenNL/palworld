#!/usr/bin/env python3
"""
Download the real paldb.cc map tile pyramids (Palpagos Islands + The World Tree)
for fully offline use. Tiles are CRS.Simple (flat, no Mercator), 512px webp,
zoom levels 0-4 (native max zoom on paldb.cc).

Saves to public/map-tiles/<map>/z<zoom>/x<x>y<y>.webp so Vite serves them
statically, no server/internet dependency at runtime.
"""

import urllib.request
import urllib.error
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = PROJECT_ROOT / "public" / "map-tiles"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0.0.0 Safari/537.36"
REFERER = "https://paldb.cc/en/Palpagos_Islands"
CDN_BASE = "https://cdn.paldb.cc"

MAPS = {
    "palpagos": "image/map8/",
    "world-tree": "image/treemap8/",
}

MAX_ZOOM = 4


def fetch(url: str) -> bytes | None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Referer": REFERER})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 404):
            return None
        raise
    except urllib.error.URLError:
        return None


def download_map(name: str, image_map_dir: str) -> None:
    out_root = OUT_DIR / name
    total = downloaded = skipped = 0
    for z in range(MAX_ZOOM + 1):
        n = 1 << z
        zdir = out_root / f"z{z}"
        for x in range(n):
            for y in range(n):
                total += 1
                dest = zdir / f"x{x}y{y}.webp"
                if dest.exists() and dest.stat().st_size > 0:
                    skipped += 1
                    continue
                data = fetch(f"{CDN_BASE}/{image_map_dir}z{z}x{x}y{y}.webp")
                if data is None:
                    continue
                zdir.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
                downloaded += 1
        print(f"[{name}] z{z}: {n}x{n} done")
    print(f"[{name}] total={total} downloaded={downloaded} already-cached={skipped}")


def main() -> None:
    for name, image_map_dir in MAPS.items():
        download_map(name, image_map_dir)


if __name__ == "__main__":
    main()
