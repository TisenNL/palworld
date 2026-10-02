import { defineStore } from 'pinia'
import { computed, reactive, ref, watch } from 'vue'

import { ApiError, api } from '@/services/api'
import type { AutoLoopState } from '@/types/server'

const STORAGE_KEY = 'palworld:autoloop:waits'

const DEFAULT_WAITS = { afterThrow: 2, wait1: 0 }
type Waits = typeof DEFAULT_WAITS

function loadWaits(): Waits {
  try {
    const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}') as Record<string, unknown>
    const read = (value: unknown, fallback: number): number =>
      typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : fallback
    return {
      afterThrow: read(raw.afterThrow, DEFAULT_WAITS.afterThrow),
      wait1: read(raw.wait1, DEFAULT_WAITS.wait1),
    }
  } catch {
    return { ...DEFAULT_WAITS }
  }
}

function describeError(cause: unknown): string {
  if (cause instanceof ApiError) {
    try {
      const parsed = JSON.parse(cause.message) as { error?: unknown }
      if (typeof parsed.error === 'string' && parsed.error) return parsed.error
    } catch {
      /* corpo não-JSON */
    }
    return cause.message
  }
  return 'Helper offline — inicie o helper Python (start.bat)'
}

export const useAutoLoopStore = defineStore('autoLoop', () => {
  const waits = reactive<Waits>(loadWaits())
  const state = ref<AutoLoopState | null>(null)
  const error = ref('')
  let timer: number | undefined
  let polling = false

  watch(waits, () => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(waits))
    } catch {
      /* storage indisponível */
    }
  })

  const running = computed(() => state.value?.active === true)
  const calibrating = computed(() => state.value?.calibrating === true)
  const paused = computed(() => state.value?.status === 'paused')

  function schedule(): void {
    window.clearTimeout(timer)
    timer = undefined
    if (running.value || calibrating.value) {
      timer = window.setTimeout(() => void poll(), 400)
    }
  }

  async function poll(): Promise<void> {
    if (polling) return
    polling = true
    try {
      state.value = await api.getAutoLoopState()
      if (state.value.status !== 'error' || running.value) error.value = ''
    } catch (cause) {
      error.value = describeError(cause)
    } finally {
      polling = false
      // Mantém tentando enquanto o helper estava ativo, para detectar a volta/queda
      if (state.value?.active || state.value?.calibrating) schedule()
    }
  }

  function sanitize(value: number): number {
    return Number.isFinite(value) && value > 0 ? value : 0
  }

  async function toggle(): Promise<void> {
    error.value = ''
    try {
      if (running.value) {
        await api.stopAutoLoop()
      } else {
        for (const key of Object.keys(waits) as (keyof Waits)[]) waits[key] = sanitize(waits[key])
        await api.startAutoLoop({ ...waits })
      }
    } catch (cause) {
      error.value = describeError(cause)
    }
    await poll()
    schedule()
  }

  async function calibrate(target: string): Promise<void> {
    error.value = ''
    try {
      await api.calibrateAutoLoop(target)
    } catch (cause) {
      error.value = describeError(cause)
    }
    await poll()
    schedule()
  }

  async function resetPositions(): Promise<void> {
    error.value = ''
    try {
      await api.resetAutoLoopPositions()
    } catch (cause) {
      error.value = describeError(cause)
    }
    await poll()
  }

  function stopPolling(): void {
    window.clearTimeout(timer)
    timer = undefined
  }

  return { waits, state, error, running, calibrating, paused, poll, toggle, calibrate, resetPositions, stopPolling }
})
