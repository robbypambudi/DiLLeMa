import { FormEvent, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'

import { useAuth } from '@/auth'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'

export function LoginPage() {
  const { user, ready, login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  if (!ready) {
    return <div className="min-h-screen bg-background p-6 text-sm text-muted-foreground">Loading…</div>
  }

  if (user) {
    return <Navigate to={user.role === 'admin' ? '/admin' : '/'} replace />
  }

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError('')
    setLoading(true)
    try {
      const nextUser = await login(email.trim(), password)
      navigate(nextUser.role === 'admin' ? '/admin' : '/', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Email or password is wrong.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-background flex items-center justify-center px-4">
      <form onSubmit={handleSubmit} className="w-full max-w-sm border bg-background p-6 space-y-4">
        <div>
          <h1 className="text-xl font-semibold">DiLLeMa</h1>
          <p className="text-sm text-muted-foreground mt-1">Sign in to manage collections</p>
        </div>
        {error && (
          <div className="border border-destructive text-sm px-3 py-2">{error}</div>
        )}
        <div className="space-y-1">
          <label className="text-sm" htmlFor="email">Email</label>
          <Input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="username"
          />
        </div>
        <div className="space-y-1">
          <label className="text-sm" htmlFor="password">Password</label>
          <Input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="current-password"
          />
        </div>
        <Button type="submit" className="w-full" disabled={loading || !email.trim() || !password}>
          {loading ? 'Signing in…' : 'Sign in'}
        </Button>
      </form>
    </div>
  )
}
