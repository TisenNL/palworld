<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'

import SafeImage from '@/components/common/SafeImage.vue'
import type { BracketTile, CraftBracket } from '@/domain/itemCraft'

const props = defineProps<{ bracket: CraftBracket }>()

const fmt = (value: number) => value.toLocaleString('en-US')

// ─── Sizing ─────────────────────────────────────────────────────────────────
// Rounds never squeeze below this width — on narrow screens the strip scrolls
// horizontally instead of breaking the layout.
const MIN_COLUMN_WIDTH = 152
const PAD_X = 4
const MIN_TILE_HEIGHT = 26
const MAX_TILE_HEIGHT = 58

const host = ref<HTMLElement | null>(null)
const scroller = ref<HTMLElement | null>(null)
const box = reactive({ w: 0, h: 0 })

let observer: ResizeObserver | null = null

onMounted(() => {
  // Measure the *available* space (the scroller), never the host: the host
  // width is what we compute, so observing it would never shrink back.
  const el = scroller.value
  if (!el) return
  observer = new ResizeObserver((entries) => {
    const rect = entries[0]?.contentRect
    if (!rect) return
    box.w = rect.width
    box.h = rect.height
  })
  observer.observe(el)
})

onBeforeUnmount(() => observer?.disconnect())

// ─── Layout ─────────────────────────────────────────────────────────────────
interface Placed {
  tile: BracketTile
  x: number
  y: number
  w: number
  h: number
}

const layout = computed(() => {
  const levels = props.bracket.levels
  const columns = levels.length
  const widest = levels.reduce((max, level) => Math.max(max, level.length), 1)

  const height = box.h
  const width = Math.max(box.w, columns * MIN_COLUMN_WIDTH + PAD_X * 2)
  const columnWidth = width / columns
  const tileHeight = Math.max(
    MIN_TILE_HEIGHT,
    Math.min(MAX_TILE_HEIGHT, (height - 4 * (widest - 1)) / widest),
  )
  const tileWidth = Math.max(110, Math.min(columnWidth - 30, 250))

  const centerInColumn = (level: number, w: number) => level * columnWidth + (columnWidth - w) / 2

  const placed = new Map<string, Placed>()
  levels.forEach((level, levelIndex) => {
    level.forEach((tile, index) => {
      // Champion stands out: wider and taller, always vertically centered.
      const w = tile.champion ? Math.min(tileWidth + 26, columnWidth - 12) : tileWidth
      const h = tile.champion ? Math.min(tileHeight * 1.4, height) : tileHeight
      const y = tile.champion ? height / 2 - h / 2 : ((index + 0.5) * height) / level.length - h / 2
      placed.set(tile.id, {
        tile,
        x: centerInColumn(levelIndex, w),
        y,
        w,
        h,
      })
    })
  })

  const paths: string[] = []
  for (const edge of props.bracket.edges) {
    const child = placed.get(edge.from)
    const parent = placed.get(edge.to)
    if (!child || !parent) continue
    const x1 = child.x + child.w
    const y1 = child.y + child.h / 2
    const x2 = parent.x
    const y2 = parent.y + parent.h / 2
    const bend = Math.max(18, (x2 - x1) / 2)
    paths.push(`M ${x1} ${y1} C ${x1 + bend} ${y1}, ${x2 - bend} ${y2}, ${x2} ${y2}`)
  }

  return {
    width,
    height,
    placed: [...placed.values()],
    paths,
  }
})
</script>

<template>
  <div ref="scroller" class="bk-scroll">
    <div ref="host" class="bk-host" :style="{ width: `${layout.width}px` }">
      <svg
        class="bk-links"
        :viewBox="`0 0 ${layout.width} ${layout.height}`"
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        <path v-for="(path, index) in layout.paths" :key="index" :d="path" />
      </svg>

      <div
        v-for="item in layout.placed"
        :key="item.tile.id"
        class="bk-tile"
        :class="{
          'bk-tile--champion': item.tile.champion,
          'bk-tile--raw': item.tile.raw,
        }"
        :style="{
          left: `${item.x}px`,
          top: `${item.y}px`,
          width: `${item.w}px`,
          height: `${item.h}px`,
        }"
        :title="`${item.tile.name} × ${fmt(item.tile.qty)}`"
        role="listitem"
      >
        <span class="bk-icon">
          <SafeImage
            :src="item.tile.icon ?? ''"
            :alt="item.tile.name"
            :fallback-label="item.tile.name"
          />
        </span>
        <span class="bk-copy">
          <span class="bk-name">{{ item.tile.name }}</span>
          <span class="bk-qty">× {{ fmt(item.tile.qty) }}</span>
          <span v-if="item.tile.champion" class="bk-crown-label">Champion</span>
        </span>
        <i v-if="item.tile.champion" class="pi pi-crown bk-crown" aria-hidden="true" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.bk-scroll {
  width: 100%;
  height: 100%;
  min-height: 0;
  overflow-x: auto;
  overflow-y: hidden;
  scrollbar-color: color-mix(in srgb, var(--muted, #9aabc2) 52%, transparent) transparent;
  scrollbar-width: thin;
}

.bk-host {
  position: relative;
  height: 100%;
  min-width: 100%;
}

.bk-links {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}

.bk-links path {
  fill: none;
  stroke: rgba(125, 211, 252, 0.3);
  stroke-width: 1.5;
}

.bk-tile {
  position: absolute;
  display: flex;
  align-items: center;
  gap: 6px;
  box-sizing: border-box;
  padding: 3px 8px 3px 5px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  background: rgba(12, 20, 38, 0.72);
  box-shadow: 0 4px 14px rgba(2, 6, 23, 0.35);
  transition:
    border-color 0.16s ease,
    transform 0.16s ease;
}

.bk-tile:hover {
  z-index: 2;
  border-color: rgba(34, 211, 238, 0.5);
  transform: translateY(-1px);
}

.bk-tile--raw {
  border-style: dashed;
  background: rgba(8, 14, 28, 0.6);
}

.bk-tile--champion {
  gap: 8px;
  padding: 4px 10px 4px 6px;
  border-color: rgba(251, 191, 36, 0.75);
  background: linear-gradient(135deg, rgba(251, 191, 36, 0.2), rgba(251, 191, 36, 0.05));
  box-shadow: 0 0 22px rgba(251, 191, 36, 0.28);
}

.bk-tile--champion:hover {
  border-color: rgba(251, 191, 36, 1);
}

.bk-icon {
  display: block;
  flex: 0 0 auto;
  height: calc(100% - 4px);
  max-height: 56px;
  aspect-ratio: 1;
  overflow: hidden;
  border-radius: 7px;
}

.bk-copy {
  display: grid;
  min-width: 0;
  line-height: 1.15;
}

.bk-name {
  overflow: hidden;
  color: var(--text, #f1f5f9);
  font-size: clamp(9px, 1.15vh, 13px);
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bk-qty {
  color: var(--accent, #22d3ee);
  font-size: clamp(9px, 1.15vh, 13px);
  font-variant-numeric: tabular-nums;
  font-weight: 800;
}

.bk-crown-label {
  color: #fbbf24;
  font-size: clamp(7px, 0.95vh, 10px);
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.bk-tile--champion .bk-name {
  color: #fde68a;
  font-size: clamp(10px, 1.4vh, 15px);
  font-weight: 800;
}

.bk-tile--champion .bk-qty {
  color: #fbbf24;
  font-size: clamp(10px, 1.4vh, 15px);
}

.bk-crown {
  position: absolute;
  top: 3px;
  right: 5px;
  color: #fbbf24;
  font-size: clamp(10px, 1.5vh, 15px);
  filter: drop-shadow(0 0 6px rgba(251, 191, 36, 0.6));
}
</style>
