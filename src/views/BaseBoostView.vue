<script setup lang="ts">
import SafeImage from '@/components/common/SafeImage.vue'
import { ELEMENT_STROKE_ONLY, ELEMENT_THEME } from '@/domain/elementTheme'

// ─── Types ────────────────────────────────────────────────────────────────────

interface WorkPal {
  name: string
  code: string
  suitability: string
  suitIcon: string
  note?: string
}

interface DropPal {
  name: string
  code: string
}

interface ElementGroup {
  element: string
  pals: DropPal[]
}

// ─── CDN helper ───────────────────────────────────────────────────────────────
// Some pals have icon URLs in a non-standard subfolder (e.g. Terraria crossover pals).
// The breed.json is the authoritative source; exceptions are listed here.

const CDN_OVERRIDES: Record<string, string> = {
  YakushimaMonster002:
    'https://cdn.paldb.cc/image/Pal/Texture/PalIcon/Normal/Yakushima/T_YakushimaMonster002_icon_normal.webp',
}

const CDN = (code: string): string =>
  CDN_OVERRIDES[code] ??
  `https://cdn.paldb.cc/image/Pal/Texture/PalIcon/Normal/T_${code}_icon_normal.webp`

// ─── Work Suitability Boost data ─────────────────────────────────────────────
// Source: paldb.cc partner skills — one pal per suitability, base-only, no-stack

const workPals: WorkPal[] = [
  { name: 'Clovee',           code: 'CloverFairy',         suitability: 'Gathering',    suitIcon: '🌾' },
  { name: 'Eikthyrdeer Terra',code: 'Deer_Ground',          suitability: 'Lumbering',    suitIcon: '🪵', note: 'Rideable · double jump' },
  { name: 'Tetroise',         code: 'CubeTurtle',           suitability: 'Mining',       suitIcon: '⛏️', note: 'Rideable · Tech 48' },
  { name: 'Amione',           code: 'ClioneTwins',          suitability: 'Watering',     suitIcon: '💧' },
  { name: 'Petallia',         code: 'FlowerDoll',           suitability: 'Planting',     suitIcon: '🌱', note: 'Heals 75–85% HP on activation' },
  { name: 'Cinnamoth',        code: 'CuteButterfly',        suitability: 'Farming',      suitIcon: '🐾', note: 'Attacks with Poison Fog' },
  { name: 'Ribbuny',          code: 'PinkRabbit',           suitability: 'Handiwork',    suitIcon: '🔨', note: '+15–30% Atk to Neutral Pals in party' },
  { name: 'Katress Ignis',    code: 'CatMage_Fire',         suitability: 'Kindling',     suitIcon: '🔥' },
  { name: 'Puffolt',          code: 'ElecPomeranian',       suitability: 'Electricity',  suitIcon: '⚡' },
  { name: 'Smokie Cryst',     code: 'BlackPuppy_Ice',       suitability: 'Cooling',      suitIcon: '❄️' },
  { name: 'Mycora',           code: 'MushroomLady',         suitability: 'Medicine',     suitIcon: '💊' },
  { name: 'Wumpo',            code: 'Yeti',                 suitability: 'Transporting', suitIcon: '📦', note: 'Rideable · Tech 45' },
]

// ─── Drop Rate Boost data ─────────────────────────────────────────────────────
// BUG FIX (paldb.cc verified):
//   Cryolinx  → "Dragon Pals drop more items" → Dragon  (was incorrectly in Dark)
//   Elphidran → "Dark Pals drop more items"   → Dark    (was incorrectly in Dragon)

const elementGroups: ElementGroup[] = [
  {
    element: 'Fire',
    pals: [
      { name: 'Penking',     code: 'CaptainPenguin' },
      { name: 'Faleris Aqua',code: 'Horus_Water'    },
    ],
  },
  {
    element: 'Grass',
    pals: [{ name: 'Blazehowl', code: 'Manticore' }],
  },
  {
    element: 'Ground',
    pals: [{ name: 'Vaelet', code: 'VioletFairy' }],
  },
  {
    element: 'Electric',
    pals: [
      { name: 'Menasting Terra', code: 'DarkScorpion_Ground' },
      { name: 'Menasting',       code: 'DarkScorpion'        },
    ],
  },
  {
    element: 'Water',
    pals: [{ name: 'Fenglope Lux', code: 'FengyunDeeper_Electric' }],
  },
  {
    element: 'Ice',
    pals: [{ name: 'Faleris', code: 'Horus' }],
  },
  {
    element: 'Dark',
    pals: [
      { name: 'Enchanted Sword', code: 'YakushimaMonster002' }, // ← FIXED (was in Dragon)
      { name: 'Elphidran',       code: 'FairyDragon'         }, // ← FIXED (was in Dragon)
    ],
  },
  {
    element: 'Dragon',
    pals: [
      { name: 'Cryolinx', code: 'WhiteTiger' }, // ← FIXED (was in Dark)
    ],
  },
  {
    element: 'Neutral',
    pals: [
      { name: 'Katress',        code: 'CatMage'        },
      { name: 'Blazehowl Noct', code: 'Manticore_Dark' },
    ],
  },
]

// ─── Helpers ──────────────────────────────────────────────────────────────────

function theme(element: string) {
  return ELEMENT_THEME[element] ?? ELEMENT_THEME['Neutral']!
}

function isStrokeOnly(element: string) {
  return ELEMENT_STROKE_ONLY.has(element)
}
</script>

<template>
  <div class="content-pane bb-pane">
    <div class="bb-wrap">

      <!-- ══ HEADER ══════════════════════════════════════════════════════════ -->
      <header class="bb-header">
        <div class="bb-title-row">
          <span class="bb-eyebrow">Passive Buffs</span>
          <h1 class="bb-title">Base Boost</h1>
        </div>
        <div class="bb-rules">
          <span class="rule-chip">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>
            Work Suitability: <strong>+1 to all Pals at base</strong>
            <span class="rule-sep">·</span> base-only · no stack
          </span>
          <span class="rule-chip">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><line x1="19" y1="5" x2="5" y2="19"/><circle cx="6.5" cy="6.5" r="2.5"/><circle cx="17.5" cy="17.5" r="2.5"/></svg>
            Drop Rate: <strong>40 – 80%</strong>
            <span class="rule-sep">·</span> stacks with unique Pals
          </span>
        </div>
      </header>

      <!-- ══ BODY ════════════════════════════════════════════════════════════ -->
      <div class="bb-body">

        <!-- ── LEFT PANEL: Work Suitability ─────────────────────────────── -->
        <section class="bb-panel bb-panel--work">
          <div class="panel-accent panel-accent--work" aria-hidden="true" />

          <div class="panel-header">
            <h2 class="panel-title">Work Suitability Boost</h2>
            <p class="panel-sub">One Pal per suitability · assigned to base</p>
          </div>

          <div class="work-grid">
            <div
              v-for="pal in workPals"
              :key="pal.code"
              class="work-card"
              :title="pal.note"
            >
              <div class="work-icon-wrap">
                <SafeImage
                  :src="CDN(pal.code)"
                  :alt="pal.name"
                  :fallback-label="pal.name"
                  class="work-img"
                />
              </div>
              <div class="work-meta">
                <span class="work-name">{{ pal.name }}</span>
                <span class="work-suit">
                  <span class="work-suit-icon" aria-hidden="true">{{ pal.suitIcon }}</span>
                  {{ pal.suitability }}
                </span>
              </div>
              <div v-if="pal.note" class="work-note-dot" :title="pal.note" aria-hidden="true" />
            </div>
          </div>
        </section>

        <!-- ── RIGHT PANEL: Drop Rate ────────────────────────────────────── -->
        <section class="bb-panel bb-panel--drop">
          <div class="panel-accent panel-accent--drop" aria-hidden="true" />

          <div class="panel-header">
            <h2 class="panel-title">Drop Rate Boost</h2>
            <p class="panel-sub">Scales 40–80% · stackable with unique Pals</p>
          </div>

          <div class="element-grid">
            <div
              v-for="group in elementGroups"
              :key="group.element"
              class="el-card"
              :style="{
                '--el':        theme(group.element).color,
                '--el-strong': theme(group.element).colorStrong,
                '--el-glow':   theme(group.element).glow,
                '--el-grad':   theme(group.element).gradient,
              }"
            >
              <!-- Radial glow behind pals -->
              <div class="el-glow-layer" aria-hidden="true" />

              <!-- Element label with SVG icon -->
              <div class="el-label">
                <svg
                  class="el-svg"
                  viewBox="0 0 24 24"
                  :fill="isStrokeOnly(group.element) ? 'none' : 'currentColor'"
                  :stroke="isStrokeOnly(group.element) ? 'currentColor' : 'none'"
                  stroke-width="2"
                  aria-hidden="true"
                >
                  <path :d="theme(group.element).svgPath" />
                </svg>
                <span class="el-name">{{ group.element }}</span>
              </div>

              <!-- Pals -->
              <div class="el-pals" :class="{ 'el-pals--single': group.pals.length === 1 }">
                <div
                  v-for="pal in group.pals"
                  :key="pal.code"
                  class="el-pal"
                >
                  <div class="el-pal-icon">
                    <SafeImage
                      :src="CDN(pal.code)"
                      :alt="pal.name"
                      :fallback-label="pal.name"
                      class="el-pal-img"
                    />
                  </div>
                  <span class="el-pal-name">{{ pal.name }}</span>
                </div>
              </div>
            </div>
          </div>
        </section>

      </div><!-- /bb-body -->
    </div><!-- /bb-wrap -->
  </div><!-- /bb-pane -->
</template>

<style scoped>
/* ════════════════════════════════════════════════════════════
   SHELL
   ════════════════════════════════════════════════════════════ */
.bb-pane {
  height: 100%;
  overflow: hidden;
}

.bb-wrap {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: clamp(0.4rem, 1vmin, 0.75rem);
  height: 100%;
  max-height: 100%;
  overflow: hidden;
  padding: clamp(0.6rem, 1.5vmin, 1rem) clamp(0.9rem, 2.2vw, 1.6rem);
  box-sizing: border-box;
}

/* ════════════════════════════════════════════════════════════
   HEADER
   ════════════════════════════════════════════════════════════ */
.bb-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}

.bb-title-row {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
}

.bb-eyebrow {
  font-size: 0.62rem;
  font-weight: 800;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--accent, #22d3ee);
  white-space: nowrap;
}

.bb-title {
  margin: 0;
  font-size: clamp(1.2rem, 2.6vmin, 2rem);
  font-weight: 800;
  letter-spacing: -0.04em;
  color: var(--text, #f1f5f9);
}

.bb-rules {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.rule-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.09);
  color: var(--muted, #9aabc2);
  font-size: clamp(0.68rem, 1.2vmin, 0.78rem);
  white-space: nowrap;
  transition: border-color 0.2s, background 0.2s;
}

.rule-chip svg {
  width: 13px;
  height: 13px;
  flex-shrink: 0;
  opacity: 0.65;
}

.rule-chip strong {
  color: var(--text, #f1f5f9);
  font-weight: 700;
}

.rule-sep {
  opacity: 0.35;
}

/* ════════════════════════════════════════════════════════════
   BODY
   ════════════════════════════════════════════════════════════ */
.bb-body {
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(0, 0.95fr);
  gap: clamp(0.5rem, 1.3vmin, 1rem);
  height: 100%;
  min-height: 0;
}

/* ════════════════════════════════════════════════════════════
   PANEL SHELL (shared)
   ════════════════════════════════════════════════════════════ */
.bb-panel {
  position: relative;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  height: 100%;
  min-height: 0;
  overflow: hidden;
  border-radius: clamp(0.75rem, 1.6vmin, 1.25rem);
  border: 1px solid rgba(255, 255, 255, 0.07);
  background: rgba(8, 14, 28, 0.6);
  /* Glass shimmer */
  box-shadow:
    0 0 0 1px rgba(255, 255, 255, 0.04) inset,
    0 24px 48px rgba(2, 6, 23, 0.4);
}

/* Corner gradient accent unique per panel */
.panel-accent {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  border-radius: inherit;
}

.panel-accent--work {
  background:
    radial-gradient(ellipse at 100% 0%, rgba(14, 165, 233, 0.12) 0%, transparent 50%),
    radial-gradient(ellipse at 0% 100%, rgba(129, 140, 248, 0.10) 0%, transparent 50%);
}

.panel-accent--drop {
  background:
    radial-gradient(ellipse at 100% 0%, rgba(236, 72, 153, 0.12) 0%, transparent 50%),
    radial-gradient(ellipse at 0% 100%, rgba(139, 92, 246, 0.10) 0%, transparent 50%);
}

.panel-header {
  position: relative;
  z-index: 1;
  padding: clamp(0.5rem, 1vmin, 0.75rem) clamp(0.75rem, 1.5vmin, 1.1rem);
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(8, 14, 28, 0.55);
  backdrop-filter: blur(8px);
}

.panel-title {
  margin: 0 0 2px;
  font-size: clamp(0.82rem, 1.6vmin, 1rem);
  font-weight: 800;
  letter-spacing: -0.02em;
  color: var(--text, #f1f5f9);
}

.panel-sub {
  margin: 0;
  font-size: clamp(0.62rem, 1.1vmin, 0.72rem);
  color: var(--muted, #9aabc2);
  letter-spacing: 0.03em;
}

/* ════════════════════════════════════════════════════════════
   WORK SUITABILITY — 4×3 GRID
   ════════════════════════════════════════════════════════════ */
.work-grid {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  grid-template-rows: repeat(3, 1fr);
  gap: clamp(0.3rem, 0.7vmin, 0.5rem);
  height: 100%;
  min-height: 0;
  padding: clamp(0.35rem, 0.75vmin, 0.55rem);
}

.work-card {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: clamp(0.2rem, 0.55vmin, 0.4rem);
  padding: clamp(0.35rem, 0.8vmin, 0.6rem) clamp(0.25rem, 0.6vmin, 0.45rem);
  height: 100%;
  width: 100%;
  box-sizing: border-box;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.055);
  background: rgba(12, 20, 38, 0.55);
  cursor: default;
  overflow: hidden;
  transition:
    border-color 0.22s ease,
    background 0.22s ease,
    transform 0.18s ease,
    box-shadow 0.22s ease;
}

.work-card:hover {
  border-color: rgba(14, 165, 233, 0.45);
  background: rgba(14, 165, 233, 0.06);
  transform: translateY(-2px) scale(1.02);
  box-shadow:
    0 0 18px rgba(14, 165, 233, 0.18),
    0 8px 24px rgba(2, 6, 23, 0.35);
}

.work-icon-wrap {
  flex: 1 1 0;
  min-height: 0;
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.work-img {
  display: block;
  height: 100%;
  width: auto;
  max-width: 100%;
  aspect-ratio: 1;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.25);
  overflow: hidden;
}

.work-meta {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  width: 100%;
  min-width: 0;
}

.work-name {
  font-size: clamp(0.62rem, 1.25vmin, 0.82rem);
  font-weight: 700;
  color: var(--text, #f1f5f9);
  text-align: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  width: 100%;
  line-height: 1.2;
}

.work-suit {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: clamp(0.56rem, 1.05vmin, 0.7rem);
  font-weight: 600;
  letter-spacing: 0.04em;
  color: var(--accent, #22d3ee);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}

.work-suit-icon {
  font-size: 0.75em;
  line-height: 1;
}

/* Dot indicator for pals with a secondary note */
.work-note-dot {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--accent-strong, #818cf8);
  box-shadow: 0 0 6px var(--accent-strong, #818cf8);
  opacity: 0.8;
}

/* ════════════════════════════════════════════════════════════
   DROP RATE — 3×3 ELEMENT GRID
   ════════════════════════════════════════════════════════════ */
.element-grid {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  grid-template-rows: repeat(3, 1fr);
  gap: clamp(0.3rem, 0.7vmin, 0.5rem);
  height: 100%;
  min-height: 0;
  padding: clamp(0.35rem, 0.75vmin, 0.55rem);
}

.el-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: clamp(0.2rem, 0.5vmin, 0.35rem);
  padding: clamp(0.35rem, 0.8vmin, 0.6rem) clamp(0.3rem, 0.7vmin, 0.5rem);
  height: 100%;
  width: 100%;
  box-sizing: border-box;
  border-radius: 10px;
  /* Dynamic border from --el */
  border: 1px solid color-mix(in srgb, var(--el) 28%, rgba(255, 255, 255, 0.06));
  /* Gradient background from elementTheme */
  background:
    var(--el-grad),
    rgba(8, 14, 28, 0.58);
  overflow: hidden;
  transition:
    border-color 0.22s ease,
    background 0.22s ease,
    transform 0.18s ease,
    box-shadow 0.22s ease;
}

.el-card:hover {
  border-color: color-mix(in srgb, var(--el) 65%, rgba(255, 255, 255, 0.15));
  transform: translateY(-2px) scale(1.02);
  box-shadow:
    0 0 22px color-mix(in srgb, var(--el) 30%, transparent),
    0 8px 24px rgba(2, 6, 23, 0.4);
}

/* Radial glow behind pal icons */
.el-glow-layer {
  position: absolute;
  inset: 0;
  background: var(--el-glow);
  pointer-events: none;
  z-index: 0;
  opacity: 0.55;
  transition: opacity 0.22s ease;
}

.el-card:hover .el-glow-layer {
  opacity: 0.9;
}

/* Element label row: SVG icon + name */
.el-label {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 5px;
  flex-shrink: 0;
}

.el-svg {
  width: clamp(10px, 1.6vmin, 16px);
  height: clamp(10px, 1.6vmin, 16px);
  flex-shrink: 0;
  color: var(--el);
  filter: drop-shadow(0 0 4px color-mix(in srgb, var(--el) 70%, transparent));
}

.el-name {
  font-size: clamp(0.6rem, 1.1vmin, 0.72rem);
  font-weight: 800;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--el);
  text-shadow: 0 0 10px color-mix(in srgb, var(--el) 60%, transparent);
  white-space: nowrap;
}

/* Pals row */
.el-pals {
  position: relative;
  z-index: 1;
  flex: 1 1 0;
  min-height: 0;
  display: flex;
  flex-direction: row;
  align-items: stretch;
  justify-content: space-evenly;
  gap: clamp(0.2rem, 0.5vmin, 0.35rem);
  overflow: hidden;
}

.el-pal {
  flex: 1 1 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  gap: clamp(0.15rem, 0.4vmin, 0.28rem);
  overflow: hidden;
}

.el-pal-icon {
  flex: 1 1 0;
  min-height: 0;
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.el-pal-img {
  display: block;
  height: 100%;
  width: auto;
  max-width: 100%;
  aspect-ratio: 1;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.22);
  overflow: hidden;
  /* Glow ring matching element */
  filter: drop-shadow(0 2px 8px color-mix(in srgb, var(--el) 40%, transparent));
  transition: filter 0.22s ease, transform 0.18s ease;
}

.el-card:hover .el-pal-img {
  filter: drop-shadow(0 2px 14px color-mix(in srgb, var(--el) 65%, transparent));
  transform: scale(1.04);
}

.el-pal-name {
  flex-shrink: 0;
  font-size: clamp(0.6rem, 1.15vmin, 0.76rem);
  font-weight: 700;
  color: var(--text, #f1f5f9);
  text-align: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  width: 100%;
  line-height: 1.2;
}

/* ════════════════════════════════════════════════════════════
   TABLET  640–1024px
   ════════════════════════════════════════════════════════════ */
@media (max-width: 1024px) and (min-width: 641px) {
  .bb-body {
    grid-template-columns: 1fr 1fr;
  }

  .work-grid {
    grid-template-columns: repeat(3, 1fr);
    grid-template-rows: repeat(4, 1fr);
  }
}

/* ════════════════════════════════════════════════════════════
   MOBILE  ≤640px
   ════════════════════════════════════════════════════════════ */
@media (max-width: 640px) {
  .bb-pane,
  .bb-wrap {
    overflow: auto;
  }

  .bb-wrap {
    height: auto;
    min-height: 100%;
    max-height: none;
    padding: 12px 14px;
  }

  .bb-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }

  .bb-rules {
    flex-direction: column;
    align-items: flex-start;
  }

  .rule-chip {
    white-space: normal;
    line-height: 1.5;
  }

  .bb-body {
    grid-template-columns: 1fr;
    height: auto;
  }

  .bb-panel {
    height: auto;
  }

  /* Work: horizontal list on mobile */
  .work-grid {
    grid-template-columns: 1fr;
    grid-template-rows: auto;
    height: auto;
  }

  .work-card {
    flex-direction: row;
    justify-content: flex-start;
    align-items: center;
    gap: 14px;
    padding: 10px 14px;
    height: auto;
    min-height: 56px;
  }

  .work-card:hover {
    transform: none;
  }

  .work-icon-wrap {
    flex: 0 0 auto;
    width: 44px;
    height: 44px;
  }

  .work-img {
    height: 44px;
    width: 44px;
    aspect-ratio: 1;
  }

  .work-meta {
    align-items: flex-start;
    flex-direction: row;
    gap: 8px;
    align-items: center;
    flex-wrap: wrap;
  }

  .work-name {
    text-align: left;
    white-space: nowrap;
    width: auto;
    flex-shrink: 0;
  }

  .work-suit {
    white-space: nowrap;
  }

  .work-note-dot {
    top: 8px;
    right: 8px;
  }

  /* Drop rate: 2-column on mobile */
  .element-grid {
    grid-template-columns: repeat(2, 1fr);
    grid-template-rows: auto;
    height: auto;
  }

  .el-card {
    height: auto;
    min-height: 100px;
  }

  .el-card:hover {
    transform: none;
  }

  .el-pals {
    flex-wrap: wrap;
  }

  .el-pal {
    flex: 0 0 auto;
    min-width: 60px;
  }

  .el-pal-icon {
    flex: 0 0 auto;
    width: 44px;
    height: 44px;
  }

  .el-pal-img {
    height: 44px;
    width: 44px;
  }
}
</style>
