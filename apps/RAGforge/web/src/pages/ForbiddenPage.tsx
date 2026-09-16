import { Link } from 'react-router-dom'

export function ForbiddenPage() {
  return (
    <div className="min-h-screen bg-background flex items-center justify-center px-4">
      <div className="max-w-sm space-y-3">
        <h1 className="text-xl font-semibold">You don’t have access to this page.</h1>
        <Link to="/" className="text-sm underline">Back to chat</Link>
      </div>
    </div>
  )
}
