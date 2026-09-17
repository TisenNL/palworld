<script setup lang="ts">
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import InputNumber from 'primevue/inputnumber'
import SelectButton from 'primevue/selectbutton'
import { useToast } from 'primevue/usetoast'
import { computed } from 'vue'

import { useCakeStore } from '@/stores/cake'
import type { CakeKey } from '@/domain/cakes'

const cake = useCakeStore()
const toast = useToast()

const priceFields = computed(() => [
  { key: 'wheat' as CakeKey, label: 'Wheat' },
  ...cake.recipe.ingredients.map((item) => ({ key: item.price, label: item.label })),
])

const stockFields = computed(() => [
  { key: 'flour' as CakeKey, label: 'Flour' },
  ...(cake.recipe.honeyPer > 0 ? [{ key: 'honey' as CakeKey, label: 'Honey' }] : []),
  ...cake.recipe.ingredients.map((item) => ({ key: item.stock, label: item.label })),
])

const purchaseRows = computed(() => [
  ...cake.recipe.ingredients.map((item) => ({
    name: item.label,
    price: cake.prices[item.price],
    quantity: cake.result.purchases[item.key] ?? 0,
  })),
  {
    name: 'Wheat',
    price: cake.prices.wheat,
    quantity: cake.result.purchases.wheat ?? 0,
  },
])

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
  <div class="content-pane">
    <div class="view-page cakes-page">
      <header>
        <h1 class="view-title">Cake calculator</h1>
        <p class="view-subtitle">
          Calculate maximum production using current gold, prices, and inventory.
        </p>
      </header>

      <SelectButton
        v-model="cake.recipeId"
        :options="cake.recipes"
        option-label="label"
        option-value="id"
        class="recipe-picker"
        aria-label="Recipe"
      />

      <section class="cake-layout">
        <div class="glass-card input-card">
          <h2 class="panel-heading">Production</h2>
          <div class="input-grid">
            <div class="compact-field">
              <label for="cake-gold">Available gold</label>
              <InputNumber id="cake-gold" v-model="cake.gold" :min="0" fluid />
            </div>
            <div class="compact-field">
              <label for="cake-target">Cake target</label>
              <InputNumber id="cake-target" v-model="cake.target" :min="0" fluid />
            </div>
          </div>

          <h2 class="panel-heading section-title">Unit prices</h2>
          <div class="input-grid">
            <div v-for="field in priceFields" :key="field.key" class="compact-field">
              <label :for="`price-${field.key}`">{{ field.label }}</label>
              <InputNumber
                :id="`price-${field.key}`"
                v-model="cake.prices[field.key]"
                :min="0"
                fluid
              />
            </div>
          </div>

          <h2 class="panel-heading section-title">Current inventory</h2>
          <div class="input-grid">
            <div v-for="field in stockFields" :key="field.key" class="compact-field">
              <label :for="`stock-${field.key}`">{{ field.label }}</label>
              <InputNumber
                :id="`stock-${field.key}`"
                v-model="cake.stock[field.key]"
                :min="0"
                fluid
              />
            </div>
          </div>

          <div class="card-actions">
            <Button
              label="Reset prices"
              icon="pi pi-refresh"
              severity="secondary"
              outlined
              @click="cake.resetPrices"
            />
            <Button label="Apply purchase" icon="pi pi-shopping-cart" @click="applyPurchase" />
          </div>
        </div>

        <div class="result-stack">
          <div class="result-hero glass-card">
            <span>Maximum possible</span>
            <strong>{{ cake.result.maximum.toLocaleString('en-US') }}</strong>
            <small>{{ cake.recipe.label }}</small>
          </div>
          <div class="glass-card result-card">
            <h2 class="panel-heading">
              Purchase for {{ cake.result.amount.toLocaleString('en-US') }}
            </h2>
            <DataTable :value="purchaseRows" size="small">
              <Column field="name" header="Ingredient" />
              <Column field="price" header="Price">
                <template #body="{ data }">{{ data.price.toLocaleString('en-US') }}</template>
              </Column>
              <Column field="quantity" header="Quantity">
                <template #body="{ data }">{{ data.quantity.toLocaleString('en-US') }}</template>
              </Column>
              <Column header="Subtotal">
                <template #body="{ data }">{{
                  (data.price * data.quantity).toLocaleString('en-US')
                }}</template>
              </Column>
            </DataTable>
            <dl class="result-totals">
              <div>
                <dt>Spent</dt>
                <dd>{{ cake.result.spent.toLocaleString('en-US') }}</dd>
              </div>
              <div>
                <dt>Remaining</dt>
                <dd>{{ cake.result.remaining.toLocaleString('en-US') }}</dd>
              </div>
              <div>
                <dt>Unit cost without inventory</dt>
                <dd>{{ cake.result.unitCost.toLocaleString('en-US') }}</dd>
              </div>
            </dl>
            <p class="recipe-note">{{ cake.recipe.note }}</p>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.cakes-page {
  display: grid;
  align-content: start;
}

.recipe-picker {
  margin-bottom: 18px;
  overflow-x: auto;
}

.cake-layout {
  display: grid;
  grid-template-columns: minmax(420px, 1fr) minmax(380px, 0.9fr);
  align-items: start;
  gap: 18px;
}

.input-card,
.result-card {
  padding: 18px;
}

.input-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.section-title {
  margin-top: 22px;
}

.card-actions {
  display: flex;
  justify-content: end;
  gap: 8px;
  margin-top: 20px;
}

.result-stack {
  display: grid;
  gap: 14px;
}

.result-hero {
  display: grid;
  min-height: 190px;
  place-content: center;
  justify-items: center;
  background:
    radial-gradient(circle at 50% 20%, rgba(56, 189, 248, 0.22), transparent 60%), var(--panel);
}

.result-hero span,
.result-hero small,
.recipe-note {
  color: var(--muted);
}

.result-hero strong {
  font-size: clamp(3rem, 7vw, 5.5rem);
  line-height: 1;
  letter-spacing: -0.06em;
}

.result-totals {
  display: grid;
  gap: 8px;
  margin: 16px 0;
}

.result-totals div {
  display: flex;
  justify-content: space-between;
  gap: 20px;
}

.result-totals dt {
  color: var(--muted);
}

.result-totals dd {
  margin: 0;
  font-weight: 800;
}

.recipe-note {
  margin: 0;
  font-size: 0.8rem;
  line-height: 1.5;
}

@media (max-width: 980px) {
  .cake-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 620px) {
  .input-grid {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
