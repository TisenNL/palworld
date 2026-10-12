import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import rawRecipes from '../src/data/recipes.json'
import {
  buildBracket,
  buildCraftPlan,
  listRootKeys,
  loadRecipeBook,
  sanitizeQuantity,
  slugify,
} from '@/domain/itemCraft'
import { useItemCrafterStore } from '@/stores/itemCrafter'

describe('recipes data file', () => {
  const book = loadRecipeBook(rawRecipes)

  it('declares its root keys so new items show up in the dropdown', () => {
    expect(listRootKeys(book)).toEqual(['ai-core'])
    expect(book.entries.get('ai-core')?.name).toBe('AI Core')
  })

  it('matches the documented first level of the AI Core recipe (per unit)', () => {
    const entry = book.entries.get('ai-core')
    expect(entry?.ingredients.map((ing) => [ing.item, ing.qty])).toEqual([
      ['Computer', 5],
      ['Soralite Ingot', 10],
      ['Thermal Core', 2],
      ['Ancient Civilization Core', 1],
    ])
  })

  it('marks items without a Production section as raw materials', () => {
    expect(book.entries.get('ore')?.ingredients).toEqual([])
    expect(book.entries.get('coal')?.ingredients).toEqual([])
  })

  it('carries the paldb icon URL for every entry', () => {
    for (const [key, entry] of book.entries) {
      expect(entry.icon, `${key} icon`).toMatch(/^https:\/\/cdn\.paldb\.cc\//)
    }
  })

  it('returns null for an unknown item', () => {
    expect(buildCraftPlan(book, 'not-an-item', 1)).toBeNull()
  })
})

describe('buildCraftPlan', () => {
  const book = loadRecipeBook(rawRecipes)

  it('consolidates raw materials across branches for 1 AI Core', () => {
    const plan = buildCraftPlan(book, 'ai-core', 1)
    expect(plan).not.toBeNull()
    const totals = Object.fromEntries(plan!.materials.map((m) => [m.name, m.total]))

    // 75 Ore from Plasteel (3×5) + 20 from Refined Ingot (2 per battery ×10)
    expect(totals['Ore']).toBe(95)
    // 16 from Thermal Core + 40 from Carbon Fiber (20 crafted) + 20 from Refined Ingot
    expect(totals['Coal']).toBe(76)
    // 20 from Circuit Board (10 crafted) + 20 from Soralite Ingot (10 crafted)
    expect(totals['Pure Quartz']).toBe(40)
    expect(totals['Ancient Civilization Core']).toBe(1)
    expect(totals['Crude Oil']).toBe(30)
    // The icon scraped from paldb is carried into the consolidated row.
    expect(plan!.materials.find((m) => m.key === 'ore')?.icon).toContain(
      'T_itemicon_Material_CopperOre',
    )

    // Intermediates never leak into the raw material table.
    expect(totals['Computer']).toBeUndefined()
    expect(totals['Carbon Fiber']).toBeUndefined()
    expect(totals['Refined Ingot']).toBeUndefined()
  })

  it('scales the whole tree with the requested quantity', () => {
    const one = buildCraftPlan(book, 'ai-core', 1)!
    const many = buildCraftPlan(book, 'ai-core', 7)!
    expect(many.materials.length).toBe(one.materials.length)
    for (const [index, material] of one.materials.entries()) {
      expect(many.materials[index]?.total).toBe(material.total * 7)
    }
    expect(many.tree[0]?.qty).toBe(7)
  })

  it('keeps intermediates in the tree with their required amounts', () => {
    const plan = buildCraftPlan(book, 'ai-core', 2)!
    const computer = plan.tree[0]?.children.find((child) => child.key === 'computer')
    expect(computer?.qty).toBe(10) // 5 per unit × 2
    expect(computer?.craftable).toBe(true)
    expect(computer?.children.map((child) => child.name)).toEqual([
      'Circuit Board',
      'Plasteel',
      'Bio Battery',
      'Carbon Fiber',
    ])
  })

  it('sorts materials by total, descending', () => {
    const plan = buildCraftPlan(book, 'ai-core', 1)!
    const totals = plan.materials.map((material) => material.total)
    expect(totals).toEqual([...totals].sort((a, b) => b - a))
  })

  it('cuts recipe cycles instead of recursing forever', () => {
    const cyclic = loadRecipeBook({
      _meta: { roots: ['a'] },
      a: { name: 'A', ingredients: [{ item: 'B', key: 'b', qty: 2 }] },
      b: { name: 'B', ingredients: [{ item: 'A', key: 'a', qty: 3 }] },
    })
    const plan = buildCraftPlan(cyclic, 'a', 1)!
    const cut = plan.tree[0]?.children[0]?.children[0]

    expect(cut?.key).toBe('a')
    expect(cut?.cycle).toBe(true)
    expect(cut?.children).toEqual([])
    expect(plan.materials).toEqual([{ key: 'a', name: 'A', total: 6 }])
    expect(plan.warnings.some((w) => w.includes('cycle'))).toBe(true)
  })

  it('treats items missing from the file as raw materials and warns', () => {
    const partial = loadRecipeBook({
      x: { name: 'X', ingredients: [{ item: 'Ghost', qty: 1 }] },
    })
    const plan = buildCraftPlan(partial, 'x', 1)!
    expect(plan.materials).toEqual([{ key: 'ghost', name: 'Ghost', total: 1 }])
    expect(plan.warnings[0]).toContain('No recipe data for "Ghost"')
  })
})

describe('buildBracket (tournament layout)', () => {
  const book = loadRecipeBook(rawRecipes)
  const plan = buildCraftPlan(book, 'ai-core', 1)!
  const bracket = buildBracket(plan.tree)!

  it('lays the tree out as rounds ending in a single champion', () => {
    expect(bracket.levels.map((level) => level.length)).toEqual([5, 13, 10, 4, 1])
    expect(bracket.maxLevel).toBe(4)

    const champion = bracket.levels[bracket.maxLevel]![0]!
    expect(champion.key).toBe('ai-core')
    expect(champion.champion).toBe(true)
    expect(champion.qty).toBe(1)
  })

  it('merges repeated items inside a round, summing their quantities', () => {
    // Coal is needed at three different stages: 16 + 20 + 40 = 76 total.
    const coalByRound = bracket.levels.map(
      (level) => level.find((tile) => tile.key === 'coal')?.qty ?? 0,
    )
    expect(coalByRound).toEqual([40, 20, 16, 0, 0])

    // Across rounds every material adds up to the consolidated table.
    for (const material of plan.materials) {
      const sum = bracket.levels
        .flat()
        .filter((tile) => tile.key === material.key)
        .reduce((total, tile) => total + tile.qty, 0)
      expect(sum, material.name).toBe(material.total)
    }
  })

  it('never repeats a tile inside a round and only links neighbouring rounds', () => {
    const ids = bracket.levels.flat().map((tile) => tile.id)
    expect(new Set(ids).size).toBe(ids.length)

    for (const edge of bracket.edges) {
      const fromLevel = Number(edge.from.split(':')[0])
      const toLevel = Number(edge.to.split(':')[0])
      expect(toLevel - fromLevel).toBe(1)
    }

    const championEdges = bracket.edges.filter((edge) => edge.to === `${bracket.maxLevel}:ai-core`)
    expect(championEdges).toHaveLength(4) // Computer, Soralite Ingot, Thermal Core, ACC
  })

  it('flags raw materials and keeps the item icons', () => {
    const ore = bracket.levels.flat().find((tile) => tile.key === 'ore')
    expect(ore?.raw).toBe(true)
    expect(ore?.icon).toContain('T_itemicon_Material_CopperOre')

    const computer = bracket.levels.flat().find((tile) => tile.key === 'computer')
    expect(computer?.raw).toBe(false)
    expect(computer?.icon).toContain('T_itemicon_Material_Computer')
  })

  it('turns a single-node tree into a one-column champion', () => {
    const lone = loadRecipeBook({ ore: { name: 'Ore', ingredients: [] } })
    const lonePlan = buildCraftPlan(lone, 'ore', 3)!
    const loneBracket = buildBracket(lonePlan.tree)!

    expect(loneBracket.levels).toHaveLength(1)
    expect(loneBracket.levels[0]).toHaveLength(1)
    expect(loneBracket.levels[0]![0]).toMatchObject({ key: 'ore', qty: 3, champion: true })
    expect(loneBracket.edges).toEqual([])
  })

  it('still terminates on cyclic recipes', () => {
    const cyclic = loadRecipeBook({
      _meta: { roots: ['a'] },
      a: { name: 'A', ingredients: [{ item: 'B', key: 'b', qty: 2 }] },
      b: { name: 'B', ingredients: [{ item: 'A', key: 'a', qty: 3 }] },
    })
    const cyclicBracket = buildBracket(buildCraftPlan(cyclic, 'a', 1)!.tree)!

    expect(cyclicBracket.levels).toHaveLength(3)
    expect(cyclicBracket.levels[0]![0]).toMatchObject({ key: 'a', champion: false })
    expect(cyclicBracket.levels[2]![0]).toMatchObject({ key: 'a', champion: true })
  })
})

describe('helpers', () => {
  it('slugifies display names into file keys', () => {
    expect(slugify('AI Core')).toBe('ai-core')
    expect(slugify('Ancient Civilization Core')).toBe('ancient-civilization-core')
    expect(slugify("Jetragon's Missile Launcher")).toBe('jetragon-s-missile-launcher')
  })

  it('sanitizes quantity to integers between 1 and 999999', () => {
    expect(sanitizeQuantity(1)).toBe(1)
    expect(sanitizeQuantity(2.9)).toBe(2)
    expect(sanitizeQuantity(0)).toBe(1)
    expect(sanitizeQuantity(-5)).toBe(1)
    expect(sanitizeQuantity(null)).toBe(1)
    expect(sanitizeQuantity(undefined)).toBe(1)
    expect(sanitizeQuantity(Number.NaN)).toBe(1)
    expect(sanitizeQuantity(10_000_000)).toBe(999_999)
  })
})

describe('item crafter store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('preselects the first root and exposes searchable options', () => {
    const store = useItemCrafterStore()
    expect(store.options).toEqual([{ key: 'ai-core', label: 'AI Core' }])
    expect(store.itemKey).toBe('ai-core')
    expect(store.plan?.rootName).toBe('AI Core')
  })

  it('updates materials live as the quantity changes', () => {
    const store = useItemCrafterStore()
    store.quantity = 2
    const ore = store.materials.find((material) => material.key === 'ore')
    expect(ore?.total).toBe(190)

    store.quantity = null // cleared input falls back to 1
    expect(store.effectiveQuantity).toBe(1)
    expect(store.materials.find((m) => m.key === 'ore')?.total).toBe(95)
  })
})
