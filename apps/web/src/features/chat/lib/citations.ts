/** Turn [Sn] markers into buttons that open the cited page in the source panel. */

const CITATION = /\[S(\d+)\]/g

/**
 * Only markers the server actually sent metadata for become buttons; the rest
 * stay as the model wrote them, so a stale [S9] never opens an empty panel.
 */
export function linkCitations(html: string, available: ReadonlySet<number>): string {
  if (!html || !available.size) return html
  return html
    .split(/(<[^>]*>)/g)
    .map((part) =>
      part.startsWith('<')
        ? part
        : part.replace(CITATION, (marker, digits) => {
            const index = Number(digits)
            if (!available.has(index)) return marker
            return `<button type="button" class="citation-chip" data-citation="${index}" title="Buka sumber S${index}">S${index}</button>`
          })
    )
    .join('')
}

/** The citation index under a click, or null when the click missed a marker. */
export function citationTarget(node: EventTarget | null): number | null {
  if (!(node instanceof Element)) return null
  const chip = node.closest('[data-citation]')
  const index = Number(chip?.getAttribute('data-citation'))
  return Number.isInteger(index) && index > 0 ? index : null
}
