import { FormEvent, useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, FileText, Save, Upload } from 'lucide-react'

import { apiFetch, readError } from '@/api'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { ErrorBanner } from '@/components/ErrorBanner'
import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'

type CollectionDetail = {
  id: string
  collection_name: string
  description?: string | null
  vectordb_collection_name: string
}

type FileRow = {
  id: string
  file_name: string
  file_type: string
  file_size: number
  status: string
  processing_ended_at?: string | null
}

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function CollectionDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const inputRef = useRef<HTMLInputElement>(null)
  const [collection, setCollection] = useState<CollectionDetail | null>(null)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [files, setFiles] = useState<FileRow[]>([])
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [pendingFile, setPendingFile] = useState<FileRow | null>(null)
  const [pendingDelete, setPendingDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const loadFiles = useCallback(async () => {
    if (!id) return
    const response = await apiFetch(`/api/v1/files?collection_id=${id}&page=1&page_size=100`)
    if (!response.ok) {
      setError(await readError(response))
      return
    }
    const body = await response.json()
    setFiles(
      (body.data || []).filter(
        (file: FileRow) => file.status !== 'deleted' && file.status !== 'archived',
      ),
    )
  }, [id])

  const load = useCallback(async () => {
    if (!id) return
    setError('')
    try {
      const response = await apiFetch(`/api/v1/collection/${id}`)
      if (!response.ok) {
        setError(await readError(response))
        return
      }
      const body = await response.json()
      const data = body.data as CollectionDetail
      setCollection(data)
      setName(data.collection_name)
      setDescription(data.description || '')
      await loadFiles()
    } catch {
      setError('Could not reach the server.')
    }
  }, [id, loadFiles])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    const busy = files.some((file) => file.status === 'pending' || file.status === 'processing')
    if (!busy) return
    const timer = window.setInterval(() => {
      loadFiles().catch(() => undefined)
    }, 2000)
    return () => window.clearInterval(timer)
  }, [files, loadFiles])

  const saveMeta = async (event: FormEvent) => {
    event.preventDefault()
    if (!id) return
    setSaving(true)
    setError('')
    try {
      const response = await apiFetch(`/api/v1/collection/${id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          collection_name: name.trim(),
          description,
        }),
      })
      if (!response.ok) {
        setError(await readError(response))
        return
      }
      await load()
    } catch {
      setError('Could not reach the server.')
    } finally {
      setSaving(false)
    }
  }

  const uploadFiles = async (fileList: FileList | null) => {
    if (!id || !fileList?.length) return
    setError('')
    for (const file of Array.from(fileList)) {
      const form = new FormData()
      form.append('collection_id', id)
      form.append('file', file)
      try {
        const response = await apiFetch('/api/v1/files', { method: 'POST', body: form })
        if (!response.ok) {
          setError(await readError(response))
          break
        }
      } catch {
        setError('Could not reach the server.')
        break
      }
    }
    await loadFiles()
  }

  const retry = async (file: FileRow) => {
    setError('')
    try {
      const response = await apiFetch(`/api/v1/files/${file.id}/retry`, { method: 'POST' })
      if (!response.ok) {
        setError(await readError(response))
        return
      }
      await loadFiles()
    } catch {
      setError('Could not reach the server.')
    }
  }

  const confirmDeleteFile = async () => {
    if (!pendingFile) return
    try {
      const response = await apiFetch(`/api/v1/files/${pendingFile.id}`, { method: 'DELETE' })
      if (!response.ok) {
        setError(await readError(response))
      } else {
        setPendingFile(null)
        await loadFiles()
      }
    } catch {
      setError('Could not reach the server.')
    }
  }

  const confirmDeleteCollection = async () => {
    if (!id || deleting) return
    setDeleting(true)
    setError('')
    try {
      const response = await apiFetch(`/api/v1/collection/${id}`, { method: 'DELETE' })
      if (!response.ok) {
        setError(await readError(response))
        return
      }
      navigate('/admin', { replace: true })
    } catch {
      setError('Could not reach the server.')
    } finally {
      setDeleting(false)
    }
  }

  if (!collection && !error) {
    return <p className="text-sm text-muted-foreground">Loading…</p>
  }

  return (
    <div className="space-y-6">
      <div>
        <Button variant="ghost" size="sm" onClick={() => navigate('/admin')} className="mb-4"><ArrowLeft className="h-4 w-4" /> Collections</Button>
        <h1 className="break-words text-2xl font-semibold tracking-tight">{collection?.collection_name || 'Collection'}</h1>
        <p className="mt-2 text-sm text-muted-foreground">Manage collection details and the documents available for chat.</p>
      </div>
      <ErrorBanner message={error} />
      {collection && (
        <section className="surface-card space-y-5 p-5 sm:p-7">
          <div className="border-b pb-4">
            <h2 className="text-lg font-semibold">Collection details</h2>
            <p className="mt-1 text-sm text-muted-foreground">Help people understand what this collection contains.</p>
          </div>
          <form onSubmit={saveMeta} className="max-w-2xl space-y-5">
            <div className="space-y-2">
              <label className="field-label" htmlFor="name">Collection name</label>
              <Input id="name" value={name} onChange={(e) => setName(e.target.value)} required />
            </div>
            <div className="space-y-2">
              <label className="field-label" htmlFor="description">Description</label>
              <textarea
                id="description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="field-control min-h-[112px] resize-y"
                placeholder="Describe the documents in this collection"
              />
            </div>
            <div className="rounded-lg border bg-secondary/50 px-4 py-3">
              <div className="text-sm text-muted-foreground">Storage id</div>
              <div className="mt-1 break-all font-mono text-xs">{collection.vectordb_collection_name}</div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button type="submit" disabled={saving || !name.trim()}>
                <Save className="h-4 w-4" /> {saving ? 'Saving…' : 'Save changes'}
              </Button>
              <Button type="button" variant="destructive" onClick={() => setPendingDelete(true)}>
                Delete collection
              </Button>
            </div>
          </form>
        </section>
      )}

      <section className="surface-card p-5 sm:p-7">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <h2 className="flex items-center gap-2 text-lg font-semibold"><FileText className="h-5 w-5 text-primary" /> Documents <span className="rounded-md border bg-secondary px-2 py-0.5 text-xs text-muted-foreground">{files.length}</span></h2>
          <div>
            <input
              ref={inputRef}
              type="file"
              className="hidden"
              accept=".pdf,.txt,.docx,.md"
              multiple
              onChange={(e) => {
                uploadFiles(e.target.files)
                e.target.value = ''
              }}
            />
            <Button type="button" onClick={() => inputRef.current?.click()}><Upload className="h-4 w-4" /> Upload</Button>
          </div>
        </div>
        <div
          className="mb-5 rounded-xl border-2 border-dashed border-input bg-primary/5 p-7 text-center text-sm text-muted-foreground transition-colors hover:border-primary hover:bg-primary/10"
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault()
            uploadFiles(e.dataTransfer.files)
          }}
        >
          <Upload className="mx-auto mb-3 h-7 w-7 text-primary" />
          <p className="font-medium text-foreground">Drag and drop your documents here</p>
          <p className="mt-1">PDF, Word, Markdown, or text files</p>
          <Button type="button" variant="outline" size="sm" className="mt-4" onClick={() => inputRef.current?.click()}>Browse files</Button>
        </div>
        {files.length === 0 ? (
          <p className="py-5 text-center text-sm text-muted-foreground">No documents yet. Upload a file to get started.</p>
        ) : (
          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">Name</th>
                  <th scope="col">Type</th>
                  <th scope="col">Size</th>
                  <th scope="col">Status</th>
                  <th scope="col">Indexed at</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {files.map((file) => (
                  <tr key={file.id}>
                    <td className="min-w-[180px] break-all font-medium">{file.file_name}</td>
                    <td className="text-muted-foreground">{file.file_type}</td>
                    <td className="whitespace-nowrap text-muted-foreground">{formatSize(file.file_size)}</td>
                    <td><StatusBadge status={file.status} /></td>
                    <td className="whitespace-nowrap text-muted-foreground">
                      {file.status === 'completed' && file.processing_ended_at
                        ? new Date(file.processing_ended_at).toLocaleString()
                        : '—'}
                    </td>
                    <td className="space-x-2 whitespace-nowrap">
                      {file.status === 'failed' && (
                        <Button size="sm" variant="outline" onClick={() => retry(file)}>Retry</Button>
                      )}
                      <Button size="sm" variant="destructive" onClick={() => setPendingFile(file)}>Delete</Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <ConfirmDialog
        open={!!pendingFile}
        title="Delete document"
        body={`Delete ${pendingFile?.file_name}? It will be removed from search.`}
        onCancel={() => setPendingFile(null)}
        onConfirm={confirmDeleteFile}
      />
      <ConfirmDialog
        open={pendingDelete}
        title="Delete collection"
        body={`Delete collection ${collection?.collection_name}? Documents and indexed text will be removed. This cannot be undone.`}
        onCancel={() => !deleting && setPendingDelete(false)}
        onConfirm={confirmDeleteCollection}
      />
    </div>
  )
}
