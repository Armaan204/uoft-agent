import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8001',
      '/auth': {
        target: 'http://localhost:8001',
        bypass(req) {
          if (req.url.startsWith('/auth/reset-password') || req.url.startsWith('/auth/callback')) {
            return req.url
          }
        },
      },
    },
  },
})
