import { apiRequest } from '@/shared/api/client'
import type { AuthUser, LoginResponse } from './types'

export const authApi = {
  me: (signal?: AbortSignal) => apiRequest<AuthUser>('/api/v1/auth/me', { signal }),
  login: (email: string, password: string) => apiRequest<LoginResponse>('/api/v1/auth/login', {
    method: 'POST', body: JSON.stringify({ email, password }),
  }),
}
