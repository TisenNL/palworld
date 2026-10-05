<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue'

import { ARENA_RANKS, ARENA_WAIT_FIELDS, useArenaLoopStore } from '@/stores/arenaLoop'

const arena = useArenaLoopStore()

const statusText = computed(() => {
  if (arena.paused) return 'Paused'
  return arena.running ? 'Running' : 'Stopped'
})

const stepText = computed(() => {
  const s = arena.state
  if (!s || !arena.running || s.stepIndex < 0) return '—'
  return `${s.stepIndex + 1}/${s.steps.length} · ${s.step}`
})

const palsOk = computed(() => arena.config.pals.length === 3)

onMounted(() => void arena.poll())
onBeforeUnmount(() => arena.stopPolling())
</script>

<template>
  <div class="arena">
    <div class="tools-section-label">Arena Loop · {{ statusText }}</div>
    <div class="arena__group">
      <span class="arena__label">Ranks (rotates each fight)</span>
      <label v-for="rank in ARENA_RANKS" :key="rank" class="arena__check">
        <input
          type="checkbox"
          :checked="arena.config.ranks.includes(rank)"
          :disabled="arena.running"
          @change="arena.toggleItem(arena.config.ranks, rank, ($event.target as HTMLInputElement).checked)"
        />
        {{ rank }}
      </label>
    </div>
    <div class="arena__group">
      <span class="arena__label">Pals (select 3 out of 5 positions)</span>
      <label v-for="n in 5" :key="n" class="arena__check">
        <input
          type="checkbox"
          :checked="arena.config.pals.includes(n)"
          :disabled="arena.running"
          @change="arena.toggleItem(arena.config.pals, n, ($event.target as HTMLInputElement).checked)"
        />
        {{ n }}
      </label>
    </div>
    <div class="arena__waits">
      <label v-for="field in ARENA_WAIT_FIELDS" :key="field.key" class="arena__field" :title="field.title">
        {{ field.label }}
        <input
          v-model.number="arena.config[field.key]"
          type="number"
          class="coords-input"
          min="0"
          step="0.1"
          :disabled="arena.running"
          :aria-label="field.title"
        />
      </label>
    </div>
    <div v-if="arena.error || arena.state?.status === 'error'" class="arena__alert">
      {{ arena.error || arena.state?.error }}
    </div>
    <div class="tools-row">
      <button
        class="primary-btn"
        :class="{ 'icon-btn--danger': arena.running }"
        style="width: 100%"
        type="button"
        :disabled="!arena.running && (!palsOk || arena.config.ranks.length === 0)"
        @click="void arena.toggle()"
      >
        {{ arena.running ? 'Stop Arena Loop (F10)' : 'Start Arena Loop' }}
      </button>
    </div>
    <div class="arena__info">
      <div>Step: {{ stepText }}</div>
      <div>Fights: {{ arena.state?.iterations ?? 0 }}</div>
      <div v-if="arena.state?.message">{{ arena.state.message }}</div>
    </div>
  </div>
</template>

<style scoped>
.arena__group {
  display: flex;
  flex-wrap: wrap;
  gap: 2px 10px;
  font-size: 0.72rem;
  margin-bottom: 4px;
}
.arena__label {
  flex-basis: 100%;
  font-size: 0.65rem;
  opacity: 0.8;
}
.arena__check {
  align-items: center;
  display: flex;
  gap: 3px;
}
.arena__waits {
  display: grid;
  gap: 4px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin-bottom: 4px;
}
.arena__field {
  display: flex;
  flex-direction: column;
  font-size: 0.65rem;
  gap: 2px;
  min-width: 0;
}
.arena__field input {
  min-width: 0;
  width: 100%;
}
.arena__info {
  font-size: 0.75rem;
  line-height: 1.4;
  margin: 4px 0;
}
.arena__alert {
  background: rgba(240, 160, 64, 0.15);
  border-radius: 4px;
  font-size: 0.72rem;
  margin: 4px 0;
  padding: 4px 6px;
}
</style>