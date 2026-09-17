import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useBreedingStore = defineStore('breeding', () => {
  const parentA = ref('')
  const parentB = ref('')
  const targetChild = ref('')
  const pathFrom = ref('')
  const pathTo = ref('')
  const ownedOnly = ref(false)
  const ownedSearch = ref('')
  const showOwnedOnly = ref(false)

  return {
    parentA,
    parentB,
    targetChild,
    pathFrom,
    pathTo,
    ownedOnly,
    ownedSearch,
    showOwnedOnly,
  }
})
