import { createContext } from 'react'
import type { AuthUser } from './types'

export interface AuthContextValue {
  user: AuthUser | null
  ready: boolean
  login: (email: string, password: string) => Promise<AuthUser>
  logout: () => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)
