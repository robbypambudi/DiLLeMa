import { BACKEND_URL } from '@/config'

const TOKEN_KEY = 'access_token'
const USER_KEY = 'auth_user'

export type AuthUser = {
  id: string
  email: string
  role: 'admin' | 'user' | string
}

export function getToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY)
}

export function getStoredUser(): AuthUser | null {
  const raw = sessionStorage.getItem(USER_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as AuthUser
  } catch {
    return null
  }
}

export function setSession(token: string, user: AuthUser) {
  sessionStorage.setItem(TOKEN_KEY, token)
  sessionStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function clearSession() {
  sessionStorage.removeItem(TOKEN_KEY)
  sessionStorage.removeItem(USER_KEY)
}

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
    clearSession()
    if (window.location.pathname.startsWith('/admin')) {
      window.location.assign('/login')
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
