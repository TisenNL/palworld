import { defineStore } from 'pinia'
import { computed, onScopeDispose, ref } from 'vue'

import { api } from '@/services/api'
import type { CoordinateItem } from '@/types/data'
import type { GameMarkerState, HealthState, MouseLoopState } from '@/types/server'

export const useServerHudStore = defineStore('serverHud', () => {
  const health = ref<HealthState | null>(null)
  const checking = ref(false)
  const ocrBusy = ref(false)
  const gameMarker = ref<GameMarkerState | null>(null)
  const mouseLoop = ref<MouseLoopState | null>(null)
  const error = ref('')
  let timer: number | undefined
  let gameMarkerTimer: number | undefined
  let mouseLoopTimer: number | undefined

  const online = computed(() => health.value?.ok === true)
  const gameMarkerBusy = computed(() => gameMarker.value?.active === true)
  const mouseLoopBusy = computed(() => mouseLoop.value?.active === true)

  async function refreshHealth(): Promise<void> {
    if (checking.value) return
    checking.value = true
    try {
      health.value = await api.health()
      error.value = ''
    } catch {
      health.value = null
    } finally {
      checking.value = false
    }
  }

  function startMonitoring(): void {
    if (timer) return
    void refreshHealth()
    timer = window.setInterval(() => void refreshHealth(), 3_000)
  }

  function stopMonitoring(): void {
    window.clearInterval(timer)
    timer = undefined
  }

  function stopGameMarkerPolling(): void {
    window.clearTimeout(gameMarkerTimer)
    gameMarkerTimer = undefined
  }

  function stopMouseLoopPolling(): void {
    window.clearTimeout(mouseLoopTimer)
    mouseLoopTimer = undefined
  }

  async function pollGameMarker(): Promise<void> {
    stopGameMarkerPolling()
    try {
      gameMarker.value = await api.getGameMarkerState()
      if (gameMarker.value.active) {
        gameMarkerTimer = window.setTimeout(() => void pollGameMarker(), 150)
      }
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : 'Game marker status failed'
    }
  }

  async function pollMouseLoop(): Promise<void> {
    stopMouseLoopPolling()
    try {
      mouseLoop.value = await api.getMouseLoopState()
      if (mouseLoop.value.active) {
        mouseLoopTimer = window.setTimeout(() => void pollMouseLoop(), 800)
      }
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : 'Mouse loop status failed'
    }
  }

  async function startGameMarker(item: CoordinateItem, dryRun = false): Promise<void> {
    error.value = ''
    try {
      await api.startGameMarker(item.x, item.y, dryRun)
      await pollGameMarker()
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : 'Game marker automation failed'
      throw cause
    }
  }

  async function cancelGameMarker(): Promise<void> {
    try {
      await api.cancelGameMarker()
    } finally {
      await pollGameMarker()
    }
  }

  async function startMouseLoop(intervalSeconds: number): Promise<void> {
    error.value = ''
    try {
      await api.startMouseLoop(intervalSeconds)
      await pollMouseLoop()
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : 'Mouse combo loop failed'
      throw cause
    }
  }

  async function stopMouseLoop(): Promise<void> {
    try {
      await api.stopMouseLoop()
    } finally {
      await pollMouseLoop()
    }
  }

  async function toggleHud(item: CoordinateItem, label: string): Promise<boolean> {
    const same = health.value?.active && health.value.x === item.x && health.value.y === item.y
    if (same) {
      await api.clearHud()
      await refreshHealth()
      return false
    }
    await api.setHud(item.x, item.y, label)
    await refreshHealth()
    return true
  }

  async function clearHud(): Promise<void> {
    await api.clearHud()
    await refreshHealth()
  }

  async function readCoordinates(): Promise<string> {
    if (ocrBusy.value) return ''
    ocrBusy.value = true
    error.value = ''
    try {
      await api.startOcr()
      const deadline = Date.now() + 90_000
      while (Date.now() < deadline) {
        await new Promise((resolve) => window.setTimeout(resolve, 450))
        const state = await api.getOcrState()
        if (state.status === 'copied') return state.text
        if (state.status === 'error') throw new Error(state.error || 'OCR failed')
        if (state.status === 'cancelled') return ''
      }
      throw new Error('Tempo do OCR esgotado')
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : 'OCR failed'
      throw cause
    } finally {
      ocrBusy.value = false
    }
  }

  onScopeDispose(() => {
    stopMonitoring()
    stopGameMarkerPolling()
    stopMouseLoopPolling()
  })

  return {
    health,
    online,
    checking,
    ocrBusy,
    gameMarker,
    gameMarkerBusy,
    mouseLoop,
    mouseLoopBusy,
    error,
    startMonitoring,
    stopMonitoring,
    refreshHealth,
    toggleHud,
    clearHud,
    readCoordinates,
    startGameMarker,
    cancelGameMarker,
    pollGameMarker,
    startMouseLoop,
    stopMouseLoop,
    pollMouseLoop,
  }
})
