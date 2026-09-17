/** Collapse repeated RAG citations so one PDF is listed once. */

function fileKey(label: string): string {
  return label
    .replace(/\[S\d+\]\s*/i, '')
    .replace(/,?\s*halaman\s+[\d,\s]+/i, '')
    .replace(/\s+—[\s\S]*$/, '')
    .trim()
    .toLowerCase()
}

const FILE_CITE = /\[S\d+\]\s+[^\n<[]+?\.(?:pdf|docx?|txt|pptx?|xlsx?)\b/gi

export function collapseDuplicateSources(content: string): string {
  if (!content) return content

  const seen = new Set<string>()
  let index = 0

  const relabel = (raw: string): string => {
    const key = fileKey(raw)
    if (!key) return raw.trim()
    if (seen.has(key)) return ''
    seen.add(key)
    index += 1
    const rest = raw.replace(/\[S\d+\]\s*/i, '').trim()
    return `[S${index}] ${rest}`
  }

  const next = content
    .split(/(<li\b[^>]*>[\s\S]*?<\/li>)/gi)
    .map((part) => {
      const listItem = part.match(/^<li\b[^>]*>\s*([\s\S]*?)\s*<\/li>$/i)
      if (listItem) {
        const text = listItem[1].replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
        if (!/\[S\d+\]/i.test(text)) return part
        const label = relabel(text)
        return label ? `<li>${label}</li>` : ''
      }
      return part.replace(FILE_CITE, (cite) => relabel(cite.trim()))
    })
    .join('')

  let heading = 0
  return next
    .replace(
      /(?:<p>\s*)?(?:<b>)?Sumber konteks:?\s*(?:<\/b>)?(?:\s*<\/p>)?/gi,
      (block) => {
        heading += 1
        return heading === 1 ? block : ''
      }
    )
    .replace(/<li>\s*<\/li>/gi, '')
    .replace(/<ul>\s*<\/ul>/gi, '')
    .replace(/\n{3,}/g, '\n\n')
}
