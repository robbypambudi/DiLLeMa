import { clearToken, setToken } from '@/shared/api/session'
import type { AuthUser } from './types'

const USER_KEY = 'auth_user'

export function getStoredUser(): AuthUser | null {
  try {
    const raw = sessionStorage.getItem(USER_KEY)
    if (!raw) return null
    const user: unknown = JSON.parse(raw)
    if (typeof user !== 'object' || user === null) return null
    if ('id' in user && typeof user.id === 'string' && 'email' in user && typeof user.email === 'string' && 'role' in user && typeof user.role === 'string') {
      return user as AuthUser
    }
  } catch { /* Ignore malformed cached sessions. */ }
  return null
}

export function setSession(token: string, user: AuthUser) {
  setToken(token)
  sessionStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function clearSession() {
  clearToken()
  sessionStorage.removeItem(USER_KEY)
}
