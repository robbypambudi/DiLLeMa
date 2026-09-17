import { useRef } from 'react'
import { FileText, Upload } from 'lucide-react'
import { Button } from '@/shared/components/ui/Button'
import { StatusBadge } from './StatusBadge'
import type { DocumentFile } from '../types'

interface CollectionDocumentsProps {
  files: DocumentFile[]
  uploading: boolean
  uploadFiles: (files: FileList | null) => Promise<void>
  retry: (file: DocumentFile) => Promise<void>
  onDelete: (file: DocumentFile) => void
}

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function CollectionDocuments({ files, uploading, uploadFiles, retry, onDelete }: CollectionDocumentsProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  return (
      <section className="surface-card p-5 sm:p-7">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <h2 className="flex items-center gap-2 text-lg font-semibold"><FileText className="h-5 w-5 text-primary" /> Documents <span className="rounded-md border bg-secondary px-2 py-0.5 text-xs text-muted-foreground">{files.length}</span></h2>
          <div>
            <input
              ref={inputRef}
              type="file"
              disabled={uploading}
              className="hidden"
              accept=".pdf,.txt,.docx,.md"
              multiple
              onChange={(e) => {
                uploadFiles(e.target.files)
                e.target.value = ''
              }}
            />
            <Button type="button" disabled={uploading} onClick={() => inputRef.current?.click()}><Upload className="h-4 w-4" /> Upload</Button>
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
          <Button type="button" variant="outline" size="sm" className="mt-4" disabled={uploading} onClick={() => inputRef.current?.click()}>Browse files</Button>
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
                      <Button size="sm" variant="destructive" onClick={() => onDelete(file)}>Delete</Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
  )
}
