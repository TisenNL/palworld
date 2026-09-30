/**
 * Renomeia tiles de public/opgg-map-tiles/{map}/z{z}/x{col}y{row}.webp
 * para public/opgg-map-tiles/{map}/{z}-{col}-{row}.webp (flat, sem subpastas)
 * Compatível com o template Leaflet TileLayer: "{z}-{x}-{y}.webp"
 */
import { readdirSync, renameSync, rmdirSync, existsSync } from 'fs'
import { resolve, join } from 'path'

const TILES_BASE = resolve('./public/opgg-map-tiles')
const MAPS = ['palpagos', 'world-tree']

let totalMoved = 0

for (const map of MAPS) {
  const mapDir = join(TILES_BASE, map)
  if (!existsSync(mapDir)) { console.warn(`Skip (not found): ${mapDir}`); continue }

  // List z{n} subdirs
  const zDirs = readdirSync(mapDir).filter(n => /^z\d+$/.test(n))
  for (const zDir of zDirs) {
    const z = Number(zDir.slice(1))
    const zPath = join(mapDir, zDir)
    const files = readdirSync(zPath).filter(f => f.endsWith('.webp'))
    for (const file of files) {
      // file = x{col}y{row}.webp
      const m = file.match(/^x(\d+)y(\d+)\.webp$/)
      if (!m) { console.warn(`Unexpected filename: ${file}`); continue }
      const [, col, row] = m
      const src = join(zPath, file)
      const dst = join(mapDir, `${z}-${col}-${row}.webp`)
      renameSync(src, dst)
      totalMoved++
    }
    // Remove empty dir
    try { rmdirSync(zPath) } catch {}
  }
  console.log(`[${map}] Done`)
}

console.log(`\nTotal tiles renamed: ${totalMoved}`)
