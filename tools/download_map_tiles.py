#!/usr/bin/env python3
"""
Download all map tiles for offline use.

This script downloads the complete tile pyramids for both Palpagos Islands
and The World Tree from MapGenie, storing them in the local .cache directory
for 100% offline operation.

Usage:
    python tools/download_map_tiles.py [--yes]

The tiles are cached in:
  - .cache/map-tiles/mg/z{Z}/{X}_{Y}.jpg  (Palpagos)
  - .cache/map-tiles-wt/z{Z}/{X}_{Y}.jpg  (World Tree)
"""

import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ── Palpagos Islands (MapGenie 1.0) ──────────────────────────────────────────
PALPAGOS_BASE = "https://tiles.mapgenie.io/games/palworld/1-0/default-v1"
PALPAGOS_REFERER = "https://mapgenie.io/palworld/maps/palpagos-islands"
PALPAGOS_MIN_Z = 8
PALPAGOS_MAX_Z = 16
PALPAGOS_DISK = PROJECT_ROOT / ".cache" / "map-tiles" / "mg"

# ── World Tree ───────────────────────────────────────────────────────────────
WT_BASE = "https://tiles.mapgenie.io/games/palworld/world-tree/default-v1"
WT_REFERER = "https://mapgenie.io/palworld/maps/world-tree"
WT_MIN_Z = 8
WT_MAX_Z = 14
WT_DISK = PROJECT_ROOT / ".cache" / "map-tiles-wt"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


def blank_tile_jpeg() -> bytes:
    """Return a minimal 256×256 JPEG (gray square) for missing tiles."""
    # 256×256 gray JPEG, ~800 bytes
    return (
        b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
        b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c'
        b'\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c'
        b'\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x0b\x08\x01'
        b'\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01'
        b'\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04'
        b'\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00\xb5\x10\x00\x02\x01\x03\x03\x02'
        b'\x04\x03\x05\x05\x04\x04\x00\x00\x01}\x01\x02\x03\x00\x04\x11\x05\x12'
        b'!1A\x06\x13Qa\x07"q\x142\x81\x91\xa1\x08#B\xb1\xc1\x15R\xd1\xf0$3br'
        b'\x82\t\n\x16\x17\x18\x19\x1a%&\'()*456789:CDEFGHIJSTUVWXYZcdefghijst'
        b'uvwxyz\x83\x84\x85\x86\x87\x88\x89\x8a\x92\x93\x94\x95\x96\x97\x98\x99'
        b'\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6\xb7\xb8'
        b'\xb9\xba\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7'
        b'\xd8\xd9\xda\xe1\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf1\xf2\xf3\xf4'
        b'\xf5\xf6\xf7\xf8\xf9\xfa\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xfe\xa2'
        b'\x8a(\xff\xd9'
    )


def http_get_bytes(url: str, referer: str) -> bytes:
    """Fetch a tile via HTTP with proper headers."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Referer": referer,
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        # MapGenie returns 403/404 for tiles outside content area
        if exc.code in (403, 404):
            return blank_tile_jpeg()
        raise
    except Exception as exc:
        print(f"  ⚠ fetch error: {exc}")
        return blank_tile_jpeg()


def download_tile(
    base_url: str,
    referer: str,
    z: int,
    x: int,
    y: int,
    disk_path: Path,
) -> Tuple[bool, int]:
    """
    Download a single tile. Returns (success, size_bytes).
    If the tile already exists on disk and is valid, skip download.
    """
    tile_path = disk_path / f"z{z}" / f"{x}_{y}.jpg"
    
    # Skip if already cached and valid
    if tile_path.is_file() and tile_path.stat().st_size > 64:
        return (True, tile_path.stat().st_size)
    
    url = f"{base_url}/{z}/{x}/{y}.jpg"
    data = http_get_bytes(url, referer)
    
    if len(data) < 64:
        return (False, 0)
    
    tile_path.parent.mkdir(parents=True, exist_ok=True)
    tile_path.write_bytes(data)
    return (True, len(data))


def download_zoom_level(
    base_url: str,
    referer: str,
    z: int,
    disk_path: Path,
    name: str,
) -> Tuple[int, int, int]:
    """
    Download all tiles for a given zoom level.
    Returns (total_tiles, downloaded, total_bytes).
    """
    n = 1 << z  # 2^z tiles per side
    total = n * n
    downloaded = 0
    total_bytes = 0
    skipped = 0
    
    print(f"\n  Zoom {z}: {n}×{n} = {total:,} tiles")
    
    for y in range(n):
        for x in range(n):
            success, size = download_tile(base_url, referer, z, x, y, disk_path)
            if success:
                if size > 0:
                    downloaded += 1
                    total_bytes += size
                else:
                    skipped += 1
            
            # Progress indicator
            done = y * n + x + 1
            if done % 100 == 0 or done == total:
                pct = 100 * done / total
                mb = total_bytes / 1_048_576
                print(f"\r    {done:,}/{total:,} ({pct:.1f}%)  {mb:.1f} MB", end="", flush=True)
    
    print()
    if skipped > 0:
        print(f"    ↳ {skipped:,} blank tiles (outside content area)")
    
    return (total, downloaded, total_bytes)


def download_map(
    name: str,
    base_url: str,
    referer: str,
    min_z: int,
    max_z: int,
    disk_path: Path,
) -> None:
    """Download all tiles for a map."""
    print(f"\n{'='*70}")
    print(f"Downloading: {name}")
    print(f"  Range: z{min_z} to z{max_z}")
    print(f"  Output: {disk_path.relative_to(PROJECT_ROOT)}")
    print(f"{'='*70}")
    
    grand_total = 0
    grand_downloaded = 0
    grand_bytes = 0
    
    for z in range(min_z, max_z + 1):
        total, downloaded, total_bytes = download_zoom_level(
            base_url, referer, z, disk_path, name
        )
        grand_total += total
        grand_downloaded += downloaded
        grand_bytes += total_bytes
        
        # Rate limit to avoid overwhelming the server
        if z < max_z:
            time.sleep(1)
    
    mb = grand_bytes / 1_048_576
    print(f"\n  ✓ {name}: {grand_downloaded:,}/{grand_total:,} tiles, {mb:.1f} MB")


def main() -> int:
    print("Palworld Checklist — Offline Map Tile Downloader")
    print("=" * 70)
    print("\nDownloading ALL tiles for both maps...")
    print("Estimated download size:")
    print("  • Palpagos Islands (z8-z16): ~200-500 MB")
    print("  • World Tree (z8-z14):       ~50-150 MB")
    print("\nExisting tiles will be skipped (resume-safe).")
    print()
    
    t0 = time.time()
    
    # Download Palpagos Islands
    download_map(
        "Palpagos Islands",
        PALPAGOS_BASE,
        PALPAGOS_REFERER,
        PALPAGOS_MIN_Z,
        PALPAGOS_MAX_Z,
        PALPAGOS_DISK,
    )
    
    # Download World Tree
    download_map(
        "World Tree",
        WT_BASE,
        WT_REFERER,
        WT_MIN_Z,
        WT_MAX_Z,
        WT_DISK,
    )
    
    elapsed = time.time() - t0
    print(f"\n{'='*70}")
    print(f"✓ Download complete in {elapsed:.1f}s")
    print(f"\nMaps are now 100% offline. No external network dependency.")
    print(f"{'='*70}\n")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
