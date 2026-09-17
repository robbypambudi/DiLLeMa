import { apiFetch, apiRequest, readError } from '@/shared/api/client'
import { readSseStream } from '@/shared/api/sse'
import type { ApiResponse } from '@/shared/api/types'
import type { ConversationResponse, ConversationSummary } from './types'

export async function* streamAnswer(collectionId: string, question: string, signal: AbortSignal, conversationId?: string) {
  const body = new URLSearchParams({
    question_id: `user_${Date.now()}_${Math.random().toString(36).slice(2)}`,
    question_text: question,
    collection_id: collectionId,
    using_augment_query: 'true',
  })
  if (conversationId) body.set('conversation_id', conversationId)
  const response = await apiFetch('/api/v1/questions/stream', {
    method: 'POST',
    signal,
    body,
  })
  if (!response.ok) throw new Error(await readError(response))
  if (!response.body) throw new Error('The server did not return a stream.')
  yield* readSseStream(response.body)
}

export const conversationsApi = {
  list: (offset = 0, signal?: AbortSignal) => apiRequest<{ data: ConversationSummary[]; total: number }>(`/api/v1/conversations?offset=${offset}&limit=50`, { signal }),
  create: (collectionId: string, signal?: AbortSignal) => apiRequest<ApiResponse<ConversationResponse>>('/api/v1/conversations', {
    method: 'POST', body: JSON.stringify({ collection_id: collectionId }), signal,
  }),
  get: (id: string, signal?: AbortSignal) => apiRequest<ApiResponse<ConversationResponse>>(`/api/v1/conversations/${encodeURIComponent(id)}`, { signal }),
  remove: (id: string) => apiRequest<ApiResponse<null>>(`/api/v1/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' }),
}
