import { createContext } from 'react'
import type { ChatState } from './types'

export interface ChatContextValue {
  state: ChatState
  updateState: (updates: Partial<ChatState>) => void
}

export const ChatContext = createContext<ChatContextValue | null>(null)
