import { createContext, useContext, useEffect, useMemo, useState, ReactNode } from 'react'

import { apiFetch, AuthUser, clearSession, getStoredUser, getToken, setSession } from '@/api'

type AuthContextValue = {
  user: AuthUser | null
  ready: boolean
  login: (email: string, password: string) => Promise<AuthUser>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(getStoredUser())
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const token = getToken()
    if (!token) {
      setReady(true)
      return
    }
    apiFetch('/api/v1/auth/me')
      .then(async (response) => {
        if (!response.ok) {
          clearSession()
          setUser(null)
          return
        }
        const me = await response.json()
        setUser(me)
        setSession(token, me)
      })
      .catch(() => {
        clearSession()
        setUser(null)
      })
      .finally(() => setReady(true))
  }, [])

  const value = useMemo<AuthContextValue>(() => ({
    user,
    ready,
    login: async (email: string, password: string) => {
      const response = await apiFetch('/api/v1/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      })
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        throw new Error(body?.detail || 'Email or password is wrong.')
      }
      const data = await response.json()
      setSession(data.access_token, data.user)
      setUser(data.user)
      return data.user as AuthUser
    },
    logout: () => {
      clearSession()
      setUser(null)
    },
  }), [user, ready])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return context
}
