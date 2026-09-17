import { defineStore } from 'pinia'
import { computed, reactive, ref, watch } from 'vue'

import {
  cakeRecipes,
  calculateCakes,
  emptyStock,
  priceDefaults,
  type CakeValues,
} from '@/domain/cakes'

const STORAGE_KEY = 'palworld-cake-state-v1'

interface StoredCake {
  recipe?: string
  gold?: number
  target?: number
  prices?: Partial<CakeValues>
  stock?: Partial<CakeValues>
}

function readState(): StoredCake {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}') as StoredCake
  } catch {
    return {}
  }
}

export const useCakeStore = defineStore('cake', () => {
  const stored = readState()
  const recipeId = ref(stored.recipe ?? 'cake')
  const gold = ref(Math.max(0, Number(stored.gold) || 0))
  const target = ref(Math.max(0, Number(stored.target) || 0))
  const prices = reactive<CakeValues>({ ...priceDefaults, ...stored.prices })
  const stock = reactive<CakeValues>({ ...emptyStock, ...stored.stock })

  const recipe = computed(
    () => cakeRecipes.find((item) => item.id === recipeId.value) ?? cakeRecipes[0]!,
  )
  const result = computed(() =>
    calculateCakes(gold.value, target.value, recipe.value, stock, prices),
  )

  watch(
    [recipeId, gold, target, prices, stock],
    () => {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          recipe: recipeId.value,
          gold: gold.value,
          target: target.value,
          prices,
          stock,
        }),
      )
    },
    { deep: true },
  )

  function resetPrices(): void {
    Object.assign(prices, priceDefaults)
  }

  function applyPurchase(): void {
    if (result.value.amount <= 0) return
    stock.flour += Math.floor((result.value.purchases.wheat ?? 0) / 3)
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
    resetPrices,
    applyPurchase,
  }
})
