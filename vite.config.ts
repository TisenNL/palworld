import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

const helperTarget = 'http://127.0.0.1:8765'
const helperRoutes = [
  '/health',
  '/state',
  '/progress',
  '/set',
  '/clear',
  '/ocr-select',
  '/ocr-state',
  '/game-marker',
  '/player-position',
  '/mouse-loop',
  '/map-tile',
  '/map-icon',
]

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: Object.fromEntries(
      helperRoutes.map((route) => [
        route,
        {
          target: helperTarget,
          configure: (proxy) => {
            proxy.on('error', () => undefined)
          },
        },
      ]),
    ),
  },
  build: {
    target: 'es2022',
    sourcemap: true,
    chunkSizeWarningLimit: 750,
  },
})
