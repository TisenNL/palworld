/// <reference lib="webworker" />

import { createBreedingEngine } from '@/domain/breeding'
import type { BreedData } from '@/types/data'

export type BreedingWorkerRequest =
  | {
      id: number
      action: 'cancel'
    }
  | {
      id: number
      action: 'parents'
      data: BreedData
      child: string
      owned: string[] | null
    }
  | {
      id: number
      action: 'path'
      data: BreedData
      from: string
      to: string
      includeTarget: boolean
      hideIgnoreCombi: boolean
    }
  | {
      id: number
      action: 'generations'
      data: BreedData
      owned: string[]
    }
  | {
      id: number
      action: 'cancel'
    }

let currentCancelId: number | null = null

let cancelFlag = false
let timeoutId: number | undefined

self.onmessage = (event: MessageEvent<BreedingWorkerRequest>) => {
  const request = event.data

  // Processa mensagem de cancelamento
  if (request.action === 'cancel') {
    cancelFlag = true
    if (timeoutId !== undefined) {
      clearTimeout(timeoutId)
      timeoutId = undefined
    }
    return
  }

  // Reset flag de cancelamento para nova operação
  cancelFlag = false
  const engine = createBreedingEngine(request.data)

  // Timeout de 5 segundos para prevenir operações travadas
  timeoutId = self.setTimeout(() => {
    self.postMessage({ id: request.id, error: 'Operation timeout (>5s)' })
    cancelFlag = true
  }, 5000)

  try {
    let result: unknown
    if (request.action === 'parents') {
      result = engine.parentsFor(request.child, request.owned ? new Set(request.owned) : undefined)
    } else if (request.action === 'path') {
      result = engine.path(request.from, request.to, request.includeTarget, request.hideIgnoreCombi)
    } else {
      result = engine.generations(request.owned)
    }

    if (cancelFlag) {
      self.postMessage({ id: request.id, error: 'Operation cancelled' })
    } else {
      self.postMessage({ id: request.id, result })
    }
  } catch (cause) {
    self.postMessage({
      id: request.id,
      error: cause instanceof Error ? cause.message : 'Calculation failed',
    })
  } finally {
    if (timeoutId !== undefined) {
      clearTimeout(timeoutId)
      timeoutId = undefined
    }
  }
}

export {}
