import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8001',
      '/auth/google': 'http://localhost:8001',
      '/auth/me': 'http://localhost:8001',
      '/auth/logout': 'http://localhost:8001',
    },
  },
})
