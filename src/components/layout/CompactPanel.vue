<script setup lang="ts">
import Panel from 'primevue/panel'
import { computed } from 'vue'

const props = defineProps<{
  title: string
  open?: boolean
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
}>()

const collapsed = computed({
  get: () => !props.open,
  set: (value: boolean) => emit('update:open', !value),
})
</script>

<template>
  <Panel v-model:collapsed="collapsed" toggleable class="compact-panel">
    <template #header>
      <span class="compact-panel-title"><slot name="icon" />{{ title }}</span>
    </template>
    <slot />
  </Panel>
</template>

<style scoped>
.compact-panel {
  flex: 0 0 auto;
  overflow: hidden;
  border-color: var(--border);
  background: rgb(13 22 40 / var(--sidebar-alpha, 0.88));
}

.compact-panel-title {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 0.76rem;
  font-weight: 800;
}

:deep(.p-panel-header) {
  min-height: 38px;
  padding: 0.46rem 0.65rem;
}

:deep(.p-panel-content) {
  padding: 0.6rem;
}
</style>
