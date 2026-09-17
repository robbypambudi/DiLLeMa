// Transport only owns the token; user state belongs to the auth feature.
const TOKEN_KEY = 'access_token'
export const SESSION_EXPIRED_EVENT = 'dillema:session-expired'

export function getToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string) {
  sessionStorage.setItem(TOKEN_KEY, token)
}

export function clearToken() {
  sessionStorage.removeItem(TOKEN_KEY)
}
