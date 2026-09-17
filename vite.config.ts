import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

const helperTarget = 'http://127.0.0.1:8765'
const helperRoutes = [
  '/health',
  '/state',
  '/progress',
  '/set',
  '/clear',
  '/ocr-select',
  '/ocr-state',
  '/map-tile',
  '/map-icon',
]

export default defineConfig({
  plugins: [
    vue(),
    VitePWA({
      registerType: 'autoUpdate',
      manifest: {
        name: 'Palworld Checklist',
        short_name: 'PalChecklist',
        description: 'Checklist, interactive map, and local tools for Palworld',
        theme_color: '#07111f',
        background_color: '#050914',
        display: 'standalone',
        start_url: '/',
      },
      workbox: {
        cleanupOutdatedCaches: true,
        navigateFallback: '/index.html',
        globPatterns: ['**/*.{js,css,html,json,svg,png,webp,woff2}'],
        runtimeCaching: [
          {
            urlPattern: ({ url }) => url.pathname === '/data.json',
            handler: 'NetworkFirst',
            options: {
              cacheName: 'palworld-data',
              expiration: { maxEntries: 3, maxAgeSeconds: 86400 },
            },
          },
          {
            urlPattern: ({ url }) => url.pathname === '/map-tile' || url.pathname === '/map-icon',
            handler: 'CacheFirst',
            options: {
              cacheName: 'palworld-map-assets',
              expiration: { maxEntries: 500, maxAgeSeconds: 604800 },
            },
          },
        ],
      },
    }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: Object.fromEntries(helperRoutes.map((route) => [route, helperTarget])),
  },
  build: {
    target: 'es2022',
    sourcemap: true,
    chunkSizeWarningLimit: 750,
  },
})
