import DOMPurify from 'dompurify'

interface HtmlRendererProps {
  content: string
}

const cleanBrokenHtml = (htmlString: string) => {
  if (!htmlString || typeof htmlString !== 'string') {
    return ''
  }
  
  let cleanedText = htmlString
    .replace(/[\r\n]+/g, '')
    .replace(/```html/g, '')
    .replace(/```/g, '')

  return (cleanedText.split('</think>').pop() || '').trim();
}

export function HtmlRenderer({ content }: HtmlRendererProps) {
  const structurallyCleanContent = cleanBrokenHtml(content)
  
  // Configure DOMPurify to allow common HTML tags
  const cleanContent = typeof window !== 'undefined' 
    ? DOMPurify.sanitize(structurallyCleanContent, {
        ALLOWED_TAGS: ['p', 'br', 'b', 'strong', 'i', 'em', 'u', 'ol', 'ul', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'div', 'span'],
        ALLOWED_ATTR: ['type', 'class']
      })
    : structurallyCleanContent

  return (
    <div 
      className="prose prose-sm max-w-none dark:prose-invert [&_p]:my-1 [&_ol]:my-1 [&_ul]:my-1 [&_li]:my-0 [&_h1]:my-1 [&_h2]:my-1 [&_h3]:my-1 [&_h4]:my-1 [&_h5]:my-1 [&_h6]:my-1"
      dangerouslySetInnerHTML={{ __html: cleanContent }}
    />
  )
}
