import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Dev server on http://localhost:5173. The app calls the backend directly at
// http://localhost:8000 (see src/api.ts); the backend allows this origin via CORS.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
  },
})
