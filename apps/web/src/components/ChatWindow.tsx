import { useEffect, useRef } from 'react'
import { AppState } from '@/App'
import { cn } from '@/lib/utils'
import { HtmlRenderer } from './HtmlRenderer'
import { Button } from './ui/Button'

import { BookOpen, Copy, FileDown, MessageSquare } from 'lucide-react'

interface ChatWindowProps {
  appState: AppState
}

export function ChatWindow({ appState }: ChatWindowProps) {
  const { messages, isLoading, selectedCollection } = appState
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const copyToClipboard = (content: string) => {
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(cleanBrokenHtml(content))
    } else {
      const textArea = document.createElement('textarea')
      textArea.value = cleanBrokenHtml(content)
      document.body.appendChild(textArea)
      textArea.select()
      document.execCommand('copy')
      document.body.removeChild(textArea)
    }
  }

  const cleanBrokenHtml = (htmlString: string) => {
    if (!htmlString || typeof htmlString !== 'string') {
      return ''
    }

    let cleanedText = htmlString
      .replace(/[\r\n]+/g, '')
      .replace(/```html/g, '')
      .replace(/```/g, '')

    return (cleanedText.split('</think>').pop() || '').trim();
  }

  const downloadChatHtml = () => {
    const chatHtml = `
<!DOCTYPE html>
<html>
<head>
  <title>Chat Export</title>
  <style>
    body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
    .message { margin: 15px 0; display: flex; }
    .user { justify-content: flex-end; }
    .assistant { justify-content: flex-start; }
    .bubble { display: inline-block; padding: 15px; border-radius: 8px; max-width: 70%; }
    .user .bubble { background: #e3f2fd; }
    .assistant .bubble { background: #f5f5f5; }
    .role { font-weight: bold; margin-bottom: 8px; }
  </style>
</head>
<body>
  <h1>Chat Export - ${new Date().toLocaleDateString()}</h1>
${messages.map(msg => `
  <div class="message ${msg.role}">
    <div class="bubble">
      <div class="role">${msg.role === 'user' ? 'You' : 'Assistant'}:</div>
      <div>${msg.role === 'assistant' ? cleanBrokenHtml(msg.content) : msg.content.replace(/\n/g, '<br>')}</div>
    </div>
  </div>
`).join('')}
</body>
</html>`

    const blob = new Blob([chatHtml], { type: 'text/html' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `chat-${new Date().toISOString().split('T')[0]}.html`
    a.click()
    URL.revokeObjectURL(url)
  }

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  if (!selectedCollection) {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center overflow-y-auto p-5 sm:p-8">
        <div className="my-auto max-w-md text-center">
          <span className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-2xl border border-primary/20 bg-surface text-primary shadow-sm"><MessageSquare className="h-7 w-7" /></span>
          <p className="mb-2 text-xs font-semibold uppercase tracking-widest text-primary">A conversation with your documents</p>
          <h2 className="mb-3 text-2xl font-semibold tracking-tight sm:text-3xl">What would you like to explore?</h2>
          <p className="text-sm leading-relaxed text-muted-foreground">Select a collection, then ask a question. Your conversation starts with the knowledge in your documents.</p>
          <div className="mt-6 inline-flex items-center gap-2 rounded-lg border bg-surface px-4 py-2.5 text-xs text-muted-foreground"><BookOpen className="h-4 w-4 text-primary" /> Choose a collection to begin</div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-4 py-6 sm:px-8" role="log" aria-label="Conversation" aria-live="polite">
      <div className="mx-auto max-w-4xl space-y-6">
        {messages.map((message, index) => (
          <div
            key={index}
            className={cn(
              "flex flex-col group",
              message.role === 'user' ? 'items-end' : 'items-start'
            )}
          >
            <div
              className={cn(
                "min-w-0 max-w-[95%] break-words rounded-2xl border px-4 py-3 text-sm leading-relaxed shadow-sm sm:max-w-[85%] sm:px-5",
                message.role === 'user'
                  ? 'rounded-tr-sm border-primary bg-primary text-primary-foreground'
                  : 'rounded-tl-sm border-border bg-surface text-foreground'
              )}
            >
              <div className={cn('mb-2 text-xs font-semibold', message.role === 'user' ? 'text-primary-foreground/80' : 'text-primary')}>{message.role === 'user' ? 'You' : 'DiLLeMa'}</div>
              {message.role === 'assistant' ? (
                <HtmlRenderer content={message.content} />
              ) : (
                <div className="whitespace-pre-wrap">{message.content}</div>
              )}
            </div>

            {message.role === 'assistant' && (
              <div className="mt-2 flex gap-1">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => copyToClipboard(message.content)}
                  aria-label="Copy answer"
                  title="Copy answer"
                  className="h-6 px-2 text-xs"
                >
                  <Copy size={16} strokeWidth={2} />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={downloadChatHtml}
                  aria-label="Export conversation"
                  title="Export conversation"
                  className="h-6 px-2 text-xs"
                >
                  <FileDown size={16} strokeWidth={2} />
                </Button>
              </div>
            )}
          </div>
        ))}

        {isLoading && (
          <div className="flex justify-start">
            <div role="status" className="rounded-2xl border bg-surface px-5 py-4 text-sm text-muted-foreground shadow-sm">
              <div className="flex items-center space-x-2">
                <div className="flex space-x-1">
                  <div className="w-2 h-2 bg-current rounded-full animate-bounce"></div>
                  <div className="w-2 h-2 bg-current rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></div>
                  <div className="w-2 h-2 bg-current rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                </div>
                <span>Assistant is typing...</span>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>
    </div>
  )
}
