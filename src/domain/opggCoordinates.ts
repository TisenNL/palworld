/**
 * Sistema de coordenadas exato do op.gg/palworld/map.
 * Reverse-engineered de 02vzr4rrfn1be.js e 1ktykfxkyh0pz.js do op.gg.
 *
 * O Leaflet usa CRS.Simple com WORLD_SIZE=256.
 * As coordenadas do points.json são em Unreal Engine 5 units (cm).
 * As coordenadas "ipos" são as do pause menu do jogo (metros aprox.).
 */

/** Tamanho do mundo no espaço Leaflet (WORLD_SIZE). */
export const WORLD_SIZE = 256

/**
 * Leaflet maxBounds: [[-280, -24], [24, 280]]
 * = [[-WORLD_SIZE-24, -24], [24, WORLD_SIZE+24]]
 */
export const MAP_BOUNDS: [[number, number], [number, number]] = [
  [-(WORLD_SIZE + 24), -24],
  [24, WORLD_SIZE + 24],
]

/** Bounds UE5 do mapa Palpagos Islands. */
export const MAP_WINDOW_PALPAGOS = {
  minX: -1_099_400,
  maxX: 349_400,
  minY: -724_400,
  maxY: 724_400,
} as const

/** Bounds UE5 do mapa The World Tree. */
export const MAP_WINDOW_WORLD_TREE = {
  minX: 347_351.5,
  maxX: 689_148.5,
  minY: -818_197,
  maxY: -476_400,
} as const

export type MapWindow = typeof MAP_WINDOW_PALPAGOS

export type MapZone = 'palpagos' | 'world-tree'

/** Retorna o mapWindow correto para cada zona. */
export function getMapWindow(zone: MapZone): MapWindow {
  return zone === 'world-tree' ? MAP_WINDOW_WORLD_TREE : MAP_WINDOW_PALPAGOS
}

/**
 * Converte coordenadas UE5 (gameX, gameY) para LatLng do Leaflet CRS.Simple.
 * Fórmula exata do op.gg: toLatLng() em 1ktykfxkyh0pz.js
 *
 * @param mapWindow - Bounds UE5 do mapa (Palpagos ou World Tree)
 * @param gameX - Coordenada X UE5 (l[0] do points.json)
 * @param gameY - Coordenada Y UE5 (l[1] do points.json)
 * @returns [lat, lng] no sistema Leaflet CRS.Simple
 */
export function toLatLng(
  mapWindow: MapWindow,
  gameX: number,
  gameY: number,
): [number, number] {
  const n = (gameY - mapWindow.minY) / (mapWindow.maxY - mapWindow.minY)
  const lat = -(WORLD_SIZE * ((mapWindow.maxX - gameX) / (mapWindow.maxX - mapWindow.minX)))
  const lng = WORLD_SIZE * n
  return [lat, lng]
}

/**
 * Detecta se um ponto UE5 pertence ao mapa World Tree.
 * Fórmula exata do op.gg: isTreePoint() em 1ktykfxkyh0pz.js
 */
export function isTreePoint(gameX: number, gameY: number): boolean {
  return (
    gameX >= MAP_WINDOW_WORLD_TREE.minX &&
    gameX <= MAP_WINDOW_WORLD_TREE.maxX &&
    gameY >= MAP_WINDOW_WORLD_TREE.minY &&
    gameY <= MAP_WINDOW_WORLD_TREE.maxY
  )
}

/**
 * Resultado da conversão de coordenadas UE5 → pause menu in-game.
 */
export interface IngamePoint {
  ingameX: number
  ingameY: number
  ingameZ: number
}

/**
 * Converte coordenadas UE5 brutas para coordenadas do pause menu do jogo.
 * Fórmula exata do op.gg extraída de 1ktykfxkyh0pz.js.
 *
 * @param gameX - Coordenada X UE5 (l[0])
 * @param gameY - Coordenada Y UE5 (l[1])
 * @param gameZ - Coordenada Z UE5 (l[2])
 */
export function toIngamePoint(gameX: number, gameY: number, gameZ: number): IngamePoint {
  return {
    ingameX: Math.round((gameY - 158_000) / 459),
    ingameY: Math.round((gameX - -123_888) / 459),
    ingameZ: Math.round(gameZ / 100),
  }
}

/**
 * Converte coordenadas do pause menu para UE5.
 * Inversa de toIngamePoint.
 */
export function toGamePoint(ingameX: number, ingameY: number): { gameX: number; gameY: number } {
  return {
    gameX: 459 * ingameY + -123_888,
    gameY: 459 * ingameX + 158_000,
  }
}

/**
 * Formata coordenadas no estilo op.gg: "X 123 · Y -456 · Z 78m"
 */
export function formatIngameCoords(ingameX: number, ingameY: number, ingameZ?: number): string {
  const parts = [`X ${ingameX}`, `Y ${ingameY}`]
  if (ingameZ != null && !Number.isNaN(ingameZ)) parts.push(`Z ${ingameZ}m`)
  return parts.join(' · ')
}

/**
 * Converte coordenadas Leaflet LatLng de volta para coordenadas in-game (pause menu).
 * Usado no handler de mousemove para exibir coords do cursor.
 *
 * @param lat - Leaflet lat (negativo no Leaflet CRS.Simple)
 * @param lng - Leaflet lng
 * @param zone - Mapa ativo
 */
export function latLngToIngame(lat: number, lng: number, zone: MapZone): IngamePoint {
  const mw = getMapWindow(zone)
  // Inversa de toLatLng:
  // lat = -(WORLD_SIZE * (maxX - gameX) / (maxX - minX))
  // lng = WORLD_SIZE * (gameY - minY) / (maxY - minY)
  const gameX = mw.maxX - (-lat / WORLD_SIZE) * (mw.maxX - mw.minX)
  const gameY = (lng / WORLD_SIZE) * (mw.maxY - mw.minY) + mw.minY
  return toIngamePoint(gameX, gameY, 0)
}

/**
 * Parses a coordinate string like "-612, -17" into an {x, y} point.
 * Returns null if the string is not parseable.
 */
export function parseCoordinates(text: string): { x: number; y: number } | null {
  const match = text.trim().match(/(-?\d+(?:[.,]\d+)?)\s*[,;\s]\s*(-?\d+(?:[.,]\d+)?)/)
  if (!match || match[1] === undefined || match[2] === undefined) return null
  const x = Number(match[1].replace(',', '.'))
  const y = Number(match[2].replace(',', '.'))
  return Number.isFinite(x) && Number.isFinite(y) ? { x, y } : null
}
