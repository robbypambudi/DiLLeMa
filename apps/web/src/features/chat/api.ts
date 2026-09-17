import { apiFetch, readError } from '@/shared/api/client'
import { readSseStream } from '@/shared/api/sse'

export async function* streamAnswer(collectionId: string, question: string, signal: AbortSignal) {
  const response = await apiFetch('/api/v1/questions/stream', {
    method: 'POST',
    signal,
    body: new URLSearchParams({
      question_id: `user_${collectionId}_${Date.now()}`,
      question_text: question,
      collection_id: collectionId,
      using_augment_query: 'true',
    }),
  })
  if (!response.ok) throw new Error(await readError(response))
  if (!response.body) throw new Error('The server did not return a stream.')
  yield* readSseStream(response.body)
}
