export interface AuthUser {
  id: string
  email: string
  role: string
}

export interface LoginResponse {
  access_token: string
  user: AuthUser
}
