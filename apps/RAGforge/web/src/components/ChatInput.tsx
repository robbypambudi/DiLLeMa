import { useState } from 'react'
import { Send } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { AppState } from '@/App'

import { BACKEND_URL } from '@/config'

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
      isLoading: true 
    })
    setInput('')

    try {
      const response = await fetch(`${BACKEND_URL}/api/v1/questions/stream`, {
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
        isLoading: false 
      })
    } catch (error) {
      updateState({ 
        messages: [...appState.messages, userMessage, { role: 'assistant', content: '❌ Could not reach the server.' }],
        isLoading: false 
      })
    }
  }

  return (
    <div className="border-t bg-background p-4">
      <form onSubmit={handleSubmit} className="flex space-x-2">
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={selectedCollection ? "💭 Ask something..." : "Please select a collection first"}
          disabled={!selectedCollection || isLoading}
          className="flex-1 shadow-md"
        />
        <Button 
          type="submit" 
          disabled={!input.trim() || !selectedCollection || isLoading}
          size="default"
          className="shadow-md"
        >
          <Send className="w-5 h-5" />
        </Button>
      </form>
    </div>
  )
}
