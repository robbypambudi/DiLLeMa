import type { Collection } from '@/features/collections/types'

export interface SourceSnippet {
  page: number | null
  /** The number printed on that page, when it differs from the index. */
  page_label?: string | null
  quote: string
}

/** A cited document, as [S1] in the answer refers to it. */
export interface SourceRef {
  index: number
  file_id: string | null
  file_name: string
  /** Physical page indices; what the viewer scrolls to. */
  pages: number[]
  /** Printed labels aligned with `pages`; what the reader is told. */
  page_labels?: (string | null)[]
  quote: string
  snippets: SourceSnippet[]
}

/** Counts the server reports with a stage; never document text or the question. */
export type StageDetail = Record<string, string | number>

/** One step of the retrieval pipeline, as the answer was being prepared. */
export interface ThinkingStep {
  stage: string
  detail?: StageDetail
  /** When the client saw it, for the elapsed time shown after the answer. */
  at: number
}

export interface Message {
  role: 'user' | 'assistant'
  content: string
  status?: 'pending' | 'completed' | 'failed' | 'interrupted'
  sources?: SourceRef[]
  /** Live only for the turn this tab streamed; reloaded history has none. */
  steps?: ThinkingStep[]
  /** Milliseconds from the question to the first token of the answer. */
  thinkingMs?: number
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
    sources?: SourceRef[]
    status: NonNullable<Message['status']>
  }[]
}
