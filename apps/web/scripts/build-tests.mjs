import { build } from 'vite'
import { fileURLToPath } from 'node:url'

// Compile real TypeScript modules before starting Node's isolated test workers.
const root = fileURLToPath(new URL('../', import.meta.url))
await build({
  configFile: false,
  root,
  logLevel: 'error',
  resolve: { alias: { '@': `${root}src` } },
  build: {
    outDir: '.test-build',
    emptyOutDir: true,
    minify: false,
    ssr: true,
    rollupOptions: {
      input: {
        client: `${root}src/shared/api/client.ts`,
        sse: `${root}src/shared/api/sse.ts`,
        history: `${root}src/features/chat/lib/history.ts`,
        citations: `${root}src/features/chat/lib/citations.ts`,
        sources: `${root}src/features/chat/lib/sources.ts`,
        historyStorage: `${root}src/features/chat/lib/historyStorage.ts`,
      },
      output: { entryFileNames: '[name].mjs' },
    },
  },
})
