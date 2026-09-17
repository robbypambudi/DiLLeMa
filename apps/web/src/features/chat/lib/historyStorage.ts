import type { Conversation, Message } from '../types'

const GUEST_KEY = 'dillema:guest-conversations:v1'
const activeKey = (userId: string | null) => `dillema:active-conversation:${userId ? `user:${userId}` : 'guest'}`

function isMessage(value: unknown): value is Message {
  if (!value || typeof value !== 'object') return false
  const item = value as Partial<Message>
  return ['user', 'assistant'].includes(item.role || '') && typeof item.content === 'string'
    && (item.status === undefined || ['pending', 'completed', 'failed', 'interrupted'].includes(item.status))
}

function isConversation(value: unknown): value is Conversation {
  if (!value || typeof value !== 'object') return false
  const item = value as Partial<Conversation>
  return typeof item.id === 'string' && typeof item.title === 'string'
    && typeof item.collection_name === 'string'
    && (item.collection_id === null || typeof item.collection_id === 'string')
    && typeof item.created_at === 'string' && typeof item.updated_at === 'string'
    && Number.isFinite(Date.parse(item.created_at)) && Number.isFinite(Date.parse(item.updated_at))
    && Array.isArray(item.messages) && item.messages.every(isMessage)
}

export function readGuestHistory(): Conversation[] {
  const raw = localStorage.getItem(GUEST_KEY)
  if (!raw) return []
  let data: unknown
  try { data = JSON.parse(raw) }
  catch { throw new Error('Saved chat history could not be read. Your browser data has been kept.') }
  if (!Array.isArray(data) || !data.every(isConversation)) {
    throw new Error('Saved chat history has an unsupported format. Your browser data has been kept.')
  }
  // A browser reload cannot resume an in-flight guest request.
  return data.map((conversation) => ({
    ...conversation,
    messages: conversation.messages.map((message) => message.status === 'pending'
      ? { ...message, status: 'interrupted' as const } : message),
  })).sort((left, right) => right.updated_at.localeCompare(left.updated_at))
}

export function writeGuestHistory(conversations: Conversation[]) {
  try { localStorage.setItem(GUEST_KEY, JSON.stringify(conversations)) }
  catch { throw new Error('Chat history could not be saved in this browser. Storage may be full or unavailable.') }
}

export function readActiveConversation(userId: string | null): string | null {
  return localStorage.getItem(activeKey(userId))
}

export function writeActiveConversation(userId: string | null, id: string | null) {
  if (id) localStorage.setItem(activeKey(userId), id)
  else localStorage.removeItem(activeKey(userId))
}
