import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import rawRecipes from '@/data/recipes.json'
import {
  buildBracket,
  buildCraftPlan,
  listRootKeys,
  loadRecipeBook,
  sanitizeQuantity,
} from '@/domain/itemCraft'

/** The app only ever reads this generated file — paldb.cc is never hit at runtime. */
const book = loadRecipeBook(rawRecipes)

export const useItemCrafterStore = defineStore('itemCrafter', () => {
  const roots = listRootKeys(book)

  /** Selected root key from the dropdown; the first root (AI Core) is preselected. */
  const itemKey = ref(roots[0] ?? '')
  /** Raw input; may be null while the field is being edited. */
  const quantity = ref<number | null>(1)

  const options = computed(() =>
    roots.map((key) => ({ key, label: book.entries.get(key)?.name ?? key })),
  )

  const effectiveQuantity = computed(() => sanitizeQuantity(quantity.value))

  const plan = computed(() =>
    itemKey.value ? buildCraftPlan(book, itemKey.value, effectiveQuantity.value) : null,
  )

  /** Same tree laid out as a tournament bracket (rounds + champion column). */
  const bracket = computed(() => (plan.value ? buildBracket(plan.value.tree) : null))

  const materials = computed(() => plan.value?.materials ?? [])
  const warnings = computed(() => plan.value?.warnings ?? [])
  const hasData = computed(() => roots.length > 0)

  function selectItem(key: string | null): void {
    itemKey.value = key ?? roots[0] ?? ''
  }

  return {
    options,
    itemKey,
    quantity,
    effectiveQuantity,
    plan,
    bracket,
    materials,
    warnings,
    hasData,
    selectItem,
  }
})
