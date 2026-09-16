import { FormEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { apiFetch, readError } from '@/api'
import { ErrorBanner } from '@/components/ErrorBanner'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'

export function CollectionNewPage() {
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    if (!name.trim()) {
      setError('Collection name is required')
      return
    }
    setLoading(true)
    setError('')
    try {
      const response = await apiFetch('/api/v1/collection', {
        method: 'POST',
        body: JSON.stringify({
          collection_name: name.trim(),
          description: description.trim() || null,
        }),
      })
      if (!response.ok) {
        setError(await readError(response))
        return
      }
      const body = await response.json()
      navigate(`/admin/collections/${body.data.id}`, { replace: true })
    } catch {
      setError('Could not reach the server.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-lg">
      <h1 className="text-xl font-semibold mb-4">New collection</h1>
      <ErrorBanner message={error} />
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-1">
          <label className="text-sm" htmlFor="name">Name</label>
          <Input id="name" value={name} onChange={(e) => setName(e.target.value)} required />
        </div>
        <div className="space-y-1">
          <label className="text-sm" htmlFor="description">Description</label>
          <textarea
            id="description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="flex min-h-[96px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
          />
        </div>
        <div className="flex gap-2">
          <Button type="submit" disabled={loading || !name.trim()}>
            {loading ? 'Creating…' : 'Create'}
          </Button>
          <Button type="button" variant="outline" onClick={() => navigate('/admin')}>Cancel</Button>
        </div>
      </form>
    </div>
  )
}
