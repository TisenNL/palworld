/**
 * Tipos TypeScript para os markers normalizados do op.gg.
 * Gerados pelo script scripts/convert_opgg_points.mjs.
 */

import { z } from 'zod'

// ── Marker schema ──────────────────────────────────────────────────────────────

export const markerSchema = z.object({
  /** ID estável: "{type}:{lat.toFixed(4)}:{lng.toFixed(4)}" */
  id: z.string(),
  /** Tipo do marcador (ex: "LifmunkEffigy", "FieldBoss", "Eggs") */
  type: z.string(),
  /** Grupo de categorias (collectibles, eggs, enemies, fishing, locations, mine, npc, oilrig, resources) */
  group: z.string(),
  /** Subtipo (ex: "Carbunclo" para efígie, "grass" para ovo) */
  subtype: z.string().nullable().optional(),
  /** Latitude no Leaflet CRS.Simple */
  lat: z.number(),
  /** Longitude no Leaflet CRS.Simple */
  lng: z.number(),
  /** Coordenada X UE5 (cm) */
  gameX: z.number(),
  /** Coordenada Y UE5 (cm) */
  gameY: z.number(),
  /** Coordenada Z UE5 (cm) */
  gameZ: z.number(),
  /** Coordenada X do pause menu do jogo */
  ingameX: z.number(),
  /** Coordenada Y do pause menu do jogo */
  ingameY: z.number(),
  /** Altitude Z do pause menu (em metros) */
  ingameZ: z.number(),
  /** Campos extras opcionais (name, level, id, etc.) */
  extra: z.record(z.string(), z.unknown()).optional(),
})

export type Marker = z.infer<typeof markerSchema>

export const markersSchema = z.array(markerSchema)

// ── Counts schema ──────────────────────────────────────────────────────────────

export const markerCountsSchema = z.object({
  palpagos: z.record(z.string(), z.number()),
  worldtree: z.record(z.string(), z.number()),
})

export type MarkerCounts = z.infer<typeof markerCountsSchema>

// ── Zone ──────────────────────────────────────────────────────────────────────

export type MapZone = 'palpagos' | 'world-tree'

// ── Groups ────────────────────────────────────────────────────────────────────

export const GROUPS = [
  'collectibles',
  'eggs',
  'enemies',
  'fishing',
  'locations',
  'mine',
  'npc',
  'oilrig',
  'resources',
] as const

export type GroupId = (typeof GROUPS)[number]

export const GROUP_LABELS: Record<GroupId, string> = {
  collectibles: 'Collectibles',
  eggs:         'Eggs',
  enemies:      'Enemies',
  fishing:      'Fishing & Salvage',
  locations:    'Locations',
  mine:         'Mining',
  npc:          'NPCs',
  oilrig:       'Oil Rig',
  resources:    'Resources',
}

// ── Type labels ───────────────────────────────────────────────────────────────

/** Human-readable label for each marker type (+ subtype when relevant). */
export function markerTypeLabel(type: string, subtype?: string | null): string {
  const effigyLabels: Record<string, string> = {
    Carbunclo:     'Lifmunk Effigy',
    SheepBall:     'Lamball Effigy',
    Penguin:       'Pengullet Effigy',
    IceCrocodile:  'Munchill Effigy',
    FlameBambi:    'Rooby Effigy',
    LeafMomonga:   'Herbil Effigy',
    Monkey:        'Tanzee Effigy',
    NegativeKoala: 'Depresso Effigy',
    PinkCat:       'Cattiva Effigy',
    LazyDragon:    'Relaxaurus Effigy',
    Mutant:        'Lunaris Effigy',
    GuardianDog:   'Yakumo Effigy',
  }
  const eggLabels: Record<string, string> = {
    grass:       'Grassland Egg',
    desert:      'Desert Egg',
    volcano:     'Volcano Egg',
    snow:        'Ice Egg',
    sakurajima:  'Sakura Egg',
    darkIsland:  'Dark Egg',
    skyIsland:   'Sky Island Egg',
    worldTree:   'World Tree Egg',
  }
  const typeLabels: Record<string, string> = {
    LifmunkEffigy:    subtype ? (effigyLabels[subtype] ?? `${subtype} Effigy`) : 'Effigy',
    LootTower:        'Ancient Ruin',
    Note:             'Journal',
    Eggs:             subtype ? (eggLabels[subtype] ?? subtype) : 'Egg',
    BossTower:        subtype ? `${subtype.replace('Boss', '')} Boss Tower`.trim() : 'Boss Tower',
    FieldBoss:        subtype ? (subtype.replace(/^BOSS_/, '')) : 'Field Boss',
    Bounty:           'Bounty',
    Predator:         'Predator',
    EnemyCamp:        'Enemy Camp',
    AntiAir:          'Anti-Air Turret',
    Incident:         'Incident',
    FastTravels:      'Fast Travel',
    WatchTower:       'Watchtower',
    Dungeon:          'Dungeon',
    CaveEntrance:     'Cave Entrance',
    Respawn:          'Respawn Point',
    SkylandWarpAltar: 'Skyland Warp Altar',
    Home:             'Home Point',
    RegionName:       'Region',
    TreasureMap:      'Treasure Map',
    HeatArea:         'Heat Area',
    Quest:            'Quest',
    OreMetal:         'Metal Ore',
    OreCoal:          'Coal',
    OreQuartz:        'Pure Quartz',
    OreQuartzCluster: 'Quartz Cluster',
    OreSulfur:        'Sulfur',
    Chromites:        'Chromite',
    RainbowCrystal:   'Rainbow Crystal',
    SkyIslandOre:     'Sky Island Ore',
    WorldTreeOre:     'World Tree Ore',
    HardWood:         'Hardwood',
    AncientLava:      'Ancient Lava',
    AncientWood:      'Ancient Wood',
    AncientBeastBone: 'Ancient Beast Bone',
    Chestbox:         'Chest',
    ElementTreasure:  'Element Chest',
    Supply:           'Supply Drop',
    Junk:             'Junk Pile',
    SkillFruits:      'Skill Fruit',
    Peach:            'Kinship Peach',
    BeautifulFlower:  'Beautiful Flower',
    CrudeOil:         'Crude Oil',
    NightStone:       'Night Stone',
    FishingSpot:      'Fishing Spot',
    RareFishingSpot:  'Rare Fishing Spot',
    Salvage:          'Salvage',
    NpcSalesPerson:   'Wandering Merchant',
    NpcPalDealer:     'Pal Merchant',
    NpcDarkTrader:    'Black Marketeer',
    NpcMedalTrader:   'Medal Merchant',
    NpcPalDisplay:    'Pal Display',
    NpcEmote:         'Emote NPC',
    NpcPresenter:     'Presenter',
    NpcBountyTrader:  'Bounty Trader',
    NpcOther:         'NPC',
  }
  return typeLabels[type] ?? type
}

export function markerFilterKey(marker: Pick<Marker, 'type' | 'group' | 'subtype'>): string {
  if (marker.type === 'LifmunkEffigy' || marker.type === 'Eggs') {
    return `${marker.type}:${marker.subtype ?? ''}`
  }
  if (marker.type === 'Chestbox') {
    const oilRigKind = marker.group === 'oilrig' && marker.subtype === 'oilrigMiniGoal' ? 'goal' : 'chest'
    return `${marker.type}:${marker.group}:${oilRigKind}`
  }
  return marker.type
}

export function markerFilterLabel(key: string): string {
  const [type, scope, subtype] = key.split(':', 3)
  if (type === 'Chestbox') {
    if (scope === 'oilrig' && subtype === 'goal') return 'Oil Rig Goal'
    if (scope === 'oilrig') return 'Oil Rig Chest'
    return 'Chest'
  }
  const resolvedSubtype = type === 'LifmunkEffigy' || type === 'Eggs' ? scope : null
  return markerTypeLabel(type, resolvedSubtype)
}

/** Returns a display name for a marker, using name/level from extra when available. */
export function markerDisplayName(marker: Marker): string {
  const extra = marker.extra ?? {}
  const name = typeof extra.name === 'string' ? extra.name : null
  const level = typeof extra.level === 'number' ? extra.level : null
  const base = markerTypeLabel(marker.type, marker.subtype ?? null)

  if (marker.type === 'FieldBoss' && name && level != null) {
    return `Lv.${level} ${name.replace(/^BOSS_/, '')}`
  }
  if (marker.type === 'Bounty' && name && level != null) {
    return `Lv.${level} ${name.replace(/^BOSS_/, '')}`
  }
  if (name) return name
  return base
}
