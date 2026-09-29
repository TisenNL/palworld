import type { GameData, MapLayer, WtData } from '@/types/data'

export const layerGroups = [
  { id: 'combat', label: 'Combat and bosses' },
  { id: 'explore', label: 'Exploration' },
  { id: 'effigies', label: 'Effigies' },
  { id: 'ores', label: 'Ores and crystals' },
  { id: 'gather', label: 'Gathering' },
  { id: 'notes', label: 'Notes and maps' },
] as const

export const wtLayerGroups = [
  { id: 'wt-combat', label: 'Combat and bosses' },
  { id: 'wt-travel', label: 'Fast Travel' },
  { id: 'wt-collectibles', label: 'Collectibles' },
] as const

const baseLayers: Array<Omit<MapLayer, 'group'>> = [
  { id: 'alphas', label: 'Alpha Pals', color: '#34d399', storage: 'alphas' },
  {
    id: 'bounties',
    label: 'Bounties',
    iconKey: 'Bounties',
    color: '#60a5fa',
    storage: 'bounties',
  },
  { id: 'towers', label: 'Towers', iconKey: 'Towers', color: '#f472b6', storage: 'towers' },
  {
    id: 'dungeons',
    label: 'Dungeons',
    iconKey: 'Dungeons',
    color: '#94a3b8',
    storage: 'dungeons',
  },
  { id: 'journals', label: 'Journals', iconKey: 'Journals', color: '#eab308', storage: 'journals' },
  {
    id: 'camps',
    label: 'Enemy Camps',
    iconKey: 'Enemy Camps',
    color: '#f87171',
    storage: 'camps',
  },
  {
    id: 'oilrig-goal',
    label: 'Oil Rig Goal',
    iconKey: 'Oil Rig Goal',
    color: '#fb923c',
    storage: 'oilrigs',
    kindIn: ['goal'],
  },
  {
    id: 'oilrig-chest',
    label: 'Oil Rig Chest',
    iconKey: 'Oil Rig Chest',
    color: '#f59e0b',
    storage: 'oilrigs',
    kindIn: ['chest'],
  },
  {
    id: 'travel-fast',
    label: 'Fast Travel',
    iconKey: 'Fast Travel',
    color: '#22d3ee',
    storage: 'travel',
    typeIn: ['Fast Travel'],
  },
  {
    id: 'travel-watch',
    label: 'Watchtower',
    iconKey: 'Watchtower',
    color: '#67e8f9',
    storage: 'travel',
    typeIn: ['Watchtower'],
  },
]

const effigyColors: Record<string, string> = {
  Lifmunk: '#86efac',
  Lamball: '#fce7f3',
  Pengullet: '#7dd3fc',
  Munchill: '#fdba74',
  Rooby: '#fca5a5',
  Herbil: '#bbf7d0',
  Tanzee: '#bef264',
  Depresso: '#c4b5fd',
  Lunaris: '#a5b4fc',
  Relaxaurus: '#6ee7b7',
  Yakumo: '#fde68a',
}

const lootColors: Record<string, string> = {
  Chest: '#fbbf24',
  'Chest Element': '#f59e0b',
  'Scraping Pile': '#d6d3d1',
  'Supply Drop': '#fdba74',
  'Skill Fruit': '#4ade80',
  'Beautiful Flower': '#f9a8d4',
  'Kinship Peach': '#fb7185',
  'Fruit Tree': '#84cc16',
  'Ancient Ruin': '#a78bfa',
  'Crude Oil': '#78716c',
  'Night Stone': '#6366f1',
  Chromite: '#a8a29e',
  'Ore Cluster': '#fb923c',
  'Coal Cluster': '#64748b',
  'Pure Quartz Cluster': '#e0f2fe',
  'Sulfur Cluster': '#fde047',
  'Rainbow Crystal': '#e879f9',
  'Sky Island Ore': '#38bdf8',
  'World Tree Ore': '#65a30d',
  Hardwood: '#a16207',
  'Ancient Lava': '#ef4444',
  'Ancient Wood': '#854d0e',
  'Ancient Beast Bone': '#d6d3d1',
  'Fishing Spot': '#0ea5e9',
  'Rare Fishing Spot': '#2563eb',
  Salvage: '#64748b',
  'Loot Tower': '#f97316',
  Note: '#facc15',
  'Treasure Map': '#ca8a04',
  'Cave Entrance': '#71717a',
}

export function slug(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
}

function groupFor(layer: Omit<MapLayer, 'group'>): string {
  if (['alphas', 'bounties', 'towers', 'camps'].includes(layer.id)) return 'combat'
  if (layer.storage === 'effigies') return 'effigies'
  if (
    ['dungeons', 'journals', 'oilrigs', 'travel'].includes(layer.storage) ||
    layer.typeIn?.includes('Cave Entrance')
  )
    return layer.storage === 'journals' ? 'notes' : 'explore'
  const type = layer.typeIn?.[0] ?? ''
  if (/Ore|Coal|Sulfur|Quartz|Crystal|Chromite|Soralite|Paloxite/.test(type)) return 'ores'
  return 'gather'
}

export function buildLayers(data: GameData): MapLayer[] {
  const layers: Array<Omit<MapLayer, 'group'>> = [...baseLayers]
  for (const type of new Set(data.effigies.map((item) => item.type).filter(Boolean))) {
    if (!type) continue
    layers.push({
      id: `effigy-${slug(type)}`,
      label: `${type} Effigy`,
      color: effigyColors[type] ?? '#86efac',
      storage: 'effigies',
      typeIn: [type],
    })
  }
  for (const type of new Set(data.collectibles.map((item) => item.type).filter(Boolean))) {
    if (!type) continue
    layers.push({
      id: `loot-${slug(type)}`,
      label: type,
      color: lootColors[type] ?? (/^Egg/.test(type) ? '#a3e635' : '#94a3b8'),
      storage: 'collectibles',
      typeIn: [type],
    })
  }
  return layers.map((layer) => ({ ...layer, group: groupFor(layer) }))
}

export function layerItems(data: GameData, layer: MapLayer) {
  const source = data[layer.storage]
  return source.filter((item) => {
    if (layer.typeIn && !layer.typeIn.includes(item.type ?? '')) return false
    if (layer.kindIn && !layer.kindIn.includes(item.kind ?? '')) return false
    return true
  })
}

// ── World Tree layers ─────────────────────────────────────────────────────────

const wtLootColors: Record<string, string> = {
  'World Tree Ore': '#65a30d',
  'Egg (World Tree)': '#a3e635',
  Paloxite: '#818cf8',
  Junk: '#64748b',
  Chest: '#fbbf24',
  'Fruit Tree': '#84cc16',
  'Lifmunk Effigy': '#86efac',
  'Cattiva Effigy': '#fca5a5',
  'Yakumo Effigy': '#fde68a',
}

function wtGroupFor(layer: Omit<MapLayer, 'group'>): string {
  if (['alphas', 'towers'].includes(layer.storage)) return 'wt-combat'
  if (layer.storage === 'travel') return 'wt-travel'
  return 'wt-collectibles'
}

/**
 * Build layer definitions for the World Tree map.
 * Uses the same GameData-compatible shape as Palpagos so `layerItems()` works unmodified.
 */
export function buildWtLayers(data: WtData): MapLayer[] {
  const layers: Array<Omit<MapLayer, 'group'>> = [
    { id: 'wt-alphas', label: 'Alpha Pals', color: '#34d399', storage: 'alphas' },
    { id: 'wt-towers', label: 'Towers', iconKey: 'Towers', color: '#f472b6', storage: 'towers' },
    {
      id: 'wt-journals',
      label: 'Journals',
      iconKey: 'Journals',
      color: '#eab308',
      storage: 'journals',
    },
    {
      id: 'wt-travel-fast',
      label: 'Fast Travel',
      iconKey: 'Fast Travel',
      color: '#22d3ee',
      storage: 'travel',
      typeIn: ['Fast Travel'],
    },
    {
      id: 'wt-travel-watch',
      label: 'Watchtower',
      iconKey: 'Watchtower',
      color: '#67e8f9',
      storage: 'travel',
      typeIn: ['Watchtower'],
    },
  ]

  for (const type of new Set((data.effigies ?? []).map((item) => item.type).filter(Boolean))) {
    if (!type) continue
    layers.push({
      id: `wt-effigy-${slug(type)}`,
      label: `${type} Effigy`,
      color: effigyColors[type] ?? '#86efac',
      storage: 'effigies',
      typeIn: [type],
    })
  }

  // Dynamically add one layer per collectible type present in WT data
  for (const type of new Set((data.collectibles ?? []).map((item) => item.type).filter(Boolean))) {
    if (!type) continue
    layers.push({
      id: `wt-loot-${slug(type)}`,
      label: type,
      color: wtLootColors[type] ?? (/^Egg/.test(type) ? '#a3e635' : '#94a3b8'),
      storage: 'collectibles',
      typeIn: [type],
    })
  }

  return layers.map((layer) => ({ ...layer, group: wtGroupFor(layer) }))
}
