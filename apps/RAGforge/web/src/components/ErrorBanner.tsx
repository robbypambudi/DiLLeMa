export function ErrorBanner({ message }: { message: string }) {
  if (!message) return null
  return (
    <div className="border border-destructive text-sm px-3 py-2 mb-4">{message}</div>
  )
}
