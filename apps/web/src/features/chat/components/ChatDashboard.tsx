import { Suspense, lazy, useCallback, useEffect, useState } from 'react'
import { ArrowLeft, BookOpen } from 'lucide-react'
import logoLight from '../../../../assets/logo-light.png'
import logoDark from '../../../../assets/logo-dark.png'
import { useNavigate } from 'react-router-dom'

import { useChat } from '../hooks/useChat'
import { useTheme } from '@/shared/hooks/useTheme'
import { useAuth } from '@/features/auth/hooks/useAuth'
import { ChatInput } from '@/features/chat/components/ChatInput'
import { ChatWindow } from '@/features/chat/components/ChatWindow'
import { ChatHistory } from './ChatHistory'
import { CollectionSelector } from '@/features/collections/components/CollectionSelector'
import { ThemeToggle } from '@/shared/components/ThemeToggle'
import { Button } from '@/shared/components/ui/Button'
import type { SourceRef } from '../types'

// pdf.js is large and only a citation click needs it.
const SourcePanel = lazy(() =>
  import('@/features/sources/components/SourcePanel').then((module) => ({ default: module.SourcePanel }))
)

export function ChatDashboard() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const { state: appState, newChat } = useChat()
  const { theme, toggleTheme } = useTheme()
  const [activeSource, setActiveSource] = useState<{ messageIndex: number; source: SourceRef } | null>(null)

  const openSource = useCallback(
    (source: SourceRef, messageIndex: number) => setActiveSource({ messageIndex, source }),
    []
  )
  const closeSource = useCallback(() => setActiveSource(null), [])
  // Switching conversations retires whatever document the old one had open.
  useEffect(() => { setActiveSource(null) }, [appState.conversationId])
  useEffect(() => {
    if (!activeSource) return
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === 'Escape') closeSource() }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [activeSource, closeSource])

  return (
    <div className="flex h-[100dvh] flex-col bg-background">
      <header className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b bg-surface px-3 py-4 sm:px-6">
        <div className="flex items-center gap-2 sm:gap-4">
          <Button variant="outline" size="sm" onClick={() => navigate('/')} aria-label="Back to home" className="px-2 sm:px-3">
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
          <ThemeToggle theme={theme} onToggle={toggleTheme} />
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden md:flex-row">
        <CollectionSelector selectedCollection={appState.selectedCollection} disabled={appState.isLoading || appState.isRestoring} onSelect={newChat}>
          <ChatHistory />
        </CollectionSelector>

        <main className="flex min-h-0 min-w-0 flex-1 flex-col">
          <div className="flex shrink-0 items-center gap-3 border-b bg-surface px-5 py-3 sm:px-8">
            <BookOpen className="h-4 w-4 shrink-0 text-primary" />
            <div className="min-w-0">
              <h2 className="truncate text-sm font-semibold">{appState.selectedCollection?.collection_name || 'Your conversation'}</h2>
              <p className="text-xs text-muted-foreground">{appState.selectedCollection ? 'Ask questions about this collection' : 'Choose a collection to get started'}</p>
            </div>
          </div>
          {appState.isRestoring ? <p role="status" className="flex-1 p-6 text-sm text-muted-foreground">Opening conversation…</p> : <ChatWindow onOpenSource={openSource} activeSource={activeSource} />}
          {appState.conversationId && !appState.selectedCollection && <p className="border-t px-5 py-3 text-sm text-muted-foreground">This collection is no longer available. You can still read or export this conversation.</p>}
          <ChatInput />
        </main>

        {activeSource && (
          <Suspense fallback={<aside className="fixed inset-0 z-50 flex items-center justify-center bg-background p-6 text-sm text-muted-foreground md:static md:z-auto md:w-[26rem] md:shrink-0 md:border-l lg:w-[34rem]">Menyiapkan penampil dokumen…</aside>}>
            <SourcePanel source={activeSource.source} onClose={closeSource} />
          </Suspense>
        )}
      </div>
    </div>
  )
}
