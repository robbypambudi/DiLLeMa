import { useState, type FormEvent } from 'react'
import { Loader2, Send } from 'lucide-react'
import { Button } from '@/shared/components/ui/Button'
import { Input } from '@/shared/components/ui/Input'
import { useChatStream } from '../hooks/useChatStream'

export function ChatInput() {
  const [input, setInput] = useState('')
  const { send, selectedCollection, isLoading } = useChatStream()
  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    if (!input.trim() || !selectedCollection || isLoading) return
    void send(input)
    setInput('')
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
