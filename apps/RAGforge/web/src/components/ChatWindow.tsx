import { useEffect, useRef } from 'react'
import { AppState } from '@/App'
import { cn } from '@/lib/utils'
import { HtmlRenderer } from './HtmlRenderer'
import { Button } from './ui/Button'

import { Copy, FileDown } from 'lucide-react'

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
      <div className="flex-1 relative">
        <div className="absolute inset-0 bg-background/50 backdrop-blur-sm flex items-center justify-center">
          <div className="text-center p-8 bg-background rounded-lg border shadow-lg">
            <h2 className="text-2xl font-semibold mb-2">Welcome!</h2>
            <p className="text-muted-foreground">Please select a collection to begin</p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-4">
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
              "inline-block rounded-lg px-4 py-2",
              message.role === 'user'
                ? 'bg-primary text-primary-foreground'
                : 'bg-muted text-muted-foreground'
            )}
          >
            {message.role === 'assistant' ? (
              <HtmlRenderer content={message.content} />
            ) : (
              <div className="whitespace-pre-wrap">{message.content}</div>
            )}
          </div>
          
          {message.role === 'assistant' && (
            <div className="flex gap-1 mt-1 opacity-0 group-hover:opacity-100 transition-opacity">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => copyToClipboard(message.content)}
                className="h-6 px-2 text-xs"
              >
                <Copy size={16} strokeWidth={2} />
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={downloadChatHtml}
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
          <div className="bg-muted text-muted-foreground rounded-lg px-4 py-2">
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
  )
}
