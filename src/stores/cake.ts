import { defineStore } from 'pinia'
import { computed, reactive, ref, watch } from 'vue'

import {
  cakeRecipes,
  calculateCakes,
  emptyStock,
  priceDefaults,
  type CakeValues,
} from '@/domain/cakes'
import type { CakeState } from '@/types/progress'
import { useChecklistStore } from './checklist'

const STORAGE_KEY = 'palworld-cake-state-v1'

function clampNumber(value: unknown): number {
  const next = Number(value)
  return Number.isFinite(next) && next > 0 ? next : 0
}

function mergeValues(
  base: CakeValues,
  patch?: Partial<CakeValues> | Record<string, number>,
): CakeValues {
  const next = { ...base }
  if (!patch) return next
  for (const key of Object.keys(next) as Array<keyof CakeValues>) {
    if (patch[key] != null) next[key] = clampNumber(patch[key])
  }
  return next
}

function readState(): CakeState {
  try {
    const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}') as Partial<CakeState>
    return {
      recipe: typeof raw.recipe === 'string' ? raw.recipe : 'cake',
      gold: clampNumber(raw.gold),
      target: clampNumber(raw.target),
      prices: mergeValues(priceDefaults, raw.prices),
      stock: mergeValues(emptyStock, raw.stock),
    }
  } catch {
    return {
      recipe: 'cake',
      gold: 0,
      target: 0,
      prices: { ...priceDefaults },
      stock: { ...emptyStock },
    }
  }
}

function writeState(state: CakeState): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  } catch {
    /* quota / private mode — disco via /progress ainda cobre */
  }
}

export const useCakeStore = defineStore('cake', () => {
  const stored = readState()
  const recipeId = ref(stored.recipe)
  const gold = ref(stored.gold)
  const target = ref(stored.target)
  const prices = reactive<CakeValues>({ ...stored.prices })
  const stock = reactive<CakeValues>({ ...stored.stock })
  let suppressPersist = false

  const recipe = computed(
    () => cakeRecipes.find((item) => item.id === recipeId.value) ?? cakeRecipes[0]!,
  )
  const result = computed(() =>
    calculateCakes(gold.value, target.value, recipe.value, stock, prices),
  )

  function snapshot(): CakeState {
    return {
      recipe: recipeId.value,
      gold: gold.value,
      target: target.value,
      prices: { ...prices },
      stock: { ...stock },
    }
  }

  function hydrate(next: CakeState | undefined | null): void {
    if (!next) return
    suppressPersist = true
    try {
      recipeId.value = typeof next.recipe === 'string' ? next.recipe : recipeId.value
      gold.value = clampNumber(next.gold)
      target.value = clampNumber(next.target)
      Object.assign(prices, mergeValues(priceDefaults, next.prices))
      Object.assign(stock, mergeValues(emptyStock, next.stock))
      writeState(snapshot())
    } finally {
      suppressPersist = false
    }
  }

  watch(
    [recipeId, gold, target, prices, stock],
    () => {
      if (suppressPersist) return
      const state = snapshot()
      writeState(state)
      const checklist = useChecklistStore()
      if (checklist.initialized) checklist.scheduleSave()
    },
    { deep: true },
  )

  function resetPrices(): void {
    Object.assign(prices, priceDefaults)
  }

  function applyPurchase(): void {
    if (result.value.amount <= 0) return
    for (const item of recipe.value.ingredients) {
      stock[item.stock] += result.value.purchases[item.key] ?? 0
    }
    gold.value = result.value.remaining
  }

  return {
    recipeId,
    gold,
    target,
    prices,
    stock,
    recipes: cakeRecipes,
    recipe,
    result,
    snapshot,
    hydrate,
    resetPrices,
    applyPurchase,
  }
})
