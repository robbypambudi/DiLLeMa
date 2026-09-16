import { NavLink, Outlet, useNavigate } from 'react-router-dom'

import { useAuth } from '@/auth'
import { Button } from '@/components/ui/Button'

export function AdminLayout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <header className="h-14 border-b px-4 flex items-center justify-between">
        <div className="flex items-center gap-2 font-semibold">
          <img src="/assets/logo-light.png" alt="" className="h-7 dark:hidden" />
          <img src="/assets/logo-dark.png" alt="" className="h-7 hidden dark:block" />
          RAGforge
        </div>
        <div className="flex items-center gap-3 text-sm">
          <span className="text-muted-foreground">{user?.email}</span>
          <Button variant="outline" size="sm" onClick={() => navigate('/')}>Chat</Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              logout()
              navigate('/', { replace: true })
            }}
          >
            Logout
          </Button>
        </div>
      </header>
      <div className="flex flex-1 min-h-0">
        <nav className="w-52 border-r p-3">
          <NavLink
            to="/admin"
            end
            className={({ isActive }) =>
              `block px-3 py-2 text-sm ${isActive ? 'border-l-2 border-primary font-medium' : 'text-muted-foreground'}`
            }
          >
            Collections
          </NavLink>
        </nav>
        <main className="flex-1 p-6 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
