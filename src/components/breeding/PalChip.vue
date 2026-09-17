<script setup lang="ts">
import SafeImage from '@/components/common/SafeImage.vue'
import type { Pal } from '@/types/data'

defineProps<{
  pal?: Pal
  owned?: boolean
  interactive?: boolean
}>()

defineEmits<{
  toggle: []
}>()
</script>

<template>
  <component
    :is="interactive ? 'button' : 'span'"
    class="pal-chip"
    :class="{ owned, interactive }"
    :type="interactive ? 'button' : undefined"
    @click="interactive && $emit('toggle')"
  >
    <SafeImage v-if="pal" class="pal-image" :src="pal.icon" :fallback-label="pal.name" />
    <span>{{ pal ? `${pal.id} ${pal.name}` : 'Pal desconhecido' }}</span>
  </component>
</template>

<style scoped>
.pal-chip {
  display: inline-flex;
  min-width: 0;
  align-items: center;
  gap: 7px;
  padding: 5px 8px;
  border: 1px solid var(--border);
  border-radius: 10px;
  color: var(--text);
  font-size: 0.78rem;
  font-weight: 650;
  background: color-mix(in srgb, var(--panel-solid) 78%, transparent);
}

.pal-chip.interactive {
  width: 100%;
  text-align: left;
  cursor: pointer;
}

.pal-chip.owned {
  border-color: rgba(34, 197, 94, 0.55);
  background: rgba(34, 197, 94, 0.12);
}

.pal-image {
  flex: 0 0 30px;
  width: 30px;
  height: 30px;
  border-radius: 7px;
}

span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
