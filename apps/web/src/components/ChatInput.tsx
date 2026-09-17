import { useState } from 'react'
import { Loader2, Send } from 'lucide-react'

import { apiFetch } from '@/api'
import { AppState } from '@/App'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'

interface ChatInputProps {
  appState: AppState
  updateState: (updates: Partial<AppState>) => void
}

export function ChatInput({ appState, updateState }: ChatInputProps) {
  const [input, setInput] = useState('')
  const { selectedCollection, isLoading } = appState

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim() || !selectedCollection || isLoading) return

    const userMessage = { role: 'user' as const, content: input }
    updateState({
      messages: [...appState.messages, userMessage],
      isLoading: true,
    })
    setInput('')

    try {
      const response = await apiFetch('/api/v1/questions/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
          question_id: `user_${selectedCollection.id}_${Date.now()}`,
          question_text: input,
          collection_id: selectedCollection.id,
          using_augment_query: 'true',
        }),
      })

      if (!response.ok) throw new Error('Failed to get response')

      const reader = response.body?.getReader()
      let fullResponse = ''

      if (reader) {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          const text = new TextDecoder().decode(value)
          const lines = text.split('\n')

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              fullResponse += line.slice(6)
            }
          }
        }
      }

      updateState({
        messages: [...appState.messages, userMessage, { role: 'assistant', content: fullResponse || 'No response received.' }],
        isLoading: false,
      })
    } catch {
      updateState({
        messages: [...appState.messages, userMessage, { role: 'assistant', content: 'Could not reach the server.' }],
        isLoading: false,
      })
    }
  }

  return (
    <div className="shrink-0 border-t bg-surface px-4 py-4 sm:px-8 sm:py-5">
      <form onSubmit={handleSubmit} className="mx-auto max-w-4xl">
        <label htmlFor="chat-question" className="field-label mb-2">Your question</label>
        <div className="flex gap-2 sm:gap-3">
          <Input
            id="chat-question"
            aria-describedby="chat-input-hint"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={selectedCollection ? 'Ask something…' : 'Please select a collection first'}
            disabled={!selectedCollection || isLoading}
            className="h-12 min-w-0 flex-1"
          />
          <Button
            type="submit"
            disabled={!input.trim() || !selectedCollection || isLoading}
            size="default"
            className="h-12 px-4"
            aria-label="Send question"
          >
            {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            <span className="hidden sm:inline">Send</span>
          </Button>
        </div>
        <p id="chat-input-hint" className="mt-2 text-xs text-muted-foreground">{selectedCollection ? 'Press Enter to send. Check important details against your documents.' : 'Select a collection to enable the chat.'}</p>
      </form>
    </div>
  )
}
