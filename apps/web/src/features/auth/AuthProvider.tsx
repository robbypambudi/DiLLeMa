import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { getToken, SESSION_EXPIRED_EVENT } from '@/shared/api/session'
import { authApi } from './api'
import { AuthContext } from './context'
import { clearSession, getStoredUser, setSession } from './session'
import type { AuthUser } from './types'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(getStoredUser)
  const [ready, setReady] = useState(false)
  const logout = useCallback(() => {
    clearSession()
    setUser(null)
  }, [])

  useEffect(() => {
    window.addEventListener(SESSION_EXPIRED_EVENT, logout)
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, logout)
  }, [logout])

  useEffect(() => {
    const token = getToken()
    if (!token) {
      logout()
      setReady(true)
      return
    }
    const controller = new AbortController()
    authApi.me(controller.signal)
      .then((me) => {
        if (controller.signal.aborted || getToken() !== token) return
        setUser(me)
        setSession(token, me)
      })
      .catch(() => {
        if (!controller.signal.aborted && getToken() === token) logout()
      })
      .finally(() => {
        if (!controller.signal.aborted) setReady(true)
      })
    return () => controller.abort()
  }, [logout])

  const login = useCallback(async (email: string, password: string) => {
    const data = await authApi.login(email, password)
    setSession(data.access_token, data.user)
    setUser(data.user)
    return data.user
  }, [])

  const value = useMemo(() => ({ user, ready, login, logout }), [user, ready, login, logout])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
