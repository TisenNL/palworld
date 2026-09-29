/// <reference lib="webworker" />

import { createBreedingEngine } from '@/domain/breeding'
import type { BreedData } from '@/types/data'

export type BreedingWorkerRequest =
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

self.onmessage = (event: MessageEvent<BreedingWorkerRequest>) => {
  const request = event.data
  if (request.action === 'cancel') {
    currentCancelId = request.id
    self.postMessage({ id: request.id, cancelled: true })
    return
  }
  const engine = createBreedingEngine(request.data)
  try {
    let result: unknown
    if (request.action === 'parents') {
      result = engine.parentsFor(request.child, request.owned ? new Set(request.owned) : undefined)
    } else if (request.action === 'path') {
      result = engine.path(request.from, request.to, request.includeTarget, request.hideIgnoreCombi)
    } else {
      result = engine.generations(request.owned)
    }
    if (currentCancelId === request.id) {
      self.postMessage({ id: request.id, cancelled: true })
    } else {
      self.postMessage({ id: request.id, result })
    }
  } catch (cause) {
    self.postMessage({
      id: request.id,
      error: cause instanceof Error ? cause.message : 'Calculation failed',
    })
  }
}

export {}
