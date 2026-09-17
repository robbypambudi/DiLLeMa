export function ErrorBanner({ message }: { message: string }) {
  if (!message) return null
  return (
    <div role="alert" className="mb-4 rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm text-destructive">{message}</div>
  )
}
