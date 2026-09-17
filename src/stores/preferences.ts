import { defineStore } from 'pinia'
import { reactive, watch } from 'vue'

import { preferencesSchema, type Preferences } from '@/types/progress'

const STORAGE_KEY = 'palworld-prefs-v1'

function readPreferences(): Preferences {
  try {
    return preferencesSchema.parse(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}'))
  } catch {
    return preferencesSchema.parse({})
  }
}

export const usePreferencesStore = defineStore('preferences', () => {
  const values = reactive<Preferences>(readPreferences())

  watch(
    values,
    (next) => {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
    },
    { deep: true },
  )

  function apply(next: Partial<Preferences>): void {
    Object.assign(values, preferencesSchema.parse({ ...values, ...next }))
  }

  return { values, apply }
})
