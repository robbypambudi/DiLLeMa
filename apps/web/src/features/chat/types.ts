import type { Collection } from '@/features/collections/types'

export interface Message {
  role: 'user' | 'assistant'
  content: string
}

export interface ChatState {
  selectedCollection: Collection | null
  messages: Message[]
  isLoading: boolean
}
