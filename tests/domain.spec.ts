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
import { cakeRecipes, calculateCakes, emptyStock, priceDefaults } from '@/domain/cakes'
import CakesView from '@/views/CakesView.vue'
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


describe('map coordinates - parseCoordinates edge cases', () => {
  it('handles valid coordinate formats', () => {
    expect(parseCoordinates('-16, -339')).toEqual({ x: -16, y: -339 })
    expect(parseCoordinates('9 224')).toEqual({ x: 9, y: 224 })
    expect(parseCoordinates('100;200')).toEqual({ x: 100, y: 200 })
    expect(parseCoordinates('10.5, 20.3')).toEqual({ x: 10.5, y: 20.3 })
    expect(parseCoordinates('10,5 20,3')).toEqual({ x: 10.5, y: 20.3 }) // Vírgula como decimal
  })

  it('rejects invalid formats', () => {
    expect(parseCoordinates('invalid')).toBeNull()
    expect(parseCoordinates('123')).toBeNull() // Apenas um número
    expect(parseCoordinates('')).toBeNull() // String vazia
    expect(parseCoordinates('   ')).toBeNull() // Apenas espaços
    expect(parseCoordinates('abc, def')).toBeNull() // Não numérico
    expect(parseCoordinates('10, ')).toBeNull() // Falta segundo número
    expect(parseCoordinates(', 20')).toBeNull() // Falta primeiro número
  })

  it('handles edge case with special characters', () => {
    expect(parseCoordinates('10@20')).toBeNull()
    expect(parseCoordinates('10#20')).toBeNull()
    expect(parseCoordinates('(10, 20)')).toBeNull() // Parênteses não são suportados
  })

  it('handles very large numbers', () => {
    expect(parseCoordinates('999999, -999999')).toEqual({ x: 999999, y: -999999 })
  })

  it('rejects NaN and Infinity', () => {
    expect(parseCoordinates('Infinity, 20')).toBeNull()
    expect(parseCoordinates('10, NaN')).toBeNull()
  })

  it('handles decimal formats correctly', () => {
    expect(parseCoordinates('1.5, 2.5')).toEqual({ x: 1.5, y: 2.5 })
    expect(parseCoordinates('1,5 2,5')).toEqual({ x: 1.5, y: 2.5 }) // Vírgula europeia
  })
})


describe('LruCache - falsy values support', () => {
  it('stores and retrieves null values', () => {
    const cache = new LruCache<string, string | null>(3)
    cache.set('key1', null)
    expect(cache.get('key1')).toBeNull()
    expect(cache.has('key1')).toBe(true)
  })

  it('stores and retrieves 0 values', () => {
    const cache = new LruCache<string, number>(3)
    cache.set('key1', 0)
    expect(cache.get('key1')).toBe(0)
    expect(cache.has('key1')).toBe(true)
  })

  it('stores and retrieves false values', () => {
    const cache = new LruCache<string, boolean>(3)
    cache.set('key1', false)
    expect(cache.get('key1')).toBe(false)
    expect(cache.has('key1')).toBe(true)
  })

  it('stores and retrieves empty string values', () => {
    const cache = new LruCache<string, string>(3)
    cache.set('key1', '')
    expect(cache.get('key1')).toBe('')
    expect(cache.has('key1')).toBe(true)
  })

  it('returns undefined for non-existent keys', () => {
    const cache = new LruCache<string, string>(3)
    expect(cache.get('nonexistent')).toBeUndefined()
    expect(cache.has('nonexistent')).toBe(false)
  })

  it('distinguishes between stored undefined and non-existent key', () => {
    const cache = new LruCache<string, string | undefined>(3)
    cache.set('key1', undefined)
    
    // Key exists, mas valor é undefined
    expect(cache.has('key1')).toBe(true)
    expect(cache.get('key1')).toBeUndefined()
    
    // Key não existe
    expect(cache.has('key2')).toBe(false)
    expect(cache.get('key2')).toBeUndefined()
  })

  it('maintains LRU order with falsy values', () => {
    const cache = new LruCache<string, number>(2)
    cache.set('a', 0)
    cache.set('b', 1)
    
    // Acessa 'a' (move para fim)
    expect(cache.get('a')).toBe(0)
    
    // Adiciona 'c' (deve remover 'b', não 'a')
    cache.set('c', 2)
    
    expect(cache.has('a')).toBe(true)
    expect(cache.has('b')).toBe(false)
    expect(cache.has('c')).toBe(true)
  })

  it('handles mixed truthy and falsy values', () => {
    const cache = new LruCache<string, string | number | boolean | null>(5)
    cache.set('truthy', 'hello')
    cache.set('zero', 0)
    cache.set('null', null)
    cache.set('false', false)
    cache.set('empty', '')
    
    expect(cache.get('truthy')).toBe('hello')
    expect(cache.get('zero')).toBe(0)
    expect(cache.get('null')).toBeNull()
    expect(cache.get('false')).toBe(false)
    expect(cache.get('empty')).toBe('')
  })
})
