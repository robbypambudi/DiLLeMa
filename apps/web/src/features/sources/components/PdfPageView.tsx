import { useEffect, useRef, useState } from 'react'
import type { PDFDocumentProxy, RenderTask } from 'pdfjs-dist'
import { findQuoteRects } from '../lib/pdf'
import type { HighlightRect } from '../lib/pdf'
import { cn } from '@/shared/lib/utils'

interface PdfPageViewProps {
  document: PDFDocumentProxy
  pageNumber: number
  scale: number
  /** Estimated size, so pages that have not rendered yet still take up space. */
  placeholder: { width: number; height: number }
  visible: boolean
  quote?: string
  cited?: boolean
  /** Reports the widest highlight band so the panel can scroll to the quote. */
  onHighlight?: (page: number, rect: HighlightRect | null) => void
}

export function PdfPageView({ document, pageNumber, scale, placeholder, visible, quote, cited, onHighlight }: PdfPageViewProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [size, setSize] = useState(placeholder)
  const [highlights, setHighlights] = useState<HighlightRect[]>([])

  useEffect(() => {
    if (!visible) return
    let cancelled = false
    let task: RenderTask | null = null

    void (async () => {
      try {
        const page = await document.getPage(pageNumber)
        if (cancelled) return
        const viewport = page.getViewport({ scale })
        const canvas = canvasRef.current
        if (!canvas) return
        // Back the canvas with device pixels so the text stays sharp on retina.
        const ratio = window.devicePixelRatio || 1
        canvas.width = Math.floor(viewport.width * ratio)
        canvas.height = Math.floor(viewport.height * ratio)
        setSize({ width: viewport.width, height: viewport.height })
        task = page.render({
          canvas,
          viewport,
          transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0],
        })
        await task.promise
        if (cancelled) return
        const rects = quote ? await findQuoteRects(page, viewport, quote) : []
        setHighlights(rects)
        // The widest band is the quoted paragraph; a narrow one is often a
        // header or page number the extracted quote happened to start with.
        const anchor = rects.reduce<HighlightRect | null>(
          (widest, rect) => (!widest || rect.width > widest.width ? rect : widest),
          null
        )
        onHighlight?.(pageNumber, anchor)
      } catch (error) {
        // A cancelled render is the normal result of scrolling or rezooming.
        if (!cancelled && (error as Error)?.name !== 'RenderingCancelledException') {
          setHighlights([])
        }
      }
    })()

    return () => {
      cancelled = true
      task?.cancel()
    }
  }, [document, pageNumber, scale, visible, quote, onHighlight])

  return (
    <div
      className={cn(
        'relative mx-auto bg-white shadow-sm',
        cited ? 'ring-2 ring-primary' : 'ring-1 ring-border'
      )}
      style={{ width: size.width, height: size.height }}
    >
      <canvas ref={canvasRef} className="block h-full w-full" />
      {highlights.map((rect, index) => (
        <span
          key={index}
          aria-hidden
          className="pointer-events-none absolute rounded-sm bg-yellow-300/50 ring-1 ring-yellow-500/70 mix-blend-multiply"
          style={{ left: rect.left, top: rect.top, width: rect.width, height: rect.height }}
        />
      ))}
      <span className="absolute bottom-1 right-2 rounded bg-black/55 px-1.5 py-0.5 text-[10px] font-medium text-white">
        {pageNumber}
      </span>
    </div>
  )
}
