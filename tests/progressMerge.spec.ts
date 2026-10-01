import { describe, expect, it } from 'vitest'

import { mergeProgressChanges } from '@/domain/progressMerge'
import { emptyChecks, progressSchema } from '@/types/progress'

function progress() {
  return progressSchema.parse({
    version: 2,
    revision: 4,
    updatedAt: '2026-10-01T00:00:00Z',
    checks: emptyChecks(),
    breedOwned: {},
    prefs: {},
  })
}

describe('mergeProgressChanges', () => {
  it('keeps disjoint changes from both tabs, including deletions', () => {
    const base = progress()
    base.checks.alphas = { keep: true, remove: true }

    const local = structuredClone(base)
    delete local.checks.alphas.remove
    local.checks.alphas.local = true

    const remote = structuredClone(base)
    remote.checks.alphas.remote = true

    const merged = mergeProgressChanges(base, local, remote)
    expect(merged.checks.alphas).toEqual({ keep: true, local: true, remote: true })
  })

  it('merges independent preference and cake fields', () => {
    const base = progress()
    base.cake = {
      recipe: 'cake',
      gold: 100,
      target: 5,
      prices: { wheat: 10 },
      stock: {},
    }
    const local = structuredClone(base)
    local.prefs.activeMap = 'world-tree'
    local.prefs.mapLayers.local = false
    const localCake = local.cake
    if (!localCake) throw new Error('Test fixture must include cake state')
    localCake.gold = 150
    localCake.prices.wheat = 12

    const remote = structuredClone(base)
    remote.prefs.sidebarWidth = 400
    remote.prefs.mapLayers.remote = false
    const remoteCake = remote.cake
    if (!remoteCake) throw new Error('Test fixture must include cake state')
    remoteCake.gold = 200
    remoteCake.prices.berry = 20
    remoteCake.stock.flour = 3

    const merged = mergeProgressChanges(base, local, remote)
    expect(merged.prefs.activeMap).toBe('world-tree')
    expect(merged.prefs.sidebarWidth).toBe(400)
    expect(merged.prefs.mapLayers).toEqual({ local: false, remote: false })
    expect(merged.cake).toEqual({
      recipe: 'cake',
      gold: 150,
      target: 5,
      prices: { wheat: 12, berry: 20 },
      stock: { flour: 3 },
    })
  })

  it('uses calculator defaults when two tabs first create cake progress', () => {
    const base = progress()
    const local = structuredClone(base)
    local.cake = {
      recipe: 'cake',
      gold: 0,
      target: 0,
      prices: { wheat: 59 },
      stock: { flour: 0, honey: 0 },
    }
    local.cake.stock.flour = 4

    const remote = structuredClone(base)
    remote.cake = {
      recipe: 'cake',
      gold: 500,
      target: 0,
      prices: { wheat: 59 },
      stock: { flour: 0, honey: 0 },
    }

    const merged = mergeProgressChanges(base, local, remote)
    expect(merged.cake?.gold).toBe(500)
    expect(merged.cake?.stock.flour).toBe(4)
  })
})
