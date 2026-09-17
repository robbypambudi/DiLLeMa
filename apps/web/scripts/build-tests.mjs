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
      },
      output: { entryFileNames: '[name].mjs' },
    },
  },
})
