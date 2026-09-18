export interface SseEvent {
  /** The event name, defaulting to "message" as the SSE spec requires. */
  event: string
  data: string
}

/** Decode SSE events across arbitrary network boundaries, including split CRLF. */
export function createSseParser() {
  let pending = ''
  let data: string[] = []
  let name = ''
  let skipLf = false

  return (chunk: string, flush = false): SseEvent[] => {
    const events: SseEvent[] = []
    const emit = () => {
      if (data.length) events.push({ event: name || 'message', data: data.join('\n') })
      data = []
      name = ''
    }
    const field = (line: string): [string, string] => {
      const colon = line.indexOf(':')
      if (colon === -1) return [line, '']
      return [line.slice(0, colon), line.slice(colon + 1).replace(/^ /, '')]
    }
    const line = () => {
      if (pending === '') emit()
      else if (!pending.startsWith(':')) {
        const [key, value] = field(pending)
        if (key === 'data') data.push(value)
        else if (key === 'event') name = value
      }
      pending = ''
    }

    for (const character of chunk) {
      if (skipLf) {
        skipLf = false
        if (character === '\n') continue
      }
      if (character === '\r' || character === '\n') {
        line()
        skipLf = character === '\r'
      } else pending += character
    }
    if (flush) {
      if (pending) line()
      emit()
    }
    return events
  }
}

export async function* readSseStream(body: ReadableStream<Uint8Array>): AsyncGenerator<SseEvent> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  const parse = createSseParser()
  let finished = false
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) {
        finished = true
        yield* parse(decoder.decode(), true)
        return
      }
      yield* parse(decoder.decode(value, { stream: true }))
    }
  } finally {
    try {
      if (!finished) await reader.cancel()
    } finally {
      reader.releaseLock()
    }
  }
}
