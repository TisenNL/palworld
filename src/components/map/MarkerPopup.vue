<script setup lang="ts">
import { computed } from 'vue'
import type { Marker } from '@/types/opggMarker'
import { markerDisplayName, markerTypeLabel } from '@/types/opggMarker'
import { formatIngameCoords } from '@/domain/opggCoordinates'
import { getMarkerIconUrl, getMarkerColor } from '@/domain/opggMarkerIcons'

const props = defineProps<{
  marker: Marker
  checked: boolean       // Discovered / Found status
  batchSelected?: boolean // Selected for batch in-game marking
}>()

const emit = defineEmits<{
  close: []
  toggleChecked: []
  toggleBatch: []
  markIngame: []
}>()

const title = computed(() => markerDisplayName(props.marker))
const subtitle = computed(() => markerTypeLabel(props.marker.type, props.marker.subtype ?? null))
const coords = computed(() =>
  formatIngameCoords(props.marker.ingameX, props.marker.ingameY, props.marker.ingameZ)
)
const iconUrl = computed(() => getMarkerIconUrl(props.marker))
const color   = computed(() => getMarkerColor(props.marker))
const level   = computed(() => {
  const lv = props.marker.extra?.level
  return typeof lv === 'number' ? lv : null
})
</script>

<template>
  <div class="marker-popup palworld-map-control-blur">
    <!-- Header -->
    <div class="marker-popup__header">
      <span
        class="marker-popup__icon"
        :style="{
          borderColor: color,
          backgroundImage: iconUrl ? `url('${iconUrl}')` : undefined,
        }"
        aria-hidden="true"
      />
      <div class="marker-popup__title-group">
        <div class="marker-popup__title">
          <span v-if="level != null" class="marker-popup__level">Lv.{{ level }}</span>
          {{ title }}
        </div>
        <div class="marker-popup__subtitle">{{ subtitle }}</div>
      </div>
      <button
        class="marker-popup__close"
        type="button"
        aria-label="Close"
        @click="emit('close')"
      >✕</button>
    </div>

    <!-- Coordinates -->
    <div class="marker-popup__coords">{{ coords }}</div>

    <!-- Actions Section -->
    <div class="marker-popup__actions">
      <!-- Direct Mark in Game button -->
      <button
        class="marker-popup__btn marker-popup__btn--primary"
        type="button"
        title="Mark this position directly in game now"
        @click="emit('markIngame')"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
             fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"/>
          <line x1="12" y1="8" x2="12" y2="16"/>
          <line x1="8" y1="12" x2="16" y2="12"/>
        </svg>
        <span>Mark in Game</span>
      </button>

      <!-- Toggle Batch Selection button -->
      <button
        class="marker-popup__btn"
        :class="{ 'marker-popup__btn--active': batchSelected }"
        type="button"
        title="Add/Remove from batch marking queue"
        @click="emit('toggleBatch')"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
             fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="9 11 12 14 22 4"/>
          <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
        </svg>
        <span>{{ batchSelected ? 'In Batch Queue' : 'Add to Batch' }}</span>
      </button>

      <!-- Discovered / Found toggle -->
      <button
        class="marker-popup__toggle"
        :class="{ 'marker-popup__toggle--checked': checked }"
        type="button"
        @click="emit('toggleChecked')"
      >
        <span class="marker-popup__toggle-icon" aria-hidden="true">
          <template v-if="checked">
            <!-- Eye icon (discovered) -->
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
                 fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/>
              <circle cx="12" cy="12" r="3"/>
            </svg>
          </template>
          <template v-else>
            <!-- EyeOff icon (not discovered) -->
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
                 fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M10.733 5.076a10.744 10.744 0 0 1 11.205 6.575 1 1 0 0 1 0 .696 10.747 10.747 0 0 1-1.444 2.49"/>
              <path d="M14.084 14.158a3 3 0 0 1-4.242-4.242"/>
              <path d="M17.479 17.499a10.75 10.75 0 0 1-15.417-5.151 1 1 0 0 1 0-.696 10.75 10.75 0 0 1 4.446-5.143"/>
              <path d="m2 2 20 20"/>
            </svg>
          </template>
        </span>
        <span>{{ checked ? 'Discovered' : 'Not Discovered' }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.marker-popup {
  position: relative;
  background: rgba(20, 20, 40, 0.96);
  border: 1px solid #3c3c4d;
  border-radius: 12px;
  min-width: 220px;
  max-width: 280px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.6);
  overflow: hidden;
}

.marker-popup__header {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 12px 8px;
}

.marker-popup__icon {
  flex-shrink: 0;
  display: block;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: 2px solid transparent;
  background-color: rgba(15, 20, 40, 0.8);
  background-size: 80%;
  background-repeat: no-repeat;
  background-position: center;
}

.marker-popup__title-group {
  flex: 1;
  min-width: 0;
}

.marker-popup__title {
  font-size: 13px;
  font-weight: 700;
  color: #e0e0f8;
  line-height: 1.3;
  display: flex;
  align-items: center;
  gap: 5px;
  flex-wrap: wrap;
}

.marker-popup__level {
  font-size: 10px;
  background: rgba(108, 92, 231, 0.3);
  border: 1px solid rgba(108, 92, 231, 0.5);
  border-radius: 4px;
  color: #c4b5fd;
  padding: 1px 4px;
  white-space: nowrap;
}

.marker-popup__subtitle {
  font-size: 10px;
  color: #7777aa;
  margin-top: 2px;
}

.marker-popup__close {
  flex-shrink: 0;
  background: none;
  border: none;
  color: #6666aa;
  cursor: pointer;
  font-size: 12px;
  padding: 2px 4px;
  border-radius: 4px;
  line-height: 1;
  margin-top: -2px;
  transition: color 0.15s, background 0.15s;
}

.marker-popup__close:hover {
  color: #ccc;
  background: rgba(255, 255, 255, 0.08);
}

.marker-popup__coords {
  padding: 0 12px 10px;
  font-size: 11px;
  font-weight: 600;
  color: #8888bb;
  letter-spacing: 0.02em;
}

.marker-popup__actions {
  display: flex;
  flex-direction: column;
  border-top: 1px solid #2a2a3e;
}

.marker-popup__btn {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 12px;
  background: transparent;
  border: none;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  color: #a0a0c0;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
  text-align: left;
}

.marker-popup__btn:hover {
  background: rgba(255, 255, 255, 0.06);
  color: #ffffff;
}

.marker-popup__btn--primary {
  color: #61afef;
}

.marker-popup__btn--primary:hover {
  background: rgba(97, 175, 239, 0.15);
  color: #8cc2ff;
}

.marker-popup__btn--active {
  color: #a78bfa;
  background: rgba(108, 92, 231, 0.15);
}

.marker-popup__btn--active:hover {
  background: rgba(108, 92, 231, 0.25);
}

.marker-popup__toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.02);
  border: none;
  color: #8888aa;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
  text-align: left;
}

.marker-popup__toggle:hover {
  background: rgba(108, 92, 231, 0.12);
  color: #ccccff;
}

.marker-popup__toggle--checked {
  color: #98c379;
}

.marker-popup__toggle-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.06);
  flex-shrink: 0;
}
</style>