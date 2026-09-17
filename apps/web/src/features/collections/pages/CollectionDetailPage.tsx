import { useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Save } from 'lucide-react'

import { useCollectionDetail } from '../hooks/useCollectionDetail'
import { CollectionDocuments } from '@/features/files/components/CollectionDocuments'
import { ConfirmDialog } from '@/shared/components/ConfirmDialog'
import { ErrorBanner } from '@/shared/components/ErrorBanner'
import { Button } from '@/shared/components/ui/Button'
import { Input } from '@/shared/components/ui/Input'
import { KnowledgePanel } from '@/features/knowledge/components/KnowledgePanel'

export function CollectionDetailPage() {
  const { id } = useParams()
  return <CollectionDetailContent key={id} id={id} />
}

function CollectionDetailContent({ id }: { id: string | undefined }) {
  const navigate = useNavigate()
  const { collection, name, setName, description, setDescription, files, error,
    saving, pendingFile, setPendingFile, pendingDelete, setPendingDelete, deleting,
    uploading, saveMeta, uploadFiles, retry, confirmDeleteFile, confirmDeleteCollection } = useCollectionDetail(id)

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

      <CollectionDocuments files={files} uploading={uploading} uploadFiles={uploadFiles} retry={retry} onDelete={setPendingFile} />
      {id && <KnowledgePanel key={id} collectionId={id} files={files} />}
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
