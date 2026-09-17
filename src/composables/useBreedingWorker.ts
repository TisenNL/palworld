import { onScopeDispose, ref } from 'vue'

import type { BreedData } from '@/types/data'
import type { BreedingWorkerRequest } from '@/workers/breeding.worker'

type WorkerInput = BreedingWorkerRequest extends infer Request
  ? Request extends BreedingWorkerRequest
    ? Omit<Request, 'id' | 'data'>
    : never
  : never

export function useBreedingWorker(data: () => BreedData | null) {
  const busy = ref(false)
  let sequence = 0
  let worker: Worker | null = null
  const pending = new Map<
    number,
    { resolve: (value: unknown) => void; reject: (reason?: unknown) => void }
  >()

  function ensureWorker(): Worker {
    if (worker) return worker
    worker = new Worker(new URL('../workers/breeding.worker.ts', import.meta.url), {
      type: 'module',
    })
    worker.onmessage = (event: MessageEvent<{ id: number; result?: unknown; error?: string }>) => {
      const request = pending.get(event.data.id)
      if (!request) return
      pending.delete(event.data.id)
      busy.value = pending.size > 0
      if (event.data.error) request.reject(new Error(event.data.error))
      else request.resolve(event.data.result)
    }
    return worker
  }

  function run<T>(input: WorkerInput): Promise<T> {
    const source = data()
    if (!source) return Promise.reject(new Error('Breeding data is unavailable'))
    const id = ++sequence
    busy.value = true
    return new Promise<T>((resolve, reject) => {
      pending.set(id, {
        resolve: (value) => resolve(value as T),
        reject,
      })
      ensureWorker().postMessage({ ...input, id, data: source })
    })
  }

  onScopeDispose(() => {
    worker?.terminate()
    for (const request of pending.values()) request.reject(new Error('Calculation cancelled'))
    pending.clear()
  })

  return { busy, run }
}
