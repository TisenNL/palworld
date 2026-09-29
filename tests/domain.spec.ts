import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { describe, expect, it, vi } from 'vitest'

vi.mock('primevue/usetoast', () => ({
  useToast: () => ({ add: vi.fn() }),
}))

vi.mock('primevue/button', () => ({
  default: {
    name: 'Button',
    template: '<button><slot /></button>',
  },
}))

vi.mock('primevue/inputnumber', () => ({
  default: {
    name: 'InputNumber',
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<input :value="modelValue" />',
  },
}))

import rawGameData from '../public/data.json'
import rawMapIcons from '../public/map_icons.json'
import rawWtData from '../public/wt-data.json'
import { cakeRecipes, calculateCakes, emptyStock, priceDefaults } from '@/domain/cakes'
import CakesView from '@/views/CakesView.vue'
import { gameToImage, imageToGame, parseCoordinates } from '@/domain/coordinates'
import { buildLayers, buildWtLayers } from '@/domain/layers'
import { LruCache } from '@/domain/lruCache'
import { gameDataSchema, mapIconsSchema, wtDataSchema } from '@/types/data'

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
    const stock = { ...emptyStock, flour: 5, honey: 10 }
    const result = calculateCakes(100_000, 0, cakeRecipes[0]!, stock, priceDefaults)
    expect(result.honeyCap).toBe(5)
    expect(result.maximum).toBe(5)
    expect(result.wheatNeeded).toBe(0)
    expect(result.purchases.wheat).toBeUndefined()
  })

  it('keeps flour and wheat independent and projects wheat for the target', () => {
    const stock = {
      ...emptyStock,
      flour: 2,
      berry: 40,
      milk: 35,
      egg: 40,
      honey: 10,
    }
    const result = calculateCakes(0, 5, cakeRecipes[0]!, stock, priceDefaults)

    expect(result.maximum).toBe(2)
    expect(result.amount).toBe(2)
    expect(result.shortfall).toBe(3)
    expect(result.wheatNeeded).toBe(9)
    expect(result.purchases.wheat).toBeUndefined()
  })

  it('uses inventory before spending gold', () => {
    const stock = { ...emptyStock, flour: 5, berry: 8, milk: 7, egg: 8, honey: 2 }
    const result = calculateCakes(0, 0, cakeRecipes[0]!, stock, priceDefaults)
    expect(result.maximum).toBe(1)
    expect(result.spent).toBe(0)
  })

  it('hides price inputs for derived flour and honey cards', () => {
    setActivePinia(createPinia())
    const wrapper = mount(CakesView)
    const derivedCards = wrapper
      .findAll('.ingredient-card')
      .filter((card) => card.text().includes('Flour') || card.text().includes('Honey'))

    expect(derivedCards.length).toBeGreaterThan(0)
    for (const card of derivedCards) {
      expect(card.text()).not.toContain('Price')
      expect(card.findAll('label')).toHaveLength(1)
    }
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

describe('World Tree map data', () => {
  it('parses wt-data.json cleanly even with missing optional categories', () => {
    const wtData = wtDataSchema.parse(rawWtData)
    expect(wtData.alphas.length).toBeGreaterThan(0)
    expect(wtData.travel.length).toBeGreaterThan(0)
    expect(wtData.collectibles.length).toBeGreaterThan(0)
    expect(wtData.bounties).toEqual([])
    expect(wtData.effigies).toEqual([])
  })

  it('builds World Tree layers from parsed data', () => {
    const wtData = wtDataSchema.parse(rawWtData)
    const layers = buildWtLayers(wtData)
    expect(layers.length).toBeGreaterThan(3)
    expect(layers).toContainEqual(expect.objectContaining({ id: 'wt-alphas', storage: 'alphas' }))
  })
})
