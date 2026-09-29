import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useServerHudStore } from '@/stores/serverHud'
import { api } from '@/services/api'

vi.mock('@/services/api', () => ({
  api: {
    health: vi.fn(),
    getGameMarkerState: vi.fn(),
    getMouseLoopState: vi.fn(),
    startGameMarker: vi.fn(),
    cancelGameMarker: vi.fn(),
    startMouseLoop: vi.fn(),
    stopMouseLoop: vi.fn(),
    setHud: vi.fn(),
    clearHud: vi.fn(),
    startOcr: vi.fn(),
    getOcrState: vi.fn(),
  },
}))

describe('serverHud store - race condition fixes', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('prevents multiple simultaneous pollGameMarker calls from creating multiple timers', async () => {
    const store = useServerHudStore()
    
    // Mock API para retornar estado ativo
    vi.mocked(api.getGameMarkerState).mockResolvedValue({ active: true })
    
    // Chama pollGameMarker múltiplas vezes simultaneamente
    const promises = [
      store.pollGameMarker(),
      store.pollGameMarker(),
      store.pollGameMarker(),
    ]
    
    await Promise.all(promises)
    
    // API deve ser chamada apenas uma vez devido ao guard
    expect(api.getGameMarkerState).toHaveBeenCalledTimes(1)
  })

  it('releases polling flag even when API throws error', async () => {
    const store = useServerHudStore()
    
    // Mock API para lançar erro
    vi.mocked(api.getGameMarkerState).mockRejectedValueOnce(new Error('API Error'))
    
    // Primeira chamada falha
    await store.pollGameMarker()
    expect(store.error).toBe('API Error')
    
    // Segunda chamada deve funcionar (flag foi liberada no finally)
    vi.mocked(api.getGameMarkerState).mockResolvedValueOnce({ active: false })
    await store.pollGameMarker()
    
    expect(api.getGameMarkerState).toHaveBeenCalledTimes(2)
  })

  it('prevents multiple simultaneous pollMouseLoop calls from creating multiple timers', async () => {
    const store = useServerHudStore()
    
    // Mock API para retornar estado ativo
    vi.mocked(api.getMouseLoopState).mockResolvedValue({ active: true })
    
    // Chama pollMouseLoop múltiplas vezes simultaneamente
    const promises = [
      store.pollMouseLoop(),
      store.pollMouseLoop(),
      store.pollMouseLoop(),
    ]
    
    await Promise.all(promises)
    
    // API deve ser chamada apenas uma vez devido ao guard
    expect(api.getMouseLoopState).toHaveBeenCalledTimes(1)
  })

  it('releases mouse loop polling flag even when API throws error', async () => {
    const store = useServerHudStore()
    
    // Mock API para lançar erro
    vi.mocked(api.getMouseLoopState).mockRejectedValueOnce(new Error('Mouse Loop Error'))
    
    // Primeira chamada falha
    await store.pollMouseLoop()
    expect(store.error).toBe('Mouse Loop Error')
    
    // Segunda chamada deve funcionar (flag foi liberada no finally)
    vi.mocked(api.getMouseLoopState).mockResolvedValueOnce({ active: false })
    await store.pollMouseLoop()
    
    expect(api.getMouseLoopState).toHaveBeenCalledTimes(2)
  })

  it('stops polling when gameMarker becomes inactive', async () => {
    const store = useServerHudStore()
    
    // Primeira chamada: ativo
    vi.mocked(api.getGameMarkerState).mockResolvedValueOnce({ active: true })
    await store.pollGameMarker()
    expect(store.gameMarker?.active).toBe(true)
    
    // Segunda chamada: inativo
    vi.mocked(api.getGameMarkerState).mockResolvedValueOnce({ active: false })
    await store.pollGameMarker()
    expect(store.gameMarker?.active).toBe(false)
  })
})
