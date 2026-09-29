"""Rebuild public/data.json from the PalDB source data."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = ROOT / "tools" / "data"
MAP_JS = SOURCE_DIR / "map_data_en.js"
OUT = ROOT / "public" / "data.json"

LAND_MIN = (-1099400.0, -724400.0)
LAND_MAX = (349400.0, 724400.0)
PER_PIXEL = 459.0
INGAME_X_START = 1000.0 + (-582888.0 - LAND_MIN[0]) / PER_PIXEL
INGAME_Y_START = 1000.0 + (-301000.0 - LAND_MIN[1]) / PER_PIXEL
CLUSTER_LINK_DISTANCE = 3000.0

# ── World Tree zone (separate coordinate space) ──────────────────────────────
# PalDB uses these for World Tree in treemap_data_en_full.js and worldtree.html
WT_LAND_MIN = (347351.5, -818197.0)
WT_LAND_MAX = (689148.5, -476400.0)
WT_PER_PIXEL = 1335.144531
WT_TRANSFORM_X_PIXEL = (WT_LAND_MAX[0] - WT_LAND_MIN[0]) / WT_PER_PIXEL # ~256.0000000479349
WT_TRANSFORM_Y_PIXEL = (WT_LAND_MAX[1] - WT_LAND_MIN[1]) / WT_PER_PIXEL # ~256.0000000479349
WT_INGAME_X_START = -648.7
WT_INGAME_Y_START = 127.7
WT_MAP_JS = ROOT / "treemap_data_en_full.js"
WT_OUT = ROOT / "public" / "wt-data.json"


def wt_rpos_to_ipos(x: float, y: float) -> tuple[float, float]:
    """Convert raw Unreal coords to World Tree in-game coords (matches paldb.cc logic)."""
    # Paldb logic from paldb-map.js:
    # rposToScale: X=(rx - landMinX)/(landMaxX - landMinX), Y=(ry - landMinY)/(landMaxY - landMinY)
    # projIpos: ipos.X = round(scaleY * transform_y_pixel - ingame_y_start), ipos.Y = round(scaleX * transform_x_pixel - ingame_x_start)
    scale_x = (x - WT_LAND_MIN[0]) / (WT_LAND_MAX[0] - WT_LAND_MIN[0])
    scale_y = (y - WT_LAND_MIN[1]) / (WT_LAND_MAX[1] - WT_LAND_MIN[1])
    ix = scale_y * WT_TRANSFORM_Y_PIXEL - WT_INGAME_Y_START
    iy = scale_x * WT_TRANSFORM_X_PIXEL - WT_INGAME_X_START
    return round(ix, 1), round(iy, 1)


def wt_map_within(x: float, y: float) -> bool:
    """Return True if raw Unreal coord is within World Tree bounds."""
    return WT_LAND_MIN[0] < x < WT_LAND_MAX[0] and WT_LAND_MIN[1] < y < WT_LAND_MAX[1]
CLUSTER_NODE_TYPES = {
    "Ore Cluster": "Ore",
    "Coal Cluster": "Coal",
    "Pure Quartz Cluster": "Pure Quartz",
    "Sulfur Cluster": "Sulfur",
}


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def clean_text(text: str) -> str:
    t = strip_html(text)
    t = t.replace("\u0092", "'").replace("\u2019", "'").replace("\u2018", "'")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def rpos_to_ipos(x: float, y: float) -> tuple[int, int]:
    sx = (x - LAND_MIN[0]) / PER_PIXEL
    sy = (y - LAND_MIN[1]) / PER_PIXEL
    return round(sy - INGAME_Y_START), round(sx - INGAME_X_START)


def map_within(x: float, y: float) -> bool:
    return LAND_MIN[0] < x < LAND_MAX[0] and LAND_MIN[1] < y < LAND_MAX[1]


def calculate_cluster_volumes(rows: list[dict]) -> dict[int, int]:
    volumes: dict[int, int] = {}
    max_distance_squared = CLUSTER_LINK_DISTANCE ** 2
    for cluster_type, node_type in CLUSTER_NODE_TYPES.items():
        clusters = [row for row in rows if row.get("type") == cluster_type]
        nodes = [row for row in rows if row.get("type") == node_type]
        parents = list(range(len(nodes)))

        def find(index: int) -> int:
            while parents[index] != index:
                parents[index] = parents[parents[index]]
                index = parents[index]
            return index

        def union(first: int, second: int) -> None:
            first_root = find(first)
            second_root = find(second)
            if first_root != second_root:
                parents[second_root] = first_root

        for first, node in enumerate(nodes):
            first_pos = node["pos"]
            for second in range(first):
                second_pos = nodes[second]["pos"]
                distance_squared = (
                    (float(first_pos["X"]) - float(second_pos["X"])) ** 2
                    + (float(first_pos["Y"]) - float(second_pos["Y"])) ** 2
                )
                if distance_squared <= max_distance_squared:
                    union(first, second)

        component_sizes: dict[int, int] = {}
        for index in range(len(nodes)):
            root = find(index)
            component_sizes[root] = component_sizes.get(root, 0) + 1

        for cluster in clusters:
            cluster_pos = cluster["pos"]
            nearest = min(
                range(len(nodes)),
                key=lambda index: (
                    (float(nodes[index]["pos"]["X"]) - float(cluster_pos["X"])) ** 2
                    + (float(nodes[index]["pos"]["Y"]) - float(cluster_pos["Y"])) ** 2
                ),
            )
            volumes[id(cluster)] = component_sizes[find(nearest)]
    return volumes





def extract_array(src: str, name: str) -> list:
    m = re.search(rf"var\s+{name}\s*=\s*(\[)", src)
    if not m:
        raise RuntimeError(f"array {name} not found")
    start = m.start(1)
    depth = 0
    in_str = False
    esc = False
    quote = ""
    for i in range(start, len(src)):
        ch = src[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                in_str = False
            continue
        if ch in "\"'":
            in_str = True
            quote = ch
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return json.loads(src[start : i + 1])
    raise RuntimeError(f"unclosed array {name}")


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def journal_series(name: str) -> str:
    if " - " in name:
        return name.rsplit(" - ", 1)[0].strip()
    m = re.match(r"^(Castaway's Journal)\s+Day\s+\d+", name, re.I)
    if m:
        return m.group(1)
    if name.lower().startswith("a letter"):
        return "Letter"
    return name


def build() -> dict:
    if not MAP_JS.exists():
        raise FileNotFoundError(f"Missing {MAP_JS}")
    src = MAP_JS.read_text(encoding="utf-8", errors="ignore")
    fixed = extract_array(src, "fixedDungeon")
    cluster_volumes = calculate_cluster_volumes(fixed)

    # Sealed Realm bosses that exist in-game but are missing from PalDB Alpha Pal markers.
    # Coordinates match the Sealed Realm entrance / wiki.gg Sealed Realms list.
    sealed_realm_alphas = (
        {
            "id": "eye-of-cthulhu-45",
            "lv": 45,
            "name": "Eye of Cthulhu",
            "x": -422,
            "y": -795,
            "tag": "Sealed Realm",
            "type": "Sealed Realm of Terraria",
            "icon": "/alpha-icons/eye-of-cthulhu-45.webp",
        },
    )

    alphas = []
    for row in fixed:
        if row.get("type") != "Alpha Pal":
            continue
        name = clean_text(str(row.get("item") or ""))
        pos = row.get("pos") or {}
        x, y = rpos_to_ipos(float(pos["X"]), float(pos["Y"]))
        lv = row.get("lv")
        comment = str(row.get("comment") or "")
        entry = {
            "id": slug(f"{name}-{lv}"),
            "lv": lv,
            "name": name,
            "x": x,
            "y": y,
        }
        if comment == "Dungeon Boss":
            entry["tag"] = "Sealed Realm"
        local_icon = ROOT / "public" / "alpha-icons" / f"{entry['id']}.webp"
        if local_icon.is_file():
            entry["icon"] = f"/alpha-icons/{local_icon.name}"
        elif row.get("fixed_icon"):
            entry["icon"] = str(row.get("fixed_icon"))
        alphas.append(entry)
    existing = {(a["name"].lower(), a["lv"]) for a in alphas}
    for sealed in sealed_realm_alphas:
        key = (sealed["name"].lower(), sealed["lv"])
        if key not in existing:
            alphas.append(dict(sealed))
            existing.add(key)
    alphas.sort(key=lambda a: (a["lv"] is None, a["lv"] or 0, a["name"]))
    for i, a in enumerate(alphas, 1):
        a["n"] = i

    bounty_rows = []
    for row in fixed:
        if row.get("type") != "Bounty":
            continue
        name = clean_text(str(row.get("item") or "Bounty"))
        pos = row.get("pos") or {}
        x, y = rpos_to_ipos(float(pos["X"]), float(pos["Y"]))
        lv = row.get("lv")
        bounty_rows.append({"name": name, "lv": lv, "x": x, "y": y})
    bounty_rows.sort(key=lambda r: (r["lv"] is None, r["lv"] or 0, r["name"], r["x"], r["y"]))
    seen_b = set()
    bounties = []
    for b in bounty_rows:
        key = (b["name"], b["lv"])
        if key in seen_b:
            continue
        seen_b.add(key)
        bounties.append({
            "id": slug(f"bounty-{b['name']}-{b['lv']}"),
            "lv": b["lv"],
            "name": b["name"],
            "x": b["x"],
            "y": b["y"],
        })
    for i, b in enumerate(bounties, 1):
        b["n"] = i

    effigies = []
    for row in fixed:
        t = str(row.get("type") or "")
        if not t.endswith(" Effigy"):
            continue
        pal = t[: -len(" Effigy")]
        pos = row.get("pos") or {}
        x, y = rpos_to_ipos(float(pos["X"]), float(pos["Y"]))
        effigies.append({
            "id": f"effigy-{slug(pal)}-{x}_{y}",
            "type": pal,
            "x": x,
            "y": y,
        })
    effigies.sort(key=lambda e: (e["x"], e["y"]))

    dungeons = []
    for row in fixed:
        if row.get("type") != "Dungeon":
            continue
        name = clean_text(str(row.get("item") or "???")) or "???"
        pos = row.get("pos") or {}
        x, y = rpos_to_ipos(float(pos["X"]), float(pos["Y"]))
        lv = row.get("lv")
        dungeons.append({
            "id": slug(f"dungeon-{name}-lv{lv}-{x}_{y}"),
            "name": name,
            "lv": lv,
            "x": x,
            "y": y,
        })
    dungeons.sort(key=lambda d: (d["lv"] is None, d["lv"] or 0, d["name"], d["x"], d["y"]))

    towers = []
    for row in fixed:
        if row.get("type") != "Tower":
            continue
        name = clean_text(str(row.get("item") or "Tower")) or "Tower"
        pos = row.get("pos") or {}
        x, y = rpos_to_ipos(float(pos["X"]), float(pos["Y"]))
        lv = row.get("lv")
        towers.append({
            "id": slug(f"tower-{name}-lv{lv}"),
            "name": name,
            "lv": lv,
            "x": x,
            "y": y,
        })
    towers.sort(key=lambda t: (t["lv"] is None, t["lv"] or 0, t["name"]))
    for i, t in enumerate(towers, 1):
        t["n"] = i

    journals = []
    for row in fixed:
        if row.get("type") != "Journals":
            continue
        name = clean_text(str(row.get("item") or "Journal")) or "Journal"
        pos = row.get("pos") or {}
        x, y = rpos_to_ipos(float(pos["X"]), float(pos["Y"]))
        series = journal_series(name)
        journals.append({
            "id": slug(f"journal-{name}-{x}_{y}"),
            "name": name,
            "series": series,
            "x": x,
            "y": y,
        })
    journals.sort(key=lambda j: (j["series"], j["name"], j["x"], j["y"]))
    series_n: dict[str, int] = {}
    for j in journals:
        series_n[j["series"]] = series_n.get(j["series"], 0) + 1
        j["n"] = series_n[j["series"]]

    oilrigs = []
    for row in fixed:
        t = row.get("type")
        if t not in ("Oilrig Chest", "Oilrig Chest Goal"):
            continue
        kind = "goal" if t == "Oilrig Chest Goal" else "chest"
        name = "Oil Rig Goal" if kind == "goal" else "Oil Rig Chest"
        pos = row.get("pos") or {}
        x, y = rpos_to_ipos(float(pos["X"]), float(pos["Y"]))
        oilrigs.append({
            "id": slug(f"oilrig-{kind}-{x}_{y}"),
            "kind": kind,
            "name": name,
            "x": x,
            "y": y,
        })
    oilrigs.sort(key=lambda o: (0 if o["kind"] == "goal" else 1, o["x"], o["y"]))
    for i, o in enumerate(oilrigs, 1):
        o["n"] = i

    camps = []
    for row in fixed:
        if row.get("type") != "Enemy Camp":
            continue
        raw = clean_text(str(row.get("item") or "Enemy Camp")) or "Enemy Camp"
        if raw == "Enemy Camp" or re.fullmatch(r"[A-Za-z0-9_]+", raw):
            name = "Enemy Camp"
        else:
            name = raw
        pos = row.get("pos") or {}
        x, y = rpos_to_ipos(float(pos["X"]), float(pos["Y"]))
        camps.append({
            "id": slug(f"camp-{raw}-{x}_{y}"),
            "name": name,
            "x": x,
            "y": y,
        })
    camps.sort(key=lambda c: (c["x"], c["y"]))
    for i, c in enumerate(camps, 1):
        c["n"] = i

    collectibles = []
    cluster_types = {
        "Ore Cluster",
        "Coal Cluster",
        "Pure Quartz Cluster",
        "Sulfur Cluster",
    }
    for row in fixed:
        t = row.get("type")
        if t == "Ancient Ruin":
            ctype = "Ancient Ruin"
        elif t == "Kinship Peach":
            ctype = "Kinship Peach"
        elif t == "Beautiful Flower":
            ctype = "Beautiful Flower"
        elif t == "Fruit Tree":
            ctype = "Fruit Tree"
        elif t in cluster_types:
            ctype = str(t)
        else:
            continue
        pos = row.get("pos") or {}
        x, y = rpos_to_ipos(float(pos["X"]), float(pos["Y"]))
        collectibles.append({
            "id": slug(f"{ctype}-{x}_{y}"),
            "type": ctype,
            "name": ctype,
            "x": x,
            "y": y,
            **({"volume": cluster_volumes[id(row)]} if t in cluster_types else {}),
        })



    # Deduplicate by type and coordinates, keeping the first entry
    seen_c: set[tuple] = set()
    deduped = []
    for c in collectibles:
        key = (c["type"], c["x"], c["y"])
        if key in seen_c:
            continue
        seen_c.add(key)
        deduped.append(c)
    collectibles = deduped
    collectibles.sort(key=lambda c: (c["type"], c["x"], c["y"]))
    type_n: dict[str, int] = {}
    for c in collectibles:
        type_n[c["type"]] = type_n.get(c["type"], 0) + 1
        c["n"] = type_n[c["type"]]

    travel = []
    for row in fixed:
        t = row.get("type")
        if t == "Fast Travel":
            kind = "Fast Travel"
        elif t == "Watchtower":
            kind = "Watchtower"
        else:
            continue
        name = clean_text(str(row.get("item") or kind)) or kind
        pos = row.get("pos") or {}
        x, y = rpos_to_ipos(float(pos["X"]), float(pos["Y"]))
        travel.append({
            "id": slug(f"{kind}-{name}-{x}_{y}"),
            "type": kind,
            "name": name,
            "x": x,
            "y": y,
        })
    travel.sort(key=lambda t: (t["type"], t["name"], t["x"], t["y"]))
    for i, t in enumerate(travel, 1):
        t["n"] = i

    return {
        "alphas": alphas,
        "bounties": bounties,
        "effigies": effigies,
        "dungeons": dungeons,
        "towers": towers,
        "journals": journals,
        "oilrigs": oilrigs,
        "camps": camps,
        "collectibles": collectibles,
        "travel": travel,
    }


def build_wt() -> dict:
    """Build World Tree zone data strictly from PalDB's treemap_data_en_full.js."""
    if not WT_MAP_JS.exists():
        return {"alphas": [], "towers": [], "travel": [], "effigies": [], "journals": [], "collectibles": []}
    
    src = WT_MAP_JS.read_text(encoding="utf-8", errors="ignore")
    fixed = extract_array(src, "fixedDungeon")
    
    alphas = []
    towers = []
    travel = []
    effigies = []
    journals = []
    collectibles = []
    
    for row in fixed:
        pos = row.get("pos") or {}
        if not pos:
            continue
        rx, ry = float(pos.get("X", 0)), float(pos.get("Y", 0))
        if not wt_map_within(rx, ry):
            continue
            
        x, y = wt_rpos_to_ipos(rx, ry)
        t = str(row.get("type") or "")
        name = clean_text(str(row.get("item") or t)) or t
        lv = row.get("lv")
        
        if t == "Alpha Pal":
            alphas.append({
                "id": slug(f"wt-alpha-{name}-{lv}"),
                "lv": lv,
                "name": name,
                "x": x,
                "y": y
            })
        elif t == "Tower":
            towers.append({
                "id": slug(f"wt-tower-{name}-{x}_{y}"),
                "name": name,
                "lv": lv,
                "x": x,
                "y": y
            })
        elif t in ("Fast Travel", "Watchtower"):
            travel.append({
                "id": slug(f"wt-{t}-{name}-{x}_{y}"),
                "type": t,
                "name": name,
                "x": x,
                "y": y
            })
        elif t.endswith(" Effigy"):
            pal = t[: -len(" Effigy")]
            effigies.append({
                "id": slug(f"wt-effigy-{pal}-{x}_{y}"),
                "type": pal,
                "name": name,
                "x": x,
                "y": y
            })
        elif t == "Journals":
            journals.append({
                "id": slug(f"wt-journal-{name}-{x}_{y}"),
                "name": name,
                "x": x,
                "y": y
            })
        else:
            ctype = "Egg (World Tree)" if t == "World Tree Egg" else t
            collectibles.append({
                "id": slug(f"wt-{ctype}-{x}_{y}"),
                "type": ctype,
                "name": name,
                "x": x,
                "y": y
            })
            
    alphas.sort(key=lambda a: (a["lv"] is None, a["lv"] or 0, a["name"]))
    towers.sort(key=lambda t: (t["lv"] is None, t["lv"] or 0, t["name"]))
    travel.sort(key=lambda t: (t["type"], t["name"]))
    effigies.sort(key=lambda e: (e["type"], e["x"], e["y"]))
    journals.sort(key=lambda j: (j["name"], j["x"], j["y"]))
    collectibles.sort(key=lambda c: (c["type"], c["name"]))
    
    return {
        "alphas": alphas,
        "towers": towers,
        "travel": travel,
        "effigies": effigies,
        "journals": journals,
        "collectibles": collectibles,
    }


def main() -> int:
    data = build()
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("Wrote", OUT, {k: len(v) for k, v in data.items()})
    wt_data = build_wt()
    WT_OUT.write_text(json.dumps(wt_data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("Wrote", WT_OUT, {k: len(v) for k, v in wt_data.items()})
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("ERROR:", exc, file=sys.stderr)
        raise SystemExit(1)
