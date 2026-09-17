<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { api } from '@/services/api'
const props = withDefaults(
  defineProps<{
    src: string
    alt?: string
    fallbackLabel?: string
    lazy?: boolean
  }>(),
  {
    alt: '',
    fallbackLabel: '?',
    lazy: true,
  },
)

const failed = ref(false)
const resolvedSource = computed(() =>
  /^https:\/\/cdn\.paldb\.cc\//i.test(props.src) ? api.mapIconUrl(props.src) : props.src,
)

watch(
  () => props.src,
  () => {
    failed.value = false
  },
)
</script>

<template>
  <span class="safe-image" :class="{ failed }">
    <img
      v-if="src && !failed"
      :src="resolvedSource"
      :alt="alt"
      :loading="lazy ? 'lazy' : 'eager'"
      decoding="async"
      @error="failed = true"
    />
    <span v-else class="safe-image-fallback" aria-hidden="true">
      {{ fallbackLabel.slice(0, 2).toUpperCase() }}
    </span>
  </span>
</template>

<style scoped>
.safe-image {
  display: inline-grid;
  width: 100%;
  height: 100%;
  overflow: hidden;
  place-items: center;
  border-radius: inherit;
}

img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.safe-image-fallback {
  display: grid;
  width: 100%;
  height: 100%;
  place-items: center;
  color: #c4f1ff;
  font-size: 0.7em;
  font-weight: 900;
  background: linear-gradient(135deg, #15324a, #252f5a);
}
</style>
