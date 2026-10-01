/**
 * Mapeamento de tipo de marker → URL de ícone e cor do ring.
 * Ícones baixados de https://s-stats-platform-cdn.op.gg para public/opgg-icons/
 */

import type { Marker } from '@/types/opggMarker'

// ── Icon URLs ──────────────────────────────────────────────────────────────

// Effigy subtype → icon file
const EFFIGY_ICONS: Record<string, string> = {
  Carbunclo:     '/opgg-icons/effigies/lifmunk.webp',
  SheepBall:     '/opgg-icons/effigies/lamball.webp',
  Penguin:       '/opgg-icons/effigies/pengullet.webp',
  IceCrocodile:  '/opgg-icons/effigies/munchill.webp',
  FlameBambi:    '/opgg-icons/effigies/rooby.webp',
  LeafMomonga:   '/opgg-icons/effigies/herbil.webp',
  Monkey:        '/opgg-icons/effigies/tanzee.webp',
  NegativeKoala: '/opgg-icons/effigies/depresso.webp',
  PinkCat:       '/opgg-icons/effigies/cattiva.webp',
  LazyDragon:    '/opgg-icons/effigies/relaxaurus.webp',
  Mutant:        '/opgg-icons/effigies/lunaris.webp',
  GuardianDog:   '/opgg-icons/effigies/yakumo.webp',
}

const EGG_ICONS: Record<string, string> = {
  grass:       '/opgg-icons/eggs/grass.webp',
  desert:      '/opgg-icons/eggs/desert.webp',
  volcano:     '/opgg-icons/eggs/fire.webp',
  snow:        '/opgg-icons/eggs/ice.webp',
  sakurajima:  '/opgg-icons/eggs/dragon.webp',
  darkIsland:  '/opgg-icons/eggs/dark.webp',
  skyIsland:   '/opgg-icons/eggs/water.webp',
  worldTree:   '/opgg-icons/eggs/worldtree.webp',
}

const TYPE_ICONS: Record<string, string> = {
  FieldBoss:        '/opgg-icons/markers/field-boss.webp',
  BossTower:        '/opgg-icons/markers/boss-tower.webp',
  Bounty:           '/opgg-icons/markers/bounty.webp',
  Predator:         '/opgg-icons/markers/predator.webp',
  EnemyCamp:        '/opgg-icons/markers/enemy-camp.webp',
  AntiAir:          '/opgg-icons/markers/anti-air.webp',
  Incident:         '/opgg-icons/markers/incident.webp',
  FastTravels:      '/opgg-icons/markers/fast-travel.webp',
  WatchTower:       '/opgg-icons/markers/watch-tower.webp',
  Dungeon:          '/opgg-icons/markers/dungeon.webp',
  LootTower:        '/opgg-icons/markers/loot-tower.webp',
  Note:             '/opgg-icons/markers/note.webp',
  SkillFruits:      '/opgg-icons/markers/skill-fruit.webp',
  FishingSpot:      '/opgg-icons/markers/fishing.webp',
  RareFishingSpot:  '/opgg-icons/markers/fishing.webp',
  Salvage:          '/opgg-icons/markers/salvage.webp',
  Chestbox:         '/opgg-icons/markers/chest.webp',
  Junk:             '/opgg-icons/markers/junk.webp',
  WorldTreeOre:     '/opgg-icons/markers/world-tree-ore.webp',
  Quest:            '/opgg-icons/markers/quest.webp',
  CaveEntrance:     '/opgg-icons/markers/cave-entrance.webp',
  CrudeOil:         '/opgg-icons/markers/crude-oil.webp',
  Home:             '/opgg-icons/markers/home.webp',
  NightStone:       '/opgg-icons/markers/night-stone.webp',
  OreCoal:          '/opgg-icons/markers/ore-coal.webp',
  OreMetal:         '/opgg-icons/markers/ore-metal.webp',
  OreQuartz:        '/opgg-icons/markers/ore-quartz.webp',
  OreQuartzCluster: '/opgg-icons/markers/ore-quartz.webp',
  OreSulfur:        '/opgg-icons/markers/ore-sulfur.webp',
  Peach:            '/opgg-icons/markers/peach.webp',
  RainbowCrystal:   '/opgg-icons/markers/rainbow-crystal.webp',
  Respawn:          '/opgg-icons/markers/respawn.webp',
  SkyIslandOre:     '/opgg-icons/markers/sky-island-ore.webp',
  SkylandWarpAltar: '/opgg-icons/markers/skyland-warp-altar.webp',
  Supply:           '/opgg-icons/markers/supply.webp',
  TreasureMap:      '/opgg-icons/markers/treasure-map.webp',
  Chromites:        '/opgg-icons/markers/chromite.webp',
  ElementTreasure:  '/opgg-icons/markers/element-chest.webp',
  AncientBeastBone: '/opgg-icons/markers/world-tree-ore.webp',
  AncientLava:      '/opgg-icons/markers/crude-oil.webp',
  AncientWood:      '/opgg-icons/resources/hardwood.webp',
  BeautifulFlower:  '/opgg-icons/markers/skill-fruit.webp',
  HeatArea:         '/opgg-icons/markers/incident.webp',
  RegionName:       '/opgg-icons/markers/note.webp',
  NpcSalesPerson:   '/opgg-icons/resources/human.webp',
  NpcPalDealer:     '/opgg-icons/resources/human.webp',
  NpcDarkTrader:    '/opgg-icons/resources/human.webp',
  NpcMedalTrader:   '/opgg-icons/resources/human.webp',
  NpcBountyTrader:  '/opgg-icons/resources/human.webp',
  NpcOther:         '/opgg-icons/resources/human.webp',
  NpcEmote:         '/opgg-icons/resources/human.webp',
  NpcPalDisplay:    '/opgg-icons/resources/human.webp',
  NpcPresenter:     '/opgg-icons/resources/human.webp',
  HardWood:         '/opgg-icons/resources/hardwood.webp',
}

export function getMarkerIconUrl(marker: Marker): string {
  if (marker.type === 'LifmunkEffigy' && marker.subtype) {
    return EFFIGY_ICONS[marker.subtype] ?? '/opgg-icons/effigies/lifmunk.webp'
  }
  if (marker.type === 'Eggs' && marker.subtype) {
    return EGG_ICONS[marker.subtype] ?? '/opgg-icons/eggs/grass.webp'
  }
  return TYPE_ICONS[marker.type] ?? ''
}

export function getFilterIconUrl(filterKey: string): string {
  const [type, scope] = filterKey.split(':', 2)
  return getMarkerIconUrl({
    type,
    group: '',
    subtype: type === 'LifmunkEffigy' || type === 'Eggs' ? scope : undefined,
  } as Marker)
}

// ── Ring / border colors by group ─────────────────────────────────────────

const GROUP_COLORS: Record<string, string> = {
  collectibles: '#a78bfa',  // violet
  eggs:         '#86efac',  // green
  enemies:      '#f87171',  // red
  fishing:      '#38bdf8',  // sky
  locations:    '#34d399',  // emerald
  mine:         '#fb923c',  // orange
  npc:          '#facc15',  // yellow
  oilrig:       '#f59e0b',  // amber
  resources:    '#a3e635',  // lime
}

const TYPE_COLORS: Record<string, string> = {
  FieldBoss:   '#ef4444',
  BossTower:   '#ec4899',
  Bounty:      '#f97316',
  Predator:    '#dc2626',
  FastTravels: '#22d3ee',
  WatchTower:  '#67e8f9',
  Dungeon:     '#94a3b8',
  LootTower:   '#c084fc',
}

export function getMarkerColor(marker: Marker): string {
  return TYPE_COLORS[marker.type] ?? GROUP_COLORS[marker.group] ?? '#6c5ce7'
}

// ── Background color (fill inside the circle) ─────────────────────────────

export function getMarkerBgColor(marker: Marker): string {
  if (marker.group === 'enemies') return 'rgba(8, 14, 28, 0.88)'
  return 'rgba(15, 20, 40, 0.75)'
}

// ── HTML cache (Fix 6) ────────────────────────────────────────────────────
//
// Markers of the same type + subtype + pixelSize + checked + selected state
// always produce identical HTML. Caching avoids ~16 000 string allocations on
// every refreshMarkerIcons call and lets buildLeafletMarker reuse results
// on filter changes where the same marker reappears.
//
// Key: "{type}:{group}:{subtype}:{pixelSize}:{checked 0|1}:{selected 0|1}:{level}"
// The level is included because FieldBoss/BossTower embed it in the badge.

const _htmlCache = new Map<string, string>()

/** Clear the HTML cache — call when pixelSize baseline changes (zone switch). */
export function clearMarkerHtmlCache(): void {
  _htmlCache.clear()
}

// ── HTML for L.divIcon ─────────────────────────────────────────────────────

export function getMarkerHtml(
  marker: Marker,
  pixelSize: number,
  checked: boolean,
  selected = false,
): string {
  const level   = typeof marker.extra?.level === 'number' ? marker.extra.level : null
  // Cache key encodes every dimension that affects the output HTML.
  const cacheKey = `${marker.type}:${marker.group}:${marker.subtype ?? ''}:${pixelSize}:${checked ? 1 : 0}:${selected ? 1 : 0}:${level ?? ''}`

  const cached = _htmlCache.get(cacheKey)
  if (cached !== undefined) return cached

  const iconUrl = getMarkerIconUrl(marker)
  const color   = getMarkerColor(marker)
  const bgColor = getMarkerBgColor(marker)
  const isLarge = ['FieldBoss', 'BossTower', 'FastTravels', 'WatchTower'].includes(marker.type)

  const imageStyle = [
    `width:${pixelSize}px`,
    `height:${pixelSize}px`,
    `border-color:${color}`,
    `background-color:${bgColor}`,
    `display:block`,
    `border-radius:50%`,
    `border:2px solid ${color}`,
    `background-size:75%`,
    `background-repeat:no-repeat`,
    `background-position:center`,
    `box-shadow:0 2px 6px rgba(0,0,0,.6)`,
    iconUrl ? `background-image:url('${iconUrl.replace(/'/g, '%27')}')` : '',
  ].filter(Boolean).join(';')

  const checkedClass  = checked ? ' palworld-map-marker-checked' : ''
  const selectedClass = selected ? ' palworld-map-marker-selected' : ''
  const lgClass       = isLarge ? ' palworld-map-marker-lg' : ''
  const badge        = level != null && (marker.type === 'FieldBoss' || marker.type === 'BossTower')
    ? `<span class="palworld-map-marker-badge">${level}</span>`
    : ''

  const html = `<div class="palworld-map-marker-wrapper${checkedClass}${selectedClass}${lgClass}" style="position:relative;display:inline-block;line-height:0"><span aria-hidden="true" class="palworld-map-marker-image palworld-map-image-silhouette" style="${imageStyle}"></span>${badge}</div>`

  _htmlCache.set(cacheKey, html)
  return html
}
