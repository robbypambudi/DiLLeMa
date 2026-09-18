import { useMemo } from 'react'
import type { MouseEvent } from 'react'
import { citationTarget } from '../lib/citations'
import { sanitizeAnswer } from '../lib/sanitizeAnswer'
import type { SourceRef } from '../types'

interface HtmlRendererProps {
  content: string
  sources?: SourceRef[]
  onCitationClick?: (source: SourceRef) => void
}

export function HtmlRenderer({ content, sources = [], onCitationClick }: HtmlRendererProps) {
  const cleanContent = useMemo(() => sanitizeAnswer(content, sources), [content, sources])

  // The markers are produced by dangerouslySetInnerHTML, so their clicks are
  // caught here rather than bound per element.
  const handleClick = (event: MouseEvent<HTMLDivElement>) => {
    const index = citationTarget(event.target)
    if (index === null) return
    const source = sources.find((item) => item.index === index)
    if (source) onCitationClick?.(source)
  }

  return (
    <div
      onClick={onCitationClick ? handleClick : undefined}
      className="prose prose-sm max-w-none dark:prose-invert [&_p]:my-2 [&_ol]:my-2 [&_ol]:list-decimal [&_ol]:pl-5 [&_ul]:my-2 [&_ul]:list-disc [&_ul]:pl-5 [&_li]:my-1.5 [&_h1]:my-1 [&_h2]:my-1 [&_h3]:my-2 [&_h4]:my-1 [&_h5]:my-1 [&_h6]:my-1"
      dangerouslySetInnerHTML={{ __html: cleanContent }}
    />
  )
}
