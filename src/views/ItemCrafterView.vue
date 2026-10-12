<script setup lang="ts">
import InputNumber from 'primevue/inputnumber'
import Select from 'primevue/select'
import { ref } from 'vue'

import SafeImage from '@/components/common/SafeImage.vue'
import CraftBracket from '@/components/crafter/CraftBracket.vue'
import { useItemCrafterStore } from '@/stores/itemCrafter'

const crafter = useItemCrafterStore()
const rawOpen = ref(true)

const fmt = (value: number) => value.toLocaleString('en-US')
</script>

<template>
  <div class="content-pane ic-pane">
    <div class="ic-wrap">
      <!-- ══ HEADER — title + controls share one row to give the bracket space ══ -->
      <header class="ic-header">
        <div class="title-block">
          <p class="eyebrow">Crafting calculator</p>
          <h1>Item Crafter</h1>
          <p v-if="crafter.plan?.note" class="ic-note" :title="crafter.plan.note">
            <i class="pi pi-info-circle" aria-hidden="true" />
            <span>{{ crafter.plan.note }}</span>
          </p>
        </div>

        <div class="ic-controls">
          <label class="ic-field ic-field--item">
            <span>Item</span>
            <Select
              v-model="crafter.itemKey"
              :options="crafter.options"
              option-label="label"
              option-value="key"
              filter
              placeholder="Search items…"
              aria-label="Item to craft"
              fluid
            />
          </label>
          <label class="ic-field ic-field--qty">
            <span>Quantity</span>
            <InputNumber
              v-model="crafter.quantity"
              :min="1"
              :max="999999"
              :max-fraction-digits="0"
              locale="en"
              input-id="ic-quantity"
              aria-label="Quantity to craft"
              fluid
            />
          </label>
        </div>
      </header>

      <!-- ══ RAW MATERIALS — slim, collapsible shopping list ══ -->
      <section v-if="crafter.plan" class="ic-raw" aria-label="Raw materials">
        <div class="ic-raw-head">
          <h2 class="panel-heading">
            Raw materials
            <span class="ic-count">{{ fmt(crafter.materials.length) }}</span>
            <span class="ic-qty-chip"
              >{{ fmt(crafter.effectiveQuantity) }} × {{ crafter.plan.rootName }}</span
            >
          </h2>
          <button
            type="button"
            class="ic-raw-toggle"
            :aria-expanded="rawOpen"
            @click="rawOpen = !rawOpen"
          >
            <i :class="rawOpen ? 'pi pi-chevron-up' : 'pi pi-chevron-down'" aria-hidden="true" />
            {{ rawOpen ? 'Hide' : 'Show' }}
          </button>
        </div>

        <div
          v-show="rawOpen"
          class="ic-mat-grid"
          role="list"
          aria-label="Raw materials with totals"
        >
          <div
            v-for="material in crafter.materials"
            :key="material.key"
            class="mat-tile"
            role="listitem"
            :title="`${material.name} — ${fmt(material.total)}`"
            :aria-label="`${material.name}: ${fmt(material.total)}`"
          >
            <span class="mat-icon">
              <SafeImage
                :src="material.icon ?? ''"
                :alt="material.name"
                :fallback-label="material.name"
              />
            </span>
            <span class="mat-total">{{ fmt(material.total) }}</span>
          </div>
        </div>
      </section>

      <!-- ══ BRACKET — the whole remaining screen ══ -->
      <section class="ic-panel ic-bracket" aria-label="Crafting tree tournament">
        <div class="ic-bracket-head">
          <h2 class="panel-heading">Crafting tree</h2>
          <p>Every round feeds the next — raw materials on the left, the champion on the right.</p>
          <ul v-if="crafter.warnings.length > 0" class="ic-warnings">
            <li v-for="warning in crafter.warnings" :key="warning">
              <i class="pi pi-exclamation-triangle" aria-hidden="true" />
              <span>{{ warning }}</span>
            </li>
          </ul>
        </div>

        <div class="ic-bracket-body">
          <CraftBracket v-if="crafter.bracket" :bracket="crafter.bracket" />
          <p v-else class="ic-empty">
            {{
              crafter.hasData
                ? 'Select an item to see its crafting tree.'
                : 'No recipe data yet. Run "node scripts/fetch-recipes.mjs" to generate src/data/recipes.json.'
            }}
          </p>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.ic-pane {
  height: 100%;
  overflow: hidden;
}

.ic-wrap {
  display: flex;
  flex-direction: column;
  gap: clamp(4px, 0.8vmin, 10px);
  height: 100%;
  max-height: 100%;
  padding: clamp(0.5rem, 1.3vmin, 0.9rem) clamp(0.9rem, 2.2vw, 1.6rem);
  box-sizing: border-box;
  overflow: hidden;
}

/* ════════════════════════════════════════════════════════════
   HEADER
   ════════════════════════════════════════════════════════════ */
.ic-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.title-block {
  min-width: 0;
}

.title-block h1 {
  margin: 2px 0 0;
  font-size: clamp(1.15rem, 2.4vmin, 1.8rem);
  font-weight: 800;
  letter-spacing: -0.04em;
}

.eyebrow {
  margin: 0;
  color: var(--accent, #22d3ee);
  font-size: 0.64rem;
  font-weight: 800;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.ic-note {
  display: flex;
  align-items: center;
  gap: 6px;
  max-width: min(60ch, 50vw);
  margin: 3px 0 0;
  color: var(--muted, #9aabc2);
  font-size: 0.7rem;
  line-height: 1.3;
}

.ic-note span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ic-note i {
  flex-shrink: 0;
  color: var(--accent, #22d3ee);
}

.ic-controls {
  display: flex;
  align-items: flex-end;
  gap: 10px;
}

.ic-field {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.ic-field--item {
  width: clamp(200px, 26vw, 320px);
}

.ic-field--qty {
  width: clamp(110px, 12vw, 150px);
}

.ic-field > span {
  color: var(--muted, #9aabc2);
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

/* ════════════════════════════════════════════════════════════
   RAW MATERIALS STRIP
   ════════════════════════════════════════════════════════════ */
.ic-raw {
  display: grid;
  gap: 6px;
}

.ic-raw-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.panel-heading {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin: 0;
  font-size: 0.85rem;
  font-weight: 800;
  letter-spacing: -0.02em;
}

.ic-count {
  padding: 1px 8px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 999px;
  color: var(--muted, #9aabc2);
  font-size: 0.66rem;
  font-variant-numeric: tabular-nums;
}

.ic-qty-chip {
  color: var(--accent, #22d3ee);
  font-size: 0.68rem;
  font-variant-numeric: tabular-nums;
  font-weight: 700;
  white-space: nowrap;
}

.ic-raw-toggle {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 10px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
  color: var(--muted, #9aabc2);
  font-size: 0.68rem;
  font-weight: 700;
  cursor: pointer;
  transition:
    border-color 0.16s ease,
    color 0.16s ease;
}

.ic-raw-toggle:hover {
  border-color: rgba(34, 211, 238, 0.45);
  color: var(--text, #f1f5f9);
}

.ic-mat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(clamp(50px, 5.6vw, 74px), 1fr));
  gap: clamp(5px, 0.8vmin, 9px);
}

.mat-tile {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 2px;
  aspect-ratio: 1;
  min-width: 0;
  padding: 5px 4px 4px;
  box-sizing: border-box;
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 10px;
  background: rgba(12, 20, 38, 0.55);
  cursor: help;
  transition:
    border-color 0.16s ease,
    background 0.16s ease,
    transform 0.16s ease;
}

.mat-tile:hover {
  border-color: rgba(34, 211, 238, 0.45);
  background: rgba(34, 211, 238, 0.06);
  transform: translateY(-2px);
}

.mat-icon {
  display: block;
  flex: 1 1 auto;
  min-height: 0;
  width: 100%;
  overflow: hidden;
  border-radius: 7px;
}

.mat-total {
  flex: 0 0 auto;
  text-align: center;
  color: var(--text, #f1f5f9);
  font-size: clamp(0.62rem, 1.1vmin, 0.75rem);
  font-variant-numeric: tabular-nums;
  font-weight: 800;
  line-height: 1.1;
}

/* ════════════════════════════════════════════════════════════
   BRACKET PANEL
   ════════════════════════════════════════════════════════════ */
.ic-bracket {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  gap: 4px;
  min-height: 0;
  padding: clamp(0.5rem, 1.1vmin, 0.8rem);
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: clamp(0.75rem, 1.6vmin, 1.25rem);
  background: rgba(8, 14, 28, 0.6);
  box-shadow:
    0 0 0 1px rgba(255, 255, 255, 0.04) inset,
    0 24px 48px rgba(2, 6, 23, 0.4);
}

.ic-bracket-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
  flex: 0 0 auto;
}

.ic-bracket-head p {
  margin: 0;
  color: var(--muted, #9aabc2);
  font-size: 0.68rem;
  letter-spacing: 0.02em;
}

.ic-bracket-body {
  position: relative;
  flex: 1 1 auto;
  min-height: 0;
}

.ic-warnings {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  width: 100%;
  margin: 0;
  padding: 0;
  list-style: none;
}

.ic-warnings li {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #fbbf24;
  font-size: 0.68rem;
}

.ic-empty {
  display: grid;
  height: 100%;
  margin: 0;
  place-content: center;
  padding: 16px;
  color: var(--muted, #9aabc2);
  font-size: 0.8rem;
  text-align: center;
}

/* ════════════════════════════════════════════════════════════
   MOBILE  ≤900px — stack the header, scroll inside the pane
   ════════════════════════════════════════════════════════════ */
@media (max-width: 900px) {
  .ic-pane {
    overflow-x: hidden;
    overflow-y: auto;
    overscroll-behavior: contain;
    scrollbar-color: color-mix(in srgb, var(--muted, #9aabc2) 52%, transparent) transparent;
    scrollbar-width: thin;
  }

  .ic-wrap {
    height: auto;
    max-height: none;
    min-height: 100%;
    overflow: visible;
    padding: 12px 14px;
  }

  .ic-header {
    align-items: stretch;
    flex-direction: column;
    gap: 8px;
  }

  .ic-controls {
    width: 100%;
  }

  .ic-field--item {
    flex: 1 1 auto;
    width: auto;
  }

  .ic-note {
    max-width: 100%;
  }

  /* The bracket keeps a definite height so it never collapses in an auto row. */
  .ic-bracket {
    flex: 0 0 auto;
  }

  .ic-bracket-body {
    flex: 0 0 auto;
    height: 68vh;
    min-height: 380px;
  }
}
</style>
