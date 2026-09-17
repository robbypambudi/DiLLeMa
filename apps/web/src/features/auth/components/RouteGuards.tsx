import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { ForbiddenPage } from '../pages/ForbiddenPage'

export function RequireAuth() {
  const { user, ready } = useAuth()
  if (!ready) return <div className="min-h-screen bg-background p-6 text-sm text-muted-foreground">Loading…</div>
  return user ? <Outlet /> : <Navigate to="/login" replace />
}

export function RequireAdmin() {
  const { user } = useAuth()
  return user?.role === 'admin' ? <Outlet /> : <ForbiddenPage />
}
