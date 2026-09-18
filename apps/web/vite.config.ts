import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// The repository keeps one .env (DiLLeMa/.env) for the CLI, the API and this
// app; there is no apps/web/.env.
const repoRoot = path.resolve(__dirname, '../..')

export default defineConfig(({ mode }) => {
  // All keys, for this config only; the client still sees VITE_* alone.
  const env = loadEnv(mode, repoRoot, '')
  // BACKEND_URL is the one name to set. Vite reads VITE_* from process.env
  // after this runs, so exporting it here reaches import.meta.env. Empty
  // means same-origin `/api` through the proxy below.
  if (!env.VITE_BACKEND_URL) {
    process.env.VITE_BACKEND_URL = env.BACKEND_URL || ''
  }

  return {
    envDir: repoRoot,
    plugins: [react()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      host: '0.0.0.0',
      port: 3000,
      proxy: {
        '/api': {
          // `dillema dashboard` points this at the API port it started.
          target: env.DILLEMA_API_PROXY_TARGET || 'http://localhost:8080',
          changeOrigin: true,
          timeout: 0,
          proxyTimeout: 0,
        },
      },
    },
  }
})
