<script setup lang="ts">
import Button from 'primevue/button'
import Message from 'primevue/message'
import ProgressSpinner from 'primevue/progressspinner'
import { onBeforeUnmount, onMounted, watch } from 'vue'

import AppShell from '@/components/layout/AppShell.vue'
import { useAppStore } from '@/stores/app'
import { useChecklistStore } from '@/stores/checklist'
import { usePreferencesStore } from '@/stores/preferences'
import { useServerHudStore } from '@/stores/serverHud'

const app = useAppStore()
const checklist = useChecklistStore()
const preferences = usePreferencesStore()
const server = useServerHudStore()

watch(
  preferences.values,
  () => {
    if (checklist.initialized) checklist.scheduleSave()
  },
  { deep: true },
)

function initialize(): void {
  void app.initialize()
}

onMounted(() => {
  initialize()
  server.startMonitoring()
  window.addEventListener('beforeunload', checklist.flush)
})

onBeforeUnmount(() => {
  server.stopMonitoring()
  window.removeEventListener('beforeunload', checklist.flush)
})
</script>

<template>
  <AppShell>
    <div v-if="app.loading && !app.ready" class="center-state">
      <ProgressSpinner aria-label="Loading data" />
      <p>Loading Palworld data…</p>
    </div>
    <div v-else-if="app.error && !app.ready" class="center-state">
      <Message severity="error" :closable="false">{{ app.error }}</Message>
      <Button label="Try again" icon="pi pi-refresh" @click="initialize" />
    </div>
    <RouterView v-else />
  </AppShell>
</template>
