/**
 * Palpagos Islands map projection, matching paldb.cc's real tile pyramid.
 * paldb.cc uses Leaflet CRS.Simple (flat, linear) — not Web Mercator —
 * with 512px webp tiles, native zoom 0-4 (16x16 tiles at z4 = 8192px image).
 *
 * The in-game (x, y) shown on the pause menu ("ipos") maps linearly to
 * image pixels via constants reverse-engineered from paldb.cc's own map
 * config (transform_x_pixel/ingame_x_start derived from its landscape
 * real-position bounds and perPixel=459 scale factor).
 */
export const mapProjection = {
  tileSize: 512,
  worldZoom: 4,
  minTileZoom: 0,
  maxTileZoom: 4,
  width: 512 * 2 ** 4,
  height: 512 * 2 ** 4,
  transformXPixel: 3156.4270152505446,
  ingameXStart: 2125.2984749455336,
  transformYPixel: 3156.4270152505446,
  ingameYStart: 1922.4400871459695,
} as const

export interface Point {
  x: number
  y: number
}

export function parseCoordinates(text: string): Point | null {
  const match = text.trim().match(/(-?\d+(?:[.,]\d+)?)\s*[,;\s]\s*(-?\d+(?:[.,]\d+)?)/)
  if (!match || match[1] === undefined || match[2] === undefined) return null
  const x = Number(match[1].replace(',', '.'))
  const y = Number(match[2].replace(',', '.'))
  return Number.isFinite(x) && Number.isFinite(y) ? { x, y } : null
}

export function gameToImage(x: number, y: number): Point {
  const scaleX = (y + mapProjection.ingameXStart) / mapProjection.transformXPixel
  const scaleY = (x + mapProjection.ingameYStart) / mapProjection.transformYPixel
  return {
    x: scaleY * mapProjection.width,
    y: (1 - scaleX) * mapProjection.height,
  }
}

export function imageToGame(x: number, y: number): Point {
  const scaleY = x / mapProjection.width
  const scaleX = 1 - y / mapProjection.height
  return {
    x: scaleY * mapProjection.transformYPixel - mapProjection.ingameYStart,
    y: scaleX * mapProjection.transformXPixel - mapProjection.ingameXStart,
  }
}

/**
 * Format coordinates in the op.gg style: "X -612 · Y -17 · Z -17m"
 * If z is not available, it will be omitted.
 */
export function formatCoordinatesOpgg(x: number, y: number, z?: number | null): string {
  const formattedX = Math.round(x).toString()
  const formattedY = Math.round(y).toString()
  const parts = [`X ${formattedX}`, `Y ${formattedY}`]
  
  if (z != null && !Number.isNaN(z)) {
    const formattedZ = Math.round(z).toString()
    parts.push(`Z ${formattedZ}m`)
  }
  
  return parts.join(' · ')
}
