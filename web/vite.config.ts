import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// Memory-light config. Dev + preview both bind to all interfaces on port 3000
// so the app is reachable on the team's public surface.
// If a real backend is running on a private loopback port, set VITE_API_PROXY
// (e.g. http://127.0.0.1:8000) to proxy /api there.

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiProxy = env.VITE_API_PROXY || ''
  const proxy = apiProxy
    ? { '/api': { target: apiProxy, changeOrigin: true } }
    : undefined

  return {
    plugins: [react()],
    server: { host: '0.0.0.0', port: 3000, proxy },
    preview: { host: '0.0.0.0', port: 3000, proxy },
  }
})
