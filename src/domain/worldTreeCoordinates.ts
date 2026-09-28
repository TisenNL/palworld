/**
 * World Tree map projection.
 *
 * The World Tree is a dungeon-interior zone in Palworld 1.0.
 * It uses a SIMPLE LINEAR projection — not Web Mercator — because it
 * is a self-contained interior space, not a curved planet surface.
 *
 * In-game coordinate bounds (from wiki.gg / allthings.how research):
 *   X  ~−2200 to  +600   (2800 units wide)
 *   Y  ~  600 to 1800    (1200 units tall)
 *
 * Tile pyramid:
 *   worldZoom = 14  →  total image = 256 × 2¹⁴ = 4,194,304 px
 *   Same tileSize/zoom structure as the main map, just smaller worldZoom.
 *
 * Conversion:
 *   imageX = (gameX − originX) × scaleX
 *   imageY = (gameY − originY) × scaleY
 */

import type { Point } from './coordinates'

export const wtProjection = {
  tileSize:    256,
  worldZoom:   14,
  minTileZoom:  8,
  maxTileZoom: 14,

  /** Full image width/height at worldZoom 14 (256 × 2¹⁴). */
  width:  256 * (2 ** 14),   // 4,194,304
  height: 256 * (2 ** 14),

  /**
   * In-game coord that maps to image pixel 0 on each axis.
   * Provides a ~200-unit margin beyond the known data extents.
   */
  originX: -2400,   // left  edge (game coord)
  originY:   500,   // top   edge (game coord)

  /**
   * Pixels per in-game unit (linear scale).
   *  X range 3000 units  (−2400 to +600)
   *  Y range 1800 units  (500   to 2300)
   *  Scale = 4,194,304 / range
   */
  scaleX: 256 * (2 ** 14) / 3000,   // ≈ 1398 px/unit
  scaleY: 256 * (2 ** 14) / 1800,   // ≈ 2330 px/unit — taller image = more Y resolution
} as const

/** Convert World Tree in-game (x, y) to image-space pixel (x, y). */
export function wtGameToImage(x: number, y: number): Point {
  return {
    x: (x - wtProjection.originX) * wtProjection.scaleX,
    y: (y - wtProjection.originY) * wtProjection.scaleY,
  }
}

/** Convert World Tree image-space pixel (x, y) back to in-game (x, y). */
export function wtImageToGame(x: number, y: number): Point {
  return {
    x: x / wtProjection.scaleX + wtProjection.originX,
    y: y / wtProjection.scaleY + wtProjection.originY,
  }
}
