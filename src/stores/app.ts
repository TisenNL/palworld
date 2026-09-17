import { defineStore } from 'pinia'
import { computed } from 'vue'

import { useChecklistStore } from './checklist'

export const useAppStore = defineStore('app', () => {
  const checklist = useChecklistStore()
  const ready = computed(() => checklist.initialized)
  const loading = computed(() => checklist.loading)
  const error = computed(() => checklist.error)

  const initialize = (): Promise<void> => checklist.initialize()

  return { ready, loading, error, initialize }
})
