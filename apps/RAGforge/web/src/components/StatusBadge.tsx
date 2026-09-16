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
    <span className={`inline-block whitespace-nowrap rounded-full border border-transparent px-2.5 py-1 text-xs font-medium ${styles[status] || 'bg-muted'}`}>
      {labels[status] || status}
    </span>
  )
}
