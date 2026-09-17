import { describe, expect, it } from 'vitest'

import rawGameData from '../public/data.json'
import rawMapIcons from '../public/map_icons.json'
import { cakeRecipes, calculateCakes, emptyStock, priceDefaults } from '@/domain/cakes'
import { gameToImage, imageToGame, parseCoordinates } from '@/domain/coordinates'
import { buildLayers } from '@/domain/layers'
import { LruCache } from '@/domain/lruCache'
import { gameDataSchema, mapIconsSchema } from '@/types/data'

describe('map coordinates', () => {
  it('accepts positive and negative coordinates', () => {
    expect(parseCoordinates('-16, -339')).toEqual({ x: -16, y: -339 })
    expect(parseCoordinates('9 224')).toEqual({ x: 9, y: 224 })
    expect(parseCoordinates('invalid')).toBeNull()
  })

  it('keeps precision through game, image, and game conversion', () => {
    const image = gameToImage(-16, -339)
    const game = imageToGame(image.x, image.y)
    expect(game.x).toBeCloseTo(-16, 5)
    expect(game.y).toBeCloseTo(-339, 5)
  })
})

describe('ore clusters', () => {
  const gameData = gameDataSchema.parse(rawGameData)
  const mapIcons = mapIconsSchema.parse(rawMapIcons)
  const expected = {
    'Ore Cluster': 31,
    'Coal Cluster': 33,
    'Pure Quartz Cluster': 11,
    'Sulfur Cluster': 8,
  }

  it('contains every cluster published by PalDB', () => {
    for (const [type, count] of Object.entries(expected)) {
      const clusters = gameData.collectibles.filter((item) => item.type === type)
      expect(clusters).toHaveLength(count)
      expect(clusters.every((item) => item.volume && item.volume > 0)).toBe(true)
    }
  })

  it('reproduces documented cluster volumes', () => {
    const volumeNear = (type: string, x: number, y: number): number | null | undefined => {
      const matches = gameData.collectibles.filter((item) => item.type === type)
      return matches.sort(
        (first, second) =>
          Math.hypot(first.x - x, first.y - y) - Math.hypot(second.x - x, second.y - y),
      )[0]?.volume
    }
    expect(volumeNear('Ore Cluster', 71, -403)).toBe(9)
    expect(volumeNear('Pure Quartz Cluster', -212, 249)).toBe(9)
    expect(volumeNear('Sulfur Cluster', -597, -519)).toBe(8)
  })

  it('exposes every cluster in the ores group with an icon', () => {
    const layers = buildLayers(gameData)
    for (const type of Object.keys(expected)) {
      expect(layers).toContainEqual(
        expect.objectContaining({ label: type, group: 'ores', typeIn: [type] }),
      )
      expect(mapIcons.icons[type]).toMatch(/^https:\/\//)
    }
  })
})

describe('cake calculator', () => {
  it('calculates purchases and the honey limit', () => {
    const stock = { ...emptyStock, honey: 10 }
    const result = calculateCakes(100_000, 0, cakeRecipes[0]!, stock, priceDefaults)
    expect(result.honeyCap).toBe(5)
    expect(result.maximum).toBe(5)
    expect(result.purchases.wheat).toBe(75)
  })

  it('uses inventory before spending gold', () => {
    const stock = { ...emptyStock, flour: 5, berry: 8, milk: 7, egg: 8, honey: 2 }
    const result = calculateCakes(0, 0, cakeRecipes[0]!, stock, priceDefaults)
    expect(result.maximum).toBe(1)
    expect(result.spent).toBe(0)
  })
})

describe('LRU cache', () => {
  it('removes the least recently used entry', () => {
    const cache = new LruCache<string, number>(2)
    cache.set('a', 1)
    cache.set('b', 2)
    expect(cache.get('a')).toBe(1)
    cache.set('c', 3)
    expect(cache.has('a')).toBe(true)
    expect(cache.has('b')).toBe(false)
  })
})
