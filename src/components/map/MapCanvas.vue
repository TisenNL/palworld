<script setup lang="ts">
import { api } from '@/services/api'
import { gameToImage, imageToGame, mapProjection, formatCoordinatesOpgg } from '@/domain/coordinates'
import { wtGameToImage, wtImageToGame, wtProjection } from '@/domain/worldTreeCoordinates'
import { LruCache } from '@/domain/lruCache'
import type { MapMarker } from '@/types/data'
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps<{
  markers: MapMarker[]
  camera: { x: number; y: number; scale: number }
  selectedIds: Set<string>
  mapZone: 'palpagos' | 'world-tree'
}>()

const emit = defineEmits<{
  select: [marker: MapMarker | null, position: { x: number; y: number }]
  context: [marker: MapMarker, position: { x: number; y: number }]
  hover: [text: string]
  cameraChange: [camera: { x: number; y: number; scale: number }]
}>()

const canvas = ref<HTMLCanvasElement | null>(null)
const hasVisibleTile = ref(false)
const mapLoadFailed = ref(false)
const tileCache = new LruCache<string, ImageBitmap>(320)
const iconCache = new LruCache<string, CanvasImageSource>(420)
const tileLoading = new Set<string>()
const iconLoading = new Set<string>()
const failedTiles = new Map<string, { attempts: number; retryAt: number }>()
const failedIcons = new Map<string, { attempts: number; retryAt: number }>()
const tileQueue: Array<{ key: string; url: string }> = []
const iconQueue: Array<{ key: string; url: string; enhance: boolean }> = []
const controllers = new Set<AbortController>()
const retryTimers = new Set<number>()
let activeTiles = 0
let activeIcons = 0
let frame = 0
let observer: ResizeObserver | null = null
let dragging = false
let moved = false
let lastX = 0
let lastY = 0
let hoverMarker: MapMarker | null = null

const clampScale = (value: number): number => Math.max(0.0005, Math.min(1, value))

function activeProjection() {
  return props.mapZone === 'world-tree' ? wtProjection : mapProjection
}

function activeGameToImage(x: number, y: number) {
  return props.mapZone === 'world-tree' ? wtGameToImage(x, y) : gameToImage(x, y)
}

function activeImageToGame(x: number, y: number) {
  return props.mapZone === 'world-tree' ? wtImageToGame(x, y) : imageToGame(x, y)
}

function activeTileUrl(z: number, tx: number, ty: number): string {
  return props.mapZone === 'world-tree' ? api.mapTileUrlWt(z, tx, ty) : api.mapTileUrl(z, tx, ty)
}

function updateCamera(next: { x: number; y: number; scale: number }): void {
  emit('cameraChange', next)
}

function scheduleDraw(): void {
  if (frame) return
  frame = requestAnimationFrame(() => {
    frame = 0
    draw()
  })
}

function resize(): void {
  const element = canvas.value
  if (!element) return
  const rect = element.getBoundingClientRect()
  const dpr = Math.min(2.5, window.devicePixelRatio || 1)
  const width = Math.max(1, Math.round(rect.width * dpr))
  const height = Math.max(1, Math.round(rect.height * dpr))
  if (element.width !== width || element.height !== height) {
    element.width = width
    element.height = height
  }
  scheduleDraw()
}

function viewport(): { width: number; height: number; dpr: number } {
  const element = canvas.value
  const dpr = Math.min(2.5, window.devicePixelRatio || 1)
  return {
    width: element?.clientWidth ?? 1,
    height: element?.clientHeight ?? 1,
    dpr,
  }
}

function requestTile(z: number, x: number, y: number): void {
  const key = `${props.mapZone}/${z}/${x}/${y}`
  const failure = failedTiles.get(key)
  if (
    tileCache.has(key) ||
    tileLoading.has(key) ||
    (failure && (failure.attempts >= 3 || failure.retryAt > Date.now()))
  )
    return
  tileLoading.add(key)
  tileQueue.push({ key, url: activeTileUrl(z, x, y) })
  pumpTiles()
}

function pumpTiles(): void {
  while (activeTiles < 4 && tileQueue.length) {
    const item = tileQueue.shift()!
    activeTiles++
    const controller = new AbortController()
    controllers.add(controller)
    // no-store: bypass HTTP cache — old builds served bad tiles under these same URLs
    void fetch(item.url, { signal: controller.signal, cache: 'no-store' })
      .then((response) => {
        if (!response.ok) throw new Error(`Tile ${response.status}`)
        return response.blob()
      })
      .then(createImageBitmap)
      .then((image) => {
        tileCache.set(item.key, image)
        failedTiles.delete(item.key)
        hasVisibleTile.value = true
        mapLoadFailed.value = false
      })
      .catch(() => {
        const attempts = (failedTiles.get(item.key)?.attempts ?? 0) + 1
        failedTiles.set(item.key, { attempts, retryAt: Date.now() + attempts * 1200 })
        if (attempts < 3) {
          const timer = window.setTimeout(
            () => {
              retryTimers.delete(timer)
              scheduleDraw()
            },
            attempts * 1200 + 50,
          )
          retryTimers.add(timer)
        } else if (!hasVisibleTile.value) mapLoadFailed.value = true
      })
      .finally(() => {
        controllers.delete(controller)
        tileLoading.delete(item.key)
        activeTiles--
        scheduleDraw()
        pumpTiles()
      })
  }
}

function requestIcon(source: string, enhance: boolean): void {
  const failure = failedIcons.get(source)
  if (
    iconCache.has(source) ||
    iconLoading.has(source) ||
    (failure && (failure.attempts >= 3 || failure.retryAt > Date.now()))
  )
    return
  iconLoading.add(source)
  const url =
    source.startsWith('/') || source.startsWith('data:') || source.startsWith('blob:')
      ? source
      : api.mapIconUrl(source)
  iconQueue.push({ key: source, url, enhance })
  pumpIcons()
}

function enhancedIcon(image: ImageBitmap): HTMLCanvasElement {
  const size = 96
  const output = document.createElement('canvas')
  output.width = size
  output.height = size
  const context = output.getContext('2d')!
  context.imageSmoothingEnabled = true
  context.imageSmoothingQuality = 'high'
  context.save()
  context.filter = 'brightness(0) saturate(100%) drop-shadow(0 1px 1px rgba(0,0,0,.9))'
  context.globalAlpha = 0.72
  context.drawImage(image, 3, 3, size - 6, size - 6)
  context.restore()
  context.filter = 'saturate(1.3) contrast(1.18) brightness(1.04)'
  context.drawImage(image, 3, 3, size - 6, size - 6)
  return output
}

function pumpIcons(): void {
  while (activeIcons < 6 && iconQueue.length) {
    const item = iconQueue.shift()!
    activeIcons++
    const controller = new AbortController()
    controllers.add(controller)
    void fetch(item.url, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error(`Icon request failed with status ${response.status}`)
        return response.blob()
      })
      .then((blob) => {
        // Check if it's an SVG
        if (blob.type === 'image/svg+xml' || item.url.endsWith('.svg')) {
          return new Promise<ImageBitmap>((resolve, reject) => {
            const img = new Image()
            const objectUrl = URL.createObjectURL(blob)
            img.onload = () => {
              const canvas = document.createElement('canvas')
              canvas.width = img.width || 30
              canvas.height = img.height || 30
              const ctx = canvas.getContext('2d')!
              ctx.drawImage(img, 0, 0)
              URL.revokeObjectURL(objectUrl)
              createImageBitmap(canvas).then(resolve).catch(reject)
            }
            img.onerror = () => {
              URL.revokeObjectURL(objectUrl)
              reject(new Error('Failed to load SVG'))
            }
            img.src = objectUrl
          })
        }
        return createImageBitmap(blob)
      })
      .then((image) => {
        iconCache.set(item.key, item.enhance ? enhancedIcon(image) : image)
        failedIcons.delete(item.key)
      })
      .catch(() => {
        const attempts = (failedIcons.get(item.key)?.attempts ?? 0) + 1
        failedIcons.set(item.key, { attempts, retryAt: Date.now() + attempts * 1200 })
        if (attempts < 3) {
          const timer = window.setTimeout(
            () => {
              retryTimers.delete(timer)
              scheduleDraw()
            },
            attempts * 1200 + 50,
          )
          retryTimers.add(timer)
        }
      })
      .finally(() => {
        controllers.delete(controller)
        iconLoading.delete(item.key)
        activeIcons--
        scheduleDraw()
        pumpIcons()
      })
  }
}

function drawTiles(context: CanvasRenderingContext2D, width: number, height: number): void {
  const proj = activeProjection()
  const ideal = proj.worldZoom + Math.log2(props.camera.scale)
  const zoom = Math.max(proj.minTileZoom, Math.min(proj.maxTileZoom, Math.round(ideal)))
  const worldPerTile = proj.tileSize * 2 ** (proj.worldZoom - zoom)
  const minX = Math.max(0, Math.floor(-props.camera.x / props.camera.scale / worldPerTile) - 1)
  const minY = Math.max(0, Math.floor(-props.camera.y / props.camera.scale / worldPerTile) - 1)
  const maxIndex = 2 ** zoom - 1
  const maxX = Math.min(
    maxIndex,
    Math.ceil((width - props.camera.x) / props.camera.scale / worldPerTile) + 1,
  )
  const maxY = Math.min(
    maxIndex,
    Math.ceil((height - props.camera.y) / props.camera.scale / worldPerTile) + 1,
  )
  for (let y = minY; y <= maxY; y++) {
    for (let x = minX; x <= maxX; x++) {
      const key = `${props.mapZone}/${zoom}/${x}/${y}`
      const image = tileCache.get(key)
      const dx = props.camera.x + x * worldPerTile * props.camera.scale
      const dy = props.camera.y + y * worldPerTile * props.camera.scale
      const size = worldPerTile * props.camera.scale + 0.5
      if (image) context.drawImage(image, dx, dy, size, size)
      else {
        context.fillStyle = '#15202b'
        context.fillRect(dx, dy, size, size)
        requestTile(zoom, x, y)
      }
    }
  }
}

function markerPosition(marker: MapMarker): { x: number; y: number } {
  const image = activeGameToImage(marker.item.x, marker.item.y)
  return {
    x: props.camera.x + image.x * props.camera.scale,
    y: props.camera.y + image.y * props.camera.scale,
  }
}

function drawMarkers(context: CanvasRenderingContext2D, width: number, height: number): void {
  const markerSize = Math.max(18, Math.min(34, 22 + props.camera.scale * 16))
  for (const marker of props.markers) {
    const point = markerPosition(marker)
    const isAlpha = marker.storage === 'alphas'
    const size = isAlpha
      ? Math.max(markerSize, Math.min(48, 28 + props.camera.scale * 28))
      : markerSize
    if (point.x < -size || point.y < -size || point.x > width + size || point.y > height + size)
      continue
    context.save()
    if (marker.done) context.globalAlpha = 0.5
    const icon = marker.iconUrl ? iconCache.get(marker.iconUrl) : undefined
    if (marker.iconUrl && !icon) {
      requestIcon(marker.iconUrl, false)
    }
    context.beginPath()
    context.fillStyle = isAlpha ? 'rgba(8, 14, 28, 0.92)' : 'rgba(5, 10, 20, 0.72)'
    context.arc(point.x, point.y, size * (isAlpha ? 0.52 : 0.46), 0, Math.PI * 2)
    context.fill()
    if (isAlpha) {
      context.beginPath()
      context.strokeStyle = 'rgba(255,255,255,0.88)'
      context.lineWidth = 2
      context.arc(point.x, point.y, size * 0.52, 0, Math.PI * 2)
      context.stroke()
    }
    if (icon) {
      context.imageSmoothingEnabled = true
      context.imageSmoothingQuality = 'high'
      const pad = isAlpha ? size * 0.12 : 0
      context.drawImage(
        icon,
        point.x - size / 2 + pad,
        point.y - size / 2 + pad,
        size - pad * 2,
        size - pad * 2,
      )
    } else {
      context.beginPath()
      context.fillStyle = marker.color
      context.arc(point.x, point.y, size * 0.32, 0, Math.PI * 2)
      context.fill()
    }
    if (isAlpha && marker.item.lv != null) {
      const badge = String(marker.item.lv)
      context.font = `bold ${Math.max(10, Math.round(size * 0.28))}px Segoe UI, sans-serif`
      context.textAlign = 'center'
      context.textBaseline = 'middle'
      const bx = point.x + size * 0.34
      const by = point.y + size * 0.34
      const bw = Math.max(16, badge.length * 7 + 8)
      const bh = Math.max(14, size * 0.3)
      context.fillStyle = 'rgba(15, 23, 42, 0.92)'
      context.beginPath()
      context.roundRect(bx - bw / 2, by - bh / 2, bw, bh, 6)
      context.fill()
      context.fillStyle = '#fff'
      context.fillText(badge, bx, by + 0.5)
    }
    // Selection ring: solid navy-blue fill + black border (drawn before hover ring)
    if (props.selectedIds.has(marker.id)) {
      context.beginPath()
      context.strokeStyle = '#000'
      context.lineWidth = 2.5
      context.arc(point.x, point.y, size * 0.74, 0, Math.PI * 2)
      context.stroke()
      context.beginPath()
      context.strokeStyle = '#1e3a8a'
      context.lineWidth = 3.5
      context.arc(point.x, point.y, size * 0.74, 0, Math.PI * 2)
      context.stroke()
    }
    // Hover ring (outermost)
    if (hoverMarker?.id === marker.id) {
      context.beginPath()
      context.strokeStyle = '#fff'
      context.lineWidth = 2
      context.arc(point.x, point.y, size * 0.62, 0, Math.PI * 2)
      context.stroke()
    }
    context.restore()
  }
}

function draw(): void {
  const element = canvas.value
  const context = element?.getContext('2d')
  if (!element || !context) return
  const { width, height, dpr } = viewport()
  context.setTransform(dpr, 0, 0, dpr, 0, 0)
  context.clearRect(0, 0, width, height)
  drawTiles(context, width, height)
  drawMarkers(context, width, height)
}

function findMarker(x: number, y: number): MapMarker | null {
  let nearest: MapMarker | null = null
  let distance = 20
  for (let index = props.markers.length - 1; index >= 0; index--) {
    const marker = props.markers[index]!
    const point = markerPosition(marker)
    const hit =
      marker.storage === 'alphas' ? Math.max(24, Math.min(36, 26 + props.camera.scale * 20)) : 20
    const next = Math.hypot(point.x - x, point.y - y)
    if (next < Math.min(distance, hit)) {
      nearest = marker
      distance = next
    }
  }
  return nearest
}

function localPoint(event: PointerEvent | MouseEvent): { x: number; y: number } {
  const rect = canvas.value!.getBoundingClientRect()
  return { x: event.clientX - rect.left, y: event.clientY - rect.top }
}

function emitCursorStatus(
  screenX: number,
  screenY: number,
  marker: MapMarker | null,
  camera = props.camera,
): void {
  const imageX = (screenX - camera.x) / camera.scale
  const imageY = (screenY - camera.y) / camera.scale
  const game = activeImageToGame(imageX, imageY)
  const x = Math.round(game.x)
  const y = Math.round(game.y)
  const coords = formatCoordinatesOpgg(x, y, marker?.item.z)
  emit('hover', marker ? `${coords} · ${marker.label}` : coords)
}

function pointerDown(event: PointerEvent): void {
  if (event.button !== 0) return
  dragging = true
  moved = false
  lastX = event.clientX
  lastY = event.clientY
  canvas.value?.setPointerCapture(event.pointerId)
}

function pointerMove(event: PointerEvent): void {
  let camera = props.camera
  if (dragging) {
    const dx = event.clientX - lastX
    const dy = event.clientY - lastY
    if (Math.abs(dx) + Math.abs(dy) > 1) moved = true
    camera = {
      x: props.camera.x + dx,
      y: props.camera.y + dy,
      scale: props.camera.scale,
    }
    updateCamera(camera)
    lastX = event.clientX
    lastY = event.clientY
    scheduleDraw()
  }
  const point = localPoint(event)
  const marker = dragging ? null : findMarker(point.x, point.y)
  if (marker?.id !== hoverMarker?.id) {
    hoverMarker = marker
    if (!dragging) scheduleDraw()
  }
  emitCursorStatus(point.x, point.y, marker, camera)
}

function pointerUp(event: PointerEvent): void {
  if (!dragging) return
  dragging = false
  canvas.value?.releasePointerCapture(event.pointerId)
  if (!moved) {
    const point = localPoint(event)
    emit('select', findMarker(point.x, point.y), point)
  }
}

function wheel(event: WheelEvent): void {
  event.preventDefault()
  const point = localPoint(event)
  const imageX = (point.x - props.camera.x) / props.camera.scale
  const imageY = (point.y - props.camera.y) / props.camera.scale
  const scale = clampScale(props.camera.scale * Math.exp(-event.deltaY * 0.0014))
  const camera = {
    x: point.x - imageX * scale,
    y: point.y - imageY * scale,
    scale,
  }
  updateCamera(camera)
  scheduleDraw()
  emitCursorStatus(point.x, point.y, hoverMarker, camera)
}

function contextMenu(event: MouseEvent): void {
  event.preventDefault()
  const point = localPoint(event)
  const marker = findMarker(point.x, point.y)
  if (marker) emit('context', marker, point)
}

function cameraIntersectsMarkerBounds(): boolean {
  if (!props.markers.length) return false
  const { width, height } = viewport()
  let minX = Number.POSITIVE_INFINITY
  let maxX = Number.NEGATIVE_INFINITY
  let minY = Number.POSITIVE_INFINITY
  let maxY = Number.NEGATIVE_INFINITY
  for (const marker of props.markers) {
    const point = markerPosition(marker)
    minX = Math.min(minX, point.x)
    maxX = Math.max(maxX, point.x)
    minY = Math.min(minY, point.y)
    maxY = Math.max(maxY, point.y)
  }
  return maxX >= 0 && minX <= width && maxY >= 0 && minY <= height
}

function fitMarkers(): void {
  if (!props.markers.length) return
  const { width, height } = viewport()
  const points = props.markers.map((marker) => activeGameToImage(marker.item.x, marker.item.y))
  const minX = Math.min(...points.map((point) => point.x))
  const maxX = Math.max(...points.map((point) => point.x))
  const minY = Math.min(...points.map((point) => point.y))
  const maxY = Math.max(...points.map((point) => point.y))
  const scale = clampScale(Math.min((width - 80) / (maxX - minX), (height - 80) / (maxY - minY)))
  updateCamera({
    x: width / 2 - ((minX + maxX) / 2) * scale,
    y: height / 2 - ((minY + maxY) / 2) * scale,
    scale,
  })
  scheduleDraw()
}

function centerGame(x: number, y: number): void {
  const { width, height } = viewport()
  const point = activeGameToImage(x, y)
  updateCamera({
    x: width / 2 - point.x * props.camera.scale,
    y: height / 2 - point.y * props.camera.scale,
    scale: props.camera.scale,
  })
  scheduleDraw()
}

function coordinatesAt(x: number, y: number): { x: number; y: number } {
  return activeImageToGame(
    (x - props.camera.x) / props.camera.scale,
    (y - props.camera.y) / props.camera.scale,
  )
}

defineExpose({ fitMarkers, centerGame, coordinatesAt, redraw: scheduleDraw })

watch(
  () => [props.camera.x, props.camera.y, props.camera.scale, props.markers, props.mapZone],
  (newVal, oldVal) => {
    // Clear tile cache when switching maps to avoid showing wrong tiles
    if (Array.isArray(oldVal) && Array.isArray(newVal) && oldVal[4] !== newVal[4]) {
      tileCache.clear()
      failedTiles.clear()
      hasVisibleTile.value = false
    }
    scheduleDraw()
  },
  {
    deep: false,
  },
)

// Redraw when selection changes (deep watch needed because reactive Set mutates in place)
watch(() => props.selectedIds, scheduleDraw, { deep: true })

onMounted(() => {
  observer = new ResizeObserver(resize)
  observer.observe(canvas.value!)
  void nextTick(() => {
    resize()
    if (!cameraIntersectsMarkerBounds()) fitMarkers()
  })
})

onBeforeUnmount(() => {
  observer?.disconnect()
  cancelAnimationFrame(frame)
  controllers.forEach((controller) => controller.abort())
  controllers.clear()
  retryTimers.forEach((timer) => window.clearTimeout(timer))
  retryTimers.clear()
  tileCache.clear()
  iconCache.clear()
  failedTiles.clear()
  failedIcons.clear()
})
</script>

<template>
  <div class="map-canvas-container">
    <canvas
      ref="canvas"
      class="map-canvas"
      aria-label="Interactive Palworld map"
      @pointerdown="pointerDown"
      @pointermove="pointerMove"
      @pointerup="pointerUp"
      @pointercancel="pointerUp"
      @pointerleave="hoverMarker = null"
      @wheel="wheel"
      @contextmenu="contextMenu"
    />
    <div v-if="!hasVisibleTile" class="map-loading" role="status">
      <i :class="mapLoadFailed ? 'pi pi-exclamation-triangle' : 'pi pi-spin pi-spinner'" />
      <span>{{
        mapLoadFailed ? 'Map tiles are temporarily unavailable' : 'Loading map tiles…'
      }}</span>
    </div>
  </div>
</template>

<style scoped>
.map-canvas-container {
  position: relative;
  width: 100%;
  height: 100%;
}

.map-canvas {
  display: block;
  width: 100%;
  height: 100%;
  touch-action: none;
  cursor: grab;
  background: #101824;
}

.map-loading {
  position: absolute;
  top: 18px;
  left: 50%;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border: 1px solid rgba(125, 211, 252, 0.25);
  border-radius: 999px;
  color: #dbeafe;
  font-size: 0.8rem;
  font-weight: 700;
  background: rgba(5, 9, 20, 0.88);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
  transform: translateX(-50%);
  pointer-events: none;
}

.map-canvas:active {
  cursor: grabbing;
}
</style>
