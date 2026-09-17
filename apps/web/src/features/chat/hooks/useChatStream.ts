import { useEffect, useRef } from 'react'
import { errorMessage } from '@/shared/lib/errors'
import { streamAnswer } from '../api'
import { useChat } from './useChat'
import type { Message } from '../types'

const MAX_RESPONSE_CHARS = 4000

export function useChatStream() {
  const { state, updateState } = useChat()
  const request = useRef<AbortController | null>(null)

  useEffect(() => () => {
    request.current?.abort()
    request.current = null
    updateState({ isLoading: false })
  }, [updateState])

  const send = async (question: string) => {
    if (!question.trim() || !state.selectedCollection || state.isLoading || request.current) return
    const controller = new AbortController()
    request.current = controller
    const history: Message[] = [...state.messages, { role: 'user', content: question }]
    const setAnswer = (content: string, isLoading: boolean) => {
      if (request.current !== controller) return
      updateState({ messages: [...history, { role: 'assistant', content }], isLoading })
    }
    setAnswer('', true)
    let answer = ''
    try {
      for await (const delta of streamAnswer(state.selectedCollection.id, question, controller.signal)) {
        // The backend already converts model snapshots to deltas. Repeated tokens
        // are valid text and must not be deduplicated a second time here.
        answer += delta
        setAnswer(answer, true)
        if (answer.length >= MAX_RESPONSE_CHARS) break
      }
      setAnswer(answer || 'No response received.', false)
    } catch (error) {
      if (!controller.signal.aborted) setAnswer(errorMessage(error), false)
    } finally {
      controller.abort()
      if (request.current === controller) request.current = null
    }
  }

  return { send, isLoading: state.isLoading, selectedCollection: state.selectedCollection }
}
