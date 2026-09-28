#!/usr/bin/env python3
"""
Download ESSENTIAL map tiles for offline use (reduced set).

This downloads only zoom levels 10-14 for Palpagos and 10-12 for World Tree,
which is sufficient for normal map viewing while reducing download size to ~50-100 MB total.

For full quality, run download_map_tiles.py instead.
"""

import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Palpagos: z10-14 only (instead of z8-16)
PALPAGOS_BASE = "https://tiles.mapgenie.io/games/palworld/1-0/default-v1"
PALPAGOS_REFERER = "https://mapgenie.io/palworld/maps/palpagos-islands"
PALPAGOS_ZOOM_LEVELS = [10, 11, 12, 13, 14]
PALPAGOS_DISK = PROJECT_ROOT / ".cache" / "map-tiles" / "mg"

# World Tree: z10-12 only (instead of z8-14)
WT_BASE = "https://tiles.mapgenie.io/games/palworld/world-tree/default-v1"
WT_REFERER = "https://mapgenie.io/palworld/maps/world-tree"
WT_ZOOM_LEVELS = [10, 11, 12]
WT_DISK = PROJECT_ROOT / ".cache" / "map-tiles-wt"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0.0.0 Safari/537.36"


def blank_tile() -> bytes:
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


def fetch(url: str, referer: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Referer": referer})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read()
    except:
        return blank_tile()


def download_tile(base: str, ref: str, z: int, x: int, y: int, disk: Path) -> int:
    path = disk / f"z{z}" / f"{x}_{y}.jpg"
    if path.exists() and path.stat().st_size > 64:
        return 0  # already cached
    data = fetch(f"{base}/{z}/{x}/{y}.jpg", ref)
    if len(data) < 64:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return len(data)


def download_zoom(base: str, ref: str, z: int, disk: Path, name: str):
    n = 1 << z
    total = downloaded = total_bytes = 0
    print(f"  [{name}] z{z}: {n}×{n} tiles...", end="", flush=True)
    for y in range(n):
        for x in range(n):
            total += 1
            size = download_tile(base, ref, z, x, y, disk)
            if size > 0:
                downloaded += 1
                total_bytes += size
            if total % 500 == 0:
                print(".", end="", flush=True)
    mb = total_bytes / 1_048_576
    print(f" {downloaded}/{total} ({mb:.1f} MB)")
    time.sleep(0.5)


def main():
    print("Downloading essential tiles (reduced set for faster setup)...\n")
    
    for z in PALPAGOS_ZOOM_LEVELS:
        download_zoom(PALPAGOS_BASE, PALPAGOS_REFERER, z, PALPAGOS_DISK, "Palpagos")
    
    for z in WT_ZOOM_LEVELS:
        download_zoom(WT_BASE, WT_REFERER, z, WT_DISK, "WorldTree")
    
    print("\n✓ Essential tiles downloaded. Maps are now offline-ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
