<script setup lang="ts">
import Button from 'primevue/button'
import InputNumber from 'primevue/inputnumber'
import { useToast } from 'primevue/usetoast'
import { computed } from 'vue'

import { useCakeStore } from '@/stores/cake'
import type { CakeKey } from '@/domain/cakes'

const cake = useCakeStore()
const toast = useToast()

const recipeMeta: Record<string, { tint: string; blurb: string }> = {
  cake: { tint: '#fb7185', blurb: 'Classic ranch staple' },
  mushroom: { tint: '#a3e635', blurb: 'Earthy dungeon bake' },
  vegetable: { tint: '#4ade80', blurb: 'Garden fresh batch' },
  extravagant: { tint: '#c084fc', blurb: 'Luxury veggie crown' },
  special: { tint: '#fbbf24', blurb: 'Festival centerpiece' },
}

const ingredientTint: Record<string, string> = {
  berry: '#fb7185',
  milk: '#e2e8f0',
  egg: '#fde68a',
  mushroom: '#a3e635',
  cavern: '#86efac',
  tomato: '#f87171',
  lettuce: '#4ade80',
  cotton: '#f9a8d4',
  potato: '#fcd34d',
  onion: '#fdba74',
  carrot: '#fb923c',
  caramel: '#f59e0b',
  mammorest: '#f87171',
  wheat: '#fbbf24',
  flour: '#e7e5e4',
  honey: '#f59e0b',
}

interface MaterialCard {
  key: string
  label: string
  tint: string
  badge: string
  priceKey?: CakeKey
  stockKey?: CakeKey
  buy?: number
  subtotal?: number
  per?: number
}

const materials = computed<MaterialCard[]>(() => {
  const cards: MaterialCard[] = cake.recipe.ingredients.map((item) => {
    const buy = cake.result.purchases[item.key] ?? 0
    const price = cake.prices[item.price]
    return {
      key: item.key,
      label: item.label,
      tint: ingredientTint[item.key] ?? '#67e8f9',
      badge: `${item.per} / cake`,
      priceKey: item.price,
      stockKey: item.stock,
      buy,
      subtotal: price * buy,
      per: item.per,
    }
  })
  const wheatBuy = cake.result.purchases.wheat ?? 0
  cards.push({
    key: 'wheat',
    label: 'Wheat',
    tint: ingredientTint.wheat,
    badge: 'for flour',
    priceKey: 'wheat',
    stockKey: 'wheat',
    buy: wheatBuy,
    subtotal: cake.prices.wheat * wheatBuy,
  })
  cards.push({
    key: 'flour',
    label: 'Flour',
    tint: ingredientTint.flour,
    badge: `${cake.recipe.flourPer} / cake`,
    stockKey: 'flour',
    per: cake.recipe.flourPer,
  })
  if (cake.recipe.honeyPer > 0) {
    cards.push({
      key: 'honey',
      label: 'Honey',
      tint: ingredientTint.honey,
      badge: `${cake.recipe.honeyPer} / cake`,
      stockKey: 'honey',
      per: cake.recipe.honeyPer,
    })
  }
  return cards
})

const activeMeta = computed(
  () => recipeMeta[cake.recipeId] ?? { tint: '#fbbf24', blurb: cake.recipe.label },
)

const fillRatio = computed(() => {
  if (cake.result.maximum <= 0) return 0
  return Math.min(1, cake.result.amount / Math.max(cake.result.maximum, 1))
})

const fmt = (n: number) => n.toLocaleString('en-US')

function applyPurchase(): void {
  if (cake.result.amount <= 0) {
    toast.add({
      severity: 'info',
      summary: 'Nothing to apply',
      detail: 'Enter enough gold or inventory to produce cakes.',
      life: 2500,
    })
    return
  }
  cake.applyPurchase()
  toast.add({
    severity: 'success',
    summary: 'Purchase applied',
    detail: 'Inventory and available gold were updated.',
    life: 2500,
  })
}
</script>

<template>
  <div class="content-pane cakes-pane">
    <div class="cakes-scene" :style="{ '--cake-tint': activeMeta.tint }">
      <div class="scene-glow" aria-hidden="true" />

      <header class="scene-top">
        <div class="title-block">
          <p class="eyebrow">Palworld kitchen</p>
          <h1>Cake calculator</h1>
        </div>
        <div class="top-actions">
          <Button
            label="Reset prices"
            icon="pi pi-refresh"
            severity="secondary"
            text
            size="small"
            @click="cake.resetPrices"
          />
          <Button
            label="Apply purchase"
            icon="pi pi-check"
            size="small"
            class="apply-btn"
            @click="applyPurchase"
          />
        </div>
      </header>

      <nav class="recipe-rail" aria-label="Recipes">
        <button
          v-for="item in cake.recipes"
          :key="item.id"
          type="button"
          class="recipe-tile"
          :class="{ active: cake.recipeId === item.id }"
          :style="{ '--tile-tint': recipeMeta[item.id]?.tint ?? '#fbbf24' }"
          @click="cake.recipeId = item.id"
        >
          <span class="tile-swatch" />
          <span class="tile-copy">
            <strong>{{ item.label }}</strong>
            <small>{{ recipeMeta[item.id]?.blurb }}</small>
          </span>
        </button>
      </nav>

      <div class="scene-body">
        <section class="hero-card">
          <div class="cake-art" aria-hidden="true">
            <div class="cake-plate" />
            <div class="cake-layer bottom" />
            <div class="cake-layer top" />
            <div class="cake-icing" />
            <div class="cake-cherry" />
          </div>

          <div class="hero-copy">
            <p class="hero-kicker">{{ activeMeta.blurb }}</p>
            <div class="hero-count">
              <strong>{{ fmt(cake.result.amount) }}</strong>
              <span>cakes ready</span>
            </div>
            <div class="hero-meter">
              <div class="hero-meter-fill" :style="{ width: `${fillRatio * 100}%` }" />
            </div>
            <p class="hero-cap">
              Maximum with current gold & stock:
              <b>{{ fmt(cake.result.maximum) }}</b>
            </p>
            <p class="hero-note">{{ cake.recipe.note }}</p>
          </div>

          <div class="hero-inputs">
            <label class="soft-field">
              <span>Gold on hand</span>
              <InputNumber v-model="cake.gold" :min="0" fluid />
            </label>
            <label class="soft-field">
              <span>Target batch</span>
              <InputNumber v-model="cake.target" :min="0" fluid />
            </label>
          </div>

          <div class="hero-stats">
            <div>
              <span>Spent</span>
              <strong>{{ fmt(cake.result.spent) }}</strong>
            </div>
            <div>
              <span>Left</span>
              <strong>{{ fmt(cake.result.remaining) }}</strong>
            </div>
            <div>
              <span>Unit</span>
              <strong>{{ fmt(cake.result.unitCost) }}</strong>
            </div>
          </div>
        </section>

        <section class="market">
          <div class="market-head">
            <h2>Market tray</h2>
            <p>Tune prices and pantry — buys update live.</p>
          </div>

          <div class="market-grid">
            <article
              v-for="card in materials"
              :key="card.key"
              class="ingredient-card"
              :class="{ buying: (card.buy ?? 0) > 0 }"
              :style="{ '--item-tint': card.tint }"
            >
              <header>
                <span class="item-blob" />
                <div>
                  <strong>{{ card.label }}</strong>
                  <small>{{ card.badge }}</small>
                </div>
                <span v-if="(card.buy ?? 0) > 0" class="buy-pill">+{{ fmt(card.buy!) }}</span>
              </header>

              <div class="item-fields">
                <label v-if="card.priceKey">
                  <span>Price</span>
                  <InputNumber v-model="cake.prices[card.priceKey]" :min="0" fluid />
                </label>
                <label v-if="card.stockKey">
                  <span>Stock</span>
                  <InputNumber v-model="cake.stock[card.stockKey]" :min="0" fluid />
                </label>
              </div>

              <footer v-if="card.subtotal != null">
                <span>Subtotal</span>
                <strong>{{ fmt(card.subtotal) }}</strong>
              </footer>
            </article>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cakes-pane {
  height: 100%;
  overflow: hidden;
}

:global(.app-main > .content-pane.cakes-pane) {
  overflow: hidden;
}

.cakes-scene {
  --pad-y: clamp(0.5rem, 1.4vmin, 1.15rem);
  --pad-x: clamp(0.75rem, 2.2vw, 1.85rem);
  --gap: clamp(0.5rem, 1.35vmin, 1.15rem);
  --radius: clamp(0.75rem, 1.6vmin, 1.35rem);
  --card-pad: clamp(0.55rem, 1.25vmin, 0.95rem);
  --ink: clamp(0.72rem, 1.35vmin, 0.88rem);
  position: relative;
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr);
  gap: var(--gap);
  box-sizing: border-box;
  width: 100%;
  height: 100%;
  max-height: 100%;
  margin: 0;
  padding: var(--pad-y) var(--pad-x);
  isolation: isolate;
  overflow: hidden;
}

.scene-glow {
  position: absolute;
  inset: -10% 10% auto;
  height: 280px;
  background:
    radial-gradient(ellipse at 30% 40%, color-mix(in srgb, var(--cake-tint) 28%, transparent), transparent 55%),
    radial-gradient(ellipse at 75% 20%, rgba(251, 191, 36, 0.16), transparent 50%);
  filter: blur(8px);
  pointer-events: none;
  z-index: -1;
}

.scene-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.eyebrow {
  margin: 0;
  color: color-mix(in srgb, var(--cake-tint) 75%, #fff);
  font-size: 0.7rem;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.title-block h1 {
  margin: 2px 0 0;
  font-size: clamp(1.15rem, 2.6vmin, 1.95rem);
  letter-spacing: -0.04em;
}

.top-actions {
  display: flex;
  gap: 6px;
}

.apply-btn {
  border: none !important;
  background: linear-gradient(
    135deg,
    color-mix(in srgb, var(--cake-tint) 85%, #fff),
    var(--cake-tint)
  ) !important;
  color: #1a1020 !important;
  font-weight: 750 !important;
  box-shadow: 0 8px 20px color-mix(in srgb, var(--cake-tint) 35%, transparent);
}

.recipe-rail {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: clamp(0.35rem, 0.9vmin, 0.65rem);
}

.recipe-tile {
  display: grid;
  grid-template-columns: 12px minmax(0, 1fr);
  align-items: center;
  gap: clamp(0.4rem, 1vmin, 0.7rem);
  min-width: 0;
  overflow: hidden;
  padding: clamp(0.4rem, 1vmin, 0.7rem) clamp(0.5rem, 1.1vmin, 0.85rem);
  border: 1px solid color-mix(in srgb, var(--tile-tint) 28%, var(--border));
  border-radius: calc(var(--radius) - 4px);
  color: inherit;
  text-align: left;
  cursor: pointer;
  background: color-mix(in srgb, #0b1220 86%, var(--tile-tint));
  transition:
    transform 0.15s ease,
    border-color 0.15s ease,
    box-shadow 0.15s ease;
}

.recipe-tile:hover {
  transform: translateY(-1px);
  border-color: color-mix(in srgb, var(--tile-tint) 55%, var(--border));
}

.recipe-tile.active {
  border-color: transparent;
  background: linear-gradient(
    145deg,
    color-mix(in srgb, var(--tile-tint) 35%, #0b1220),
    color-mix(in srgb, var(--tile-tint) 12%, #0b1220)
  );
  box-shadow:
    0 10px 24px color-mix(in srgb, var(--tile-tint) 22%, transparent),
    inset 0 1px 0 rgba(255, 255, 255, 0.08);
}

.tile-swatch {
  width: 12px;
  height: 36px;
  border-radius: 999px;
  background: linear-gradient(180deg, #fff8, var(--tile-tint));
  box-shadow: 0 0 12px color-mix(in srgb, var(--tile-tint) 45%, transparent);
}

.tile-copy {
  display: grid;
  min-width: 0;
  gap: 1px;
  overflow: hidden;
}

.tile-copy strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.8rem;
}

.tile-copy small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--muted);
  font-size: 0.68rem;
}

.scene-body {
  display: grid;
  grid-template-columns: minmax(15rem, 0.82fr) minmax(0, 1.6fr);
  gap: var(--gap);
  min-height: 0;
  height: 100%;
  align-items: stretch;
}

.hero-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: clamp(0.45rem, 1.2vmin, 0.85rem);
  height: 100%;
  min-height: 0;
  padding: var(--card-pad);
  border: 1px solid color-mix(in srgb, var(--cake-tint) 30%, var(--border));
  border-radius: var(--radius);
  background:
    radial-gradient(circle at 80% 0%, color-mix(in srgb, var(--cake-tint) 22%, transparent), transparent 45%),
    linear-gradient(165deg, rgba(255, 255, 255, 0.04), transparent 40%),
    #0c1424;
  box-shadow: 0 18px 40px rgba(2, 6, 23, 0.35);
  overflow: hidden;
}

.cake-art {
  position: absolute;
  top: 18px;
  right: 18px;
  width: 88px;
  height: 78px;
  opacity: 0.95;
}

.cake-plate {
  position: absolute;
  left: 6px;
  right: 6px;
  bottom: 4px;
  height: 10px;
  border-radius: 999px;
  background: radial-gradient(ellipse, #94a3b8, #334155 70%);
  opacity: 0.55;
}

.cake-layer {
  position: absolute;
  left: 14px;
  right: 14px;
  border-radius: 10px 10px 8px 8px;
}

.cake-layer.bottom {
  bottom: 14px;
  height: 22px;
  background: linear-gradient(180deg, #fcd34d, #d97706);
}

.cake-layer.top {
  bottom: 32px;
  height: 20px;
  background: linear-gradient(180deg, #fda4af, #fb7185);
}

.cake-icing {
  position: absolute;
  left: 12px;
  right: 12px;
  bottom: 48px;
  height: 10px;
  border-radius: 999px;
  background: #fff7ed;
  box-shadow: 0 2px 0 #fecdd3;
}

.cake-cherry {
  position: absolute;
  left: 50%;
  bottom: 54px;
  width: 12px;
  height: 12px;
  margin-left: -6px;
  border-radius: 50%;
  background: radial-gradient(circle at 30% 30%, #fda4af, #be123c);
  box-shadow: 0 -8px 0 -5px #4ade80;
}

.hero-copy {
  display: flex;
  flex: 0 1 auto;
  flex-direction: column;
  justify-content: flex-start;
  gap: 2px;
  min-height: 0;
  padding-right: 96px;
}

.hero-kicker {
  margin: 0;
  color: color-mix(in srgb, var(--cake-tint) 80%, #fff);
  font-size: 0.72rem;
  font-weight: 750;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.hero-count {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-top: 4px;
}

.hero-count strong {
  font-size: clamp(1.85rem, 5.8vmin, 3.7rem);
  font-weight: 850;
  letter-spacing: -0.06em;
  line-height: 0.92;
  background: linear-gradient(180deg, #fff, color-mix(in srgb, var(--cake-tint) 70%, #fff));
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.hero-count span {
  color: var(--muted);
  font-size: 0.9rem;
}

.hero-meter {
  height: 10px;
  margin-top: 8px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.65);
  overflow: hidden;
}

.hero-meter-fill {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--cake-tint), #fde68a);
  transition: width 0.28s ease;
}

.hero-cap {
  margin: 10px 0 0;
  color: var(--muted);
  font-size: 0.78rem;
}

.hero-cap b {
  color: var(--text);
}

.hero-note {
  margin: 8px 0 0;
  color: color-mix(in srgb, var(--muted) 90%, var(--cake-tint));
  font-size: 0.76rem;
  line-height: 1.4;
}

.hero-inputs {
  display: grid;
  grid-template-columns: 1fr 1fr;
  flex: 0 0 auto;
  gap: 10px;
  margin-top: auto;
}

.soft-field {
  display: grid;
  gap: 6px;
  padding: 10px 11px;
  border-radius: 14px;
  background: rgba(8, 14, 28, 0.45);
  border: 1px solid color-mix(in srgb, var(--border) 80%, transparent);
}

.soft-field > span {
  color: var(--muted);
  font-size: 0.7rem;
  font-weight: 750;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.soft-field :deep(.p-inputtext),
.item-fields :deep(.p-inputtext) {
  padding: 0.4rem 0.55rem;
  font-variant-numeric: tabular-nums;
}

.hero-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  flex: 0 0 auto;
  gap: 8px;
  margin-top: auto;
  padding-top: 4px;
}

.hero-stats div {
  display: grid;
  gap: 3px;
  padding: 10px 11px;
  border-radius: 14px;
  background: color-mix(in srgb, var(--cake-tint) 8%, rgba(8, 14, 28, 0.55));
  border: 1px solid color-mix(in srgb, var(--cake-tint) 18%, transparent);
}

.hero-stats span {
  color: var(--muted);
  font-size: 0.65rem;
  font-weight: 750;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.hero-stats strong {
  font-size: 0.95rem;
  font-variant-numeric: tabular-nums;
}

.market {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: clamp(0.4rem, 1.1vmin, 0.75rem);
  height: 100%;
  min-height: 0;
  padding: var(--card-pad);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: color-mix(in srgb, #0b1220 92%, var(--cake-tint));
  box-shadow: 0 18px 40px rgba(2, 6, 23, 0.28);
  overflow: hidden;
}

.market-head h2 {
  margin: 0;
  font-size: 1rem;
  letter-spacing: -0.02em;
}

.market-head p {
  margin: 4px 0 0;
  color: var(--muted);
  font-size: 0.76rem;
}

.market-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  grid-auto-rows: minmax(0, 1fr);
  gap: clamp(0.4rem, 1.15vmin, 0.9rem);
  align-content: stretch;
  min-height: 0;
  height: 100%;
  overflow: hidden;
  padding: 0;
}

.ingredient-card {
  display: flex;
  flex-direction: column;
  gap: clamp(0.35rem, 0.9vmin, 0.6rem);
  min-width: 0;
  height: 100%;
  min-height: 0;
  padding: clamp(0.55rem, 1.15vmin, 0.85rem);
  border: 1px solid color-mix(in srgb, var(--item-tint) 22%, var(--border));
  border-radius: calc(var(--radius) - 4px);
  background:
    linear-gradient(160deg, color-mix(in srgb, var(--item-tint) 14%, transparent), transparent 55%),
    rgba(8, 14, 28, 0.55);
  transition:
    border-color 0.15s ease,
    box-shadow 0.15s ease;
  overflow: hidden;
}

.ingredient-card:hover {
  border-color: color-mix(in srgb, var(--item-tint) 45%, var(--border));
}

.ingredient-card.buying {
  box-shadow: 0 10px 24px color-mix(in srgb, var(--item-tint) 18%, transparent);
  border-color: color-mix(in srgb, var(--item-tint) 55%, var(--border));
}

.ingredient-card header {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.ingredient-card header > div {
  min-width: 0;
  overflow: hidden;
}

.ingredient-card header strong,
.ingredient-card header small {
  min-width: 0;
}

.item-blob {
  width: 28px;
  height: 28px;
  border-radius: 10px;
  background:
    radial-gradient(circle at 30% 30%, #fff8, transparent 40%),
    var(--item-tint);
  box-shadow: 0 6px 14px color-mix(in srgb, var(--item-tint) 35%, transparent);
}

.ingredient-card strong,
.ingredient-card small {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ingredient-card strong {
  line-height: 1.2;
  font-size: 0.82rem;
}

.ingredient-card small {
  margin-top: 2px;
  color: var(--muted);
  font-size: 0.66rem;
}

.buy-pill {
  flex: 0 0 auto;
  min-width: 0;
  padding: 3px 7px;
  border-radius: 999px;
  color: #1a1020;
  font-size: 0.68rem;
  font-weight: 800;
  background: var(--item-tint);
}

.item-fields {
  display: grid;
  flex: 1 1 auto;
  align-content: start;
  gap: 8px;
  min-width: 0;
  min-height: 0;
}

.item-fields label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
  width: 100%;
  padding-top: 2px;
}

.item-fields label > span {
  display: block;
  min-width: 0;
}

.item-fields span {
  color: var(--muted);
  font-size: 0.64rem;
  font-weight: 750;
  line-height: 1.2;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  white-space: nowrap;
  margin-bottom: 1px;
}

.item-fields :deep(.p-inputnumber),
.item-fields :deep(.p-inputnumber-input),
.item-fields :deep(.p-inputtext) {
  display: block;
  width: 100%;
  box-sizing: border-box;
}

.ingredient-card footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex: 0 0 auto;
  margin-top: auto;
  padding: 8px 2px 1px;
  border-top: 1px solid color-mix(in srgb, var(--item-tint) 18%, transparent);
  color: var(--muted);
  font-size: 0.7rem;
}

.ingredient-card footer strong {
  color: color-mix(in srgb, var(--item-tint) 55%, #fff);
  font-size: 0.86rem;
  font-variant-numeric: tabular-nums;
}

@media (max-height: 600px) {
  .tile-copy small {
    display: none;
  }

  .hero-copy {
    padding-right: 0;
  }

  .hero-note {
    -webkit-line-clamp: 2;
  }

  .recipe-tile {
    padding: clamp(0.35rem, 0.9vmin, 0.55rem) clamp(0.45rem, 1vmin, 0.7rem);
  }
}

@media (max-width: 1100px) {
  .scene-body {
    grid-template-columns: minmax(14rem, 0.78fr) minmax(0, 1.5fr);
  }
}

@media (max-width: 900px) {
  .cakes-pane,
  :global(.app-main > .content-pane.cakes-pane) {
    overflow: auto;
  }

  .cakes-scene {
    height: auto;
    min-height: 100%;
    max-height: none;
    overflow: visible;
  }

  .recipe-rail {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .scene-body {
    grid-template-columns: 1fr;
    height: auto;
  }

  .hero-card,
  .market {
    height: auto;
    min-height: min(48vh, 26rem);
  }

  .market-grid {
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 11.5rem), 1fr));
    grid-auto-rows: minmax(9rem, auto);
    height: auto;
    overflow: visible;
  }

  .ingredient-card header {
    grid-template-columns: 24px minmax(0, 1fr) auto;
    gap: 6px;
  }

  .item-blob {
    width: 24px;
    height: 24px;
  }

  .ingredient-card strong {
    font-size: 0.76rem;
  }

  .ingredient-card small {
    font-size: 0.6rem;
  }

  .item-fields span {
    font-size: 0.58rem;
  }
}

@media (max-width: 640px) {
  .recipe-rail {
    grid-template-columns: 1fr 1fr;
  }

  .scene-top {
    align-items: start;
    flex-direction: column;
  }

  .top-actions {
    width: 100%;
  }

  .top-actions :deep(.p-button) {
    flex: 1;
  }

  .hero-inputs,
  .hero-stats {
    grid-template-columns: 1fr;
  }

  .hero-card,
  .market {
    min-height: 0;
  }
}

@media (min-width: 1600px) {
  .scene-body {
    grid-template-columns: minmax(20rem, 0.75fr) minmax(0, 1.7fr);
  }
}
</style>
