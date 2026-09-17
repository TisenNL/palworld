"""Validate every remote image URL used by the application."""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"
)
IMAGE_PROXY = "http://127.0.0.1:8765/map-icon?src="


def image_urls() -> list[tuple[str, str]]:
    breed = json.loads((ROOT / "breed.json").read_text(encoding="utf-8"))
    icons = json.loads((ROOT / "map_icons.json").read_text(encoding="utf-8"))
    values = [
        *((f"Pal: {pal['name']}", str(pal.get("icon") or "")) for pal in breed["pals"]),
        *((f"Map icon: {name}", str(url or "")) for name, url in icons["icons"].items()),
    ]
    return list(dict.fromkeys(values))


def has_image_signature(data: bytes) -> bool:
    stripped = data.lstrip()
    return (
        data.startswith((b"\x89PNG", b"\xff\xd8\xff", b"GIF8", b"RIFF"))
        or stripped.startswith((b"<svg", b"<?xml"))
    )


def validate(entry: tuple[str, str]) -> tuple[str, str, str | None]:
    label, url = entry
    if not url:
        return label, url, "empty URL"
    proxy_url = IMAGE_PROXY + urllib.parse.quote(url, safe="")
    request = urllib.request.Request(
        proxy_url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "image/avif,image/webp,image/png,image/svg+xml,image/*",
            "Range": "bytes=0-255",
        },
    )
    last_error = "unknown error"
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                content_type = response.headers.get_content_type()
                data = response.read(256)
                if content_type.startswith("image/") or has_image_signature(data):
                    return label, url, None
                last_error = f"unexpected content type: {content_type}"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = str(exc)
        if attempt == 0:
            time.sleep(0.4)
    return label, url, last_error


def run(entries: Iterable[tuple[str, str]]) -> list[tuple[str, str, str]]:
    failures: list[tuple[str, str, str]] = []
    values = list(entries)
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(validate, entry): entry for entry in values}
        for future in as_completed(futures):
            label, url, error = future.result()
            if error:
                failures.append((label, url, error))
    return sorted(failures)


def main() -> int:
    entries = image_urls()
    failures = run(entries)
    print(f"Validated {len(entries)} application image URLs.")
    if not failures:
        print("All application image URLs are valid.")
        return 0
    print(f"{len(failures)} broken image URLs:")
    for label, url, error in failures:
        print(f"- {label}: {error}\n  {url}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
