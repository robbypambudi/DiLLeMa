import { ArrowLeft } from 'lucide-react'
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
    <div className="h-screen flex flex-col bg-background">
      <header className="border-b p-4 flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <Button variant="outline" size="sm" onClick={onBack}>
            <ArrowLeft className="w-4 h-4 mr-2" />
            Back
          </Button>
          <div className="flex items-center space-x-3">
            <img
              src="/assets/logo-light.png"
              alt="DiLLeMa"
              className="h-8 dark:hidden"
            />
            <img
              src="/assets/logo-dark.png"
              alt="DiLLeMa"
              className="h-8 hidden dark:block"
            />
            <h1 className="text-2xl font-semibold">DiLLeMa</h1>
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

      <div className="flex-1 flex overflow-hidden">
        <CollectionSelector appState={appState} updateState={updateState} />

        <div className="flex-1 flex flex-col">
          <ChatWindow appState={appState} />
          <ChatInput appState={appState} updateState={updateState} />
        </div>
      </div>
    </div>
  )
}
