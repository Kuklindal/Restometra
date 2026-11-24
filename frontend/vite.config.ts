import tailwindcss from '@tailwindcss/vite'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  server: {
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
  build: {
    rollupOptions: {
      output: { manualChunks: id => id.includes('/node_modules/zrender/') ? 'chart-renderer' : undefined },
    },
  },
  test: { environment: 'jsdom' },
})
