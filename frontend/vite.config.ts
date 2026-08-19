import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['icon-192.png', 'icon-512.png', 'apple-touch-icon.png'],
      manifest: {
        name: 'Run Analizer',
        short_name: 'Run',
        description: 'Race-date-driven AI running coach built on Garmin data',
        theme_color: '#000000',
        background_color: '#000000',
        display: 'standalone',
        orientation: 'portrait',
        start_url: '/',
        icons: [
          { src: '/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icon-512.png', sizes: '512x512', type: 'image/png' },
          {
            src: '/icon-512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable',
          },
        ],
      },
      workbox: {
        // The API is never precached. A cached training plan that silently disagrees
        // with the server is worse than an offline message.
        navigateFallbackDenylist: [/^\/api/, /^\/admin/],
      },
      // Off in development on purpose. A service worker caching assets while you
      // are editing them produces stale-bundle bugs that look like your change
      // simply did nothing. Verify the real worker against `npm run preview`.
      devOptions: { enabled: false },
    }),
  ],
  server: {
    host: '0.0.0.0',
    port: 5173,
    // Same-origin in development, so cookies work without CORS credentials games.
    proxy: {
      '/api': { target: process.env.VITE_PROXY_TARGET ?? 'http://backend:8000', changeOrigin: true },
    },
    watch: {
      // Vite's native watcher misses newly created files under a bind mount, and the
      // symptom is a new component that simply never appears. This cost run-project
      // several restarts before it was diagnosed.
      usePolling: true,
    },
  },
})
