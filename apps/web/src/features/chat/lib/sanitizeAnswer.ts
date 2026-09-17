import DOMPurify from 'dompurify'
import { formatAnswer } from './formatAnswer'
import { collapseDuplicateSources } from './sources'

export function sanitizeAnswer(content: string): string {
  const formatted = formatAnswer(collapseDuplicateSources(content))

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
            'div',
            'span',
          ],
          ALLOWED_ATTR: ['type', 'class'],
        })
      : formatted

}
