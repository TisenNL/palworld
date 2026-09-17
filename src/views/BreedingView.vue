<script setup lang="ts">
import Button from 'primevue/button'
import Checkbox from 'primevue/checkbox'
import InputText from 'primevue/inputtext'
import Select from 'primevue/select'
import Tab from 'primevue/tab'
import TabList from 'primevue/tablist'
import TabPanel from 'primevue/tabpanel'
import TabPanels from 'primevue/tabpanels'
import Tabs from 'primevue/tabs'
import { useToast } from 'primevue/usetoast'
import { computed, ref, watch } from 'vue'

import PalChip from '@/components/breeding/PalChip.vue'
import { createBreedingEngine, type BreedPath } from '@/domain/breeding'
import { useBreedingWorker } from '@/composables/useBreedingWorker'
import { useBreedingStore } from '@/stores/breeding'
import { useChecklistStore } from '@/stores/checklist'
import type { Pal } from '@/types/data'

const checklist = useChecklistStore()
const state = useBreedingStore()
const toast = useToast()
const activeTab = ref('owned')
const parentPairs = ref<Array<[string, string]>>([])
const visibleParentLimit = ref(200)
const parentsSearched = ref(false)
const pathResult = ref<BreedPath | null>(null)
const pathSearched = ref(false)
const generations = ref<string[][]>([])
const missing = ref<string[]>([])
const includeTarget = ref(true)
const hideIgnore = ref(true)
const worker = useBreedingWorker(() => checklist.breedData)

const pals = computed(() =>
  [...(checklist.breedData?.pals ?? [])].sort((first, second) => {
    const firstNumber = Number.parseInt(first.id, 10)
    const secondNumber = Number.parseInt(second.id, 10)
    const firstHasNumber = Number.isFinite(firstNumber)
    const secondHasNumber = Number.isFinite(secondNumber)
    if (firstHasNumber && secondHasNumber && firstNumber !== secondNumber) {
      return firstNumber - secondNumber
    }
    if (firstHasNumber !== secondHasNumber) return firstHasNumber ? -1 : 1
    return first.id.localeCompare(second.id, 'en', { numeric: true })
  }),
)
const engine = computed(() =>
  checklist.breedData ? createBreedingEngine(checklist.breedData) : null,
)
const byCode = computed(() => new Map(pals.value.map((pal) => [pal.code, pal])))
const palOptions = computed(() =>
  pals.value.map((pal) => ({ label: `${pal.id} · ${pal.name}`, value: pal.code })),
)
const pairChildren = computed(() =>
  state.parentA && state.parentB ? (engine.value?.results(state.parentA, state.parentB) ?? []) : [],
)
const filteredOwned = computed(() => {
  const query = state.ownedSearch.trim().toLocaleLowerCase()
  return pals.value.filter((pal) => {
    if (state.showOwnedOnly && !checklist.breedOwned[pal.code]) return false
    return !query || `${pal.id} ${pal.name} ${pal.code}`.toLocaleLowerCase().includes(query)
  })
})
const ownedSignature = computed(() => Object.keys(checklist.breedOwned).sort().join('|'))

const pal = (code: string): Pal | undefined => byCode.value.get(code)

async function calculateParents(): Promise<void> {
  if (!state.targetChild) return
  const child = state.targetChild
  const ownedOnly = state.ownedOnly
  const owned = ownedOnly ? Object.keys(checklist.breedOwned) : null
  const signature = ownedSignature.value
  parentsSearched.value = false
  try {
    const result = await worker.run<Array<[string, string]>>({
      action: 'parents',
      child,
      owned,
    })
    if (
      state.targetChild !== child ||
      state.ownedOnly !== ownedOnly ||
      (ownedOnly && ownedSignature.value !== signature)
    ) {
      return
    }
    parentPairs.value = result
    visibleParentLimit.value = 200
    parentsSearched.value = true
  } catch (cause) {
    showError(cause)
  }
}

async function calculatePath(): Promise<void> {
  if (!state.pathFrom || !state.pathTo) return
  const from = state.pathFrom
  const to = state.pathTo
  const allowTarget = includeTarget.value
  const ignoreRestricted = hideIgnore.value
  pathSearched.value = false
  try {
    const result = await worker.run<BreedPath | null>({
      action: 'path',
      from,
      to,
      includeTarget: allowTarget,
      hideIgnoreCombi: ignoreRestricted,
    })
    if (
      state.pathFrom !== from ||
      state.pathTo !== to ||
      includeTarget.value !== allowTarget ||
      hideIgnore.value !== ignoreRestricted
    ) {
      return
    }
    pathResult.value = result
    pathSearched.value = true
  } catch (cause) {
    showError(cause)
  }
}

async function calculateGenerations(): Promise<void> {
  const owned = Object.keys(checklist.breedOwned)
  const signature = ownedSignature.value
  try {
    const result = await worker.run<{ generations: string[][]; missing: string[] }>({
      action: 'generations',
      owned,
    })
    if (ownedSignature.value !== signature) return
    generations.value = result.generations
    missing.value = result.missing
  } catch (cause) {
    showError(cause)
  }
}

function showError(cause: unknown): void {
  toast.add({
    severity: 'error',
    summary: 'Calculation failed',
    detail: cause instanceof Error ? cause.message : 'Could not complete the calculation.',
    life: 3500,
  })
}

watch([() => state.targetChild, () => state.ownedOnly], () => {
  parentPairs.value = []
  parentsSearched.value = false
})
watch([() => state.pathFrom, () => state.pathTo, includeTarget, hideIgnore], () => {
  pathResult.value = null
  pathSearched.value = false
})
watch(ownedSignature, () => {
  generations.value = []
  missing.value = []
  if (state.ownedOnly) {
    parentPairs.value = []
    parentsSearched.value = false
  }
})
</script>

<template>
  <div class="content-pane">
    <div class="view-page breeding-page">
      <header>
        <h1 class="view-title">Breeding tools</h1>
        <p class="view-subtitle">
          Combinations, possible parents, paths, and generations calculated locally.
        </p>
      </header>

      <Tabs v-model:value="activeTab" class="breeding-tabs">
        <TabList>
          <Tab value="owned">My Pals</Tab>
          <Tab value="pair">Two Pals</Tab>
          <Tab value="parents">Parents</Tab>
          <Tab value="path">Path</Tab>
          <Tab value="multi">Multiple generations</Tab>
        </TabList>
        <TabPanels>
          <TabPanel value="owned">
            <div class="owned-tools">
              <InputText v-model="state.ownedSearch" placeholder="Search Pals…" />
              <label class="inline-check">
                <Checkbox v-model="state.showOwnedOnly" binary />
                Show owned only
              </label>
              <strong>{{ Object.keys(checklist.breedOwned).length }} marked</strong>
            </div>
            <div class="owned-grid">
              <PalChip
                v-for="item in filteredOwned"
                :key="item.code"
                :pal="item"
                :owned="Boolean(checklist.breedOwned[item.code])"
                interactive
                @toggle="checklist.setBreedOwned(item.code, !checklist.breedOwned[item.code])"
              />
            </div>
          </TabPanel>

          <TabPanel value="pair">
            <div class="tool-card">
              <div class="form-row">
                <Select
                  v-model="state.parentA"
                  :options="palOptions"
                  option-label="label"
                  option-value="value"
                  filter
                  placeholder="Parent A"
                  fluid
                />
                <span class="operator">+</span>
                <Select
                  v-model="state.parentB"
                  :options="palOptions"
                  option-label="label"
                  option-value="value"
                  filter
                  placeholder="Parent B"
                  fluid
                />
              </div>
              <div v-if="state.parentA && state.parentB" class="equation">
                <PalChip :pal="pal(state.parentA)" />
                <span class="operator">+</span>
                <PalChip :pal="pal(state.parentB)" />
                <span class="operator">=</span>
                <template v-if="pairChildren.length">
                  <PalChip v-for="child in pairChildren" :key="child" :pal="pal(child)" />
                </template>
                <span v-else class="empty-text">No valid offspring</span>
              </div>
            </div>
          </TabPanel>

          <TabPanel value="parents">
            <div class="tool-card">
              <div class="form-row action-row">
                <Select
                  v-model="state.targetChild"
                  :options="palOptions"
                  option-label="label"
                  option-value="value"
                  filter
                  placeholder="Desired offspring"
                  fluid
                />
                <label class="inline-check">
                  <Checkbox v-model="state.ownedOnly" binary />
                  Use owned Pals only
                </label>
                <Button
                  label="Calculate"
                  icon="pi pi-search"
                  :loading="worker.busy.value"
                  :disabled="!state.targetChild"
                  @click="calculateParents"
                />
              </div>
              <p v-if="parentPairs.length" class="result-count">
                Showing {{ Math.min(visibleParentLimit, parentPairs.length) }} of
                {{ parentPairs.length }} combinations
              </p>
              <p v-else-if="parentsSearched" class="empty-text">No parent combinations found</p>
              <div class="pair-list">
                <div
                  v-for="[a, b] in parentPairs.slice(0, visibleParentLimit)"
                  :key="`${a}-${b}`"
                  class="equation compact"
                >
                  <PalChip :pal="pal(a)" />
                  <span class="operator">+</span>
                  <PalChip :pal="pal(b)" />
                  <span class="operator">=</span>
                  <PalChip :pal="pal(state.targetChild)" />
                </div>
              </div>
              <Button
                v-if="visibleParentLimit < parentPairs.length"
                class="show-more"
                label="Show 200 more"
                icon="pi pi-chevron-down"
                severity="secondary"
                @click="visibleParentLimit += 200"
              />
            </div>
          </TabPanel>

          <TabPanel value="path">
            <div class="tool-card">
              <div class="form-row">
                <Select
                  v-model="state.pathFrom"
                  :options="palOptions"
                  option-label="label"
                  option-value="value"
                  filter
                  placeholder="Starting Pal"
                  fluid
                />
                <span class="operator">→</span>
                <Select
                  v-model="state.pathTo"
                  :options="palOptions"
                  option-label="label"
                  option-value="value"
                  filter
                  placeholder="Target Pal"
                  fluid
                />
              </div>
              <div class="option-row">
                <label class="inline-check"
                  ><Checkbox v-model="includeTarget" binary />Allow target as parent</label
                >
                <label class="inline-check"
                  ><Checkbox v-model="hideIgnore" binary />Ignore restricted combinations</label
                >
                <Button
                  label="Find path"
                  icon="pi pi-directions"
                  :loading="worker.busy.value"
                  :disabled="!state.pathFrom || !state.pathTo"
                  @click="calculatePath"
                />
              </div>
              <div v-if="pathResult" class="path-list">
                <div class="equation compact">
                  <PalChip :pal="pal(pathResult.start)" /><span class="empty-text">start</span>
                </div>
                <div
                  v-for="(step, index) in pathResult.steps"
                  :key="index"
                  class="equation compact"
                >
                  <PalChip
                    :pal="pal(index ? pathResult.steps[index - 1]!.result : pathResult.start)"
                  />
                  <span class="operator">+</span>
                  <PalChip :pal="pal(step.with)" />
                  <span class="operator">=</span>
                  <PalChip :pal="pal(step.result)" />
                </div>
              </div>
              <p v-else-if="pathSearched" class="empty-text">No breeding path found</p>
            </div>
          </TabPanel>

          <TabPanel value="multi">
            <div class="tool-card">
              <Button
                label="Calculate from my Pals"
                icon="pi pi-bolt"
                :loading="worker.busy.value"
                :disabled="!Object.keys(checklist.breedOwned).length"
                @click="calculateGenerations"
              />
              <div v-if="generations.length" class="generation-grid">
                <section
                  v-for="(values, index) in generations"
                  :key="index"
                  class="generation-card"
                >
                  <h2>
                    {{
                      ['Owned', 'First generation', 'Second generation', 'Third generation'][index]
                    }}
                    ({{ values.length }})
                  </h2>
                  <div class="chip-wrap">
                    <PalChip v-for="code in values" :key="code" :pal="pal(code)" />
                  </div>
                </section>
                <section class="generation-card">
                  <h2>Unreachable ({{ missing.length }})</h2>
                  <div class="chip-wrap">
                    <PalChip v-for="code in missing.slice(0, 120)" :key="code" :pal="pal(code)" />
                  </div>
                </section>
              </div>
            </div>
          </TabPanel>
        </TabPanels>
      </Tabs>
    </div>
  </div>
</template>

<style scoped>
.breeding-page {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
}

.breeding-tabs {
  min-height: 0;
}

.owned-tools,
.option-row {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 14px;
}

.owned-tools strong {
  margin-left: auto;
}

.owned-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(185px, 1fr));
  gap: 7px;
}

.tool-card {
  min-height: 220px;
  padding: 16px;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: color-mix(in srgb, var(--panel-solid) 72%, transparent);
}

.form-row {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) auto minmax(220px, 1fr);
  align-items: center;
  gap: 10px;
}

.action-row {
  grid-template-columns: minmax(280px, 1fr) auto auto;
}

.option-row {
  justify-content: end;
  margin-top: 12px;
}

.inline-check {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--muted);
  font-size: 0.82rem;
}

.operator {
  color: var(--muted);
  font-size: 1.2rem;
  font-weight: 900;
}

.equation {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 9px;
  margin-top: 28px;
}

.equation.compact {
  justify-content: start;
  margin-top: 0;
  padding: 8px 0;
  border-bottom: 1px solid var(--border);
}

.empty-text,
.result-count {
  color: var(--muted);
  font-size: 0.84rem;
}

.pair-list,
.path-list {
  max-height: 56vh;
  margin-top: 12px;
  overflow: auto;
}

.show-more {
  margin-top: 12px;
}

.generation-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 16px;
}

.generation-card {
  padding: 14px;
  border: 1px solid var(--border);
  border-radius: 12px;
}

.generation-card h2 {
  margin: 0 0 10px;
  font-size: 0.95rem;
}

.chip-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

@media (max-width: 760px) {
  .form-row,
  .action-row {
    grid-template-columns: 1fr;
  }

  .operator {
    display: none;
  }

  .owned-tools,
  .option-row {
    align-items: stretch;
    flex-direction: column;
  }

  .owned-tools strong {
    margin-left: 0;
  }

  .generation-grid {
    grid-template-columns: 1fr;
  }
}
</style>
