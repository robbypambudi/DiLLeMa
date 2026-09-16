import { X } from 'lucide-react'

interface DeleteCollectionModalProps {
  isOpen: boolean
  collectionName: string
  onClose: () => void
  onConfirm: () => void
}

export function DeleteCollectionModal({ isOpen, collectionName, onClose, onConfirm }: DeleteCollectionModalProps) {
  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-background rounded-lg p-6 w-full max-w-md mx-4">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-destructive">Delete Collection</h2>
          <button onClick={onClose} className="p-1 hover:bg-accent rounded">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="mb-6">
          <p className="text-sm text-muted-foreground mb-2">
            Are you sure you want to delete the collection:
          </p>
          <p className="font-medium">{collectionName}</p>
          <p className="text-sm text-muted-foreground mt-2">
            This action cannot be undone.
          </p>
        </div>

        <div className="flex gap-2">
          <button
            onClick={onClose}
            className="flex-1 px-4 py-2 border rounded-md hover:bg-accent transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className="flex-1 px-4 py-2 bg-destructive text-destructive-foreground rounded-md hover:bg-destructive/90 transition-colors"
          >
            Delete
          </button>
        </div>
      </div>
    </div>
  )
}
