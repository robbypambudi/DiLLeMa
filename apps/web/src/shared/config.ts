// Empty means same-origin: requests go to `/api` on whatever host served the
// page, and the Vite dev server (or a reverse proxy) forwards them to the API.
// A fixed host such as localhost would send a remote viewer's browser to their
// own machine. Set VITE_BACKEND_URL only when the API lives on another origin.
export const BACKEND_URL = (import.meta.env.VITE_BACKEND_URL || '').replace(/\/+$/, '')
