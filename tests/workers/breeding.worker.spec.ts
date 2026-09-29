import { describe, expect, it, vi, beforeEach } from 'vitest'
import type { BreedData } from '@/types/data'

// Mock do worker para testes
class MockBreedingWorker {
  private cancelFlag = false
  private timeoutId: number | undefined
  onmessage: ((event: MessageEvent) => void) | null = null

  postMessage(data: any) {
    // Simula o comportamento do worker
    if (!this.onmessage) return

    if (data.action === 'cancel') {
      this.cancelFlag = true
      if (this.timeoutId !== undefined) {
        clearTimeout(this.timeoutId)
        this.timeoutId = undefined
      }
      return
    }

    this.cancelFlag = false
    
    // Simula timeout de 5 segundos
    this.timeoutId = window.setTimeout(() => {
      if (this.onmessage) {
        this.onmessage(new MessageEvent('message', {
          data: { id: data.id, error: 'Operation timeout (>5s)' }
        }))
      }
      this.cancelFlag = true
    }, 5000)

    // Simula processamento
    setTimeout(() => {
      if (this.cancelFlag) {
        if (this.onmessage) {
          this.onmessage(new MessageEvent('message', {
            data: { id: data.id, error: 'Operation cancelled' }
          }))
        }
      } else {
        if (this.onmessage) {
          this.onmessage(new MessageEvent('message', {
            data: { id: data.id, result: 'mock-result' }
          }))
        }
      }

      if (this.timeoutId !== undefined) {
        clearTimeout(this.timeoutId)
        this.timeoutId = undefined
      }
    }, 100)
  }

  terminate() {
    if (this.timeoutId !== undefined) {
      clearTimeout(this.timeoutId)
      this.timeoutId = undefined
    }
  }
}

describe('breeding worker - timeout and cancellation', () => {
  let worker: MockBreedingWorker

  beforeEach(() => {
    worker = new MockBreedingWorker()
    vi.useFakeTimers()
  })

  afterEach(() => {
    worker.terminate()
    vi.useRealTimers()
  })

  it('responds with timeout error after 5 seconds', async () => {
    const mockData: BreedData = {
      version: 1,
      source: 'test',
      pals: [],
      unique: [],
    }

    return new Promise<void>((resolve) => {
      worker.onmessage = (event: MessageEvent) => {
        const response = event.data
        expect(response.error).toBe('Operation timeout (>5s)')
        resolve()
      }

      worker.postMessage({
        id: 1,
        action: 'path',
        data: mockData,
        from: 'a',
        to: 'b',
        includeTarget: false,
        hideIgnoreCombi: false,
      })

      // Avança tempo para acionar timeout
      vi.advanceTimersByTime(5000)
    })
  })

  it('can cancel an ongoing operation', async () => {
    const mockData: BreedData = {
      version: 1,
      source: 'test',
      pals: [],
      unique: [],
    }

    return new Promise<void>((resolve) => {
      worker.onmessage = (event: MessageEvent) => {
        const response = event.data
        // Deve receber mensagem de cancelamento
        if (response.error === 'Operation cancelled') {
          resolve()
        }
      }

      worker.postMessage({
        id: 1,
        action: 'generations',
        data: mockData,
        owned: [],
      })

      // Cancela após 50ms
      setTimeout(() => {
        worker.postMessage({ id: 1, action: 'cancel' })
      }, 50)

      // Avança tempo para processar cancelamento
      vi.advanceTimersByTime(150)
    })
  })

  it('completes successfully when not cancelled or timed out', async () => {
    const mockData: BreedData = {
      version: 1,
      source: 'test',
      pals: [],
      unique: [],
    }

    return new Promise<void>((resolve) => {
      worker.onmessage = (event: MessageEvent) => {
        const response = event.data
        // Deve completar com sucesso
        if (response.result === 'mock-result') {
          expect(response.error).toBeUndefined()
          resolve()
        }
      }

      worker.postMessage({
        id: 1,
        action: 'parents',
        data: mockData,
        child: 'test',
        owned: null,
      })

      // Avança apenas 100ms (antes do timeout de 5s)
      vi.advanceTimersByTime(100)
    })
  })

  it('clears timeout after successful completion', async () => {
    const mockData: BreedData = {
      version: 1,
      source: 'test',
      pals: [],
      unique: [],
    }

    let timeoutCleared = false

    return new Promise<void>((resolve) => {
      const originalSetTimeout = window.setTimeout
      const originalClearTimeout = window.clearTimeout

      // Espiona clearTimeout
      window.clearTimeout = (id: number) => {
        timeoutCleared = true
        return originalClearTimeout(id)
      }

      worker.onmessage = (event: MessageEvent) => {
        const response = event.data
        if (response.result === 'mock-result') {
          // Timeout deve ter sido limpo
          expect(timeoutCleared).toBe(true)
          
          // Restaura funções originais
          window.setTimeout = originalSetTimeout
          window.clearTimeout = originalClearTimeout
          resolve()
        }
      }

      worker.postMessage({
        id: 1,
        action: 'parents',
        data: mockData,
        child: 'test',
        owned: null,
      })

      vi.advanceTimersByTime(100)
    })
  })
})
