/**
 * Converte public/opgg-data/points.json (coordenadas UE5) para dois arquivos
 * de markers normalizados com lat/lng Leaflet:
 *   public/opgg-markers-palpagos.json
 *   public/opgg-markers-worldtree.json
 *
 * Também gera public/opgg-marker-counts.json com contagens por tipo e mapa.
 *
 * Re-executável: regenera os arquivos a cada execução.
 *
 * Usage: node scripts/convert_opgg_points.mjs
 */

import { readFileSync, writeFileSync } from 'fs'
import { resolve } from 'path'

// ── Reproduce op.gg coordinate functions (without importing TS) ──────────────

const WORLD_SIZE = 256

const MAP_WINDOW_PALPAGOS = {
  minX: -1_099_400, maxX: 349_400,
  minY: -724_400,   maxY: 724_400,
}
const MAP_WINDOW_WORLD_TREE = {
  minX: 347_351.5, maxX: 689_148.5,
  minY: -818_197,  maxY: -476_400,
}

function isTreePoint(gameX, gameY) {
  return (
    gameX >= MAP_WINDOW_WORLD_TREE.minX && gameX <= MAP_WINDOW_WORLD_TREE.maxX &&
    gameY >= MAP_WINDOW_WORLD_TREE.minY && gameY <= MAP_WINDOW_WORLD_TREE.maxY
  )
}

function toLatLng(mw, gameX, gameY) {
  const n = (gameY - mw.minY) / (mw.maxY - mw.minY)
  const lat = -(WORLD_SIZE * ((mw.maxX - gameX) / (mw.maxX - mw.minX)))
  const lng = WORLD_SIZE * n
  return [lat, lng]
}

function toIngamePoint(gameX, gameY, gameZ) {
  return {
    ingameX: Math.round((gameY - 158_000) / 459),
    ingameY: Math.round((gameX - -123_888) / 459),
    ingameZ: Math.round(gameZ / 100),
  }
}

// ── Group → category definitions (from op.gg index.json) ─────────────────────

const GROUP_DEFS = {
  collectibles: [
    'LifmunkEffigy', 'LootTower', 'Note',
  ],
  eggs: [
    'Eggs',
  ],
  enemies: [
    'BossTower', 'FieldBoss', 'Bounty', 'Predator', 'EnemyCamp', 'AntiAir', 'Incident',
  ],
  fishing: [
    'FishingSpot', 'RareFishingSpot', 'Salvage',
  ],
  locations: [
    'FastTravels', 'Respawn', 'SkylandWarpAltar', 'Home', 'WatchTower',
    'RegionName', 'DungeonFixed', 'DungeonPortal', 'CaveEntrance',
    'TreasureMap', 'HeatArea', 'Quest',
  ],
  mine: [
    'OreMetal', 'OreCoal', 'OreQuartz', 'OreQuartzCluster', 'OreSulfur',
    'Chromites', 'RainbowCrystal', 'SkyIslandOre', 'WorldTreeOre',
    'HardWood', 'AncientLava', 'AncientWood', 'AncientBeastBone',
  ],
  npc: [
    'NpcSalesPerson', 'NpcPalDealer', 'NpcDarkTrader', 'NpcMedalTrader',
    'NpcPalDisplay', 'NpcEmote', 'NpcPresenter', 'NpcBountyTrader', 'NpcOther',
  ],
  oilrig: [
    'Chestbox', // filtered by t = 'oilrig*'
    'ElementTreasure',
  ],
  resources: [
    'Chestbox', // t != oilrig*
    'Supply', 'Junk', 'SkillFruits', 'Peach', 'BeautifulFlower',
    'CrudeOil', 'NightStone',
  ],
}

// Build reverse map: type → group (some types like Chestbox appear in multiple)
const TYPE_TO_GROUP = {}
for (const [group, types] of Object.entries(GROUP_DEFS)) {
  for (const t of types) {
    // Chestbox is split at conversion time by subtype
    if (t === 'Chestbox') continue
    if (!TYPE_TO_GROUP[t]) TYPE_TO_GROUP[t] = group
  }
}

// ── Effigy subtype → display label ──────────────────────────────────────────

const EFFIGY_LABELS = {
  Carbunclo:     'Lifmunk Effigy',
  SheepBall:     'Lamball Effigy',
  Penguin:       'Pengullet Effigy',
  IceCrocodile:  'Munchill Effigy',
  FlameBambi:    'Rooby Effigy',
  LeafMomonga:   'Herbil Effigy',
  Monkey:        'Tanzee Effigy',
  NegativeKoala: 'Depresso Effigy',
  PinkCat:       'Cattiva Effigy',
  LazyDragon:    'Lunaris Effigy',
  Mutant:        'Relaxaurus Effigy',
  GuardianDog:   'Yakumo Effigy',
}

const EGG_LABELS = {
  grass:       'Grassland Egg',
  desert:      'Desert Egg',
  volcano:     'Volcano Egg',
  snow:        'Ice Egg',
  sakurajima:  'Sakura Egg',
  darkIsland:  'Dark Egg',
  skyIsland:   'Sky Island Egg',
  worldTree:   'World Tree Egg',
}

// ── Main conversion ──────────────────────────────────────────────────────────

const ROOT = resolve('.')
const pointsPath  = resolve(ROOT, 'public/opgg-data/points.json')
const outPalpagos = resolve(ROOT, 'public/opgg-markers-palpagos.json')
const outWorldTree= resolve(ROOT, 'public/opgg-markers-worldtree.json')
const outCounts   = resolve(ROOT, 'public/opgg-marker-counts.json')

console.log('Reading points.json...')
const points = JSON.parse(readFileSync(pointsPath, 'utf-8'))

const palpagosMarkers = []
const worldtreeMarkers = []
const counts = { palpagos: {}, worldtree: {} }

/**
 * Id estável e **único**: `{type}:{lat}:{lng}` com 4 casas + sufixo se repetir.
 *
 * Pontos distintos podem cair nas mesmas coordenadas (veio de carvão com Z
 * diferente; duas quests empilhadas). Sem o sufixo eles colapsam num só id e o
 * renderer deduplica por id — o marcador extra fica invisível, a contagem do
 * sidebar não bate com o mapa e o estado de "checked" vira compartilhado.
 */
const usedIds = new Set()

function makeId(type, lat, lng) {
  const base = `${type}:${lat.toFixed(4)}:${lng.toFixed(4)}`
  if (!usedIds.has(base)) {
    usedIds.add(base)
    return base
  }
  let n = 1
  let unique
  do {
    n += 1
    unique = `${base}#${n}`
  } while (usedIds.has(unique))
  usedIds.add(unique)
  return unique
}

function addMarker(type, group, subtype, coords, extra) {
  const [gameX, gameY, gameZ = 0] = coords
  const tree = isTreePoint(gameX, gameY)
  const mw = tree ? MAP_WINDOW_WORLD_TREE : MAP_WINDOW_PALPAGOS
  const [lat, lng] = toLatLng(mw, gameX, gameY)
  const { ingameX, ingameY, ingameZ } = toIngamePoint(gameX, gameY, gameZ)
  const id = makeId(type, lat, lng)
  const zone = tree ? 'worldtree' : 'palpagos'

  const marker = {
    id,
    type,
    group,
    ...(subtype != null ? { subtype } : {}),
    lat: Math.round(lat * 1e6) / 1e6,
    lng: Math.round(lng * 1e6) / 1e6,
    gameX,
    gameY,
    gameZ,
    ingameX,
    ingameY,
    ingameZ,
    ...(extra && Object.keys(extra).length ? { extra } : {}),
  }

  if (tree) {
    worldtreeMarkers.push(marker)
  } else {
    palpagosMarkers.push(marker)
  }

  counts[zone][type] = (counts[zone][type] ?? 0) + 1
}

// ── Process each type ────────────────────────────────────────────────────────

for (const [rawType, items] of Object.entries(points)) {
  if (!Array.isArray(items)) continue

  for (const item of items) {
    // Resolve coords field (most use 'l', BossTower uses 'loc')
    const coords = item.l ?? item.loc
    if (!coords) continue

    switch (rawType) {
      // ── Effigies ────────────────────────────────────────────────────────
      case 'LifmunkEffigy': {
        const subtype = item.t ?? 'Carbunclo'
        addMarker('LifmunkEffigy', 'collectibles', subtype, coords, {
          label: EFFIGY_LABELS[subtype] ?? `${subtype} Effigy`,
        })
        break
      }

      // ── Loot Tower (Ancient Ruins) ───────────────────────────────────
      case 'LootTower':
        addMarker('LootTower', 'collectibles', null, coords, {})
        break

      // ── Notes / Journals ─────────────────────────────────────────────
      case 'Note':
        addMarker('Note', 'collectibles', null, coords, {
          name: item.name,
        })
        break

      // ── Eggs ──────────────────────────────────────────────────────────
      case 'Eggs': {
        const subtype = item.t ?? 'grass'
        addMarker('Eggs', 'eggs', subtype, coords, {
          label: EGG_LABELS[subtype] ?? subtype,
          key: item.k,
        })
        break
      }

      // ── Boss Towers ───────────────────────────────────────────────────
      case 'BossTower': {
        const bossType = (item.bossType ?? '').replace('EPalBossType::', '')
        addMarker('BossTower', 'enemies', bossType, coords, {
          ref: item.ref,
          name: bossType,
        })
        break
      }

      // ── Field Bosses ──────────────────────────────────────────────────
      case 'FieldBoss':
        addMarker('FieldBoss', 'enemies', item.id, coords, {
          name: item.name ?? item.id,
          level: item.lv,
          id: item.id,
        })
        break

      // ── Bounties ──────────────────────────────────────────────────────
      case 'Bounty':
        addMarker('Bounty', 'enemies', null, coords, {
          name: item.name,
          level: item.lv,
        })
        break

      // ── Predators ─────────────────────────────────────────────────────
      case 'Predator':
        addMarker('Predator', 'enemies', item.id, coords, {
          name: item.id,
          level: item.lv,
        })
        break

      // ── Enemy Camps ───────────────────────────────────────────────────
      case 'EnemyCamp':
        addMarker('EnemyCamp', 'enemies', item.t, coords, {})
        break

      // ── Anti-Air ──────────────────────────────────────────────────────
      case 'AntiAir':
        addMarker('AntiAir', 'enemies', null, coords, {})
        break

      // ── Incidents ─────────────────────────────────────────────────────
      case 'Incident':
        addMarker('Incident', 'enemies', null, coords, {})
        break

      // ── Fast Travel ───────────────────────────────────────────────────
      case 'FastTravels':
        addMarker('FastTravels', 'locations', null, coords, {
          name: item.name,
        })
        break

      // ── Watch Tower ───────────────────────────────────────────────────
      case 'WatchTower':
        addMarker('WatchTower', 'locations', null, coords, {
          name: item.name,
        })
        break

      // ── Dungeons ──────────────────────────────────────────────────────
      case 'DungeonPortal':
      case 'DungeonFixed':
        addMarker('Dungeon', 'locations', rawType === 'DungeonFixed' ? 'fixed' : 'portal', coords, {
          name: item.name,
        })
        break

      // ── Cave Entrance ─────────────────────────────────────────────────
      case 'CaveEntrance':
        addMarker('CaveEntrance', 'locations', null, coords, {
          id: item.id,
        })
        break

      // ── Respawn ───────────────────────────────────────────────────────
      case 'Respawn':
        addMarker('Respawn', 'locations', null, coords, {})
        break

      // ── Skyland Warp Altar ────────────────────────────────────────────
      case 'SkylandWarpAltar':
        addMarker('SkylandWarpAltar', 'locations', null, coords, {})
        break

      // ── Home ──────────────────────────────────────────────────────────
      case 'Home':
        addMarker('Home', 'locations', null, coords, {})
        break

      // ── Region Names ──────────────────────────────────────────────────
      case 'RegionName':
        addMarker('RegionName', 'locations', null, coords, {
          id: item.id,
        })
        break

      // ── Treasure Map ──────────────────────────────────────────────────
      case 'TreasureMap':
        addMarker('TreasureMap', 'locations', null, coords, {})
        break

      // ── Heat Area ─────────────────────────────────────────────────────
      case 'HeatArea':
        addMarker('HeatArea', 'locations', null, coords, {
          extent: item.extent,
          day: item.day,
          night: item.night,
        })
        break

      // ── Quest ─────────────────────────────────────────────────────────
      case 'Quest':
        addMarker('Quest', 'locations', null, coords, {
          name: item.name,
        })
        break

      // ── Ore types ─────────────────────────────────────────────────────
      case 'OreMetal':
      case 'OreCoal':
      case 'OreQuartz':
      case 'OreQuartzCluster':
      case 'OreSulfur':
      case 'Chromites':
      case 'RainbowCrystal':
      case 'SkyIslandOre':
      case 'WorldTreeOre':
      case 'HardWood':
      case 'AncientLava':
      case 'AncientWood':
      case 'AncientBeastBone':
        addMarker(rawType, 'mine', null, coords, {})
        break

      // ── Chestbox (split oilrig vs regular) ────────────────────────────
      case 'Chestbox': {
        const t = item.t ?? ''
        const isOilrig = t.startsWith('oilrig')
        addMarker('Chestbox', isOilrig ? 'oilrig' : 'resources', t || null, coords, {
          chestType: t,
        })
        break
      }

      // ── Element Treasure ──────────────────────────────────────────────
      case 'ElementTreasure':
        addMarker('ElementTreasure', 'oilrig', item.t, coords, {})
        break

      // ── Supply ────────────────────────────────────────────────────────
      case 'Supply':
        addMarker('Supply', 'resources', item.t, coords, {})
        break

      // ── Junk ──────────────────────────────────────────────────────────
      case 'Junk':
        addMarker('Junk', 'resources', null, coords, {})
        break

      // ── Skill Fruits ──────────────────────────────────────────────────
      case 'SkillFruits':
        addMarker('SkillFruits', 'resources', item.t, coords, {})
        break

      // ── Peach ─────────────────────────────────────────────────────────
      case 'Peach':
        addMarker('Peach', 'resources', null, coords, {})
        break

      // ── Beautiful Flower ──────────────────────────────────────────────
      case 'BeautifulFlower':
        addMarker('BeautifulFlower', 'resources', null, coords, {})
        break

      // ── Crude Oil ─────────────────────────────────────────────────────
      case 'CrudeOil':
        addMarker('CrudeOil', 'resources', null, coords, {})
        break

      // ── Night Stone ───────────────────────────────────────────────────
      case 'NightStone':
        addMarker('NightStone', 'resources', null, coords, {})
        break

      // ── Fishing Spots ─────────────────────────────────────────────────
      case 'FishingSpot':
        addMarker('FishingSpot', 'fishing', item.type ?? 'Normal', coords, {})
        break

      case 'RareFishingSpot':
        addMarker('RareFishingSpot', 'fishing', item.type ?? 'Rare', coords, {})
        break

      // ── Salvage ───────────────────────────────────────────────────────
      case 'Salvage':
        addMarker('Salvage', 'fishing', item.type, coords, {})
        break

      // ── NPCs ──────────────────────────────────────────────────────────
      case 'NpcSalesPerson':
      case 'NpcPalDealer':
      case 'NpcDarkTrader':
      case 'NpcMedalTrader':
      case 'NpcPalDisplay':
      case 'NpcEmote':
      case 'NpcPresenter':
      case 'NpcBountyTrader':
      case 'NpcOther':
        addMarker(rawType, 'npc', null, coords, {
          name: item.name,
          level: item.lv,
        })
        break

      default:
        // Skip unknown types silently
        break
    }
  }
}

// ── Write output ─────────────────────────────────────────────────────────────

writeFileSync(outPalpagos, JSON.stringify(palpagosMarkers, null, 0), 'utf-8')
writeFileSync(outWorldTree, JSON.stringify(worldtreeMarkers, null, 0), 'utf-8')
writeFileSync(outCounts, JSON.stringify(counts, null, 2), 'utf-8')

// ── Report ────────────────────────────────────────────────────────────────────

console.log(`\nPalpagos: ${palpagosMarkers.length} markers`)
console.log(`World Tree: ${worldtreeMarkers.length} markers`)
console.log(`Total: ${palpagosMarkers.length + worldtreeMarkers.length}`)

console.log('\n── Palpagos counts (selected) ──')
const pKeys = Object.entries(counts.palpagos).sort((a,b) => b[1]-a[1])
for (const [k, n] of pKeys) {
  if (n > 50) console.log(`  ${k}: ${n}`)
}

console.log('\n── World Tree counts (selected) ──')
const wtKeys = Object.entries(counts.worldtree).sort((a,b) => b[1]-a[1])
for (const [k, n] of wtKeys) {
  if (n > 0) console.log(`  ${k}: ${n}`)
}

console.log('\n── Key verification ──')
const palEffigy = counts.palpagos['LifmunkEffigy'] ?? 0
const wtEgg = counts.worldtree['Eggs'] ?? 0
console.log(`  Lifmunk Effigy (Palpagos): ${palEffigy} (expected 407 total effigies)`)
console.log(`  Eggs (World Tree):          ${wtEgg} (expected 30 World Tree Eggs)`)
console.log(`  LootTower (Palpagos):       ${counts.palpagos['LootTower'] ?? 0} (expected 106)`)

console.log('\n✅ Done!')
console.log(`  ${outPalpagos}`)
console.log(`  ${outWorldTree}`)
console.log(`  ${outCounts}`)
