import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // In dev, forward API calls to FastAPI. In production FastAPI serves this build directly.
    proxy: { '/api': 'http://localhost:8000' },
  },
})
