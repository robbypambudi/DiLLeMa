/** Collapse repeated RAG citations so one PDF is listed once. */

import type { SourceRef } from '../types'

/**
 * How a page is named in text.
 *
 * A document with front matter prints "iii" on its third page, so citing the
 * physical index sends the reader to the wrong page of the copy in their hands.
 * The index stays in `pages` for the viewer to scroll to.
 */
export function pageLabelFor(source: SourceRef, page: number): string {
  const position = source.pages.indexOf(page)
  const label = position === -1 ? null : source.page_labels?.[position]
  return String(label ?? page)
}

/** "halaman iii, iv", or an empty string for sources without page numbers. */
export function formatPages(source: SourceRef): string {
  if (!source.pages.length) return ''
  return `halaman ${source.pages.map((page) => pageLabelFor(source, page)).join(', ')}`
}

const FOOTER = /(?:<p>\s*)?(?:<b>\s*)?Sumber konteks\s*:/i

/**
 * Remove the rendered "Sumber konteks" list from an answer.
 *
 * Answers stored before the chat listed its sources separately still carry one,
 * and showing both repeats every file.
 */
export function dropSourceFooter(content: string): string {
  const start = content.search(FOOTER)
  return start === -1 ? content : content.slice(0, start).trimEnd()
}

/** Rebuild that list for exports, which have no panel to click through to. */
export function renderSourceFooter(sources: SourceRef[]): string {
  if (!sources.length) return ''
  const escape = (text: string) =>
    text.replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]!))
  const rows = sources.map((source) => {
    const pages = source.pages.length ? `, ${formatPages(source)}` : ''
    const quote = source.quote ? ` — ${escape(source.quote)}` : ''
    return `<li>${escape(`[S${source.index}] ${source.file_name}${pages}`)}${quote}</li>`
  })
  return `<p><b>Sumber konteks:</b></p><ul>${rows.join('')}</ul>`
}

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
