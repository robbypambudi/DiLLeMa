import { BookOpen, Check, FolderOpen, Loader2 } from 'lucide-react'
import { Button } from '@/shared/components/ui/Button'
import { useCollectionList } from '../hooks/useCollectionList'
import type { Collection } from '../types'

interface CollectionSelectorProps {
  selectedCollection: Collection | null
  disabled: boolean
  onSelect: (collection: Collection) => void
}

export function CollectionSelector({ selectedCollection, disabled, onSelect }: CollectionSelectorProps) {
  const { rows: collections, loading, error, load } = useCollectionList()
  const handleCollectionChange = (collection: Collection) => {
    if (!disabled && selectedCollection?.id !== collection.id) onSelect(collection)
  }

  return (
    <aside className="flex shrink-0 flex-col border-b bg-surface p-4 md:w-72 md:border-b-0 md:border-r md:p-5 lg:w-80" aria-label="Document collections">
      <div className="mb-4 hidden items-center justify-between md:flex">
        <h2 className="flex items-center gap-2 text-sm font-semibold"><BookOpen className="h-4 w-4 text-primary" /> Collections</h2>
        <span className="rounded-md border bg-secondary px-2 py-0.5 text-xs text-muted-foreground">{collections.length}</span>
      </div>
      <p className="mb-5 hidden text-xs leading-relaxed text-muted-foreground md:block">Choose the documents you want to explore.</p>
      {loading ? (
        <p role="status" className="flex items-center gap-2 py-3 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Loading collections…</p>
      ) : error ? (
        <div role="alert" className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm">
          <p>Could not load collections.</p>
          <Button variant="outline" size="sm" className="mt-3" onClick={load}>Try again</Button>
        </div>
      ) : collections.length === 0 ? (
        <div className="rounded-xl border border-dashed p-5 text-center text-sm text-muted-foreground">
          <FolderOpen className="mx-auto mb-3 hidden h-7 w-7 md:block" />
          No collections available
        </div>
      ) : (
        <>
          <div className="md:hidden">
            <label htmlFor="mobile-collection" className="field-label mb-2">Collection</label>
            <select id="mobile-collection" className="field-control" value={selectedCollection?.id || ''} disabled={disabled} onChange={(event) => {
              const collection = collections.find((item) => item.id === event.target.value)
              if (collection) handleCollectionChange(collection)
            }}>
              <option value="" disabled>Select a collection</option>
              {collections.map((collection) => <option key={collection.id} value={collection.id}>{collection.collection_name}</option>)}
            </select>
          </div>
          <div className="hidden min-h-0 space-y-2 overflow-y-auto md:block">
            {collections.map((collection) => {
              const selected = selectedCollection?.id === collection.id
              return (
                <button key={collection.id} type="button" aria-pressed={selected} disabled={disabled} onClick={() => handleCollectionChange(collection)}
                  className={`flex w-full items-start gap-3 rounded-xl border p-3.5 text-left transition-colors disabled:cursor-wait ${selected ? 'border-primary/60 bg-primary/10 shadow-sm' : 'border-border bg-surface hover:border-primary/50 hover:bg-primary/5'}`}>
                  <FolderOpen className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                  <span className="min-w-0 flex-1">
                    <span className="block break-words text-sm font-semibold">{collection.collection_name}</span>
                    <span className="mt-1 block break-words text-xs leading-relaxed text-muted-foreground">{collection.description || 'Document collection'}</span>
                  </span>
                  {selected && <Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" />}
                </button>
              )
            })}
          </div>
        </>
      )}
      <div className="mt-auto hidden pt-6 md:block">
        <p className="border-t pt-4 text-xs leading-relaxed text-muted-foreground">Each conversation is focused on your selected collection.</p>
      </div>
    </aside>
  )
}
