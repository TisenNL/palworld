"""
Baixa todos os dados de marcadores do op.gg para uso local.
Salva em public/opgg-data/ como JSON.
"""
import urllib.request
import urllib.error
import json
import os
from pathlib import Path

CDN = "https://s-stats-platform-cdn.op.gg"
REVISION = "2026091501"
OUT = Path("public/opgg-data")
OUT.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
    "Referer": "https://op.gg/palworld/map",
    "Accept": "application/json, */*",
}


def fetch(url: str) -> bytes | None:
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code}: {url}")
        return None
    except Exception as e:
        print(f"  Error: {e}: {url}")
        return None


def download(url: str, dest: Path) -> bool:
    if dest.exists():
        print(f"  skip: {dest.name}")
        return True
    data = fetch(url)
    if data is None:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    size = len(data)
    print(f"  ok ({size:,} bytes): {dest.name}")
    return True


def meta_url(path: str) -> str:
    return f"{CDN}/palworld/meta/{path}?v={REVISION}"


# ── 1. Index ────────────────────────────────────────────────────────────────
print("=== Baixando index ===")
index_url = meta_url("web-contract/v1/map-points/index.json")
index_dest = OUT / "index.json"
if not download(index_url, index_dest):
    print("ERRO: Não foi possível baixar o index")
    exit(1)

with open(index_dest, encoding="utf-8") as f:
    index = json.load(f)

# ── 2. points.json (dados completos legado) ─────────────────────────────────
print("\n=== Baixando points.json (dados completos) ===")
points_url = meta_url("points.json")
download(points_url, OUT / "points.json")

# ── 3. Grupos individuais ───────────────────────────────────────────────────
print("\n=== Baixando grupos ===")
groups = index.get("groups", {})
for group_name, group_info in groups.items():
    path = group_info.get("path", "")
    if not path:
        continue
    url = meta_url(path)
    dest = OUT / path
    download(url, dest)

# ── 4. egg-loot.json ────────────────────────────────────────────────────────
print("\n=== Baixando egg-loot.json ===")
download(meta_url("egg-loot.json"), OUT / "egg-loot.json")

# ── 5. Tenta spawns de alguns Pals comuns ───────────────────────────────────
print("\n=== Baixando spawns de Alpha Pals ===")
spawn_dir = OUT / "spawns"
spawn_dir.mkdir(exist_ok=True)
# Lista de IDs relevantes para Alpha Pals (campo boss + regular)
alpha_ids = [
    "BOSS_Bushi", "BOSS_SheepBall", "BOSS_Penguin", "BOSS_GrassGolem",
    "BOSS_Anubis", "BOSS_Blazamut", "BOSS_Frostallion", "BOSS_Jetragon",
]
for pid in alpha_ids:
    url = meta_url(f"spawns/{pid}.json")
    download(url, spawn_dir / f"{pid}.json")

# ── 6. Salva mapeamento completo de categorias ──────────────────────────────
print("\n=== Gerando mapeamento de categorias ===")
category_map = {}
for group_name, group_info in groups.items():
    for cat in group_info.get("categories", []):
        category_map[cat] = {
            "group": group_name,
            "file": group_info.get("path", ""),
            "count_world": index.get("counts", {}).get("world", {}).get(cat, 0),
            "count_tree": index.get("counts", {}).get("tree", {}).get(cat, 0),
        }

with open(OUT / "category-map.json", "w", encoding="utf-8") as f:
    json.dump(category_map, f, indent=2, ensure_ascii=False)
print(f"  ok: category-map.json ({len(category_map)} categories)")

print(f"\n✅ Download completo! Arquivos em: {OUT.resolve()}")
