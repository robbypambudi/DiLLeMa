import type { Collection } from '@/features/collections/types'

export interface Message {
  role: 'user' | 'assistant'
  content: string
  status?: 'pending' | 'completed' | 'failed' | 'interrupted'
}

export interface ChatState {
  selectedCollection: Collection | null
  messages: Message[]
  isLoading: boolean
  isRestoring: boolean
  conversationId: string | null
}

export interface ConversationSummary {
  id: string
  title: string
  collection_id: string | null
  collection_name: string
  created_at: string
  updated_at: string
}

export interface Conversation extends ConversationSummary {
  messages: Message[]
}

export interface ConversationResponse extends ConversationSummary {
  turns: {
    id: string
    question_id: string
    sequence: number
    question_text: string
    answer: string
    status: NonNullable<Message['status']>
  }[]
}
