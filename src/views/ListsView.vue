<script setup lang="ts">
import Button from 'primevue/button'
import Checkbox from 'primevue/checkbox'
import InputText from 'primevue/inputtext'
import ProgressBar from 'primevue/progressbar'
import Select from 'primevue/select'
import VirtualScroller from 'primevue/virtualscroller'
import { useToast } from 'primevue/usetoast'
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import CompactPanel from '@/components/layout/CompactPanel.vue'
import { layerGroups } from '@/domain/layers'
import { useChecklistStore } from '@/stores/checklist'
import { usePreferencesStore } from '@/stores/preferences'
import { progressSchema } from '@/types/progress'

// Set the desired number of columns
const COLS_PER_ROW = 5 

const checklist = useChecklistStore()
const preferences = usePreferencesStore()
const route = useRoute()
const router = useRouter()
const toast = useToast()
const query = ref('')

const fileInput = ref<HTMLInputElement | null>(null)
const scroller = ref<InstanceType<typeof VirtualScroller> | null>(null)

const layerId = computed({
  get: () => preferences.values.listBrowseLayer ?? '',
  set: (value: string) => {
    preferences.values.listBrowseLayer = value
  },
})

const group = computed({
  get: () => preferences.values.listBrowseGroup,
  set: (value: string) => {
    if (preferences.values.listBrowseGroup !== value) {
      preferences.values.listBrowseGroup = value
      preferences.values.listBrowseLayer = ''
    }
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
    return true
  })
})

// Chunks items into row arrays based on the defined number of columns
const chunkedFiltered = computed(() => {
  const chunks = []
  const items = filtered.value
  for (let i = 0; i < items.length; i += COLS_PER_ROW) {
    chunks.push(items.slice(i, i + COLS_PER_ROW))
  }
  return chunks
})

const doneCount = computed(
  () => checklist.entries.filter((item) => checklist.isDone(item.storage, item.id)).length,
)

const visibleDoneCount = computed(
  () => filtered.value.filter((item) => checklist.isDone(item.storage, item.id)).length,
)

const progress = computed(() =>
  checklist.entries.length ? (doneCount.value / checklist.entries.length) * 100 : 0,
)

const itemLabel = (item: (typeof filtered.value)[number]): string => {
  return item.name ?? `${item.type ?? item.layerLabel}${item.n ? ` #${item.n}` : ''}`
}

function panelOpen(key: string, fallback = true): boolean {
  return preferences.values.sideBlockOpen[key] ?? fallback
}

function setPanelOpen(key: string, value: boolean): void {
  preferences.values.sideBlockOpen[key] = value
}

function toggleSidebar(): void {
  preferences.values.sidebarCollapsed = !preferences.values.sidebarCollapsed
}

function setFiltered(done: boolean): void {
  for (const item of filtered.value) checklist.setDone(item.storage, item.id, done)
}

function goToMap(item: { x: number; y: number }): void {
  void router.push({
    path: '/map',
    query: { x: item.x, y: item.y },
  })
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
  if (index >= 0) {
    const rowIndex = Math.floor(index / COLS_PER_ROW)
    scroller.value?.scrollToIndex(rowIndex, 'smooth')
  }
}

onMounted(() => void focusRouteItem())
watch(
  () => route.query.item,
  () => void focusRouteItem(),
)
</script>

<template>
  <div class="workspace lists-view">
    <aside class="sidebar" :aria-hidden="preferences.values.sidebarCollapsed">
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

    <button
      type="button"
      class="sidebar-edge-toggle"
      :aria-label="preferences.values.sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'"
      :title="preferences.values.sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'"
      @click="toggleSidebar"
    >
      <i
        :class="preferences.values.sidebarCollapsed ? 'pi pi-angle-right' : 'pi pi-angle-left'"
        aria-hidden="true"
      />
    </button>

    <section class="content-pane list-content">
      <header class="dashboard-header">
        <div class="header-main">
          <h1 class="view-title">Progress Lists</h1>
          <p class="view-subtitle">Manage your achievements and sync coordinates with the map.</p>
        </div>

        <div class="stats-row">
          <div class="stat-card">
            <span class="stat-label">Overall Progress</span>
            <div class="stat-value">
              <strong>{{ Math.round(progress) }}%</strong>
              <small>{{ doneCount }} / {{ checklist.entries.length }}</small>
            </div>
            <ProgressBar :value="progress" :show-value="false" class="custom-progress" />
          </div>

          <div class="stat-card compact">
            <span class="stat-label">Current Filter</span>
            <div class="stat-value">
              <strong>{{ visibleDoneCount }} / {{ filtered.length }}</strong>
              <small>Completed</small>
            </div>
          </div>
        </div>
      </header>

      <div class="grid-scroller-wrapper glass-card">
        <VirtualScroller
          ref="scroller"
          :items="chunkedFiltered"
          :item-size="88"
          class="list-scroller"
        >
          <template #item="{ item: row }">
            <div class="card-row" :style="{ '--cols': COLS_PER_ROW }">
              <div
                v-for="item in row"
                :key="item.uid"
                class="checklist-card"
                :class="{ done: checklist.isDone(item.storage, item.id) }"
                @click="checklist.setDone(item.storage, item.id, !checklist.isDone(item.storage, item.id))"
              >
                <div class="card-left">
                  <Checkbox
                    :model-value="checklist.isDone(item.storage, item.id)"
                    binary
                    @click.stop
                    @update:model-value="checklist.setDone(item.storage, item.id, Boolean($event))"
                  />
                  <span class="row-color" :style="{ background: item.color }" />
                </div>

                <div class="card-body">
                  <div class="card-title-row">
                    <strong class="item-title">{{ itemLabel(item) }}</strong>
                    <span v-if="item.tag" class="tag-badge">{{ item.tag }}</span>
                  </div>

                  <div class="card-meta-row">
                    <span class="layer-badge">{{ item.layerLabel }}</span>
                    <small class="coords-text">
                      <i class="pi pi-map-marker" /> {{ item.x }}, {{ item.y }}
                    </small>
                  </div>
                </div>

                <div class="card-actions" @click.stop>
                  <Button
                    icon="pi pi-compass"
                    severity="secondary"
                    text
                    rounded
                    size="small"
                    title="View on Map"
                    class="map-btn"
                    @click="goToMap(item)"
                  />
                </div>
              </div>

              <!-- Invisible spacers to maintain grid alignment on the last row -->
              <div
                v-for="i in (COLS_PER_ROW - row.length)"
                :key="'empty-' + i"
                class="checklist-card empty-spacer"
              />
            </div>
          </template>
        </VirtualScroller>
      </div>
    </section>
  </div>
</template>

<style scoped>
.list-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 22px;
  height: 100%;
}

.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 20px;
  background: color-mix(in srgb, var(--surface-card, #1e1e2d) 60%, transparent);
  border: 1px solid var(--border, rgba(255, 255, 255, 0.08));
  border-radius: 12px;
  padding: 16px 20px;
}

.header-main .view-title {
  margin: 0;
  font-size: 1.5rem;
  font-weight: 700;
}

.header-main .view-subtitle {
  margin: 4px 0 0 0;
  color: var(--muted, #8888aa);
  font-size: 0.85rem;
}

.stats-row {
  display: flex;
  gap: 12px;
  align-items: center;
}

.stat-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  background: color-mix(in srgb, var(--accent, #6c5ce7) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--accent, #6c5ce7) 25%, transparent);
  border-radius: 8px;
  padding: 10px 14px;
  min-width: 200px;
}

.stat-card.compact {
  min-width: 130px;
}

.stat-label {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--muted, #8888aa);
  font-weight: 600;
}

.stat-value {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}

.stat-value strong {
  font-size: 1.15rem;
  font-weight: 800;
}

.stat-value small {
  font-size: 0.75rem;
  color: var(--muted, #8888aa);
}

.custom-progress {
  height: 6px !important;
  margin-top: 4px;
}

.grid-scroller-wrapper {
  flex: 1;
  min-height: 0;
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid var(--border, rgba(255, 255, 255, 0.08));
}

/* Force PrimeVue VirtualScroller and internal wrappers to take 100% width */
.list-scroller,
.list-scroller :deep(.p-virtualscroller-content),
.list-scroller :deep(.p-virtualscroller-viewport) {
  width: 100% !important;
  box-sizing: border-box;
}

/* Dynamic CSS Grid row based on the defined column count */
.card-row {
  display: grid;
  grid-template-columns: repeat(var(--cols, 5), minmax(0, 1fr));
  align-items: stretch; /* Garante que todas as colunas da linha sigam a altura do maior card */
  gap: 10px;
  padding: 6px 14px;
  min-height: 82px;
  height: auto;
  width: 100%;
  box-sizing: border-box;
}

/* Each card fills 100% of its Grid cell height and width */
.checklist-card {
  width: 100%;
  height: 100%; /* Estica o card para ocupar toda a altura da linha da grid */
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  min-height: 72px;
  background: color-mix(in srgb, var(--surface-card, #181824) 80%, transparent);
  border: 1px solid var(--border, rgba(255, 255, 255, 0.07));
  border-radius: 10px;
  cursor: pointer;
  transition: all 160ms cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
  overflow: hidden;
  box-sizing: border-box;
}

.checklist-card.empty-spacer {
  visibility: hidden;
  border: none;
  background: transparent;
  pointer-events: none;
}

.checklist-card:hover {
  border-color: color-mix(in srgb, var(--accent, #6c5ce7) 50%, transparent);
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
  background: color-mix(in srgb, var(--surface-card, #1e1e2f) 95%, transparent);
}

.checklist-card.done {
  opacity: 0.5;
  background: color-mix(in srgb, var(--surface-card, #12121a) 60%, transparent);
  border-color: transparent;
}

.card-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.card-body {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 4px;
  min-width: 0;
  flex: 1;
}

.card-title-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px 6px;
}

.item-title {
  font-size: 0.85rem;
  font-weight: 600;
  white-space: normal;
  word-break: break-word;
  line-height: 1.2;
}

.tag-badge {
  font-size: 0.65rem;
  padding: 1px 5px;
  border-radius: 4px;
  background: color-mix(in srgb, var(--accent, #6c5ce7) 20%, transparent);
  color: var(--accent, #a29bfe);
  white-space: nowrap;
  align-self: flex-start;
}

.card-meta-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px 8px;
}

.layer-badge {
  font-size: 0.72rem;
  color: var(--muted, #a0a0c0);
  white-space: normal;
  word-break: break-word;
}

.coords-text {
  font-size: 0.72rem;
  color: var(--muted, #7777aa);
  display: flex;
  align-items: center;
  gap: 3px;
  white-space: nowrap;
}

.card-actions {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.map-btn {
  opacity: 0.7;
  transition: opacity 140ms;
}

.checklist-card:hover .map-btn {
  opacity: 1;
  color: var(--accent, #6c5ce7) !important;
}

.filter-stack,
.layer-list {
  display: grid;
  gap: 7px;
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
  justify-content: flex-start;
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

@media (max-width: 900px) {
  .dashboard-header {
    flex-direction: column;
    align-items: stretch;
  }

  .stats-row {
    flex-direction: column;
  }
}
</style>