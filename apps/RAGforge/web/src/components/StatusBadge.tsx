export function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    pending: 'bg-muted text-muted-foreground',
    processing: 'bg-primary text-primary-foreground',
    completed: 'bg-green-800 text-white',
    failed: 'bg-destructive text-destructive-foreground',
  }
  const labels: Record<string, string> = {
    pending: 'Queued',
    processing: 'Indexing',
    completed: 'Ready',
    failed: 'Failed',
  }
  return (
    <span className={`inline-block px-2 py-0.5 text-xs ${styles[status] || 'bg-muted'}`}>
      {labels[status] || status}
    </span>
  )
}
