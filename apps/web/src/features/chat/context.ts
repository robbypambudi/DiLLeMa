import { createContext } from 'react'
import type { useChatSession } from './hooks/useChatSession'

export type ChatContextValue = ReturnType<typeof useChatSession>

export const ChatContext = createContext<ChatContextValue | null>(null)
