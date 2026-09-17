import type { ReactNode } from 'react'
import { useAuth } from '@/features/auth/hooks/useAuth'
import { ChatContext } from './context'
import { useChatSession } from './hooks/useChatSession'

export function ChatProvider({ children }: { children: ReactNode }) {
  const { user, ready } = useAuth()
  // A login/logout replaces the provider so requests and state never cross owners.
  return <ChatSessionProvider key={ready ? user?.id ?? 'guest' : 'loading'} userId={user?.id ?? null} ready={ready}>{children}</ChatSessionProvider>
}

function ChatSessionProvider({ children, userId, ready }: { children: ReactNode; userId: string | null; ready: boolean }) {
  const value = useChatSession(userId, ready)
  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>
}
