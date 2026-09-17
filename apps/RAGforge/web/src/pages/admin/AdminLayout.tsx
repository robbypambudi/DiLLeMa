import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { BookOpen, MessageSquare } from 'lucide-react'
import logoLight from '../../../assets/logo-light.png'
import logoDark from '../../../assets/logo-dark.png'

import { useAuth } from '@/auth'
import { Button } from '@/components/ui/Button'

export function AdminLayout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <header className="flex min-h-[73px] flex-wrap items-center justify-between gap-3 border-b bg-surface px-4 py-4 sm:px-6">
        <div className="flex items-center gap-2 font-semibold">
          <img src={logoLight} alt="" className="h-7 dark:hidden" />
          <img src={logoDark} alt="" className="h-7 hidden dark:block" />
          <span className="tracking-tight">DiLLeMa</span>
          <span className="ml-2 rounded-md border bg-secondary px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Admin</span>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <span className="hidden text-muted-foreground lg:inline">{user?.email}</span>
          <Button variant="outline" size="sm" onClick={() => navigate('/chat')}><MessageSquare className="h-4 w-4" /> Chat</Button>
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
      <div className="flex min-h-0 flex-1 flex-col md:flex-row">
        <nav className="shrink-0 border-b bg-surface p-4 md:w-56 md:border-b-0 md:border-r md:p-5" aria-label="Administration">
          <p className="mb-4 hidden px-3 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground md:block">Workspace</p>
          <NavLink
            to="/admin"
            className={({ isActive }) =>
              `flex items-center gap-2.5 rounded-lg border px-3 py-3 text-sm transition-colors ${isActive ? 'border-primary/30 bg-primary/10 font-semibold text-primary' : 'border-transparent text-muted-foreground hover:bg-secondary'}`
            }
          >
            <BookOpen className="h-4 w-4" /> Collections
          </NavLink>
        </nav>
        <main className="min-w-0 flex-1 p-4 sm:p-6 lg:p-10">
          <div className="mx-auto max-w-6xl"><Outlet /></div>
        </main>
      </div>
    </div>
  )
}
