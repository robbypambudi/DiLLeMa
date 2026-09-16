import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { apiFetch, readError } from '@/api'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { ErrorBanner } from '@/components/ErrorBanner'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'

type CollectionRow = {
  id: string
  collection_name: string
  description?: string | null
  file_count: number
  created_at?: string | null
}

export function CollectionsPage() {
  const navigate = useNavigate()
  const [rows, setRows] = useState<CollectionRow[]>([])
  const [filter, setFilter] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [pendingDelete, setPendingDelete] = useState<CollectionRow | null>(null)

  const load = async () => {
    setError('')
    setLoading(true)
    try {
      const response = await apiFetch('/api/v1/collection?page=1&page_size=100')
      if (!response.ok) {
        setError(await readError(response))
        return
      }
      const body = await response.json()
      setRows(body.data || [])
    } catch {
      setError('Could not reach the server.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const visible = useMemo(() => {
    const q = filter.trim().toLowerCase()
    if (!q) return rows
    return rows.filter((row) => row.collection_name.toLowerCase().includes(q))
  }, [rows, filter])

  const confirmDelete = async () => {
    if (!pendingDelete) return
    try {
      const response = await apiFetch(`/api/v1/collection/${pendingDelete.id}`, { method: 'DELETE' })
      if (!response.ok) {
        setError(await readError(response))
      } else {
        setPendingDelete(null)
        await load()
      }
    } catch {
      setError('Could not reach the server.')
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold">Collections</h1>
        <Button onClick={() => navigate('/admin/collections/new')}>New collection</Button>
      </div>
      <ErrorBanner message={error} />
      <div className="mb-4 max-w-xs">
        <Input
          placeholder="Filter by name"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
      </div>
      {loading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : visible.length === 0 ? (
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">No collections yet.</p>
          <Button onClick={() => navigate('/admin/collections/new')}>New collection</Button>
        </div>
      ) : (
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b text-left">
              <th className="py-2 pr-3 font-medium">Name</th>
              <th className="py-2 pr-3 font-medium">Description</th>
              <th className="py-2 pr-3 font-medium">Documents</th>
              <th className="py-2 pr-3 font-medium">Created</th>
              <th className="py-2 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((row) => (
              <tr key={row.id} className="border-b">
                <td className="py-2 pr-3">{row.collection_name}</td>
                <td className="py-2 pr-3 text-muted-foreground">
                  {row.description ? (row.description.length > 80 ? `${row.description.slice(0, 80)}…` : row.description) : '—'}
                </td>
                <td className="py-2 pr-3">{row.file_count}</td>
                <td className="py-2 pr-3">{row.created_at ? new Date(row.created_at).toLocaleDateString() : '—'}</td>
                <td className="py-2 space-x-2">
                  <Button size="sm" variant="outline" onClick={() => navigate(`/admin/collections/${row.id}`)}>Open</Button>
                  <Button size="sm" variant="destructive" onClick={() => setPendingDelete(row)}>Delete</Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <ConfirmDialog
        open={!!pendingDelete}
        title="Delete collection"
        body={`Delete collection ${pendingDelete?.collection_name}? Documents and indexed text will be removed. This cannot be undone.`}
        onCancel={() => setPendingDelete(null)}
        onConfirm={confirmDelete}
      />
    </div>
  )
}
