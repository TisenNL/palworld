import { defineStore } from 'pinia'
import { computed, onScopeDispose, ref } from 'vue'
import { z } from 'zod'

import { api } from '@/services/api'
import {
  batchQueueItemSchema,
  type BatchEnqueueResult,
  type BatchQueueDraft,
  type BatchQueueItem,
  type BatchRunSummary,
} from '@/types/batch'
import type { CoordinateItem } from '@/types/data'
import type {
  GameMarkerState,
  HealthState,
  MouseLoopState,
  PlayerPositionState,
} from '@/types/server'

// ── Fila de "Mark in game" em lote ─────────────────────────────────────────────

const BATCH_QUEUE_KEY = 'palworld:map:mark-queue'
const MARK_MAX_RETRIES = 3
const MARK_RETRY_DELAY_MS = 800
/** Segurança contra travamento: automação que nunca chega a um status terminal */
const MARK_WAIT_TIMEOUT_MS = 180_000
const TERMINAL_GAME_MARKER_STATUSES = new Set(['completed', 'cancelled', 'error'])

function loadBatchQueue(): BatchQueueItem[] {
  try {
    const raw = localStorage.getItem(BATCH_QUEUE_KEY)
    if (!raw) return []
    const parsed = z.array(batchQueueItemSchema).parse(JSON.parse(raw))
    // Estado transiente nunca é restaurado: item interrompido volta para a fila
    return parsed.map((item) =>
      item.status === 'processing' ? { ...item, status: 'pending' } : item,
    )
  } catch {
    return []
  }
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

export const useServerHudStore = defineStore('serverHud', () => {
  const health = ref<HealthState | null>(null)
  const checking = ref(false)
  const ocrBusy = ref(false)
  const gameMarker = ref<GameMarkerState | null>(null)
  const mouseLoop = ref<MouseLoopState | null>(null)
  const playerPosition = ref<PlayerPositionState | null>(null)
  const error = ref('')
  let timer: number | undefined
  let gameMarkerTimer: number | undefined
  let mouseLoopTimer: number | undefined
  let playerPositionTimer: number | undefined
  let pollingGameMarker = false
  let pollingMouseLoop = false
  let pollingPlayerPosition = false
  let playerPositionPollingEnabled = false

  const online = computed(() => health.value?.ok === true)
  const gameMarkerBusy = computed(() => gameMarker.value?.active === true)
  const mouseLoopBusy = computed(() => mouseLoop.value?.active === true)

  // ── Fila de marcação em lote ──────────────────────────────────────────────────
  const batchQueue = ref<BatchQueueItem[]>(loadBatchQueue())
  const batchRunning = ref(false)
  const batchCurrentIndex = ref(-1)
  const batchTotal = ref(0)
  let batchCancelRequested = false

  /** Itens que ainda serão executados (pending/failed/processing) */
  const pendingBatchCount = computed(
    () => batchQueue.value.filter((item) => item.status !== 'completed').length,
  )

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

  async function pollPlayerPosition(): Promise<void> {
    if (!playerPositionPollingEnabled || pollingPlayerPosition) return
    pollingPlayerPosition = true
    try {
      playerPosition.value = await api.getPlayerPositionState()
    } catch (cause) {
      playerPosition.value = null
      error.value = cause instanceof Error ? cause.message : 'Player position status failed'
    } finally {
      pollingPlayerPosition = false
      if (playerPositionPollingEnabled) {
        const delayMs =
          playerPosition.value?.status === 'ready' ? 250 : 1_500
        playerPositionTimer = window.setTimeout(() => void pollPlayerPosition(), delayMs)
      }
    }
  }

  function startPlayerPositionPolling(): void {
    if (playerPositionPollingEnabled) return
    playerPositionPollingEnabled = true
    void pollPlayerPosition()
  }

  function stopPlayerPositionPolling(): void {
    playerPositionPollingEnabled = false
    window.clearTimeout(playerPositionTimer)
    playerPositionTimer = undefined
  }

  async function pollGameMarker(): Promise<void> {
    if (pollingGameMarker) return
    pollingGameMarker = true
    stopGameMarkerPolling()
    try {
      gameMarker.value = await api.getGameMarkerState()
      if (gameMarker.value.active) {
        gameMarkerTimer = window.setTimeout(() => void pollGameMarker(), 150)
      }
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : 'Game marker status failed'
      // Uma falha transitória não pode matar o polling: `waitForGameMarkerDone`
      // depende dele para sair do laço. Reagenda com backoff enquanto a
      // automação ainda estiver ativa.
      if (gameMarker.value?.active === true) {
        gameMarkerTimer = window.setTimeout(() => void pollGameMarker(), 1_000)
      }
    } finally {
      pollingGameMarker = false
    }
  }

  async function pollMouseLoop(): Promise<void> {
    if (pollingMouseLoop) return
    pollingMouseLoop = true
    stopMouseLoopPolling()
    try {
      mouseLoop.value = await api.getMouseLoopState()
      if (mouseLoop.value.active) {
        mouseLoopTimer = window.setTimeout(() => void pollMouseLoop(), 800)
      }
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : 'Mouse loop status failed'
      if (mouseLoop.value?.active === true) {
        mouseLoopTimer = window.setTimeout(() => void pollMouseLoop(), 1_000)
      }
    } finally {
      pollingMouseLoop = false
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

  /** Aguarda a automação atual chegar a um status terminal (poll do /game-marker/state). */
  async function waitForGameMarkerDone(): Promise<string> {
    const deadline = Date.now() + MARK_WAIT_TIMEOUT_MS
    for (;;) {
      const state = gameMarker.value
      if (state && !state.active && TERMINAL_GAME_MARKER_STATUSES.has(state.status)) {
        return state.status
      }
      // Estado desconhecido (o primeiro poll falhou) ou já fora de execução:
      // pergunta de novo em vez de girar ocioso até estourar o timeout.
      if (!state || !state.active) await pollGameMarker()
      const fresh = gameMarker.value
      if (fresh && !fresh.active && TERMINAL_GAME_MARKER_STATUSES.has(fresh.status)) {
        return fresh.status
      }
      if (Date.now() > deadline) return 'error'
      await delay(150)
    }
  }

  /**
   * Executa a automação de mark para um único alvo, com retries.
   * Reutilizada pelo fluxo single (MapView) e pelo lote (startBatchMark).
   */
  async function runSingleMark(
    item: { id: string; x: number; y: number },
    options: { maxRetries?: number; onStarted?: () => void } = {},
  ): Promise<'completed' | 'cancelled' | 'error'> {
    const maxRetries = options.maxRetries ?? MARK_MAX_RETRIES
    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      try {
        await startGameMarker(item)
      } catch {
        // Falha ao iniciar (ocupado/offline) — nova tentativa após um intervalo
        if (attempt === maxRetries) return 'error'
        await delay(MARK_RETRY_DELAY_MS)
        continue
      }
      options.onStarted?.()
      const status = await waitForGameMarkerDone()
      if (status === 'completed' || status === 'cancelled') return status
      if (attempt < maxRetries) await delay(MARK_RETRY_DELAY_MS)
    }
    return 'error'
  }

  function persistBatchQueue(): void {
    try {
      localStorage.setItem(BATCH_QUEUE_KEY, JSON.stringify(batchQueue.value))
    } catch {
      // storage indisponível — a fila simplesmente não persiste nesta sessão
    }
  }

  /** Adiciona itens à fila. A fila nunca mistura zonas de mapa. */
  function enqueueBatch(drafts: BatchQueueDraft[]): BatchEnqueueResult {
    if (batchRunning.value) return 'running'
    if (drafts.length === 0) return 'ok'
    const zone = drafts[0]!.zone
    if (drafts.some((draft) => draft.zone !== zone)) return 'mixed-zone'
    if (batchQueue.value.some((item) => item.zone !== zone)) return 'mixed-zone'
    batchQueue.value.push(...drafts.map((draft) => ({ ...draft, status: 'pending' as const })))
    persistBatchQueue()
    return 'ok'
  }

  function removeBatchItem(id: string): void {
    if (batchRunning.value) return
    batchQueue.value = batchQueue.value.filter((item) => item.id !== id)
    persistBatchQueue()
  }

  function clearBatchQueue(): void {
    if (batchRunning.value) return
    batchQueue.value = []
    batchCurrentIndex.value = -1
    batchTotal.value = 0
    persistBatchQueue()
  }

  /** Cancela o item em execução e interrompe o lote; o item volta para a fila. */
  async function cancelBatchMark(): Promise<void> {
    batchCancelRequested = true
    try {
      await cancelGameMarker()
    } catch {
      // waitForGameMarkerDone detectará o terminal (ou estourará o timeout)
    }
  }

  /**
   * Executa a fila sequencialmente: cada item pending/failed roda via
   * runSingleMark; no primeiro erro o lote para e o restante fica pending.
   * Itens completed são pulados (re-run = refazer o que falta).
   */
  async function startBatchMark(): Promise<BatchRunSummary> {
    if (batchRunning.value) return { completed: 0, failed: 0, cancelled: true }
    const runnable = batchQueue.value.filter((item) => item.status !== 'completed')
    if (runnable.length === 0) return { completed: 0, failed: 0, cancelled: false }

    batchRunning.value = true
    batchCancelRequested = false
    batchTotal.value = runnable.length
    batchCurrentIndex.value = -1
    let completed = 0
    let failed = 0
    let cancelled = false

    try {
      for (const item of batchQueue.value) {
        if (item.status === 'completed') continue
        if (batchCancelRequested) break
        batchCurrentIndex.value++
        item.status = 'processing'
        delete item.error
        persistBatchQueue()

        const status = await runSingleMark({ id: item.id, x: item.x, y: item.y })
        if (status === 'completed') {
          item.status = 'completed'
          completed++
        } else if (status === 'cancelled' || batchCancelRequested) {
          item.status = 'pending'
          cancelled = true
          break
        } else {
          item.status = 'failed'
          item.error = gameMarker.value?.error || gameMarker.value?.message || 'Automation failed'
          failed++
          break
        }
        persistBatchQueue()
      }
    } finally {
      batchRunning.value = false
      batchCurrentIndex.value = -1
      persistBatchQueue()
    }
    return { completed, failed, cancelled }
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
    stopPlayerPositionPolling()
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
    playerPosition,
    error,
    batchQueue,
    batchRunning,
    batchCurrentIndex,
    batchTotal,
    pendingBatchCount,
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
    startPlayerPositionPolling,
    stopPlayerPositionPolling,
    waitForGameMarkerDone,
    runSingleMark,
    enqueueBatch,
    removeBatchItem,
    clearBatchQueue,
    cancelBatchMark,
    startBatchMark,
  }
})
