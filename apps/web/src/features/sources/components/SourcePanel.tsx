import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ChevronLeft, ChevronRight, FileText, Minus, Plus, X } from 'lucide-react'
import type { SourceRef } from '@/features/chat/types'
import { formatPages, pageLabelFor } from '@/features/chat/lib/sources'
import { Button } from '@/shared/components/ui/Button'
import { cn } from '@/shared/lib/utils'
import type { HighlightRect } from '../lib/pdf'
import { usePdfDocument } from '../hooks/usePdfDocument'
import { PdfPageView } from './PdfPageView'

interface SourcePanelProps {
  source: SourceRef
  onClose: () => void
}

const MIN_SCALE = 0.5
const MAX_SCALE = 2.5
const A4 = { width: 612, height: 792 }

export function SourcePanel({ source, onClose }: SourcePanelProps) {
  const { document: pdf, loading, error } = usePdfDocument(source.file_id)
  const scrollRef = useRef<HTMLDivElement>(null)
  const pageRefs = useRef(new Map<number, HTMLDivElement>())
  const [scale, setScale] = useState(1.1)
  const [placeholder, setPlaceholder] = useState(A4)
  const [visiblePages, setVisiblePages] = useState<Set<number>>(() => new Set())
  const [citationIndex, setCitationIndex] = useState(0)

  const citedPages = useMemo(
    () => source.pages.filter((page) => Number.isInteger(page) && page > 0),
    [source.pages]
  )
  const targetPage = citedPages[citationIndex] ?? citedPages[0] ?? 1
  const quoteFor = useCallback(
    (page: number) => source.snippets.find((snippet) => snippet.page === page)?.quote,
    [source.snippets]
  )

  // Keyed on the citation itself, not its file: two answers can cite the same
  // document on different pages. Page refs stay owned by the ref callbacks --
  // clearing them here would strand a document that is still mounted.
  useEffect(() => {
    setCitationIndex(0)
  }, [source])

  // A new document starts with nothing rendered; carrying the old document's
  // page numbers over would render a screenful of the wrong pages at once.
  useEffect(() => {
    setVisiblePages(new Set())
  }, [pdf])

  // Page one sizes the placeholders, so the scrollbar is right before rendering.
  useEffect(() => {
    if (!pdf) return
    let cancelled = false
    void (async () => {
      const page = await pdf.getPage(1)
      if (cancelled) return
      const viewport = page.getViewport({ scale })
      setPlaceholder({ width: viewport.width, height: viewport.height })
    })()
    return () => {
      cancelled = true
    }
  }, [pdf, scale])

  const observePage = useCallback((page: number, element: HTMLDivElement | null) => {
    if (element) pageRefs.current.set(page, element)
    else pageRefs.current.delete(page)
  }, [])

  // The observer reads the target through a ref so scrolling to a citation does
  // not drop its canvas before the smooth scroll gets there.
  const targetRef = useRef(targetPage)
  targetRef.current = targetPage

  useEffect(() => {
    const root = scrollRef.current
    if (!pdf || !root) return
    const observer = new IntersectionObserver(
      (entries) => {
        setVisiblePages((previous) => {
          const next = new Set(previous)
          for (const entry of entries) {
            const page = Number((entry.target as HTMLElement).dataset.page)
            if (entry.isIntersecting) next.add(page)
            else if (page !== targetRef.current) next.delete(page)
          }
          return next
        })
      },
      // Render a screenful ahead so scrolling does not reveal blank pages, and
      // release canvases past it so a long document stays affordable.
      { root, rootMargin: '150% 0px' }
    )
    for (const element of pageRefs.current.values()) observer.observe(element)
    return () => observer.disconnect()
  }, [pdf, scale])

  // Opening a citation, or stepping to the next one, jumps straight to the page.
  const scrollToTarget = useCallback((offsetWithinPage = 0) => {
    const element = pageRefs.current.get(targetRef.current)
    const root = scrollRef.current
    if (!element || !root) return
    root.scrollTo({ top: Math.max(0, element.offsetTop + offsetWithinPage - 12), behavior: 'smooth' })
  }, [])

  const anchored = useRef('')
  useEffect(() => {
    if (!pdf) return
    anchored.current = ''
    setVisiblePages((previous) => new Set(previous).add(targetPage))
    const frame = window.requestAnimationFrame(() => scrollToTarget())
    return () => window.cancelAnimationFrame(frame)
  }, [pdf, targetPage, scrollToTarget])

  // Once the page has rendered, close in on the highlight itself, so a quote
  // near the bottom of a tall page is not left below the fold.
  const handleHighlight = useCallback((page: number, rect: HighlightRect | null) => {
    if (page !== targetRef.current || !rect) return
    const key = `${source.file_id}:${page}:${rect.top.toFixed(0)}`
    if (anchored.current === key) return
    anchored.current = key
    scrollToTarget(Math.max(0, rect.top - 96))
  }, [source.file_id, scrollToTarget])

  const pageCount = pdf?.numPages ?? 0
  const pages = useMemo(() => Array.from({ length: pageCount }, (_, index) => index + 1), [pageCount])

  return (
    <aside
      aria-label={`Sumber S${source.index}`}
      className="fixed inset-0 z-50 flex flex-col bg-background md:static md:z-auto md:w-[26rem] md:shrink-0 md:border-l lg:w-[34rem]"
    >
      <header className="flex shrink-0 items-start gap-2 border-b bg-surface px-4 py-3">
        <FileText className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold" title={source.file_name}>{source.file_name}</p>
          <p className="text-xs text-muted-foreground">
            {citedPages.length
              ? `[S${source.index}] · ${formatPages(source)}`
              : `[S${source.index}] · dokumen sumber`}
          </p>
        </div>
        <Button variant="ghost" size="sm" onClick={onClose} aria-label="Tutup panel sumber" className="h-7 px-2">
          <X className="h-4 w-4" />
        </Button>
      </header>

      <div className="flex shrink-0 flex-wrap items-center gap-1 border-b bg-surface px-3 py-2 text-xs">
        <Button
          variant="ghost"
          size="sm"
          className="h-7 px-2"
          disabled={citationIndex === 0}
          onClick={() => setCitationIndex((index) => Math.max(0, index - 1))}
          aria-label="Kutipan sebelumnya"
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <span className="min-w-[8.5rem] text-center text-muted-foreground">
          {citedPages.length
            ? `Kutipan ${citationIndex + 1}/${citedPages.length} · hal. ${pageLabelFor(source, targetPage)}`
            : 'Tanpa nomor halaman'}
        </span>
        <Button
          variant="ghost"
          size="sm"
          className="h-7 px-2"
          disabled={citationIndex >= citedPages.length - 1}
          onClick={() => setCitationIndex((index) => Math.min(citedPages.length - 1, index + 1))}
          aria-label="Kutipan berikutnya"
        >
          <ChevronRight className="h-4 w-4" />
        </Button>
        <span className="ml-auto flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2"
            disabled={scale <= MIN_SCALE}
            onClick={() => setScale((value) => Math.max(MIN_SCALE, Number((value - 0.2).toFixed(2))))}
            aria-label="Perkecil"
          >
            <Minus className="h-4 w-4" />
          </Button>
          <span className="w-10 text-center tabular-nums text-muted-foreground">{Math.round(scale * 100)}%</span>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2"
            disabled={scale >= MAX_SCALE}
            onClick={() => setScale((value) => Math.min(MAX_SCALE, Number((value + 0.2).toFixed(2))))}
            aria-label="Perbesar"
          >
            <Plus className="h-4 w-4" />
          </Button>
        </span>
      </div>

      {source.quote && (
        <p className="shrink-0 border-b bg-primary/5 px-4 py-2 text-xs italic leading-relaxed text-muted-foreground">
          “{quoteFor(targetPage) || source.quote}”
        </p>
      )}

      <div ref={scrollRef} className="min-h-0 flex-1 overflow-auto bg-muted/40 p-3">
        {!source.file_id && (
          <p className="p-4 text-sm text-muted-foreground">
            Dokumen asli untuk sumber ini tidak tersedia lagi.
          </p>
        )}
        {loading && <p role="status" className="p-4 text-sm text-muted-foreground">Memuat dokumen…</p>}
        {error && <p role="alert" className="p-4 text-sm text-destructive">{error}</p>}
        {pdf && (
          <div className="flex flex-col items-center gap-3">
            {pages.map((page) => (
              <div
                key={page}
                data-page={page}
                ref={(element) => observePage(page, element)}
                className={cn('w-full', page === targetPage && 'scroll-mt-3')}
              >
                <PdfPageView
                  document={pdf}
                  pageNumber={page}
                  scale={scale}
                  placeholder={placeholder}
                  visible={visiblePages.has(page)}
                  cited={citedPages.includes(page)}
                  quote={quoteFor(page)}
                  onHighlight={handleHighlight}
                />
              </div>
            ))}
          </div>
        )}
      </div>
    </aside>
  )
}
