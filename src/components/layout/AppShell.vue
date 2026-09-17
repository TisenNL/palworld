<script setup lang="ts">
import Toast from 'primevue/toast'
import { onBeforeUnmount, onMounted } from 'vue'
import { useRoute } from 'vue-router'

import { usePreferencesStore } from '@/stores/preferences'

const route = useRoute()
const preferences = usePreferencesStore()

const items = [
  { route: '/lists', label: 'Lists', icon: 'pi pi-list-check' },
  { route: '/map', label: 'Map', icon: 'pi pi-map' },
  { route: '/cakes', label: 'Cakes', icon: 'pi pi-calculator' },
  { route: '/breeding', label: 'Breeding', icon: 'pi pi-sitemap' },
]

const isActive = (path: string): boolean => route.path === path

onMounted(() => document.documentElement.classList.add('app-dark'))

onBeforeUnmount(() => document.documentElement.classList.remove('app-dark'))
</script>

<template>
  <div
    class="app-shell app-dark"
    :style="{
      '--sidebar-width': `${preferences.values.sidebarWidth}px`,
      '--sidebar-alpha': `${Math.max(0.18, 1 - preferences.values.sidebarTransparency / 100)}`,
    }"
  >
    <header class="app-header">
      <RouterLink to="/map" class="brand">
        <span class="brand-mark">P</span>
        <span class="brand-copy">
          <strong>Palworld Checklist</strong>
          <small>local progress and interactive map</small>
        </span>
      </RouterLink>
      <nav aria-label="Primary navigation">
        <RouterLink
          v-for="item in items"
          :key="item.route"
          :to="item.route"
          class="nav-link"
          :class="{ active: isActive(item.route) }"
        >
          <i :class="item.icon" aria-hidden="true" />
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>
    </header>
    <main class="app-main">
      <slot />
    </main>
    <Toast position="bottom-right" />
  </div>
</template>
