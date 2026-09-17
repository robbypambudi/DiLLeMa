import assert from 'node:assert/strict'
import { beforeEach, test } from 'node:test'
import { conversationCollection, conversationTitle, fromResponse } from '../.test-build/history.mjs'
import { readActiveConversation, readGuestHistory, writeActiveConversation, writeGuestHistory } from '../.test-build/historyStorage.mjs'

let storage
beforeEach(() => {
  storage = new Map()
  globalThis.localStorage = {
    getItem: (key) => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, value),
    removeItem: (key) => storage.delete(key),
  }
})

const conversation = (overrides = {}) => ({
  id: 'guest-1', title: 'A saved conversation', collection_id: 'collection-1', collection_name: 'Documents',
  created_at: '2026-09-18T10:00:00Z', updated_at: '2026-09-18T10:00:00Z',
  messages: [{ role: 'user', content: 'A question' }, { role: 'assistant', content: 'An answer', status: 'completed' }],
  ...overrides,
})

test('guest history survives reload and sorts newest first', () => {
  writeGuestHistory([conversation(), conversation({ id: 'guest-2', updated_at: '2026-09-18T11:00:00Z' })])
  const restored = readGuestHistory()
  assert.deepEqual(restored.map((item) => item.id), ['guest-2', 'guest-1'])
  assert.deepEqual(restored[1].messages, conversation().messages)
  restored[1].messages[0].content = 'Changed in memory'
  assert.equal(readGuestHistory()[1].messages[0].content, 'A question')
})

test('reload retains interrupted guest answers and makes the chat usable again', () => {
  writeGuestHistory([conversation({ messages: [{ role: 'user', content: 'Question' }, { role: 'assistant', content: 'Partial', status: 'pending' }] })])
  assert.deepEqual(readGuestHistory()[0].messages[1], { role: 'assistant', content: 'Partial', status: 'interrupted' })
})

test('deleting one guest chat preserves the remaining conversation', () => {
  writeGuestHistory([conversation(), conversation({ id: 'guest-2' })])
  writeGuestHistory(readGuestHistory().filter((item) => item.id !== 'guest-1'))
  assert.deepEqual(readGuestHistory().map((item) => item.id), ['guest-2'])
})

test('unreadable and invalid stored data is reported without overwriting it', () => {
  for (const raw of ['{broken', '{"messages": []}', '[{"id": "incomplete"}]']) {
    storage.set('dillema:guest-conversations:v1', raw)
    assert.throws(() => readGuestHistory(), /has been kept/)
    assert.equal(storage.get('dillema:guest-conversations:v1'), raw)
  }
})

test('storage quota errors are surfaced instead of claiming history was saved', () => {
  globalThis.localStorage.setItem = () => { throw new Error('QuotaExceededError') }
  assert.throws(() => writeGuestHistory([conversation()]), /could not be saved/)
})

test('active conversations are isolated between guest and different accounts', () => {
  writeActiveConversation(null, 'guest-chat')
  writeActiveConversation('user-1', 'private-1')
  writeActiveConversation('user-2', 'private-2')
  assert.equal(readActiveConversation(null), 'guest-chat')
  assert.equal(readActiveConversation('user-1'), 'private-1')
  assert.equal(readActiveConversation('user-2'), 'private-2')
  writeActiveConversation('user-1', null)
  assert.equal(readActiveConversation('user-1'), null)
  assert.equal(readActiveConversation('user-2'), 'private-2')
  assert.equal(readActiveConversation(null), 'guest-chat')
})

test('API turns restore question/answer order including failures and partial answers', () => {
  const { messages: _, ...summary } = conversation()
  const restored = fromResponse({ ...summary, turns: [
    { question_text: 'First', answer: '<p>First answer</p>', status: 'completed' },
    { question_text: 'Second', answer: 'Partial answer', status: 'interrupted' },
  ] })
  assert.deepEqual(restored.messages, [
    { role: 'user', content: 'First' },
    { role: 'assistant', content: '<p>First answer</p>', status: 'completed' },
    { role: 'user', content: 'Second' },
    { role: 'assistant', content: 'Partial answer', status: 'interrupted' },
  ])
  assert.equal(conversationCollection(restored).id, 'collection-1')
  assert.equal(conversationCollection({ ...restored, collection_id: null }), null)
})

test('conversation titles normalize whitespace and remain short', () => {
  assert.equal(conversationTitle('  A\n question\t here  '), 'A question here')
  assert.equal(conversationTitle('x'.repeat(150)).length, 120)
  assert.equal(conversationTitle('  '), 'New chat')
})
