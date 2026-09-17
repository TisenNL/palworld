<script setup lang="ts">
import Button from 'primevue/button'
import Checkbox from 'primevue/checkbox'
import InputText from 'primevue/inputtext'
import ProgressBar from 'primevue/progressbar'
import Select from 'primevue/select'
import VirtualScroller from 'primevue/virtualscroller'
import { useToast } from 'primevue/usetoast'
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import CompactPanel from '@/components/layout/CompactPanel.vue'
import { layerGroups } from '@/domain/layers'
import { useChecklistStore } from '@/stores/checklist'
import { usePreferencesStore } from '@/stores/preferences'
import { progressSchema } from '@/types/progress'

const checklist = useChecklistStore()
const preferences = usePreferencesStore()
const route = useRoute()
const toast = useToast()
const query = ref('')
const layerId = ref('')
const fileInput = ref<HTMLInputElement | null>(null)
const scroller = ref<InstanceType<typeof VirtualScroller> | null>(null)

const group = computed({
  get: () => preferences.values.listBrowseGroup,
  set: (value: string) => {
    preferences.values.listBrowseGroup = value
    layerId.value = ''
  },
})

const groupLayers = computed(() =>
  group.value ? checklist.layers.filter((layer) => layer.group === group.value) : checklist.layers,
)

const layerOptions = computed(() => [
  { label: 'All types', value: '' },
  ...groupLayers.value.map((layer) => ({ label: layer.label, value: layer.id })),
])

function layersForGroup(groupId: string) {
  return checklist.layers.filter((layer) => layer.group === groupId)
}

function toggleGroup(groupId: string, event: Event): void {
  const open = (event.currentTarget as HTMLDetailsElement).open
  if (open) group.value = groupId
  else if (group.value === groupId) group.value = ''
}

const filtered = computed(() => {
  const normalized = query.value.trim().toLocaleLowerCase()
  const allowed = new Set(groupLayers.value.map((layer) => layer.id))
  return checklist.entries.filter((item) => {
    if (group.value && !allowed.has(item.layerId)) return false
    if (layerId.value && item.layerId !== layerId.value) return false
    if (
      normalized &&
      !`${item.name ?? ''} ${item.type ?? ''} ${item.layerLabel} ${item.x} ${item.y} ${item.n ?? ''}`
        .toLocaleLowerCase()
        .includes(normalized)
    )
      return false
    return !preferences.values.hideDone || !checklist.isDone(item.storage, item.id)
  })
})

const doneCount = computed(
  () => checklist.entries.filter((item) => checklist.isDone(item.storage, item.id)).length,
)
const progress = computed(() =>
  checklist.entries.length ? (doneCount.value / checklist.entries.length) * 100 : 0,
)

const itemLabel = (item: (typeof filtered.value)[number]): string => {
  const label = item.name ?? `${item.type ?? item.layerLabel}${item.n ? ` #${item.n}` : ''}`
  return item.volume ? `${label} · ${item.volume} nodes` : label
}

function panelOpen(key: string, fallback = true): boolean {
  return preferences.values.sideBlockOpen[key] ?? fallback
}

function setPanelOpen(key: string, value: boolean): void {
  preferences.values.sideBlockOpen[key] = value
}

function setFiltered(done: boolean): void {
  for (const item of filtered.value) checklist.setDone(item.storage, item.id, done)
}

function exportProgress(): void {
  const blob = new Blob([JSON.stringify(checklist.exportProgress(), null, 2)], {
    type: 'application/json',
  })
  const anchor = document.createElement('a')
  anchor.href = URL.createObjectURL(blob)
  anchor.download = `palworld-progress-${new Date().toISOString().slice(0, 10)}.json`
  anchor.click()
  URL.revokeObjectURL(anchor.href)
}

async function importProgress(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  try {
    checklist.replaceProgress(progressSchema.parse(JSON.parse(await file.text())))
    toast.add({
      severity: 'success',
      summary: 'Progress imported',
      detail: 'Lists and preferences were restored.',
      life: 2800,
    })
  } catch {
    toast.add({
      severity: 'error',
      summary: 'Invalid file',
      detail: 'The file does not contain compatible progress data.',
      life: 3500,
    })
  } finally {
    input.value = ''
  }
}

async function focusRouteItem(): Promise<void> {
  const target = String(route.query.item ?? '')
  if (!target) return
  group.value = ''
  layerId.value = ''
  query.value = ''
  await nextTick()
  const index = filtered.value.findIndex((item) => item.uid === target)
  if (index >= 0) scroller.value?.scrollToIndex(index, 'smooth')
}

onMounted(() => void focusRouteItem())
watch(
  () => route.query.item,
  () => void focusRouteItem(),
)
</script>

<template>
  <div class="workspace lists-view">
    <aside class="sidebar">
      <div class="sidebar-scroll">
        <CompactPanel
          title="Search and filters"
          :open="panelOpen('lists-filters')"
          @update:open="setPanelOpen('lists-filters', $event)"
        >
          <div class="filter-stack">
            <InputText v-model="query" fluid placeholder="Search by name, type, or coordinates…" />
            <Select
              v-model="layerId"
              :options="layerOptions"
              option-label="label"
              option-value="value"
              fluid
              aria-label="Filter by type"
            />
            <label class="inline-check">
              <Checkbox v-model="preferences.values.hideDone" binary />
              Hide completed
            </label>
          </div>
        </CompactPanel>

        <CompactPanel
          title="Categories"
          :open="panelOpen('lists-categories')"
          @update:open="setPanelOpen('lists-categories', $event)"
        >
          <div class="category-accordions">
            <details
              v-for="item in layerGroups"
              :key="item.id"
              class="category-section"
              :open="group === item.id"
              @toggle="toggleGroup(item.id, $event)"
            >
              <summary>{{ item.label }}</summary>
              <div class="layer-list">
                <button
                  v-for="layer in layersForGroup(item.id)"
                  :key="layer.id"
                  type="button"
                  class="layer-button"
                  :class="{ active: layerId === layer.id }"
                  @click="layerId = layerId === layer.id ? '' : layer.id"
                >
                  <span class="layer-color" :style="{ background: layer.color }" />
                  <span>{{ layer.label }}</span>
                </button>
              </div>
            </details>
          </div>
        </CompactPanel>

        <CompactPanel
          title="Actions"
          :open="panelOpen('lists-actions', false)"
          @update:open="setPanelOpen('lists-actions', $event)"
        >
          <div class="action-grid">
            <Button
              label="Mark visible"
              icon="pi pi-check"
              size="small"
              @click="setFiltered(true)"
            />
            <Button
              label="Clear visible"
              icon="pi pi-times"
              size="small"
              severity="secondary"
              @click="setFiltered(false)"
            />
            <Button
              label="Export"
              icon="pi pi-download"
              size="small"
              outlined
              @click="exportProgress"
            />
            <Button
              label="Import"
              icon="pi pi-upload"
              size="small"
              outlined
              @click="fileInput?.click()"
            />
            <input
              ref="fileInput"
              hidden
              type="file"
              accept="application/json"
              @change="importProgress"
            />
          </div>
        </CompactPanel>
      </div>
      <div class="sidebar-footer">
        <span>{{ filtered.length.toLocaleString('en-US') }} visible</span>
        <span
          >{{ doneCount.toLocaleString('en-US') }}/{{
            checklist.entries.length.toLocaleString('en-US')
          }}</span
        >
      </div>
    </aside>

    <section class="content-pane list-content">
      <header class="list-header">
        <div>
          <h1 class="view-title">Progress lists</h1>
          <p class="view-subtitle">Mark visited locations and keep the map synchronized.</p>
        </div>
        <div class="progress-summary">
          <strong>{{ Math.round(progress) }}%</strong>
          <ProgressBar :value="progress" :show-value="false" />
        </div>
      </header>

      <VirtualScroller
        ref="scroller"
        :items="filtered"
        :item-size="64"
        class="list-scroller glass-card"
      >
        <template #item="{ item }">
          <label class="checklist-row" :class="{ done: checklist.isDone(item.storage, item.id) }">
            <Checkbox
              :model-value="checklist.isDone(item.storage, item.id)"
              binary
              @update:model-value="checklist.setDone(item.storage, item.id, Boolean($event))"
            />
            <span class="row-color" :style="{ background: item.color }" />
            <span class="row-copy">
              <strong>{{ itemLabel(item) }}</strong>
              <small>{{ item.layerLabel }} · {{ item.x }}, {{ item.y }}</small>
            </span>
          </label>
        </template>
      </VirtualScroller>
    </section>
  </div>
</template>

<style scoped>
.list-content {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 14px;
  padding: 22px;
}

.list-header {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 24px;
}

.view-subtitle {
  margin-bottom: 0;
}

.progress-summary {
  display: grid;
  grid-template-columns: 42px 150px;
  align-items: center;
  gap: 8px;
}

.filter-stack,
.layer-list {
  display: grid;
  gap: 7px;
}

.inline-check {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--muted);
  font-size: 0.82rem;
}

.category-accordions {
  display: grid;
  gap: 5px;
}

.category-section {
  border: 1px solid transparent;
  border-radius: 8px;
}

.category-section[open] {
  border-color: var(--border);
  background: color-mix(in srgb, var(--accent) 6%, transparent);
}

.category-section > summary,
.layer-button {
  display: flex;
  width: 100%;
  min-height: 34px;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 9px;
  border: 1px solid transparent;
  border-radius: 8px;
  color: var(--text);
  text-align: left;
  background: transparent;
  cursor: pointer;
}

.category-section > summary {
  list-style: none;
}

.category-section > summary::-webkit-details-marker {
  display: none;
}

.category-section > summary::after {
  content: '›';
  margin-left: auto;
  font-size: 1.15rem;
  line-height: 1;
  transition: transform 140ms;
}

.category-section[open] > summary::after {
  transform: rotate(90deg);
}

.category-section > summary:hover,
.layer-button:hover,
.layer-button.active {
  border-color: var(--border);
  background: color-mix(in srgb, var(--accent) 10%, transparent);
}

.layer-button {
  justify-content: start;
}

.category-section .layer-list {
  padding: 0 5px 6px;
}

.layer-color,
.row-color {
  flex: 0 0 9px;
  width: 9px;
  height: 9px;
  border-radius: 50%;
}

.action-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
}

.list-scroller {
  min-height: 0;
  height: 100%;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.checklist-row {
  display: flex;
  height: 64px;
  align-items: center;
  gap: 11px;
  padding: 8px 14px;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  transition: background 120ms;
}

.checklist-row:hover {
  background: color-mix(in srgb, var(--accent) 7%, transparent);
}

.checklist-row.done {
  opacity: 0.55;
}

.row-copy {
  display: grid;
  min-width: 0;
  gap: 3px;
}

.row-copy strong,
.row-copy small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.row-copy strong {
  font-size: 0.88rem;
}

.row-copy small {
  color: var(--muted);
  font-size: 0.75rem;
}

@media (max-width: 860px) {
  .list-content {
    padding: 12px;
  }

  .list-header {
    align-items: start;
  }

  .view-subtitle {
    display: none;
  }

  .progress-summary {
    grid-template-columns: 34px 90px;
  }
}
</style>
