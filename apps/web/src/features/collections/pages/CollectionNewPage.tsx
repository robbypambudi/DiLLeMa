import type { FormEvent} from 'react';
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, FolderPlus } from 'lucide-react'

import { collectionsApi } from '../api'
import { errorMessage } from '@/shared/lib/errors'
import { ErrorBanner } from '@/shared/components/ErrorBanner'
import { Button } from '@/shared/components/ui/Button'
import { Input } from '@/shared/components/ui/Input'

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
      const body = await collectionsApi.create({
        collection_name: name.trim(),
        description: description.trim() || null,
      })
      navigate(`/admin/collections/${body.data.id}`, { replace: true })
    } catch (error) {
      setError(errorMessage(error))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-2xl">
      <Button variant="ghost" size="sm" onClick={() => navigate('/admin')} className="mb-5"><ArrowLeft className="h-4 w-4" /> Collections</Button>
      <h1 className="text-2xl font-semibold tracking-tight">New collection</h1>
      <p className="mb-6 mt-2 text-sm text-muted-foreground">Give your documents a shared space. You can add files after creating the collection.</p>
      <ErrorBanner message={error} />
      <form onSubmit={handleSubmit} className="surface-card space-y-6 p-5 sm:p-7">
        <div className="space-y-2">
          <label className="field-label" htmlFor="name">Collection name <span className="text-destructive">*</span></label>
          <Input id="name" placeholder="e.g. Research papers" value={name} onChange={(e) => setName(e.target.value)} required />
        </div>
        <div className="space-y-2">
          <label className="field-label" htmlFor="description">Description <span className="font-normal text-muted-foreground">(optional)</span></label>
          <textarea
            id="description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="field-control min-h-[128px] resize-y"
            placeholder="What will people find in this collection?"
          />
        </div>
        <div className="flex flex-wrap items-center gap-3 border-t pt-5">
          <Button type="submit" disabled={loading || !name.trim()}>
            <FolderPlus className="h-4 w-4" /> {loading ? 'Creating…' : 'Create collection'}
          </Button>
          <Button type="button" variant="outline" onClick={() => navigate('/admin')}>Cancel</Button>
        </div>
      </form>
    </div>
  )
}
