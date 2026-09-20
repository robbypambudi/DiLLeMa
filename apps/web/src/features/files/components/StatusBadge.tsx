import type { IngestProgress } from '../types'

/** What each ingestion stage is doing, in the words a reader can act on. */
const STAGES: Record<string, (progress: IngestProgress) => string> = {
  reading: () => 'Reading document',
  chunking: (progress) =>
    progress.sections ? `Splitting ${progress.sections} pages` : 'Splitting text',
  indexing: (progress) =>
    progress.total ? `Indexing ${progress.done ?? 0}/${progress.total}` : 'Indexing',
}

function label(status: string, progress?: IngestProgress | null): string {
  const labels: Record<string, string> = {
    pending: 'Queued',
    processing: 'Indexing',
    completed: 'Ready',
    failed: 'Failed',
  }
  if (status !== 'processing' || !progress?.stage) return labels[status] || status
  const stage = STAGES[progress.stage]
  return stage ? stage(progress) : labels.processing
}

/** How far indexing has got, when the stage counts its work. */
function percent(progress?: IngestProgress | null): number | null {
  if (progress?.stage !== 'indexing' || !progress.total) return null
  return Math.min(100, Math.round(((progress.done ?? 0) / progress.total) * 100))
}

export function StatusBadge({ status, progress }: { status: string; progress?: IngestProgress | null }) {
  const styles: Record<string, string> = {
    pending: 'bg-muted text-muted-foreground',
    processing: 'bg-primary text-primary-foreground',
    completed: 'bg-green-800 text-white',
    failed: 'bg-destructive text-destructive-foreground',
  }
  const share = percent(progress)
  return (
    <span className="inline-flex flex-col gap-1">
      <span
        className={`inline-block whitespace-nowrap rounded-full border border-transparent px-2.5 py-1 text-xs font-medium ${styles[status] || 'bg-muted'}`}
        // The stage changes while the row stays put, so the reader is told.
        aria-live={status === 'processing' ? 'polite' : undefined}
      >
        {label(status, progress)}
      </span>
      {share !== null && (
        <span className="h-1 w-full overflow-hidden rounded-full bg-muted" aria-hidden>
          <span className="block h-full bg-primary transition-all" style={{ width: `${share}%` }} />
        </span>
      )}
    </span>
  )
}
