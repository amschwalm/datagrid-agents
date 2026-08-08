import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    // Cursor / cloud preview URLs use *.cursorvm.com / *.cvm.dev hosts
    allowedHosts: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        // Multi-pass extraction streams for several minutes
        timeout: 0,
        proxyTimeout: 0,
      },
    },
  },
})
