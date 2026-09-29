import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useCakeStore } from '@/stores/cake'

describe('cake store - error logging', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()

    // Limpa console.warn spy
    vi.spyOn(console, 'warn').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('logs warning when localStorage.setItem fails', () => {
    // Mock localStorage para lançar erro (quota excedida)
    const mockError = new Error('QuotaExceededError')
    const localStorageMock = {
      getItem: vi.fn(() => null),
      setItem: vi.fn(() => {
        throw mockError
      }),
      removeItem: vi.fn(),
      clear: vi.fn(),
    }
    Object.defineProperty(window, 'localStorage', { value: localStorageMock, writable: true })

    const store = useCakeStore()
    
    // Modifica algo que aciona writeState
    store.gold = 1000

    // Deve ter logado o warning
    expect(console.warn).toHaveBeenCalledWith(
      expect.stringContaining('Falha ao salvar configurações de bolo no localStorage'),
      expect.stringContaining('QuotaExceededError'),
    )
  })

  it('continues to work even when localStorage fails', () => {
    // Mock localStorage para falhar
    const localStorageMock = {
      getItem: vi.fn(() => null),
      setItem: vi.fn(() => {
        throw new Error('QuotaExceededError')
      }),
      removeItem: vi.fn(),
      clear: vi.fn(),
    }
    Object.defineProperty(window, 'localStorage', { value: localStorageMock, writable: true })

    const store = useCakeStore()
    
    // Store deve funcionar mesmo com localStorage quebrado
    store.gold = 1000
    store.target = 5

    expect(store.gold).toBe(1000)
    expect(store.target).toBe(5)
    expect(store.result).toBeDefined()
  })

  it('handles non-Error exceptions gracefully', () => {
    // Mock localStorage para lançar algo que não é Error
    const localStorageMock = {
      getItem: vi.fn(() => null),
      setItem: vi.fn(() => {
        throw 'String error'
      }),
      removeItem: vi.fn(),
      clear: vi.fn(),
    }
    Object.defineProperty(window, 'localStorage', { value: localStorageMock, writable: true })

    const store = useCakeStore()
    store.gold = 500

    // Deve ter logado mesmo com exceção não-Error
    expect(console.warn).toHaveBeenCalledWith(
      expect.stringContaining('Falha ao salvar configurações de bolo no localStorage'),
      'String error',
    )
  })

  it('does not log when localStorage works correctly', () => {
    // Mock localStorage normal
    const localStorageMock = {
      getItem: vi.fn(() => null),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
    }
    Object.defineProperty(window, 'localStorage', { value: localStorageMock, writable: true })

    const store = useCakeStore()
    store.gold = 2000

    // Não deve ter logado warning
    expect(console.warn).not.toHaveBeenCalled()
  })

  it('maintains state consistency across localStorage failures', () => {
    let shouldFail = true
    
    const localStorageMock = {
      getItem: vi.fn(() => null),
      setItem: vi.fn(() => {
        if (shouldFail) throw new Error('QuotaExceededError')
      }),
      removeItem: vi.fn(),
      clear: vi.fn(),
    }
    Object.defineProperty(window, 'localStorage', { value: localStorageMock, writable: true })

    const store = useCakeStore()
    
    // Primeira mudança falha
    store.gold = 1000
    expect(store.gold).toBe(1000)
    
    // localStorage "recupera"
    shouldFail = false
    
    // Segunda mudança funciona
    store.gold = 2000
    expect(store.gold).toBe(2000)
    expect(localStorageMock.setItem).toHaveBeenCalled()
  })
})
