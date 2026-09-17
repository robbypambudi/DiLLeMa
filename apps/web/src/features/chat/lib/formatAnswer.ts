/** Clean glued/repeating LLM lists into one numbered HTML list. */

const MAX_ITEMS = 8

function applyInline(text: string): string {
  return text.replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
}

function stripTags(text: string): string {
  return text.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
}

function splitFooter(text: string): [string, string] {
  const match = text.search(/(?:<p>\s*)?(?:<b>)?Sumber konteks\s*:/i)
  if (match === -1) return [text, '']
  return [text.slice(0, match), text.slice(match)]
}

function normalizeItem(text: string): string {
  return stripTags(text)
    .replace(/\*\*/g, '')
    .replace(/^\d+\.\s*/, '')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase()
}

function itemTitle(text: string): string {
  return normalizeItem(text).split(':')[0].slice(0, 80).trim()
}

function tokenSet(text: string): Set<string> {
  return new Set(normalizeItem(text).split(' ').filter((word) => word.length > 2))
}

function isNearDuplicate(left: string, right: string): boolean {
  const titleLeft = itemTitle(left)
  const titleRight = itemTitle(right)
  if (titleLeft && titleLeft === titleRight) return true
  const a = tokenSet(left)
  const b = tokenSet(right)
  if (!a.size || !b.size) return false
  let overlap = 0
  for (const word of a) {
    if (b.has(word)) overlap += 1
  }
  const union = a.size + b.size - overlap
  return union > 0 && overlap / union >= 0.72
}

function uniqueItems(items: string[]): string[] {
  const kept: string[] = []
  for (const item of items) {
    const clean = item.replace(/^\d+\.\s*/, '').trim()
    if (!clean || /^\d+$/.test(clean)) continue
    if (kept.some((existing) => isNearDuplicate(existing, clean))) continue
    kept.push(clean)
    if (kept.length >= MAX_ITEMS) break
  }
  return kept
}

function collectItems(body: string): { lead: string; items: string[] } {
  const items: string[] = []
  let work = body.replace(/<li\b[^>]*>([\s\S]*?)<\/li>/gi, (_match, inner: string) => {
    const text = stripTags(inner)
    if (text && !/^\d+$/.test(text)) items.push(text)
    return '\n'
  })
  work = work.replace(/<\/?(?:ol|ul|p|div|br|h[1-6])[^>]*>/gi, '\n')
  work = work.replace(/(?=\d+\.\s+\*\*)/g, '\n')
  work = work.replace(/(?<=[:.])(?=\d+\.\s)/g, '\n')

  const lines = work
    .split('\n')
    .map((line) => stripTags(line) || line.trim())
    .map((line) => line.trim())
    .filter(Boolean)

  const leadParts: string[] = []
  let seenList = items.length > 0
  for (const line of lines) {
    if (/^\d+$/.test(line)) continue
    const numbered = line.match(/^\d+\.\s+(.*)$/)
    if (numbered?.[1]?.trim()) {
      seenList = true
      items.push(numbered[1].trim())
      continue
    }
    if (!seenList) leadParts.push(line)
  }
  return { lead: leadParts.join(' ').trim(), items }
}

export function formatAnswer(content: string): string {
  if (!content) return ''
  const withoutFences = content.replace(/```(?:html)?/g, '')
  const withoutThink = (withoutFences.split('</think>').pop() || '').trim()
  const [body, footer] = splitFooter(withoutThink)
  const { lead, items } = collectItems(body)
  const unique = uniqueItems(items)

  const parts: string[] = []
  if (lead) parts.push(`<p>${applyInline(lead)}</p>`)
  if (unique.length) {
    parts.push(`<ol>${unique.map((item) => `<li>${applyInline(item)}</li>`).join('')}</ol>`)
  } else if (!lead && body.trim()) {
    parts.push(
      /<(?:p|div|ul|ol|li|br|h[1-6])\b/i.test(body)
        ? applyInline(body.trim())
        : `<p>${applyInline(body.trim())}</p>`
    )
  }

  if (!footer.trim()) return parts.join('')
  const footerHtml = /<(?:p|ul|ol|li)\b/i.test(footer)
    ? applyInline(footer.trim())
    : `<p>${applyInline(footer.trim())}</p>`
  return parts.join('') + footerHtml
}
