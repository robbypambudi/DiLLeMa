import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// The repository keeps one .env (DiLLeMa/.env) for the CLI, the API and this
// app. It is read here rather than through `envDir`: Vite watches envDir
// recursively, and the repository root holds .venv and node_modules, which
// exhausts the inotify watch limit.
const repoRoot = path.resolve(__dirname, '../..')

export default defineConfig(({ mode }) => {
  // All keys, for this config only; the client still sees VITE_* alone.
  const env = loadEnv(mode, repoRoot, '')
  // Vite gives process.env priority over .env files when it builds
  // import.meta.env, so exporting here makes the repository file win.
  for (const [key, value] of Object.entries(env)) {
    if (key.startsWith('VITE_') && process.env[key] === undefined) {
      process.env[key] = value
    }
  }
  // BACKEND_URL is the one name to set. Always defined (possibly empty, which
  // means same-origin `/api` through the proxy below), so a stale
  // apps/web/.env can no longer point the browser elsewhere.
  process.env.VITE_BACKEND_URL = env.VITE_BACKEND_URL || env.BACKEND_URL || ''

  return {
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
