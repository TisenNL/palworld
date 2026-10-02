<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue'

import { useAutoLoopStore } from '@/stores/autoLoop'

const loop = useAutoLoopStore()

const COORD_LABELS: Record<string, string> = {
  RETURN_TO_TITLE: 'Return to Title',
  YES: 'Yes',
  START_GAME: 'Start Game (1º)',
  PALPAGOS_ISLANDS: 'Palpagos Islands',
  START_GAME_2: 'Start Game (2º, final)',
}

// Na ordem em que acontecem na sequência
const WAIT_FIELDS = [
  { key: 'afterThrow', label: 'Lançar→ataque', title: 'Espera após lançar o Pal, antes do ataque (s)' },
  { key: 'wait1', label: 'Espera 1', title: 'Espera 1 após o ataque, antes do Esc (s)' },
  { key: 'afterYes', label: 'Pós-Yes', title: 'Espera após clicar em Yes (s)' },
  { key: 'wait2', label: 'Espera 2', title: 'Espera 2 no fim da sequência (s)' },
] as const

const statusText = computed(() => {
  if (loop.paused) return 'Pausado'
  if (loop.running) return 'Rodando'
  if (loop.calibrating) return 'Calibrando'
  return 'Parado'
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
        {{ loop.running ? 'Parar Auto Loop (F10)' : 'Iniciar Auto Loop' }}
      </button>
    </div>
    <div class="autoloop__info">
      <div>Passo: {{ stepText }}</div>
      <div>Iterações: {{ loop.state?.iterations ?? 0 }}</div>
      <div v-if="loop.paused" class="autoloop__warn">{{ loop.state?.message }}</div>
      <div v-else-if="loop.state?.message">{{ loop.state.message }}</div>
    </div>
    <details class="autoloop__calibrate">
      <summary>Posições (aprendidas pelo OCR na 1ª execução)</summary>
      <div v-for="(label, key) in COORD_LABELS" :key="key" class="coords-display">
        {{ label }}:
        <template v-if="loop.state?.coords[key]">
          {{ loop.state.coords[key]![0] }}, {{ loop.state.coords[key]![1] }}
        </template>
        <em v-else>ainda não aprendido</em>
      </div>
      <div class="tools-row">
        <button
          class="primary-btn"
          style="width: 100%"
          type="button"
          :disabled="loop.running || loop.calibrating"
          title="Esquece as posições; na próxima execução o OCR localiza os botões de novo"
          @click="void loop.resetPositions()"
        >
          Calibrar por OCR de novo
        </button>
      </div>
    </details>
  </div>
</template>

<style scoped>
.autoloop__waits {
  display: grid;
  gap: 4px;
  grid-template-columns: repeat(4, minmax(0, 1fr));
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
