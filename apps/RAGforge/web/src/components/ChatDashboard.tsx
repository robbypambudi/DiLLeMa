import { ArrowLeft, BookOpen } from 'lucide-react'
import logoLight from '../../assets/logo-light.png'
import logoDark from '../../assets/logo-dark.png'
import { useNavigate } from 'react-router-dom'

import { AppState } from '@/App'
import { useAuth } from '@/auth'
import { ChatInput } from '@/components/ChatInput'
import { ChatWindow } from '@/components/ChatWindow'
import { CollectionSelector } from '@/components/CollectionSelector'
import { ThemeToggle } from '@/components/ThemeToggle'
import { Button } from '@/components/ui/Button'

interface ChatDashboardProps {
  onBack: () => void
  appState: AppState
  updateState: (updates: Partial<AppState>) => void
}

export function ChatDashboard({ onBack, appState, updateState }: ChatDashboardProps) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const toggleTheme = () => {
    updateState({ theme: appState.theme === 'light' ? 'dark' : 'light' })
  }

  return (
    <div className="flex h-[100dvh] flex-col bg-background">
      <header className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b bg-surface px-3 py-4 sm:px-6">
        <div className="flex items-center gap-2 sm:gap-4">
          <Button variant="outline" size="sm" onClick={onBack} aria-label="Back to home" className="px-2 sm:px-3">
            <ArrowLeft className="h-4 w-4" />
            <span className="hidden sm:inline">Back</span>
          </Button>
          <div className="flex items-center space-x-3">
            <img
              src={logoLight}
              alt="DiLLeMa"
              className="h-8 dark:hidden"
            />
            <img
              src={logoDark}
              alt="DiLLeMa"
              className="h-8 hidden dark:block"
            />
            <h1 className="text-lg font-semibold tracking-tight sm:text-xl">DiLLeMa</h1>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {user?.role === 'admin' && (
            <Button variant="outline" size="sm" onClick={() => navigate('/admin')}>
              Admin
            </Button>
          )}
          {user ? (
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
          ) : (
            <Button variant="outline" size="sm" onClick={() => navigate('/login')}>
              Sign in
            </Button>
          )}
          <ThemeToggle theme={appState.theme} onToggle={toggleTheme} />
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden md:flex-row">
        <CollectionSelector appState={appState} updateState={updateState} />

        <main className="flex min-h-0 min-w-0 flex-1 flex-col">
          <div className="flex shrink-0 items-center gap-3 border-b bg-surface px-5 py-3 sm:px-8">
            <BookOpen className="h-4 w-4 shrink-0 text-primary" />
            <div className="min-w-0">
              <h2 className="truncate text-sm font-semibold">{appState.selectedCollection?.name || 'Your conversation'}</h2>
              <p className="text-xs text-muted-foreground">{appState.selectedCollection ? 'Ask questions about this collection' : 'Choose a collection to get started'}</p>
            </div>
          </div>
          <ChatWindow appState={appState} />
          <ChatInput appState={appState} updateState={updateState} />
        </main>
      </div>
    </div>
  )
}
