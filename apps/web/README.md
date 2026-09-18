# DiLLeMa frontend

React 18, TypeScript, Vite and Tailwind power the dashboard.

```bash
npm ci
npm run dev
```

The development server runs on port 3000. Configure `VITE_BACKEND_URL` in
`.env`; the default API URL is `http://localhost:8080`.

```bash
npm run check       # lint + regression tests + production build
npm run typecheck
npm run build
npm run preview
```

Use Node.js 18 or newer.

Feature modules in `src/features` own auth, chat, collections, files and
knowledge. `src/app` composes routes and layouts; `src/shared` contains common
UI, HTTP transport and utilities. Hooks own requests and state so UI components
remain focused on rendering and user interaction.

Chat and collection browsing are public. Administrative routes require a signed-in
admin. Authentication uses session storage. Signed-in chat history is saved to
the user's account in PostgreSQL; guest history is saved in this browser's local
storage. The chat sidebar supports new chats, reopening history and deletion,
and restores the active conversation after refresh. Guest chats stay separate
from account history. Theme state is shared for the current page session.

Before running the updated backend, apply the chat history migration from `apps`:
`uv run alembic upgrade head`. Previously unsaved conversations cannot
be recovered.

Read the [development guide](../../docs/DASHBOARD_DEVELOPMENT.md) before adding
features or changing module boundaries. Existing endpoint URLs and response
contracts are preserved.
