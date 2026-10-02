import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useServerHudStore } from '../src/stores/serverHud'
import type { BatchQueueItem } from '../src/types/batch'
import type { GameMarkerState } from '../src/types/server'

const apiMocks = vi.hoisted(() => ({
  startGameMarker: vi.fn<(x: number, y: number, dryRun?: boolean) => Promise<void>>(),
  getGameMarkerState: vi.fn<() => Promise<unknown>>(),
  getPlayerPositionState: vi.fn<() => Promise<unknown>>(),
  cancelGameMarker: vi.fn<() => Promise<void>>(),
}))

vi.mock('../src/services/api', () => ({ api: apiMocks }))

function gmState(overrides: Partial<GameMarkerState> = {}): GameMarkerState {
  return {
    ok: true,
    active: false,
    status: 'completed',
    target: null,
    current: null,
    distanceMeters: null,
    message: '',
    error: '',
    ...overrides,
  }
}

function d(overrides: Partial<BatchQueueItem> = {}) {
  return {
    id: 'Chestbox:1:1',
    zone: 'palpagos' as const,
    type: 'Chestbox',
    subtype: null,
    name: 'Chest',
    x: -612,
    y: -17,
    ...overrides,
  }
}

function startedXs(): number[] {
  return apiMocks.startGameMarker.mock.calls.map((call) => call[0])
}

describe('serverHud batch mark queue', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    setActivePinia(createPinia())
    localStorage.clear()
    apiMocks.startGameMarker.mockResolvedValue(undefined)
    apiMocks.getGameMarkerState.mockResolvedValue(gmState())
    apiMocks.getPlayerPositionState.mockResolvedValue({
      ok: true,
      status: 'ready',
      processFound: true,
      readAccess: true,
      pid: 123,
      position: {
        gameX: 100,
        gameY: 200,
        gameZ: 300,
        mapZone: 'palpagos',
        updatedAt: '2026-10-02T12:00:00.000Z',
      },
      error: '',
    })
    apiMocks.cancelGameMarker.mockResolvedValue(undefined)
  })

  it('continues polling the live player position until stopped', async () => {
    vi.useFakeTimers()
    const store = useServerHudStore()

    store.startPlayerPositionPolling()
    await vi.waitFor(() => expect(apiMocks.getPlayerPositionState).toHaveBeenCalledTimes(1))

    await vi.advanceTimersByTimeAsync(250)

    expect(apiMocks.getPlayerPositionState).toHaveBeenCalledTimes(2)
    expect(store.playerPosition?.status).toBe('ready')

    store.stopPlayerPositionPolling()
    await vi.advanceTimersByTimeAsync(1_000)

    expect(apiMocks.getPlayerPositionState).toHaveBeenCalledTimes(2)
    vi.useRealTimers()
  })

  describe('enqueueBatch', () => {
    it('accepts a homogeneous queue', () => {
      const store = useServerHudStore()

      expect(store.enqueueBatch([d({ id: 'a' }), d({ id: 'b', zone: 'palpagos' })])).toBe('ok')
      expect(store.batchQueue.map((item) => item.id)).toEqual(['a', 'b'])
      expect(store.batchQueue.every((item) => item.status === 'pending')).toBe(true)
    })

    it('rejects a draft list with mixed zones', () => {
      const store = useServerHudStore()

      const result = store.enqueueBatch([d({ id: 'a' }), d({ id: 'b', zone: 'world-tree' })])

      expect(result).toBe('mixed-zone')
      expect(store.batchQueue).toHaveLength(0)
    })

    it('rejects new items from a different zone than the persisted queue', () => {
      const store = useServerHudStore()
      store.enqueueBatch([d({ id: 'a' })])

      expect(store.enqueueBatch([d({ id: 'b', zone: 'world-tree' })])).toBe('mixed-zone')
      expect(store.batchQueue.map((item) => item.id)).toEqual(['a'])
    })

    it('removes and clears items while not running', () => {
      const store = useServerHudStore()
      store.enqueueBatch([d({ id: 'a' }), d({ id: 'b' })])

      store.removeBatchItem('a')
      expect(store.batchQueue.map((item) => item.id)).toEqual(['b'])

      store.clearBatchQueue()
      expect(store.batchQueue).toHaveLength(0)
      expect(localStorage.getItem('palworld:map:mark-queue')).toBe('[]')
    })
  })

  describe('startBatchMark', () => {
    it('runs the queue sequentially in enqueue order', async () => {
      const store = useServerHudStore()
      store.enqueueBatch([d({ id: 'a', x: 1 }), d({ id: 'b', x: 2 }), d({ id: 'c', x: 3 })])
      const calls: Array<[number, number]> = []
      apiMocks.startGameMarker.mockImplementation((x, y) => {
        calls.push([x, y])
        return Promise.resolve()
      })

      const summary = await store.startBatchMark()

      expect(calls).toEqual([
        [1, -17],
        [2, -17],
        [3, -17],
      ])
      expect(summary).toEqual({ completed: 3, failed: 0, cancelled: false })
      expect(store.batchQueue.map((item) => item.status)).toEqual([
        'completed',
        'completed',
        'completed',
      ])
      expect(store.batchRunning).toBe(false)
    })

    it('stops on the first failed item and keeps the rest pending', async () => {
      const store = useServerHudStore()
      store.enqueueBatch([d({ id: 'a', x: 1 }), d({ id: 'b', x: 2 }), d({ id: 'c', x: 3 })])
      // item a → completed; item b → erro nas 3 tentativas (política de retry)
      apiMocks.getGameMarkerState
        .mockResolvedValueOnce(gmState())
        .mockResolvedValue(gmState({ status: 'error', error: 'OCR failed', message: 'OCR failed' }))

      const summary = await store.startBatchMark()

      expect(summary).toEqual({ completed: 1, failed: 1, cancelled: false })
      // 1 tentativa do item a + 3 tentativas do item b; item c nunca roda
      expect(startedXs()).toEqual([1, 2, 2, 2])
      expect(store.batchQueue.map((item) => item.status)).toEqual([
        'completed',
        'failed',
        'pending',
      ])
      expect(store.batchQueue[1]?.error).toBe('OCR failed')
    }, 10_000)

    it('cancel reverts the current item to pending and stops the batch', async () => {
      const store = useServerHudStore()
      store.enqueueBatch([d({ id: 'a', x: 1 }), d({ id: 'b', x: 2 })])

      let release!: () => void
      const gate = new Promise<void>((resolve) => {
        release = resolve
      })
      apiMocks.getGameMarkerState.mockImplementation(() =>
        gate.then(() => gmState({ status: 'cancelled' })),
      )

      const batchPromise = store.startBatchMark()
      await vi.waitFor(() => expect(apiMocks.startGameMarker).toHaveBeenCalledTimes(1))
      expect(store.batchRunning).toBe(true)
      expect(store.batchQueue[0]?.status).toBe('processing')

      const cancelPromise = store.cancelBatchMark()
      release()
      const summary = await batchPromise
      await cancelPromise

      expect(apiMocks.cancelGameMarker).toHaveBeenCalledTimes(1)
      expect(summary).toEqual({ completed: 0, failed: 0, cancelled: true })
      expect(store.batchQueue.map((item) => item.status)).toEqual(['pending', 'pending'])
      expect(store.batchRunning).toBe(false)
    })

    it('skips completed items on re-run', async () => {
      const store = useServerHudStore()
      store.enqueueBatch([d({ id: 'a', x: 1 }), d({ id: 'b', x: 2 })])
      store.batchQueue[0]!.status = 'completed'

      const summary = await store.startBatchMark()

      expect(startedXs()).toEqual([2])
      expect(summary).toEqual({ completed: 1, failed: 0, cancelled: false })
      expect(store.batchQueue.map((item) => item.status)).toEqual(['completed', 'completed'])
    })

    it('does nothing when there is nothing to run', async () => {
      const store = useServerHudStore()
      store.enqueueBatch([d({ id: 'a' })])
      store.batchQueue[0]!.status = 'completed'

      const summary = await store.startBatchMark()

      expect(summary).toEqual({ completed: 0, failed: 0, cancelled: false })
      expect(apiMocks.startGameMarker).not.toHaveBeenCalled()
    })
  })

  describe('persistence', () => {
    it('persists the queue to localStorage on every mutation', () => {
      const store = useServerHudStore()
      store.enqueueBatch([d({ id: 'a' }), d({ id: 'b' })])

      const raw = localStorage.getItem('palworld:map:mark-queue')
      expect(raw).toBeTruthy()
      const saved = JSON.parse(raw!) as Array<{ id: string; status: string }>
      expect(saved.map((item) => item.id)).toEqual(['a', 'b'])
      expect(saved.every((item) => item.status === 'pending')).toBe(true)
    })

    it('restores the queue on a fresh store, mapping processing back to pending', () => {
      localStorage.setItem(
        'palworld:map:mark-queue',
        JSON.stringify([d({ id: 'a', status: 'processing' }), d({ id: 'b', status: 'completed' })]),
      )

      const store = useServerHudStore()

      expect(store.batchQueue.map((item) => item.status)).toEqual(['pending', 'completed'])
      expect(store.batchQueue.map((item) => item.id)).toEqual(['a', 'b'])
    })

    it('ignores corrupted persisted queues', () => {
      localStorage.setItem('palworld:map:mark-queue', '{oops')

      const store = useServerHudStore()

      expect(store.batchQueue).toEqual([])
    })
  })
})
