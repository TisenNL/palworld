#!/usr/bin/env python3
"""
Extract full map images from paldb.cc interactive maps.

Downloads the map images directly from:
  - https://paldb.cc/en/Palpagos_Islands
  - https://paldb.cc/en/The_World_Tree

These are saved as single high-resolution images instead of tile pyramids.
"""

import sys
import urllib.request
from pathlib import Path

from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = PROJECT_ROOT / "src" / "assets" / "maps"

# Based on inspection of paldb.cc, the maps are likely served as:
# - Full image overlays on a Leaflet/similar map
# - Or via a tile server at cdn.paldb.cc
# We need to inspect the actual URLs used by the site

MAPS = {
    "palpagos": {
        "page": "https://paldb.cc/en/Palpagos_Islands",
        "name": "Palpagos Islands",
        # URL pattern to be determined by inspecting the page
        "image_url": None,  # Will be extracted
    },
    "world-tree": {
        "page": "https://paldb.cc/en/The_World_Tree",
        "name": "The World Tree",
        "image_url": None,
    },
}

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0.0.0 Safari/537.36"


def fetch_page(url: str) -> str:
    """Fetch HTML page content."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8")


def find_map_url(html: str) -> Optional[str]:
    """
    Extract map image/tile URL from paldb.cc page HTML.
    
    Common patterns:
      - Leaflet.js with TileLayer: L.tileLayer('url/{z}/{x}/{y}.png')
      - Image overlay: L.imageOverlay('url/map.png')
      - CDN URLs: cdn.paldb.cc/image/Map/...
    """
    import re
    
    # Pattern 1: cdn.paldb.cc image URLs
    match = re.search(r'cdn\.paldb\.cc/[^"\']+(?:map|Map)[^"\']+\.(?:png|jpg|webp)', html)
    if match:
        return "https://" + match.group(0)
    
    # Pattern 2: Tile layer URL template
    match = re.search(r'["\']([^"\']*tiles?[^"\']*\{[xyz]\}[^"\']*)["\']', html)
    if match:
        return match.group(1)
    
    # Pattern 3: Image overlay
    match = re.search(r'imageOverlay\(["\']([^"\']+)["\']', html)
    if match:
        return match.group(1)
    
    return None


def download_image(url: str, output_path: Path) -> bool:
    """Download image from URL."""
    print(f"  Downloading: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(data)
            size_mb = len(data) / 1_048_576
            print(f"  ✓ Saved: {output_path.name} ({size_mb:.1f} MB)")
            return True
    except Exception as exc:
        print(f"  ✗ Error: {exc}")
        return False


def main() -> int:
    print("Extracting maps from paldb.cc...")
    print("=" * 70)
    
    for map_id, info in MAPS.items():
        print(f"\n{info['name']}:")
        print(f"  Page: {info['page']}")
        
        # Fetch the page
        try:
            html = fetch_page(info['page'])
        except Exception as exc:
            print(f"  ✗ Failed to fetch page: {exc}")
            continue
        
        # Find map URL
        map_url = find_map_url(html)
        if not map_url:
            print(f"  ✗ Could not find map URL in page HTML")
            print(f"  → Manual inspection required. Save HTML to inspect:")
            html_path = PROJECT_ROOT / ".cache" / f"{map_id}_page.html"
            html_path.parent.mkdir(parents=True, exist_ok=True)
            html_path.write_text(html, encoding="utf-8")
            print(f"     {html_path}")
            continue
        
        print(f"  Found URL: {map_url}")
        
        # Download image
        if "{x}" in map_url or "{y}" in map_url or "{z}" in map_url:
            print(f"  → Tile-based map detected. This requires a tile downloader.")
            print(f"     Use the existing download_map_tiles.py with this URL pattern.")
        else:
            output_path = ASSETS_DIR / f"{map_id}.webp"
            download_image(map_url, output_path)
    
    print(f"\n{'='*70}")
    print("Extraction complete. Check src/assets/maps/")
    print(f"{'='*70}\n")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
