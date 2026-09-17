import { useCallback, useMemo, useState, type ReactNode } from 'react'
import { ChatContext } from './context'
import type { ChatState } from './types'

export function ChatProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<ChatState>({
    selectedCollection: null,
    messages: [{ role: 'assistant', content: 'Welcome. Select a collection and ask a question.' }],
    isLoading: false,
  })
  const updateState = useCallback((updates: Partial<ChatState>) => {
    setState((previous) => ({ ...previous, ...updates }))
  }, [])
  const value = useMemo(() => ({ state, updateState }), [state, updateState])
  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>
}
