import DOMPurify from 'dompurify'
import type { SourceRef } from '../types'
import { linkCitations } from './citations'
import { formatAnswer } from './formatAnswer'
import { collapseDuplicateSources, dropSourceFooter } from './sources'

export function sanitizeAnswer(content: string, sources: SourceRef[] = []): string {
  const cited = new Set(sources.map((source) => source.index))
  const body = sources.length ? dropSourceFooter(content) : content
  const formatted = linkCitations(formatAnswer(collapseDuplicateSources(body)), cited)

  return typeof window !== 'undefined'
      ? DOMPurify.sanitize(formatted, {
          ALLOWED_TAGS: [
            'p',
            'br',
            'b',
            'strong',
            'i',
            'em',
            'u',
            'ol',
            'ul',
            'li',
            'h1',
            'h2',
            'h3',
            'h4',
            'h5',
            'h6',
            'code',
            'pre',
            'blockquote',
            'hr',
            'table',
            'thead',
            'tbody',
            'tr',
            'th',
            'td',
            'div',
            'span',
            'button',
          ],
          ALLOWED_ATTR: ['type', 'class', 'title', 'data-citation'],
        })
      : formatted

}
