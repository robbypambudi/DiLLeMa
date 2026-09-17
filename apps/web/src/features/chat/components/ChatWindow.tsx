import { useEffect, useRef } from 'react'
import { useChat } from '../hooks/useChat'
import { cn } from '@/shared/lib/utils'
import { copyToClipboard, downloadChatHtml } from '../lib/exportChat'
import { HtmlRenderer } from './HtmlRenderer'
import { Button } from '@/shared/components/ui/Button'

import { BookOpen, Copy, FileDown, MessageSquare } from 'lucide-react'

export function ChatWindow() {
  const { state: { messages, isLoading, selectedCollection } } = useChat()
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  if (!selectedCollection && messages.length === 0) {
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
                message.content ? (
                  <div>
                    <HtmlRenderer content={message.content} />
                    {(isLoading || message.status === 'pending') && index === messages.length - 1 && (
                      <span className="ml-0.5 inline-block h-4 w-1 translate-y-0.5 animate-pulse bg-current" aria-hidden />
                    )}
                  </div>
                ) : message.status === 'interrupted' || message.status === 'failed' ? (
                  <p className="text-muted-foreground">{message.status === 'failed' ? 'The answer could not be generated.' : 'The answer was interrupted.'}</p>
                ) : (
                  <div role="status" className="flex items-center space-x-2 text-muted-foreground">
                    <div className="flex space-x-1">
                      <div className="h-2 w-2 animate-bounce rounded-full bg-current" />
                      <div className="h-2 w-2 animate-bounce rounded-full bg-current" style={{ animationDelay: '0.1s' }} />
                      <div className="h-2 w-2 animate-bounce rounded-full bg-current" style={{ animationDelay: '0.2s' }} />
                    </div>
                    <span>Assistant is typing...</span>
                  </div>
                )
              ) : (
                <div className="whitespace-pre-wrap">{message.content}</div>
              )}
            </div>

            {message.role === 'assistant' && message.content && (message.status === 'interrupted' || message.status === 'failed') && (
              <p className="mt-1 text-xs text-muted-foreground">{message.status === 'interrupted' ? 'Generation was interrupted. This is a partial answer.' : 'Generation failed. You can send the question again.'}</p>
            )}

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
                  onClick={() => downloadChatHtml(messages)}
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

        <div ref={messagesEndRef} />
      </div>
    </div>
  )
}
