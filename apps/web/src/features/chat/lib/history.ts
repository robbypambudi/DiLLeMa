import type { Collection } from '@/features/collections/types'
import type { Conversation, ConversationResponse } from '../types'

export function fromResponse(response: ConversationResponse): Conversation {
  const { turns, ...summary } = response
  return {
    ...summary,
    messages: turns.flatMap((turn) => [
      { role: 'user' as const, content: turn.question_text },
      { role: 'assistant' as const, content: turn.answer, status: turn.status, sources: turn.sources ?? [] },
    ]),
  }
}

export function conversationCollection(conversation: Conversation): Collection | null {
  if (!conversation.collection_id) return null
  return {
    id: conversation.collection_id,
    collection_name: conversation.collection_name,
    description: '', vectordb_collection_name: '', file_count: 0,
  }
}

export function conversationTitle(question: string): string {
  return question.trim().replace(/\s+/g, ' ').slice(0, 120) || 'New chat'
}
