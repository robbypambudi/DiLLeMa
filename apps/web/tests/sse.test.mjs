import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createSseParser, readSseStream } from '../.test-build/sse.mjs'

test('SSE preserves multiline content with CRLF split at every possible boundary', () => {
  const input = ': ping\r\n\r\nevent: message\r\ndata: first\r\ndata: second\r\n\r\ndata: third\r\n\r\n'
  for (let boundary = 0; boundary <= input.length; boundary++) {
    const parse = createSseParser()
    const events = [...parse(input.slice(0, boundary)), ...parse(input.slice(boundary)), ...parse('', true)]
    assert.deepEqual(events, [
      { event: 'message', data: 'first\nsecond' },
      { event: 'message', data: 'third' },
    ], `boundary ${boundary}`)
  }
})

test('SSE ignores comments and preserves empty and repeated data events', () => {
  const parse = createSseParser()
  assert.deepEqual(parse(':ping\n\ndata:\n\ndata: ha\n\ndata: ha\n\ndata: last', true), [
    { event: 'message', data: '' },
    { event: 'message', data: 'ha' },
    { event: 'message', data: 'ha' },
    { event: 'message', data: 'last' },
  ])
})

test('a named event carries its name and does not leak into the next event', () => {
  const parse = createSseParser()
  const input = 'data: answer\n\nevent: sources\ndata: [{"index":1}]\n\ndata: more\n\n'
  for (let boundary = 0; boundary <= input.length; boundary++) {
    const split = createSseParser()
    const events = [...split(input.slice(0, boundary)), ...split(input.slice(boundary)), ...split('', true)]
    assert.deepEqual(events, [
      { event: 'message', data: 'answer' },
      { event: 'sources', data: '[{"index":1}]' },
      { event: 'message', data: 'more' },
    ], `boundary ${boundary}`)
  }
  // An event name with no data is dropped, and does not name the next event.
  assert.deepEqual(parse('event: sources\n\ndata: plain\n\n'), [{ event: 'message', data: 'plain' }])
})

test('stream decoder handles UTF-8 split between individual bytes and releases its reader', async () => {
  const bytes = new TextEncoder().encode('data: Halo 🌏\r\ndata: café\r\n\r\n')
  const body = new ReadableStream({
    start(controller) {
      for (const byte of bytes) controller.enqueue(new Uint8Array([byte]))
      controller.close()
    },
  })
  const result = []
  for await (const event of readSseStream(body)) result.push(event)
  assert.deepEqual(result, [{ event: 'message', data: 'Halo 🌏\ncafé' }])
  assert.equal(body.locked, false)
})

test('stopping consumption cancels the response and releases the reader', async () => {
  let cancelled = false
  const body = new ReadableStream({
    start(controller) { controller.enqueue(new TextEncoder().encode('data: first\n\n')) },
    cancel() { cancelled = true },
  })
  for await (const event of readSseStream(body)) {
    assert.deepEqual(event, { event: 'message', data: 'first' })
    break
  }
  assert.equal(cancelled, true)
  assert.equal(body.locked, false)
})
