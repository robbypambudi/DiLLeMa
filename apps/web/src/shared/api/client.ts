import { BACKEND_URL } from '@/shared/config'
import { clearToken, getToken, SESSION_EXPIRED_EVENT } from './session'

export async function apiFetch(path: string, options: RequestInit = {}): Promise<Response> {
  const token = getToken()
  const headers = new Headers(options.headers)
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  const isForm = options.body instanceof FormData || options.body instanceof URLSearchParams
  if (options.body && !isForm && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  const response = await fetch(`${BACKEND_URL}${path}`, { ...options, headers })
  if (response.status === 401 && !path.includes('/auth/login')) {
    // An old request must not invalidate a newer login.
    if (getToken() === token) {
      clearToken()
      window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT))
    }
    throw new Error('Unauthorized')
  }
  return response
}

export async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json()
    if (typeof body.detail === 'string') return body.detail
    if (Array.isArray(body.detail)) return body.detail.map((item: { msg?: string }) => item.msg || '').join(' ')
    if (body.message) return body.message
    if (Array.isArray(body.errors)) {
      return body.errors.map((item: { message?: string }) => item.message || '').join(' ')
    }
  } catch {
    /* ignore */
  }
  return `Request failed (${response.status})`
}

/** JSON endpoints share status/error handling; streaming uses apiFetch directly. */
export async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await apiFetch(path, options)
  if (!response.ok) throw new Error(await readError(response))
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}
