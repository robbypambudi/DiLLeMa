import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { FolderOpen, Plus, Search } from 'lucide-react'

import { apiFetch, readError } from '@/api'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { ErrorBanner } from '@/components/ErrorBanner'
import { RenameDialog } from '@/components/RenameDialog'
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
  const [pendingRename, setPendingRename] = useState<CollectionRow | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const [renaming, setRenaming] = useState(false)
  const [deleting, setDeleting] = useState(false)

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
    if (!pendingDelete || deleting) return
    setDeleting(true)
    setError('')
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
    } finally {
      setDeleting(false)
    }
  }

  const confirmRename = async () => {
    if (!pendingRename || renaming) return
    const nextName = renameValue.trim()
    if (!nextName) return
    setRenaming(true)
    setError('')
    try {
      const response = await apiFetch(`/api/v1/collection/${pendingRename.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ collection_name: nextName }),
      })
      if (!response.ok) {
        setError(await readError(response))
        return
      }
      setPendingRename(null)
      await load()
    } catch {
      setError('Could not reach the server.')
    } finally {
      setRenaming(false)
    }
  }

  return (
    <div>
      <div className="mb-7 flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-widest text-primary">Knowledge library</p>
          <h1 className="text-3xl font-semibold tracking-tight">Collections</h1>
          <p className="mt-2 text-sm text-muted-foreground">Organize the documents that power your conversations.</p>
        </div>
        <Button onClick={() => navigate('/admin/collections/new')}><Plus className="h-4 w-4" /> New collection</Button>
      </div>
      <ErrorBanner message={error} />
      <div className="surface-card p-4 sm:p-6">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-4">
          <h2 className="flex items-center gap-2 text-sm font-semibold">All collections <span className="rounded-md border bg-secondary px-2 py-0.5 text-xs text-muted-foreground">{rows.length}</span></h2>
          <div className="relative w-full sm:max-w-xs">
            <Search className="pointer-events-none absolute left-3 top-3.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search collections…"
              aria-label="Filter collections by name"
              className="pl-10"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
          </div>
        </div>
        {loading ? (
          <p role="status" className="py-12 text-center text-sm text-muted-foreground">Loading collections…</p>
        ) : visible.length === 0 ? (
          <div className="space-y-3 rounded-xl border border-dashed px-5 py-12 text-center">
            <FolderOpen className="mx-auto mb-4 h-9 w-9 text-primary" />
            <h3 className="font-semibold">{filter ? 'No matching collections' : 'Your library starts here'}</h3>
            <p className="text-sm text-muted-foreground">{filter ? 'Try a different name or clear your search.' : 'Create a collection, then add your documents.'}</p>
            {filter ? <Button variant="outline" onClick={() => setFilter('')}>Clear search</Button> : <Button onClick={() => navigate('/admin/collections/new')}><Plus className="h-4 w-4" /> New collection</Button>}
          </div>
        ) : (
          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">Name</th>
                  <th scope="col">Description</th>
                  <th scope="col">Documents</th>
                  <th scope="col">Created</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((row) => (
                  <tr key={row.id}>
                    <td className="min-w-[160px] font-medium"><button className="text-left hover:text-primary hover:underline" onClick={() => navigate(`/admin/collections/${row.id}`)}>{row.collection_name}</button></td>
                    <td className="min-w-[200px] text-muted-foreground">
                      {row.description ? (row.description.length > 80 ? `${row.description.slice(0, 80)}…` : row.description) : '—'}
                    </td>
                    <td>{row.file_count}</td>
                    <td className="whitespace-nowrap text-muted-foreground">{row.created_at ? new Date(row.created_at).toLocaleDateString() : '—'}</td>
                    <td>
                      <div className="flex gap-2">
                        <Button size="sm" variant="outline" onClick={() => navigate(`/admin/collections/${row.id}`)}>
                          Open
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            setPendingRename(row)
                            setRenameValue(row.collection_name)
                          }}
                        >
                          Rename
                        </Button>
                        <Button size="sm" variant="destructive" onClick={() => setPendingDelete(row)}>
                          Delete
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      <RenameDialog
        open={!!pendingRename}
        title="Rename collection"
        value={renameValue}
        saving={renaming}
        onChange={setRenameValue}
        onCancel={() => setPendingRename(null)}
        onConfirm={confirmRename}
      />
      <ConfirmDialog
        open={!!pendingDelete}
        title="Delete collection"
        body={`Delete collection ${pendingDelete?.collection_name}? Documents and indexed text will be removed. This cannot be undone.`}
        onCancel={() => !deleting && setPendingDelete(null)}
        onConfirm={confirmDelete}
      />
    </div>
  )
}
