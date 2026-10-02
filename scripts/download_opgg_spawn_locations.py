"""Download OP.GG Pal and human spawn locations for the interactive map."""

from __future__ import annotations

import concurrent.futures
import json
import re
import urllib.request
from pathlib import Path
from typing import Any

CDN = "https://s-stats-platform-cdn.op.gg"
MAP_URL = "https://op.gg/palworld/map"
REVISION = "2026091501"
OUTPUT = Path("public/opgg-spawn-locations")
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36"
    ),
    "Referer": MAP_URL,
    "Accept": "application/json, */*",
}


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def extract_catalogs() -> dict[str, list[dict[str, Any]]]:
    html = fetch(MAP_URL).decode("utf-8")
    flight_pattern = re.compile(r"self\.__next_f\.push\((\[.*?\])\)</script>")
    decoder = json.JSONDecoder()
    for match in flight_pattern.finditer(html):
        try:
            flight = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        for segment in flight:
            if not isinstance(segment, str) or '"spawnPals":' not in segment:
                continue
            catalogs: dict[str, list[dict[str, Any]]] = {}
            for name in ("spawnPals", "spawnHumans"):
                offset = segment.find(f'"{name}":')
                start = segment.find("[", offset)
                catalogs[name] = decoder.raw_decode(segment[start:])[0]
            return catalogs
    raise RuntimeError("Could not find Pal and human spawn catalogs in the OP.GG map page")


def spawn_url(kind: str, identifier: str) -> str:
    return f"{CDN}/palworld/meta/{kind}/{identifier}.json?v={REVISION}"


def compact_points(data: dict[str, Any]) -> dict[str, list[list[float]]]:
    result: dict[str, list[list[float]]] = {}
    for period in ("day", "night"):
        points = data.get(period)
        if not isinstance(points, list):
            raise ValueError(f"Spawn data has no {period} point list")
        compact: list[list[float]] = []
        for point in points:
            location = point.get("l") if isinstance(point, dict) else None
            if (
                isinstance(location, list)
                and len(location) >= 2
                and isinstance(location[0], (int, float))
                and isinstance(location[1], (int, float))
            ):
                compact.append([location[0], location[1]])
        result[period] = compact
    return result


def download_location(item: dict[str, Any], category: str) -> tuple[Path, bytes]:
    identifier = item.get("id")
    if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", identifier):
        raise ValueError(f"Unsafe or missing spawn ID in {item!r}")
    kind = "spawns" if category == "pals" else "human-spawns"
    source = json.loads(fetch(spawn_url(kind, identifier)))
    payload = json.dumps(compact_points(source), separators=(",", ":")).encode("utf-8")
    return OUTPUT / category / f"{identifier}.json", payload


def main() -> None:
    catalogs = extract_catalogs()
    pals = catalogs["spawnPals"]
    humans = catalogs["spawnHumans"]
    entries = [(item, "pals") for item in pals] + [(item, "humans") for item in humans]

    downloads: list[tuple[Path, bytes]] = []
    failures: list[str] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
        futures = {
            executor.submit(download_location, item, category): (category, item["id"])
            for item, category in entries
        }
        for future in concurrent.futures.as_completed(futures):
            category, identifier = futures[future]
            try:
                downloads.append(future.result())
            except Exception as error:
                failures.append(f"{category}/{identifier}: {error}")

    if failures:
        raise RuntimeError("Failed to download spawn data:\n" + "\n".join(failures))

    OUTPUT.mkdir(parents=True, exist_ok=True)
    for path, payload in downloads:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)

    catalog = {
        "revision": REVISION,
        "pals": pals,
        "humans": humans,
    }
    (OUTPUT / "catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(
        f"Downloaded {len(pals)} Pal and {len(humans)} human spawn records "
        f"to {OUTPUT.resolve()}"
    )


if __name__ == "__main__":
    main()
