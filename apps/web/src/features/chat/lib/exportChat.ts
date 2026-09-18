import type { Message, SourceRef } from '../types'
import { sanitizeAnswer } from './sanitizeAnswer'
import { renderSourceFooter } from './sources'

function escapeHtml(text: string) {
  return text.replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]!))
}

// An export is read on its own, so the cited files are written back in as a
// list: there is no source panel to open from a saved file or a pasted answer.
const prepareHtml = (content: string, sources: SourceRef[] = []) =>
  sanitizeAnswer(content, sources) + renderSourceFooter(sources)

export const copyToClipboard = (content: string, sources: SourceRef[] = []) => {
    const html = prepareHtml(content, sources)
    const text = html
      .replace(/<\/p>/gi, '\n\n')
      .replace(/<li>/gi, '\n- ')
      .replace(/<br\s*\/?>/gi, '\n')
      .replace(/<[^>]+>/g, '')
      .replace(/\n{3,}/g, '\n\n')
      .trim()
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text)
    } else {
      const textArea = document.createElement('textarea')
      textArea.value = text
      document.body.appendChild(textArea)
      textArea.select()
      document.execCommand('copy')
      document.body.removeChild(textArea)
    }
  }

export const downloadChatHtml = (messages: Message[]) => {
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
      <div>${msg.role === 'assistant' ? prepareHtml(msg.content, msg.sources) : escapeHtml(msg.content).replace(/\n/g, '<br>')}</div>
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

