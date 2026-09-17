import { sanitizeAnswer } from '../lib/sanitizeAnswer'

interface HtmlRendererProps {
  content: string
}

export function HtmlRenderer({ content }: HtmlRendererProps) {
  const cleanContent = sanitizeAnswer(content)

  return (
    <div
      className="prose prose-sm max-w-none dark:prose-invert [&_p]:my-2 [&_ol]:my-2 [&_ol]:list-decimal [&_ol]:pl-5 [&_ul]:my-2 [&_ul]:list-disc [&_ul]:pl-5 [&_li]:my-1.5 [&_h1]:my-1 [&_h2]:my-1 [&_h3]:my-2 [&_h4]:my-1 [&_h5]:my-1 [&_h6]:my-1"
      dangerouslySetInnerHTML={{ __html: cleanContent }}
    />
  )
}
