/** Render an LLM answer (Markdown, or HTML from older answers) as HTML. */

import { Marked } from 'marked'

const MAX_ITEMS = 8

// LLMs write Markdown natively, so it is parsed with a real parser rather than
// pattern-matched; single newlines become <br> because models rarely leave the
// blank line CommonMark needs between lines.
const markdown = new Marked({ gfm: true, breaks: true, async: false })

function stripTags(text: string): string {
  return text.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
}

function splitFooter(text: string): [string, string] {
  const match = text.search(/(?:<p>\s*)?(?:<b>)?Sumber konteks\s*:/i)
  if (match === -1) return [text, '']
  return [text.slice(0, match), text.slice(match)]
}

const LIST_LINE = /^[ \t]*(?:[-*+]|\d+\.)[ \t]+\S/

/** A list needs a blank line after a paragraph, but not between its items. */
function separateLists(text: string): string {
  const lines = text.split('\n')
  return lines
    .map((line, i) =>
      i > 0 && LIST_LINE.test(line) && lines[i - 1].trim() && !LIST_LINE.test(lines[i - 1])
        ? `\n${line}`
        : line
    )
    .join('\n')
}

/** Repair list layouts small models produce before the parser sees them. */
function normalizeMarkdown(text: string): string {
  return separateLists(
    text
      // Items glued onto one line: "...:1. **A** ...2. **B**".
      .replace(/(?<=\S)[ \t]*(?=\d+\.\s+\*\*)/g, '\n')
      .replace(/(?<=[:.])(?=\d+\.\s)/g, '\n')
      // Per-item source lines repeat what the source panel already lists.
      .replace(/^[ \t]*[-*+][ \t]+\*{0,2}Sumber\*{0,2}\s*:.*(?:\n|$)/gim, '')
  )
}

function normalizeItem(text: string): string {
  return stripTags(text).replace(/\s+/g, ' ').trim().toLowerCase()
}

function tokenSet(text: string): Set<string> {
  return new Set(normalizeItem(text).split(' ').filter((word) => word.length > 2))
}

// Items are compared by their words, not by the bold label before ":", since
// small models reuse one label for items with different facts.
function isNearDuplicate(left: string, right: string): boolean {
  const a = tokenSet(left)
  const b = tokenSet(right)
  if (!a.size || !b.size) return false
  // A different number or code is a different fact, however similar the wording.
  const hasDigit = (word: string) => /\d/.test(word)
  const numbers = (set: Set<string>) => [...set].filter(hasDigit).sort().join(' ')
  if (numbers(a) !== numbers(b)) return false
  let overlap = 0
  for (const word of a) {
    if (b.has(word)) overlap += 1
  }
  const union = a.size + b.size - overlap
  return union > 0 && overlap / union >= 0.72
}

/** Drop repeated list items (a common small-model loop) and cap list length. */
function dedupeListItems(html: string): string {
  return html.replace(/<(ol|ul)>([\s\S]*?)<\/\1>/g, (whole, tag: string, inner: string) => {
    // Nested lists are left alone; flat item matching would split them apart.
    if (/<(?:ol|ul)\b/.test(inner)) return whole
    const kept: string[] = []
    for (const [, item] of inner.matchAll(/<li>([\s\S]*?)<\/li>/g)) {
      if (!stripTags(item)) continue
      if (kept.some((existing) => isNearDuplicate(existing, item))) continue
      kept.push(item)
      if (kept.length >= MAX_ITEMS) break
    }
    return `<${tag}>${kept.map((item) => `<li>${item}</li>`).join('')}</${tag}>`
  })
}

export function formatAnswer(content: string): string {
  if (!content) return ''
  const withoutFences = content.replace(/```(?:html|markdown|md)?/g, '')
  const withoutThink = (withoutFences.split('</think>').pop() || '').trim()
  const [body, footer] = splitFooter(withoutThink)

  const html = body.trim()
    ? dedupeListItems(markdown.parse(normalizeMarkdown(body.trim())) as string)
    : ''

  if (!footer.trim()) return html
  const footerHtml = /<(?:p|ul|ol|li)\b/i.test(footer)
    ? footer.trim()
    : (markdown.parse(footer.trim()) as string)
  return html + footerHtml
}
