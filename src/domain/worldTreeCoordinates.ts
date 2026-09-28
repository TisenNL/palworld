/**
 * World Tree map projection, matching paldb.cc's real tile pyramid
 * (same CRS.Simple linear system as Palpagos, 512px tiles, native zoom 0-4).
 *
 * Constants reverse-engineered from paldb.cc's own map config for
 * The World Tree (perPixel=1335.144531, hardcoded ingame start offsets).
 */

import type { Point } from './coordinates'

export const wtProjection = {
  tileSize: 512,
  worldZoom: 4,
  minTileZoom: 0,
  maxTileZoom: 4,
  width: 512 * 2 ** 4,
  height: 512 * 2 ** 4,
  transformXPixel: 256.0000000479349,
  ingameXStart: -648.7,
  transformYPixel: 256.0000000479349,
  ingameYStart: 127.7,
} as const

/** Convert World Tree in-game (x, y) to image-space pixel (x, y). */
export function wtGameToImage(x: number, y: number): Point {
  const scaleX = (y + wtProjection.ingameXStart) / wtProjection.transformXPixel
  const scaleY = (x + wtProjection.ingameYStart) / wtProjection.transformYPixel
  return {
    x: scaleY * wtProjection.width,
    y: (1 - scaleX) * wtProjection.height,
  }
}

/** Convert World Tree image-space pixel (x, y) back to in-game (x, y). */
export function wtImageToGame(x: number, y: number): Point {
  const scaleY = x / wtProjection.width
  const scaleX = 1 - y / wtProjection.height
  return {
    x: scaleY * wtProjection.transformYPixel - wtProjection.ingameYStart,
    y: scaleX * wtProjection.transformXPixel - wtProjection.ingameXStart,
  }
}
