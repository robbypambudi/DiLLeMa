import { useEffect, useState } from 'react'
import { BrowserRouter, Navigate, Outlet, Route, Routes, useOutletContext } from 'react-router-dom'

import { AuthProvider, useAuth } from '@/auth'
import { ChatDashboard } from '@/components/ChatDashboard'
import { WelcomePage } from '@/components/WelcomePage'
import { ForbiddenPage } from '@/pages/ForbiddenPage'
import { LoginPage } from '@/pages/LoginPage'
import { AdminLayout } from '@/pages/admin/AdminLayout'
import { CollectionDetailPage } from '@/pages/admin/CollectionDetailPage'
import { CollectionNewPage } from '@/pages/admin/CollectionNewPage'
import { CollectionsPage } from '@/pages/admin/CollectionsPage'

export interface Collection {
  id: string
  name: string
  description: string
}

export interface Message {
  role: 'user' | 'assistant'
  content: string
}

export interface AppState {
  theme: 'light' | 'dark'
  collections: Collection[]
  selectedCollection: Collection | null
  messages: Message[]
  isLoading: boolean
}

const welcomeMessage: Message = {
  role: 'assistant',
  content: 'Welcome. Select a collection and ask a question.',
}

function RequireAuth() {
  const { user, ready } = useAuth()
  if (!ready) {
    return <div className="min-h-screen bg-background p-6 text-sm text-muted-foreground">Loading…</div>
  }
  if (!user) {
    return <Navigate to="/login" replace />
  }
  return <Outlet />
}

function RequireAdmin() {
  const { user } = useAuth()
  if (user?.role !== 'admin') {
    return <ForbiddenPage />
  }
  return <Outlet />
}

type PublicOutlet = {
  appState: AppState
  updateState: (updates: Partial<AppState>) => void
}

function PublicLayout() {
  const [appState, setAppState] = useState<AppState>({
    theme: 'light',
    collections: [],
    selectedCollection: null,
    messages: [welcomeMessage],
    isLoading: false,
  })

  useEffect(() => {
    if (appState.theme === 'dark') {
      document.documentElement.classList.add('dark')
    } else {
      document.documentElement.classList.remove('dark')
    }
  }, [appState.theme])

  const updateState = (updates: Partial<AppState>) => {
    setAppState((prev) => ({ ...prev, ...updates }))
  }

  return <Outlet context={{ appState, updateState } satisfies PublicOutlet} />
}

function WelcomeRoute() {
  const { appState, updateState } = useOutletContext<PublicOutlet>()
  return <WelcomePage appState={appState} updateState={updateState} />
}

function ChatRoute() {
  const { appState, updateState } = useOutletContext<PublicOutlet>()
  return <ChatDashboard appState={appState} updateState={updateState} />
}

function AppRoutes() {
  return (
    <Routes>
      <Route element={<PublicLayout />}>
        <Route path="/" element={<WelcomeRoute />} />
        <Route path="/chat" element={<ChatRoute />} />
      </Route>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<RequireAdmin />}>
          <Route path="/admin" element={<AdminLayout />}>
            <Route index element={<CollectionsPage />} />
            <Route path="collections/new" element={<CollectionNewPage />} />
            <Route path="collections/:id" element={<CollectionDetailPage />} />
          </Route>
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  )
}

export default App
