import { describe, it, expect } from 'vitest'
import {
  toLatLng,
  toIngamePoint,
  toGamePoint,
  latLngToIngame,
  isTreePoint,
  formatIngameCoords,
  MAP_WINDOW_PALPAGOS,
} from '../src/domain/opggCoordinates'

// Known points from op.gg data (confirmed from points.json inspection)
// Palpagos: FieldBoss "Faleris Aqua" at gameX=-867561, gameY=-441338, gameZ=18640
// toIngamePoint: ingameX=round((-441338-158000)/459)=round(-1302) = -1302, ingameY=round((-867561+123888)/459)=round(-1619) = -1619

describe('toIngamePoint', () => {
  it('converts Palpagos field boss coords', () => {
    // gameX=-867561, gameY=-441338, gameZ=18640
    // ingameX = round((-441338 - 158000) / 459) = round(-599338/459) = round(-1305.75) = -1306
    // ingameY = round((-867561 + 123888) / 459) = round(-743673/459) = round(-1619.33) = -1619
    const { ingameX, ingameY } = toIngamePoint(-867561, -441338, 18640)
    expect(ingameX).toBe(-1306)
    expect(ingameY).toBe(-1620)
    expect(toIngamePoint(-867561, -441338, 18640).ingameZ).toBe(186)
  })

  it('converts coordinates near origin', () => {
    // gameX=0, gameY=0 → ingameX=round(-158000/459)≈-344, ingameY=round(123888/459)≈270
    const r = toIngamePoint(0, 0, 0)
    expect(r.ingameX).toBe(-344)
    expect(r.ingameY).toBe(270)
    expect(r.ingameZ).toBe(0)
  })
})

describe('toGamePoint / round-trip', () => {
  it('round-trips ingame → game → ingame', () => {
    const ingameX = -612
    const ingameY = -17
    const { gameX, gameY } = toGamePoint(ingameX, ingameY)
    const back = toIngamePoint(gameX, gameY, 0)
    expect(back.ingameX).toBe(ingameX)
    expect(back.ingameY).toBe(ingameY)
  })
})

describe('toLatLng', () => {
  it('maps top-left corner of Palpagos to lat≈0,lng≈0', () => {
    // gameX=maxX, gameY=minY → lat≈0, lng≈0
    const [lat, lng] = toLatLng(MAP_WINDOW_PALPAGOS, MAP_WINDOW_PALPAGOS.maxX, MAP_WINDOW_PALPAGOS.minY)
    expect(lat).toBeCloseTo(0, 3)
    expect(lng).toBeCloseTo(0, 3)
  })

  it('maps bottom-right corner of Palpagos to lat≈-256,lng≈256', () => {
    const [lat, lng] = toLatLng(MAP_WINDOW_PALPAGOS, MAP_WINDOW_PALPAGOS.minX, MAP_WINDOW_PALPAGOS.maxY)
    expect(lat).toBeCloseTo(-256, 3)
    expect(lng).toBeCloseTo(256, 3)
  })

  it('maps center of Palpagos to lat≈-128,lng≈128', () => {
    const centerX = (MAP_WINDOW_PALPAGOS.minX + MAP_WINDOW_PALPAGOS.maxX) / 2
    const centerY = (MAP_WINDOW_PALPAGOS.minY + MAP_WINDOW_PALPAGOS.maxY) / 2
    const [lat, lng] = toLatLng(MAP_WINDOW_PALPAGOS, centerX, centerY)
    expect(lat).toBeCloseTo(-128, 1)
    expect(lng).toBeCloseTo(128, 1)
  })
})

describe('latLngToIngame', () => {
  it('round-trips through game coords', () => {
    const ingameX = -612
    const ingameY = -17
    const { gameX, gameY } = toGamePoint(ingameX, ingameY)
    const [lat, lng] = toLatLng(MAP_WINDOW_PALPAGOS, gameX, gameY)
    const back = latLngToIngame(lat, lng, 'palpagos')
    expect(back.ingameX).toBe(ingameX)
    expect(back.ingameY).toBe(ingameY)
  })
})

describe('isTreePoint', () => {
  it('detects World Tree points', () => {
    // FastTravel "WorldTree_MiddleBoss_1" at l=[628791, -610720, ...]
    expect(isTreePoint(628791, -610720)).toBe(true)
    // WorldTreeOre at l=[408215, -745505, ...]
    expect(isTreePoint(408215, -745505)).toBe(true)
  })

  it('rejects Palpagos points', () => {
    // FieldBoss in Palpagos at l=[-867561, -441338, ...]
    expect(isTreePoint(-867561, -441338)).toBe(false)
    // OreMetal near origin at l=[1231, 947, ...]
    expect(isTreePoint(1231, 947)).toBe(false)
  })
})

describe('formatIngameCoords', () => {
  it('formats with Z', () => {
    expect(formatIngameCoords(-612, -17, 42)).toBe('X -612 · Y -17 · Z 42m')
  })
  it('formats without Z', () => {
    expect(formatIngameCoords(100, 200)).toBe('X 100 · Y 200')
  })
})
