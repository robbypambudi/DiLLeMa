import { FormEvent, useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'

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
  const inputRef = useRef<HTMLInputElement>(null)
  const [collection, setCollection] = useState<CollectionDetail | null>(null)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [files, setFiles] = useState<FileRow[]>([])
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [pendingFile, setPendingFile] = useState<FileRow | null>(null)

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

  if (!collection && !error) {
    return <p className="text-sm text-muted-foreground">Loading…</p>
  }

  return (
    <div className="space-y-8">
      <ErrorBanner message={error} />
      {collection && (
        <section className="max-w-lg space-y-4">
          <h1 className="text-xl font-semibold">Collection</h1>
          <form onSubmit={saveMeta} className="space-y-4">
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
            <div>
              <div className="text-sm text-muted-foreground">Storage id</div>
              <div className="text-sm mt-1">{collection.vectordb_collection_name}</div>
            </div>
            <Button type="submit" disabled={saving || !name.trim()}>{saving ? 'Saving…' : 'Save'}</Button>
          </form>
        </section>
      )}

      <section>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">Documents</h2>
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
            <Button type="button" onClick={() => inputRef.current?.click()}>Upload</Button>
          </div>
        </div>
        <div
          className="border border-dashed p-6 text-sm text-muted-foreground mb-4"
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault()
            uploadFiles(e.dataTransfer.files)
          }}
        >
          Drop PDF, Word, Markdown, or text files here.
        </div>
        {files.length === 0 ? (
          <p className="text-sm text-muted-foreground">No documents in this collection.</p>
        ) : (
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b text-left">
                <th className="py-2 pr-3 font-medium">Name</th>
                <th className="py-2 pr-3 font-medium">Type</th>
                <th className="py-2 pr-3 font-medium">Size</th>
                <th className="py-2 pr-3 font-medium">Status</th>
                <th className="py-2 pr-3 font-medium">Indexed at</th>
                <th className="py-2 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {files.map((file) => (
                <tr key={file.id} className="border-b">
                  <td className="py-2 pr-3">{file.file_name}</td>
                  <td className="py-2 pr-3">{file.file_type}</td>
                  <td className="py-2 pr-3">{formatSize(file.file_size)}</td>
                  <td className="py-2 pr-3"><StatusBadge status={file.status} /></td>
                  <td className="py-2 pr-3">
                    {file.status === 'completed' && file.processing_ended_at
                      ? new Date(file.processing_ended_at).toLocaleString()
                      : '—'}
                  </td>
                  <td className="py-2 space-x-2">
                    {file.status === 'failed' && (
                      <Button size="sm" variant="outline" onClick={() => retry(file)}>Retry</Button>
                    )}
                    <Button size="sm" variant="destructive" onClick={() => setPendingFile(file)}>Delete</Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      <ConfirmDialog
        open={!!pendingFile}
        title="Delete document"
        body={`Delete ${pendingFile?.file_name}? It will be removed from search.`}
        onCancel={() => setPendingFile(null)}
        onConfirm={confirmDeleteFile}
      />
    </div>
  )
}
