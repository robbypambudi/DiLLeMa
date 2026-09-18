import * as pdfjs from 'pdfjs-dist'
import type { PDFPageProxy, PageViewport } from 'pdfjs-dist'
import type { TextItem } from 'pdfjs-dist/types/src/display/api'
// Vite serves the worker as its own asset; pdf.js will not parse without it.
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl

export { pdfjs }

export interface HighlightRect {
  left: number
  top: number
  width: number
  height: number
}

/** Ignore whitespace: the indexed quote and the PDF's text run split lines differently. */
function strip(text: string): string {
  return text.replace(/\s+/g, '').toLowerCase()
}

function isTextItem(item: unknown): item is TextItem {
  return typeof (item as TextItem)?.str === 'string'
}

/**
 * Where a cited quote sits on a rendered page.
 *
 * The quote was stored at index time from the same extractor, but it is capped
 * at 350 characters and may end mid-word, so shorter prefixes are tried before
 * giving up. An empty result means "page found, exact spot unknown".
 */
export async function findQuoteRects(
  page: PDFPageProxy,
  viewport: PageViewport,
  quote: string
): Promise<HighlightRect[]> {
  const needle = strip(quote)
  if (needle.length < 12) return []

  const content = await page.getTextContent()
  const items = content.items.filter(isTextItem)
  let haystack = ''
  const owner: number[] = []
  items.forEach((item, index) => {
    for (const character of item.str) {
      if (/\s/.test(character)) continue
      haystack += character.toLowerCase()
      owner.push(index)
    }
  })

  let start = -1
  let length = 0
  for (const size of [needle.length, 200, 120, 60, 30]) {
    if (size > needle.length || size < 12) continue
    start = haystack.indexOf(needle.slice(0, size))
    if (start !== -1) {
      length = size
      break
    }
  }
  if (start === -1) return []

  const boxes: HighlightRect[] = []
  for (let index = owner[start]; index <= owner[start + length - 1]; index++) {
    const item = items[index]
    if (!item.str.trim()) continue
    const transform = pdfjs.Util.transform(viewport.transform, item.transform)
    const height = Math.hypot(transform[2], transform[3]) || item.height * viewport.scale
    boxes.push({
      left: transform[4],
      top: transform[5] - height,
      width: item.width * viewport.scale,
      height,
    })
  }
  return mergeLines(boxes)
}

/** One band per line reads better than a box per text run. */
function mergeLines(boxes: HighlightRect[]): HighlightRect[] {
  const lines: HighlightRect[] = []
  for (const box of boxes) {
    const line = lines.find((candidate) => Math.abs(candidate.top - box.top) <= box.height * 0.5)
    if (!line) {
      lines.push({ ...box })
      continue
    }
    const right = Math.max(line.left + line.width, box.left + box.width)
    line.left = Math.min(line.left, box.left)
    line.top = Math.min(line.top, box.top)
    line.height = Math.max(line.height, box.height)
    line.width = right - line.left
  }
  return lines
}
