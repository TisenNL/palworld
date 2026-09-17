"""Build breed.json from iv_en.json + breed_data_extracted.json (paldb)."""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IV_URL = "https://paldb.cc/json/iv_en.json"
IV_CACHE = ROOT / "tools" / "iv_en.json"
EXTRACTED = ROOT / "tools" / "breed_data_extracted.json"
OUT = ROOT / "breed.json"

SKIP_CODES = {"KingWhale", "WorldTreeDragon"}


def fetch_iv() -> list:
    if IV_CACHE.exists():
        return json.loads(IV_CACHE.read_text(encoding="utf-8"))
    req = urllib.request.Request(IV_URL, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://paldb.cc/"})
    with urllib.request.urlopen(req, timeout=60) as res:
        raw = res.read()
    IV_CACHE.write_bytes(raw)
    return json.loads(raw.decode("utf-8"))


def icon_url(code: str) -> str:
    base = "https://cdn.paldb.cc/image/Pal/Texture/PalIcon/Normal"
    if code.startswith("Yakushima"):
        return f"{base}/Yakushima/T_{code}_icon_normal.webp"
    return f"{base}/T_{code}_icon_normal.webp"


def main() -> int:
    iv = fetch_iv()
    extracted = json.loads(EXTRACTED.read_text(encoding="utf-8"))
    ranks = extracted["combiRank"]
    mut_yes = set(extracted.get("mutationFlagYes") or [])
    sex = extracted.get("sexRatio") or {}
    uniques = extracted.get("uniqueBreeds") or []

    pals = []
    by_code = {}
    for row in iv:
        code = str(row.get("Code") or "")
        if not code or code in SKIP_CODES:
            continue
        if code not in ranks:
            continue
        pal = {
            "code": code,
            "name": str(row.get("NameEn") or row.get("Name") or code),
            "id": str(row.get("Id") or ""),
            "rank": int(ranks[code]),
            "ignoreCombi": bool(row.get("IgnoreCombi")),
            "mutation": code in mut_yes,
            "male": (sex.get(code) or ["50%", "50%"])[0],
            "female": (sex.get(code) or ["50%", "50%"])[1],
            "icon": icon_url(code),
        }
        pals.append(pal)
        by_code[code] = pal

    pals.sort(key=lambda p: (p["name"].lower(), p["code"]))

    # Stable order by rank then name for tie-break (closer to game index)
    rank_order = sorted(pals, key=lambda p: (p["rank"], p["name"].lower(), p["code"]))
    for i, p in enumerate(rank_order):
        p["order"] = i

    unique_out = []
    for u in uniques:
        a, b, c = u.get("parentA"), u.get("parentB"), u.get("child")
        if a in by_code and b in by_code and c in by_code:
            unique_out.append({"a": a, "b": b, "child": c})

    payload = {
        "version": 1,
        "source": "paldb.cc (iv_en + Breeding_Farm)",
        "pals": pals,
        "unique": unique_out,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("Wrote", OUT, "pals", len(pals), "unique", len(unique_out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
