import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useOpggMapStore } from '../src/stores/opggMap'
import type { Marker } from '../src/types/opggMarker'

function makeMarker(overrides: Partial<Marker> = {}): Marker {
  return {
    id: 'Chestbox:-10.0000:10.0000',
    type: 'Chestbox',
    group: 'resources',
    subtype: null,
    lat: -10,
    lng: 10,
    gameX: 0,
    gameY: 0,
    gameZ: 0,
    ingameX: -612,
    ingameY: -17,
    ingameZ: 0,
    ...overrides,
  }
}

describe('opggMap multi-select (batch mark queue)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.unstubAllGlobals()
  })

  it('toggles markers in and out of the selection in click order', () => {
    const store = useOpggMapStore()
    const a = makeMarker({ id: 'Chestbox:1:1' })
    const b = makeMarker({ id: 'Chestbox:2:2' })
    const c = makeMarker({ id: 'Chestbox:3:3' })
    store.rawMarkers = [a, b, c]

    expect(store.selectionCount).toBe(0)

    // Ordem de clique: b, depois a
    expect(store.toggleBatchSelection(b)).toBe(true)
    expect(store.toggleBatchSelection(a)).toBe(true)
    expect(store.selectionCount).toBe(2)
    expect(store.selectionMarkers.map((m) => m.id)).toEqual([b.id, a.id])

    // Toggle remove
    expect(store.toggleBatchSelection(b)).toBe(false)
    expect(store.selectionCount).toBe(1)
    expect(store.selectionMarkers.map((m) => m.id)).toEqual([a.id])

    store.clearBatchSelection()
    expect(store.selectionCount).toBe(0)
    expect(store.selectionMarkers).toEqual([])
  })

  it('keeps selectedMarker (popup/HUD) untouched by batch selection', () => {
    const store = useOpggMapStore()
    const a = makeMarker({ id: 'Chestbox:1:1' })
    store.rawMarkers = [a]

    store.toggleBatchSelection(a)
    expect(store.selectedMarker).toBeNull()

    store.selectMarker(a)
    expect(store.selectedMarker?.id).toBe(a.id)
    expect(store.selectionCount).toBe(1)
  })

  it('ignores ids that no longer exist in the loaded markers', () => {
    const store = useOpggMapStore()
    const a = makeMarker({ id: 'Chestbox:1:1' })
    store.rawMarkers = [a]

    store.toggleBatchSelection(a)
    store.toggleBatchSelection(makeMarker({ id: 'Ghost:9:9' }))

    expect(store.selectionCount).toBe(2)
    expect(store.selectionMarkers.map((m) => m.id)).toEqual([a.id])
  })

  it('keeps colocated marker progress distinct and recognizes the legacy key', () => {
    const legacyKey = 'collectible:Chestbox:-10:10'
    localStorage.setItem(
      'palworld:map:checked-collectibles',
      JSON.stringify([{ key: legacyKey, x: -10, y: 10 }]),
    )
    const store = useOpggMapStore()
    const first = makeMarker({ id: 'Chestbox:-10.0000:10.0000' })
    const second = makeMarker({ id: 'Chestbox:-10.0000:10.0000#2' })
    store.rawMarkers = [first, second]

    expect(store.isChecked(first)).toBe(true)
    expect(store.isChecked(second)).toBe(false)
    expect(store.toggleChecked(second)).toBe(true)
    expect(store.isChecked(first)).toBe(true)
    expect(store.isChecked(second)).toBe(true)

    const legacySaved = JSON.parse(
      localStorage.getItem('palworld:map:checked-collectibles') ?? '[]',
    ) as Array<{ key: string }>
    const distinctSaved = JSON.parse(
      localStorage.getItem('palworld:map:checked-collectibles:distinct') ?? '[]',
    ) as Array<{ key: string }>
    expect(legacySaved.map((item) => item.key)).toEqual([legacyKey])
    expect(distinctSaved.map((item) => item.key)).toEqual([
      `${legacyKey}#${encodeURIComponent(second.id)}`,
    ])
  })

  it('clears the selection when the map zone changes', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('offline'))),
    )
    const store = useOpggMapStore()
    const a = makeMarker({ id: 'Chestbox:1:1' })
    store.rawMarkers = [a]

    store.toggleBatchSelection(a)
    expect(store.selectionCount).toBe(1)

    await store.setZone('world-tree')

    expect(store.selectionCount).toBe(0)
  })
})
