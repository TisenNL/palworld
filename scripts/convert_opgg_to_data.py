#!/usr/bin/env python3
"""
Script para converter arquivos opgg_*.json para o formato data.json da aplicacao Vue.

Uso:
  1. Coloque os arquivos opgg_*.json na raiz do projeto
  2. Rode: python scripts/convert_opgg_to_data.py
  3. O arquivo public/data.json sera atualizado com todos os marcadores

Os arquivos opgg_*.json devem ter o formato:
  {
    "group": "collectibles",
    "points": {
      "CategoryName": [
        {"l": [x, y, z], "t": "type"},
        ...
      ]
    }
  }

O arquivo de saida sera no formato esperado pela aplicacao Vue:
  {
    "alphas": [...],
    "bounties": [...],
    "effigies": [...],
    ...
  }
"""

import json
import shutil
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent

# Mapeamento de tipos para categorias
EFFIGY_TYPES = {
    'Carbunclo', 'SheepBall', 'Penguin', 'IceCrocodile', 'FlameBambi',
    'LeafMomonga', 'Monkey', 'NegativeKoala', 'PinkCat', 'Mutant',
    'LazyDragon', 'GuardianDog'
}

def get_category(category_name, point_type):
    """Determinar a categoria com base no tipo do ponto."""
    
    # Effigies
    if 'Effigy' in category_name or point_type in EFFIGY_TYPES:
        return 'effigies'
    
    # Towers (Loot Tower)
    if point_type == 'lootTower' or category_name == 'LootTower':
        return 'towers'
    
    # Journals (Notes)
    if point_type == 'note' or category_name == 'Note':
        return 'journals'
    
    # Bounties (enemies)
    if category_name in ['AntiAir', 'BossTower', 'Bounty', 'EnemyCamp', 'FieldBoss', 'Predator', 'Incident']:
        return 'bounties'
    
    # Dungeons
    if category_name in ['Dungeon', 'CaveEntrance']:
        return 'dungeons'
    
    # Travel
    if category_name in ['FastTravel', 'Respawn', 'SkylandWarpAltar', 'Home', 'WatchTower', 
                       'RegionName', 'TreasureMap', 'HeatArea', 'Quest']:
        return 'travel'
    
    # Oilrigs
    if category_name in ['OilRig', 'OilRigGoal'] or 'Chestbox' in category_name:
        return 'oilrigs'
    
    # Camps (NPCs)
    if 'Npc' in category_name:
        return 'camps'
    
    # Collectibles (default)
    return 'collectibles'


def load_opgg_file(filepath):
    """Carregar pontos de um arquivo opgg."""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    items = []
    if 'points' not in data:
        return items
    
    for category_name, points_list in data['points'].items():
        for idx, point in enumerate(points_list):
            coords = point.get('l', [0, 0, 0])
            point_type = point.get('t', category_name)
            category = get_category(category_name, point_type)
            
            # Criar ID unico
            base_id = point_type.replace(':', '-').replace('_', '-').replace(' ', '-').lower()
            item_id = f"{base_id}-{idx}"
            
            item = {
                "id": item_id,
                "x": round(coords[0]),
                "y": round(coords[1]),
                "z": round(coords[2]) if len(coords) > 2 else None,
                "name": point_type,
                "type": category_name
            }
            
            items.append((category, item))
    
    return items


def main():
    print("Convertendo arquivos opgg_*.json para data.json...")
    print("=" * 60)
    
    # Carregar dados originais para preservar alphas
    original_data_path = PROJECT_DIR / 'public' / 'data.json'
    if original_data_path.exists():
        with open(original_data_path, 'r', encoding='utf-8') as f:
            original_data = json.load(f)
        alphas = original_data.get('alphas', [])
        print(f"Preservando {len(alphas)} alphas originais")
    else:
        alphas = []
        print("Nenhum dado original encontrado em public/data.json")
    
    # Inicializar estruturas
    game_data = {
        "alphas": alphas,
        "bounties": [],
        "effigies": [],
        "dungeons": [],
        "towers": [],
        "journals": [],
        "oilrigs": [],
        "camps": [],
        "collectibles": [],
        "travel": []
    }
    
    # Processar arquivos opgg
    opgg_files = [
        'opgg_collectibles.json',
        'opgg_eggs.json',
        'opgg_enemies.json',
        'opgg_fishing.json',
        'opgg_locations.json',
        'opgg_mine.json',
        'opgg_npc.json',
        'opgg_oilrig.json',
        'opgg_resources.json'
    ]
    
    total_added = 0
    
    for opgg_file in opgg_files:
        file_path = PROJECT_DIR / opgg_file
        if not file_path.exists():
            print(f"  Aviso: {opgg_file} nao encontrado")
            continue
        
        items = load_opgg_file(file_path)
        for category, item in items:
            if category in game_data:
                game_data[category].append(item)
            else:
                print(f"  Aviso: Categoria '{category}' nao encontrada, pulando item {item['id']}")
        
        print(f"  {opgg_file}: {len(items)} itens")
        total_added += len(items)
    
    print("=" * 60)
    print("\nItens por categoria:")
    for cat, items in game_data.items():
        print(f"  {cat}: {len(items)}")
    
    print(f"\nTotal: {total_added + len(alphas)} itens")
    
    # Salvar em public/data.json
    with open(original_data_path, 'w', encoding='utf-8') as f:
        json.dump(game_data, f, indent=2, ensure_ascii=False)
    
    # Copiar para dist/data.json
    dist_data_path = PROJECT_DIR / 'dist' / 'data.json'
    shutil.copy2(original_data_path, dist_data_path)
    
    print(f"\nDados salvos em:")
    print(f"  - {original_data_path}")
    print(f"  - {dist_data_path}")
    print("\nFeito!")


if __name__ == '__main__':
    main()
