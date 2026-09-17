/** Decode SSE events across arbitrary network boundaries, including split CRLF. */
export function createSseParser() {
  let pending = ''
  let data: string[] = []
  let skipLf = false

  return (chunk: string, flush = false): string[] => {
    const events: string[] = []
    const emit = () => {
      if (data.length) events.push(data.join('\n'))
      data = []
    }
    const line = () => {
      if (pending === '') emit()
      else if (pending === 'data') data.push('')
      else if (pending.startsWith('data:')) data.push(pending.slice(5).replace(/^ /, ''))
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

export async function* readSseStream(body: ReadableStream<Uint8Array>): AsyncGenerator<string> {
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
