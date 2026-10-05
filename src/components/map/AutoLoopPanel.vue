<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue'

import { useAutoLoopStore } from '@/stores/autoLoop'

const loop = useAutoLoopStore()

const COORD_LABELS: Record<string, string> = {
  RETURN_TO_TITLE: 'Return to Title',
  YES: 'Yes',
  START_GAME: 'Start Game (1st)',
  PALPAGOS_ISLANDS: 'Palpagos Islands',
  START_GAME_2: 'Start Game (2nd, final)',
}

// In the order they occur in the sequence
const WAIT_FIELDS = [
  { key: 'afterThrow', label: 'Throw→attack', title: 'Wait after throwing Pal, before attack (s)' },
  { key: 'wait1', label: 'Wait 1', title: 'Wait 1 after attack, before Esc (s)' },
  { key: 'afterHud', label: 'Post-HUD', title: 'Wait after HUD recognition, before key E (s)' },
] as const

const statusText = computed(() => {
  if (loop.paused) return 'Paused'
  if (loop.running) return 'Running'
  if (loop.calibrating) return 'Calibrating'
  return 'Stopped'
})

const stepText = computed(() => {
  const s = loop.state
  if (!s || !loop.running || s.stepIndex < 0) return '—'
  return `${s.stepIndex + 1}/${s.steps.length} · ${s.step}`
})

onMounted(() => void loop.poll())
onBeforeUnmount(() => loop.stopPolling())
</script>

<template>
  <div class="autoloop">
    <div class="tools-section-label">Auto Loop · {{ statusText }}</div>
    <div class="autoloop__waits">
      <label v-for="field in WAIT_FIELDS" :key="field.key" class="autoloop__field" :title="field.title">
        {{ field.label }}
        <input
          v-model.number="loop.waits[field.key]"
          type="number"
          class="coords-input"
          min="0"
          step="0.1"
          :disabled="loop.running"
          :aria-label="field.title"
        />
      </label>
    </div>
    <div v-if="loop.error || loop.state?.status === 'error'" class="autoloop__alert">
      {{ loop.error || loop.state?.error }}
    </div>
    <div class="tools-row">
      <button
        class="primary-btn"
        :class="{ 'icon-btn--danger': loop.running }"
        style="width: 100%"
        type="button"
        :disabled="loop.calibrating"
        @click="void loop.toggle()"
      >
        {{ loop.running ? 'Stop Auto Loop (F10)' : 'Start Auto Loop' }}
      </button>
    </div>
    <div class="autoloop__info">
      <div>Step: {{ stepText }}</div>
      <div>Iterations: {{ loop.state?.iterations ?? 0 }}</div>
      <div v-if="loop.paused" class="autoloop__warn">{{ loop.state?.message }}</div>
      <div v-else-if="loop.state?.message">{{ loop.state.message }}</div>
    </div>
    <details class="autoloop__calibrate">
      <summary>Positions (learned via OCR on 1st run)</summary>
      <div v-for="(label, key) in COORD_LABELS" :key="key" class="coords-display">
        {{ label }}:
        <template v-if="loop.state?.coords[key]">
          {{ loop.state.coords[key]![0] }}, {{ loop.state.coords[key]![1] }}
        </template>
        <em v-else>not learned yet</em>
      </div>
      <div class="tools-row">
        <button
          class="primary-btn"
          style="width: 100%"
          type="button"
          :disabled="loop.running || loop.calibrating"
          title="Forget positions; on the next run OCR will locate buttons again"
          @click="void loop.resetPositions()"
        >
          Recalibrate via OCR
        </button>
      </div>
    </details>
  </div>
</template>

<style scoped>
.autoloop__waits {
  display: grid;
  gap: 4px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin-bottom: 4px;
}
.autoloop__field {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 0.65rem;
  min-width: 0;
}
.autoloop__field input {
  min-width: 0;
  width: 100%;
}
.autoloop__info {
  font-size: 0.75rem;
  line-height: 1.4;
  margin: 4px 0;
}
.autoloop__warn {
  color: #f0a040;
}
.autoloop__alert {
  background: rgba(240, 160, 64, 0.15);
  border: 1px solid #f0a040;
  border-radius: 6px;
  color: #f0a040;
  font-size: 0.75rem;
  margin: 4px 0;
  padding: 6px 8px;
}
.autoloop__calibrate {
  font-size: 0.75rem;
}
</style>