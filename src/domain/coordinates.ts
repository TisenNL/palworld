export const mapProjection = {
  tileSize: 256,
  worldZoom: 16,
  minTileZoom: 8,
  maxTileZoom: 16,
  width: 256 * 2 ** 16,
  height: 256 * 2 ** 16,
  longitudeScale: 2.0733021e-4,
  longitudeOffset: -0.702925521,
  latitudeScale: 2.07686855e-4,
  latitudeOffset: 0.702599415,
} as const

export interface Point {
  x: number
  y: number
}

export function parseCoordinates(text: string): Point | null {
  const match = text.trim().match(/(-?\d+(?:[.,]\d+)?)\s*[,;\s]\s*(-?\d+(?:[.,]\d+)?)/)
  if (!match) return null
  const x = Number(match[1]!.replace(',', '.'))
  const y = Number(match[2]!.replace(',', '.'))
  return Number.isFinite(x) && Number.isFinite(y) ? { x, y } : null
}

export function gameToImage(x: number, y: number): Point {
  const longitude = mapProjection.longitudeScale * x + mapProjection.longitudeOffset
  const latitude = mapProjection.latitudeScale * y + mapProjection.latitudeOffset
  const latitudeRadians = (latitude * Math.PI) / 180
  return {
    x: ((longitude + 180) / 360) * mapProjection.width,
    y:
      ((1 - Math.log(Math.tan(latitudeRadians) + 1 / Math.cos(latitudeRadians)) / Math.PI) / 2) *
      mapProjection.height,
  }
}

export function imageToGame(x: number, y: number): Point {
  const longitude = (x / mapProjection.width) * 360 - 180
  const n = Math.PI - (2 * Math.PI * y) / mapProjection.height
  const latitude = (180 / Math.PI) * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n)))
  return {
    x: (longitude - mapProjection.longitudeOffset) / mapProjection.longitudeScale,
    y: (latitude - mapProjection.latitudeOffset) / mapProjection.latitudeScale,
  }
}
