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

self.onmessage = (event: MessageEvent<BreedingWorkerRequest>) => {
  const request = event.data
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
    self.postMessage({ id: request.id, result })
  } catch (cause) {
    self.postMessage({
      id: request.id,
      error: cause instanceof Error ? cause.message : 'Calculation failed',
    })
  }
}

export {}
