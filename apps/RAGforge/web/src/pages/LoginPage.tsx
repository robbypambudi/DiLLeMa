import { FormEvent, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { ArrowLeft, ArrowRight, Lock } from 'lucide-react'
import logoLight from '../../assets/logo-light.png'
import logoDark from '../../assets/logo-dark.png'

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
    <div className="flex min-h-screen flex-col items-center justify-center bg-background px-5 py-10">
      <div className="mb-7 flex items-center gap-3">
        <img src={logoLight} alt="" className="h-10 dark:hidden" />
        <img src={logoDark} alt="" className="hidden h-10 dark:block" />
        <span className="text-2xl font-semibold tracking-tight">DiLLeMa</span>
      </div>
      <form onSubmit={handleSubmit} className="surface-card w-full max-w-md space-y-6 p-6 sm:p-8">
        <div className="border-b pb-6">
          <span className="mb-4 flex h-10 w-10 items-center justify-center rounded-xl border border-primary/20 bg-primary/5 text-primary"><Lock className="h-5 w-5" /></span>
          <h1 className="text-2xl font-semibold tracking-tight">Welcome back</h1>
          <p className="mt-2 text-sm text-muted-foreground">Sign in to manage your document collections.</p>
        </div>
        {error && (
          <div role="alert" className="rounded-lg border border-destructive/40 bg-destructive/5 px-3 py-3 text-sm text-destructive">{error}</div>
        )}
        <div className="space-y-2">
          <label className="field-label" htmlFor="email">Email address</label>
          <Input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="username"
            placeholder="you@example.com"
          />
        </div>
        <div className="space-y-2">
          <label className="field-label" htmlFor="password">Password</label>
          <Input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="current-password"
            placeholder="Enter your password"
          />
        </div>
        <Button type="submit" className="w-full" disabled={loading || !email.trim() || !password}>
          {loading ? 'Signing in…' : 'Sign in'}
          {!loading && <ArrowRight className="h-4 w-4" />}
        </Button>
      </form>
      <Button variant="ghost" className="mt-5" onClick={() => navigate('/')}><ArrowLeft className="h-4 w-4" /> Back to home</Button>
    </div>
  )
}
