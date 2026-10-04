import { defineStore } from 'pinia'
import { computed, reactive, ref, watch } from 'vue'

import { ApiError, api } from '@/services/api'
import type { ArenaLoopState } from '@/types/server'

const STORAGE_KEY = 'palworld:arena:config'

export const ARENA_RANKS = ['Bronze', 'Silver', 'Gold', 'Platinum', 'Diamond', 'Master'] as const

export const ARENA_WAIT_FIELDS = [
  { key: 'afterF', label: 'Após F', title: 'Espera após apertar F (s)' },
  { key: 'afterChallenge', label: 'Após Challenge', title: 'Espera após clicar Challenge (s)' },
  { key: 'afterRank', label: 'Após rank', title: 'Espera após clicar no rank (s)' },
  { key: 'afterYes', label: 'Após Yes', title: 'Espera após clicar Yes, antes da lista de Pals (s)' },
  { key: 'afterPal', label: 'Entre Pals', title: 'Espera após cada clique de Pal (s)' },
  { key: 'afterReady', label: 'Após Ready', title: 'Espera após Ready, antes de vigiar a tela preta (s)' },
  { key: 'afterBlack', label: 'Pós-preto', title: 'Espera ao sair do preto, antes de segurar S (s)' },
  { key: 'beforeF', label: 'Antes do F', title: 'Espera extra antes de apertar F e reiniciar o loop (s)' },
  { key: 'findTimeout', label: 'Timeout botão', title: 'Tempo máximo para achar um botão/texto (s)' },
  { key: 'battleTimeout', label: 'Timeout luta', title: 'Tempo máximo esperando a tela ficar preta (s)' },
  { key: 'blackCycles', label: 'Ciclos de preto', title: 'Quantas vezes a tela fica preta e volta (ex.: carregamento + fim da luta)' },
] as const

const DEFAULTS = {
  afterF: 1.5,
  afterChallenge: 1,
  afterRank: 1,
  afterYes: 2,
  afterPal: 0.4,
  afterReady: 1,
  afterBlack: 1,
  beforeF: 1,
  findTimeout: 20,
  battleTimeout: 600,
  blackCycles: 2,
  ranks: ['Platinum'] as string[],
  pals: [1, 2, 3] as number[],
}
type Config = typeof DEFAULTS

function loadConfig(): Config {
  try {
    const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}') as Partial<Config>
    return { ...DEFAULTS, ...raw, ranks: [...(raw.ranks ?? DEFAULTS.ranks)], pals: [...(raw.pals ?? DEFAULTS.pals)] }
  } catch {
    return { ...DEFAULTS, ranks: [...DEFAULTS.ranks], pals: [...DEFAULTS.pals] }
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

export const useArenaLoopStore = defineStore('arenaLoop', () => {
  const config = reactive<Config>(loadConfig())
  const state = ref<ArenaLoopState | null>(null)
  const error = ref('')
  let timer: number | undefined
  let polling = false

  watch(config, () => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(config))
    } catch {
      /* storage indisponível */
    }
  })

  const running = computed(() => state.value?.active === true)
  const paused = computed(() => state.value?.status === 'paused')

  function schedule(): void {
    window.clearTimeout(timer)
    timer = running.value ? window.setTimeout(() => void poll(), 400) : undefined
  }

  async function poll(): Promise<void> {
    if (polling) return
    polling = true
    try {
      state.value = await api.getArenaLoopState()
      if (state.value.status !== 'error' || running.value) error.value = ''
    } catch (cause) {
      error.value = describeError(cause)
    } finally {
      polling = false
      if (state.value?.active) schedule()
    }
  }

  function toggleItem<T>(list: T[], item: T, checked: boolean): void {
    const index = list.indexOf(item)
    if (checked && index < 0) list.push(item)
    else if (!checked && index >= 0) list.splice(index, 1)
  }

  async function toggle(): Promise<void> {
    error.value = ''
    try {
      if (running.value) await api.stopArenaLoop()
      else await api.startArenaLoop({ ...config })
    } catch (cause) {
      error.value = describeError(cause)
    }
    await poll()
    schedule()
  }

  function stopPolling(): void {
    window.clearTimeout(timer)
    timer = undefined
  }

  return { config, state, error, running, paused, poll, toggle, toggleItem, stopPolling }
})
