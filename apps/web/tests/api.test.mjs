import assert from 'node:assert/strict'
import { afterEach, test } from 'node:test'
import { apiFetch, apiRequest, readError } from '../.test-build/client.mjs'
const originalFetch = globalThis.fetch
const originalWindow = globalThis.window
const originalStorage = globalThis.sessionStorage
afterEach(() => {
  globalThis.fetch = originalFetch
  globalThis.window = originalWindow
  globalThis.sessionStorage = originalStorage
})

function setup(token = 'test-token') {
  const values = new Map([['access_token', token]])
  globalThis.sessionStorage = { getItem: (key) => values.get(key) ?? null, removeItem: (key) => values.delete(key) }
  globalThis.window = new EventTarget()
  return values
}

test('HTTP client attaches bearer auth and JSON content type', async () => {
  setup()
  globalThis.fetch = async (_url, options) => {
    assert.equal(options.headers.get('Authorization'), 'Bearer test-token')
    assert.equal(options.headers.get('Content-Type'), 'application/json')
    return Response.json({ data: { id: 'collection' } })
  }
  assert.deepEqual(await apiRequest('/api/v1/collection', { method: 'POST', body: '{}' }), { data: { id: 'collection' } })
})

test('HTTP client leaves multipart and URL-encoded content types to fetch', async () => {
  setup()
  globalThis.fetch = async (_url, options) => {
    assert.equal(options.headers.has('Content-Type'), false)
    return new Response(null, { status: 204 })
  }
  for (const body of [new FormData(), new URLSearchParams({ question_text: 'hello' })]) {
    assert.equal(await apiRequest('/upload', { method: 'POST', body }), undefined)
  }
})

test('expired sessions notify the auth provider, but failed login does not clear a session', async () => {
  const storage = setup()
  let expired = 0
  window.addEventListener('dillema:session-expired', () => { expired++ })
  globalThis.fetch = async () => Response.json({ detail: 'Unauthorized' }, { status: 401 })
  assert.equal((await apiFetch('/api/v1/auth/login')).status, 401)
  assert.equal(storage.get('access_token'), 'test-token')
  await assert.rejects(apiRequest('/api/v1/auth/me'), /Unauthorized/)
  assert.equal(storage.has('access_token'), false)
  assert.equal(expired, 1)
})

test('HTTP errors support both FastAPI validation response shapes and non-JSON failures', async () => {
  for (const [body, expected] of [
    [{ detail: 'Forbidden' }, 'Forbidden'],
    [{ detail: [{ msg: 'Missing field' }] }, 'Missing field'],
    [{ errors: [{ field: 'name', message: 'Required' }] }, 'Required'],
  ]) assert.equal(await readError(Response.json(body, { status: 422 })), expected)
  assert.equal(await readError(new Response('Bad gateway', { status: 502 })), 'Request failed (502)')
})

test('a delayed unauthorized response does not invalidate a newer login', async () => {
  const storage = setup()
  globalThis.fetch = async () => {
    storage.set('access_token', 'new-token')
    return new Response(null, { status: 401 })
  }
  await assert.rejects(apiRequest('/api/v1/auth/me'), /Unauthorized/)
  assert.equal(storage.get('access_token'), 'new-token')
})
