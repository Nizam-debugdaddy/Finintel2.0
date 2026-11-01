import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { nodePolyfills } from 'vite-plugin-node-polyfills'

export default defineConfig({
  plugins: [react(), nodePolyfills()],
  base: '/',

  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 6000,
    // No manualChunks — let Vite decide. Avoids React/MUI load-order errors.
    // Plotly is external (loaded from CDN in index.html).
    rollupOptions: {
      external: ['plotly.js', 'plotly.js-dist-min'],
      output: {
        globals: {
          'plotly.js':          'Plotly',
          'plotly.js-dist-min': 'Plotly',
        },
      },
    },
  },

  server: {
    port: 3000,
    proxy: {
      '/company':         { target: 'http://localhost:8000', changeOrigin: true },
      '/financial-input': { target: 'http://localhost:8000', changeOrigin: true },
      '/calculate':       { target: 'http://localhost:8000', changeOrigin: true },
      '/dashboard':       { target: 'http://localhost:8000', changeOrigin: true },
      '/export':          { target: 'http://localhost:8000', changeOrigin: true },
      '/query':           { target: 'http://localhost:8000', changeOrigin: true },
      '/version':         { target: 'http://localhost:8000', changeOrigin: true },
      '/notes':           { target: 'http://localhost:8000', changeOrigin: true },
      '/health':          { target: 'http://localhost:8000', changeOrigin: true },
      '/peer':            { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})
