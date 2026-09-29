import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useChecklistStore } from '@/stores/checklist'
import { api } from '@/services/api'

vi.mock('@/services/api', () => ({
  api: {
    getData: vi.fn(),
    getBreedData: vi.fn(),
    getMapIcons: vi.fn(),
    getProgress: vi.fn(),
    saveProgress: vi.fn(),
  },
}))

describe('checklist store - scheduleSave fix', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    vi.useFakeTimers()
    
    // Mock localStorage
    const localStorageMock = {
      getItem: vi.fn(() => null),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
    }
    Object.defineProperty(window, 'localStorage', { value: localStorageMock, writable: true })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('captures latest state when saving after multiple rapid changes', async () => {
    // Mock API responses para initialize
    vi.mocked(api.getData).mockResolvedValue({
      version: 1,
      pals: [],
      bosses: [],
      effigies: [],
      npcDungeons: [],
      bounties: [],
      oreLocations: [],
    } as any)
    vi.mocked(api.getBreedData).mockResolvedValue({ version: 1, pals: [], combi: [] } as any)
    vi.mocked(api.getMapIcons).mockResolvedValue({ version: 1, icons: [] } as any)
    vi.mocked(api.getProgress).mockResolvedValue({
      version: 2,
      revision: 1,
      checks: { alphas: {}, bounties: {}, effigies: {}, dungeons: {}, towers: {} },
      breedOwned: {},
      prefs: {},
    })
    vi.mocked(api.saveProgress).mockResolvedValue(undefined)

    const store = useChecklistStore()
    await store.initialize()

    // Simula múltiplas mudanças rápidas
    store.setDone('alphas', 'pal1', true)
    store.setDone('alphas', 'pal2', true)
    store.setDone('alphas', 'pal3', true)

    // Avança o timer para executar o save
    await vi.advanceTimersByTimeAsync(350)

    // Verifica que saveProgress foi chamado
    expect(api.saveProgress).toHaveBeenCalledTimes(1)

    // Verifica que o payload inclui TODAS as três mudanças
    const savedPayload = vi.mocked(api.saveProgress).mock.calls[0]![0]!
    expect(savedPayload.checks.alphas).toEqual({
      pal1: true,
      pal2: true,
      pal3: true,
    })
  })

  it('debounces multiple scheduleSave calls correctly', async () => {
    // Mock API responses
    vi.mocked(api.getData).mockResolvedValue({
      version: 1,
      pals: [],
      bosses: [],
      effigies: [],
      npcDungeons: [],
      bounties: [],
      oreLocations: [],
    } as any)
    vi.mocked(api.getBreedData).mockResolvedValue({ version: 1, pals: [], combi: [] } as any)
    vi.mocked(api.getMapIcons).mockResolvedValue({ version: 1, icons: [] } as any)
    vi.mocked(api.getProgress).mockResolvedValue({
      version: 2,
      revision: 1,
      checks: { alphas: {}, bounties: {}, effigies: {}, dungeons: {}, towers: {} },
      breedOwned: {},
      prefs: {},
    })
    vi.mocked(api.saveProgress).mockResolvedValue(undefined)

    const store = useChecklistStore()
    await store.initialize()

    // Múltiplas mudanças em sequência rápida
    store.setDone('alphas', 'pal1', true)
    await vi.advanceTimersByTimeAsync(100) // 100ms

    store.setDone('alphas', 'pal2', true)
    await vi.advanceTimersByTimeAsync(100) // 200ms total

    store.setDone('alphas', 'pal3', true)
    await vi.advanceTimersByTimeAsync(350) // Completa o debounce

    // Deve ter chamado saveProgress apenas UMA vez (debounced)
    expect(api.saveProgress).toHaveBeenCalledTimes(1)

    // E deve incluir todas as mudanças
    const savedPayload = vi.mocked(api.saveProgress).mock.calls[0]![0]!
    expect(savedPayload.checks.alphas).toEqual({
      pal1: true,
      pal2: true,
      pal3: true,
    })
  })

  it('saves most recent state after debounce period', async () => {
    // Mock API responses
    vi.mocked(api.getData).mockResolvedValue({
      version: 1,
      pals: [],
      bosses: [],
      effigies: [],
      npcDungeons: [],
      bounties: [],
      oreLocations: [],
    } as any)
    vi.mocked(api.getBreedData).mockResolvedValue({ version: 1, pals: [], combi: [] } as any)
    vi.mocked(api.getMapIcons).mockResolvedValue({ version: 1, icons: [] } as any)
    vi.mocked(api.getProgress).mockResolvedValue({
      version: 2,
      revision: 1,
      checks: { alphas: {}, bounties: {}, effigies: {}, dungeons: {}, towers: {} },
      breedOwned: {},
      prefs: {},
    })
    vi.mocked(api.saveProgress).mockResolvedValue(undefined)

    const store = useChecklistStore()
    await store.initialize()

    // Marca item como true
    store.setDone('alphas', 'pal1', true)
    await vi.advanceTimersByTimeAsync(200)

    // Depois desmarca (toggle)
    store.setDone('alphas', 'pal1', false)
    await vi.advanceTimersByTimeAsync(350)

    // Deve salvar o estado FINAL (false), não o intermediário
    const savedPayload = vi.mocked(api.saveProgress).mock.calls[0]![0]!
    expect(savedPayload.checks.alphas.pal1).toBe(false)
  })
})


describe('checklist store - flush size validation', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()

    // Mock localStorage
    const localStorageMock = {
      getItem: vi.fn(() => null),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
    }
    Object.defineProperty(window, 'localStorage', { value: localStorageMock, writable: true })

    // Mock sendBeacon
    Object.defineProperty(navigator, 'sendBeacon', {
      value: vi.fn(() => true),
      writable: true,
      configurable: true,
    })

    // Mock fetch global
    global.fetch = vi.fn(() => Promise.resolve({} as Response))
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('uses sendBeacon for small payloads', async () => {
    // Mock API responses para initialize
    vi.mocked(api.getData).mockResolvedValue({
      version: 1,
      pals: [],
      bosses: [],
      effigies: [],
      npcDungeons: [],
      bounties: [],
      oreLocations: [],
    } as any)
    vi.mocked(api.getBreedData).mockResolvedValue({ version: 1, pals: [], combi: [] } as any)
    vi.mocked(api.getMapIcons).mockResolvedValue({ version: 1, icons: [] } as any)
    vi.mocked(api.getProgress).mockResolvedValue({
      version: 2,
      revision: 1,
      checks: { alphas: {}, bounties: {}, effigies: {}, dungeons: {}, towers: {} },
      breedOwned: {},
      prefs: {},
    })

    const store = useChecklistStore()
    await store.initialize()

    // Adiciona apenas alguns itens (payload pequeno)
    store.setDone('alphas', 'pal1', true)
    store.setDone('alphas', 'pal2', true)

    // Chama flush
    store.flush()

    // Deve ter usado sendBeacon
    expect(navigator.sendBeacon).toHaveBeenCalled()
    expect(global.fetch).not.toHaveBeenCalled()
  })

  it('uses fetch as fallback for large payloads', async () => {
    // Mock API responses para initialize
    vi.mocked(api.getData).mockResolvedValue({
      version: 1,
      pals: [],
      bosses: [],
      effigies: [],
      npcDungeons: [],
      bounties: [],
      oreLocations: [],
    } as any)
    vi.mocked(api.getBreedData).mockResolvedValue({ version: 1, pals: [], combi: [] } as any)
    vi.mocked(api.getMapIcons).mockResolvedValue({ version: 1, icons: [] } as any)
    
    // Mock com progresso enorme para forçar payload > 60KB
    const hugeChecks: Record<string, boolean> = {}
    for (let i = 0; i < 2000; i++) {
      hugeChecks[`item${i}`] = true
    }
    
    vi.mocked(api.getProgress).mockResolvedValue({
      version: 2,
      revision: 1,
      checks: { 
        alphas: hugeChecks, 
        bounties: {}, 
        effigies: {}, 
        dungeons: {}, 
        towers: {} 
      },
      breedOwned: {},
      prefs: {},
    })

    const store = useChecklistStore()
    await store.initialize()

    // Chama flush com payload grande
    store.flush()

    // Deve ter usado fetch ao invés de sendBeacon
    expect(global.fetch).toHaveBeenCalledWith(
      '/progress',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        keepalive: true,
      })
    )
  })

  it('fetch call includes keepalive flag for unload events', async () => {
    vi.mocked(api.getData).mockResolvedValue({
      version: 1,
      pals: [],
      bosses: [],
      effigies: [],
      npcDungeons: [],
      bounties: [],
      oreLocations: [],
    } as any)
    vi.mocked(api.getBreedData).mockResolvedValue({ version: 1, pals: [], combi: [] } as any)
    vi.mocked(api.getMapIcons).mockResolvedValue({ version: 1, icons: [] } as any)
    
    // Payload grande
    const hugeChecks: Record<string, boolean> = {}
    for (let i = 0; i < 2000; i++) {
      hugeChecks[`item${i}`] = true
    }
    
    vi.mocked(api.getProgress).mockResolvedValue({
      version: 2,
      revision: 1,
      checks: { alphas: hugeChecks, bounties: {}, effigies: {}, dungeons: {}, towers: {} },
      breedOwned: {},
      prefs: {},
    })

    const store = useChecklistStore()
    await store.initialize()
    store.flush()

    // Verifica que keepalive está true (importante para eventos de unload)
    const fetchCall = vi.mocked(global.fetch).mock.calls[0]
    expect(fetchCall?.[1]?.keepalive).toBe(true)
  })
})
