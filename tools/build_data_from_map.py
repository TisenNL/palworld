"""Rebuild public/data.json from the PalDB and OP.GG source data."""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = ROOT / "tools" / "data"
MAP_JS = SOURCE_DIR / "map_data_en.js"
OUT = ROOT / "public" / "data.json"
OPGG_CACHE_DIR = SOURCE_DIR
OPGG_GROUPS = (
    "resources",
    "eggs",
    "mine",
    "fishing",
    "collectibles",
    "locations",
    "oilrig",
)
OPGG_BASE = (
    "https://s-stats-platform-cdn.op.gg/palworld/meta/web-contract/v1/map-points/groups/"
)

# OP.GG point key to the type displayed in the checklist and map
OPGG_TYPE_MAP = {
    "Chestbox": "Chest",
    "ElementTreasure": "Chest Element",
    "Junk": "Scraping Pile",
    "BeautifulFlower": "Beautiful Flower",
    "Peach": "Kinship Peach",
    "SkillFruits": "Skill Fruit",
    "Supply": "Supply Drop",
    "CrudeOil": "Crude Oil",
    "NightStone": "Night Stone",
    "OreMetal": "Ore (Metal)",
    "OreCoal": "Ore (Coal)",
    "OreQuartz": "Ore (Quartz)",
    "OreSulfur": "Ore (Sulfur)",
    "Chromites": "Chromite",
    "RainbowCrystal": "Rainbow Crystal",
    "SkyIslandOre": "Sky Island Ore",
    "WorldTreeOre": "World Tree Ore",
    "HardWood": "Hardwood",
    "AncientLava": "Ancient Lava",
    "AncientWood": "Ancient Wood",
    "AncientBeastBone": "Ancient Beast Bone",
    "FishingSpot": "Fishing Spot",
    "RareFishingSpot": "Rare Fishing Spot",
    "Salvage": "Salvage",
    "LootTower": "Loot Tower",
    "Note": "Note",
    "TreasureMap": "Treasure Map",
    "CaveEntrance": "Cave Entrance",
}

EGG_TAG_LABEL = {
    "grass": "Egg (Grass)",
    "desert": "Egg (Desert)",
    "volcano": "Egg (Volcano)",
    "snow": "Egg (Snow)",
    "sakurajima": "Egg (Sakurajima)",
    "darkIsland": "Egg (Feybreak)",
    "skyIsland": "Egg (Sky Island)",
    "worldTree": "Egg (World Tree)",
}

OILRIG_TAG_LABEL = {
    "oilrigGoal": "Oil Rig Goal",
    "oilrigMiniGoal": "Oil Rig Goal",
    "oilrig": "Oil Rig Chest",
    "oilrigLarge": "Oil Rig Chest",
    "oilrigMini": "Oil Rig Chest",
}

LAND_MIN = (-1099400.0, -724400.0)
LAND_MAX = (349400.0, 724400.0)
PER_PIXEL = 459.0
INGAME_X_START = 1000.0 + (-582888.0 - LAND_MIN[0]) / PER_PIXEL
INGAME_Y_START = 1000.0 + (-301000.0 - LAND_MIN[1]) / PER_PIXEL
CLUSTER_LINK_DISTANCE = 3000.0
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


def load_opgg_group(name: str) -> dict:
    path = OPGG_CACHE_DIR / f"opgg_{name}.json"
    if path.is_file():
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(cached, dict) and "points" in cached:
                return cached
        except json.JSONDecodeError:
            pass
    url = f"{OPGG_BASE}{name}.json"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=90) as res:
        raw = res.read()
    data = json.loads(raw.decode("utf-8"))
    path.write_bytes(raw)
    return data


def load_opgg_resources() -> dict:
    return load_opgg_group("resources")


def append_opgg_loot(collectibles: list[dict]) -> None:
    def opgg_extra(pt: dict) -> dict:
        extra = {}
        if "z" in pt:
            extra["z"] = pt["z"]
        if pt.get("tag"):
            extra["tag"] = pt["tag"]
        return extra

    for group in OPGG_GROUPS:
        if group == "oilrig":
            continue
        data = load_opgg_group(group)
        points = data.get("points") or {}

        if group == "eggs":
            for pt in opgg_points(points, "Eggs"):
                tag = str(pt.get("tag") or "unknown")
                ctype = EGG_TAG_LABEL.get(tag, f"Egg ({tag})")
                collectibles.append({
                    "id": slug(f"{ctype}-{pt['x']}_{pt['y']}"),
                    "type": ctype,
                    "name": ctype,
                    "x": pt["x"],
                    "y": pt["y"],
                    **opgg_extra(pt),
                })
            continue

        if group == "collectibles":
            for key in ("LootTower", "Note"):
                ctype = OPGG_TYPE_MAP[key]
                for pt in opgg_points(points, key):
                    collectibles.append({
                        "id": slug(f"{ctype}-{pt['x']}_{pt['y']}"),
                        "type": ctype,
                        "name": ctype,
                        "x": pt["x"],
                        "y": pt["y"],
                        **opgg_extra(pt),
                    })
            continue

        if group == "locations":
            for key in ("TreasureMap", "CaveEntrance"):
                ctype = OPGG_TYPE_MAP[key]
                for pt in opgg_points(points, key):
                    collectibles.append({
                        "id": slug(f"{ctype}-{pt['x']}_{pt['y']}"),
                        "type": ctype,
                        "name": ctype,
                        "x": pt["x"],
                        "y": pt["y"],
                        **opgg_extra(pt),
                    })
            continue

        allowed = None
        if group == "resources":
            allowed = {
                "Chestbox", "ElementTreasure", "Junk", "BeautifulFlower", "Peach",
                "SkillFruits", "Supply", "CrudeOil", "NightStone",
            }
        elif group == "mine":
            allowed = {
                "OreMetal", "OreCoal", "OreQuartz", "OreSulfur",
                "Chromites", "RainbowCrystal", "SkyIslandOre", "WorldTreeOre",
                "HardWood", "AncientLava", "AncientWood", "AncientBeastBone",
            }
        elif group == "fishing":
            allowed = {"FishingSpot", "RareFishingSpot", "Salvage"}

        if not allowed:
            continue
        for key in allowed:
            ctype = OPGG_TYPE_MAP[key]
            for pt in opgg_points(points, key):
                collectibles.append({
                    "id": slug(f"{ctype}-{pt['x']}_{pt['y']}"),
                    "type": ctype,
                    "name": ctype,
                    "x": pt["x"],
                    "y": pt["y"],
                    **opgg_extra(pt),
                })


def opgg_points(points: dict, key: str) -> list[dict]:
    out = []
    for row in points.get(key) or []:
        loc = row.get("l") or []
        if len(loc) < 2:
            continue
        rx, ry = float(loc[0]), float(loc[1])
        if not map_within(rx, ry):
            continue
        x, y = rpos_to_ipos(rx, ry)
        item = {"x": x, "y": y}
        if len(loc) >= 3:
            # OP.GG: toIngameCoords → Z {round(unrealZ/100)}m
            item["z"] = round(float(loc[2]) / 100.0)
        if row.get("t"):
            item["tag"] = str(row["t"])
        out.append(item)
    return out


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

    alphas = []
    for row in fixed:
        if row.get("type") != "Alpha Pal":
            continue
        name = clean_text(str(row.get("item") or ""))
        pos = row.get("pos") or {}
        x, y = rpos_to_ipos(float(pos["X"]), float(pos["Y"]))
        lv = row.get("lv")
        alphas.append({
            "id": slug(f"{name}-{lv}"),
            "lv": lv,
            "name": name,
            "x": x,
            "y": y,
        })
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

    # OP.GG loot (chests, eggs, ores, fishing, etc.) plus paldb ruins and flowers above
    append_opgg_loot(collectibles)

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


def main() -> int:
    data = build()
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("Wrote", OUT, {k: len(v) for k, v in data.items()})
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("ERROR:", exc, file=sys.stderr)
        raise SystemExit(1)
