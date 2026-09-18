import { useEffect, useState } from 'react'
import { apiFetch, readError } from '@/shared/api/client'
import { fileRawUrl } from '@/features/chat/api'
import { errorMessage } from '@/shared/lib/errors'
import { pdfjs } from '../lib/pdf'
import type { PDFDocumentProxy } from 'pdfjs-dist'

interface PdfDocumentState {
  document: PDFDocumentProxy | null
  loading: boolean
  error: string
}

/** Load a cited file through the authenticated API, not a bare <embed> URL. */
export function usePdfDocument(fileId: string | null): PdfDocumentState {
  const [state, setState] = useState<PdfDocumentState>({ document: null, loading: false, error: '' })

  useEffect(() => {
    if (!fileId) {
      setState({ document: null, loading: false, error: '' })
      return
    }
    let cancelled = false
    let loaded: PDFDocumentProxy | null = null
    const controller = new AbortController()
    setState({ document: null, loading: true, error: '' })

    void (async () => {
      try {
        const response = await apiFetch(fileRawUrl(fileId), { signal: controller.signal })
        if (!response.ok) throw new Error(await readError(response))
        const data = await response.arrayBuffer()
        if (cancelled) return
        const task = pdfjs.getDocument({ data })
        loaded = await task.promise
        if (cancelled) {
          void loaded.destroy()
          return
        }
        setState({ document: loaded, loading: false, error: '' })
      } catch (error) {
        if (cancelled || controller.signal.aborted) return
        setState({ document: null, loading: false, error: errorMessage(error) })
      }
    })()

    return () => {
      cancelled = true
      controller.abort()
      void loaded?.destroy()
    }
  }, [fileId])

  return state
}
