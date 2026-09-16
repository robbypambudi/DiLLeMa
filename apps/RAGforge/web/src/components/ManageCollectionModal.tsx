import { useState, useEffect } from 'react'
import { X, Trash2, FileText, Upload } from 'lucide-react'
import { Collection } from '@/App'
import { DeleteCollectionModal } from './DeleteCollectionModal'

import { BACKEND_URL } from '@/config'

interface ManageCollectionModalProps {
  isOpen: boolean
  onClose: () => void
  collection: Collection | null
  onSuccess: () => void
}

interface Document {
  id: string
  file_name: string
  updated_at: string
}

export function ManageCollectionModal({ isOpen, onClose, collection, onSuccess }: ManageCollectionModalProps) {
  const [documents, setDocuments] = useState<Document[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [dragActive, setDragActive] = useState(false)

  useEffect(() => {
    if (isOpen && collection) {
      fetchDocuments()
    }
  }, [isOpen, collection])

  const fetchDocuments = async () => {
    if (!collection) return
    
    setIsLoading(true)
    try {
      const response = await fetch(`${BACKEND_URL}/api/v1/files?file_name&page=1&collection_id=${collection.id}`)
      // const response = await fetch(`${BACKEND_URL}/api/v1/collection/${collection.id}/documents`)
      if (response.ok) {
        const data = await response.json()
        console.log(data)
        setDocuments(data.data || [])
      }
    } catch (error) {
      console.error('Failed to fetcDocumenth documents:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const handleDelete = async () => {
    if (!collection) return

    setIsDeleting(true)
    try {
      const response = await fetch(`${BACKEND_URL}/api/v1/collection/${collection.name}`, {
        method: 'DELETE'
      })

      if (response.ok) {
        onSuccess()
        onClose()
        setShowDeleteModal(false)
      }
    } catch (error) {
      console.error('Failed to delete collection:', error)
    } finally {
      setIsDeleting(false)
    }
  }

  const handleFileUpload = async (files: FileList) => {
    if (!collection || files.length === 0) return

    setIsUploading(true)
    try {
      for (const file of Array.from(files)) {
        const formData = new FormData()
        formData.append('file', file)
        formData.append('collection_id', collection.id)

        const response = await fetch(`${BACKEND_URL}/api/v1/files`, {
          method: 'POST',
          body: formData
        })

        if (!response.ok) {
          throw new Error(`Failed to upload ${file.name}`)
        }
      }
      
      await fetchDocuments()
    } catch (error) {
      console.error('Failed to upload files:', error)
    } finally {
      setIsUploading(false)
    }
  }

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true)
    } else if (e.type === 'dragleave') {
      setDragActive(false)
    }
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)
    
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileUpload(e.dataTransfer.files)
    }
  }

  if (!isOpen || !collection) return null

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-background rounded-lg p-6 w-full max-w-2xl mx-4 max-h-[80vh] overflow-hidden flex flex-col">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">Manage Collection</h2>
          <button onClick={onClose} className="p-1 hover:bg-accent rounded">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Collection Info Section */}
        <div className="border rounded-lg p-4 mb-4">
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <h3 className="font-medium text-lg">{collection.name}</h3>
              <p className="text-muted-foreground mt-1">{collection.description}</p>
            </div>
            <button
              onClick={() => setShowDeleteModal(true)}
              disabled={isDeleting}
              className="ml-4 px-3 py-1 bg-destructive text-destructive-foreground rounded-md hover:bg-destructive/90 disabled:opacity-50 transition-colors flex items-center gap-2"
            >
              <Trash2 className="w-4 h-4" />
              Delete
            </button>
          </div>
        </div>

        {/* Documents Section */}
        <div className="flex-1 overflow-hidden">
          <div className="flex items-center justify-between mb-3">
            <h4 className="font-medium flex items-center gap-2">
              <FileText className="w-4 h-4" />
              Documents ({documents.length})
            </h4>
            
            {/* Upload Section */}
            <div className="flex items-center gap-2">
              <input
                type="file"
                multiple
                accept=".pdf,.txt,.docx,.md"
                onChange={(e) => e.target.files && handleFileUpload(e.target.files)}
                className="hidden"
                id="file-upload"
                disabled={isUploading}
              />
              <label
                htmlFor="file-upload"
                className="px-3 py-1 bg-primary text-primary-foreground rounded-md hover:bg-primary/90 disabled:opacity-50 transition-colors flex items-center gap-2 cursor-pointer"
              >
                <Upload className="w-4 h-4" />
                {isUploading ? 'Uploading...' : 'Upload'}
              </label>
            </div>
          </div>

          {/* Drag and Drop Area */}
          <div
            className={`border-2 border-dashed rounded-lg p-4 mb-4 transition-colors ${
              dragActive ? 'border-primary bg-primary/5' : 'border-muted-foreground/25'
            }`}
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
          >
            <div className="text-center text-sm text-muted-foreground">
              {isUploading ? (
                'Uploading files...'
              ) : (
                <>
                  Drag and drop files here or{' '}
                  <label htmlFor="file-upload" className="text-primary cursor-pointer hover:underline">
                    browse
                  </label>
                </>
              )}
            </div>
          </div>
          
          <div className="border rounded-lg overflow-hidden">
            {isLoading ? (
              <div className="p-4 text-center text-muted-foreground">
                Loading documents...
              </div>
            ) : documents.length === 0 ? (
              <div className="p-4 text-center text-muted-foreground">
                No documents found in this collection
              </div>
            ) : (
              <div className="max-h-60 overflow-y-auto">
                {documents.map((doc) => (
                  <div key={doc.id} className="p-3 border-b last:border-b-0 hover:bg-accent/50">
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="font-medium text-sm">{doc.file_name}</div>
                        <div className="text-xs text-muted-foreground">
                          Uploaded: {new Date(doc.updated_at).toLocaleString()}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="flex justify-end pt-4 mt-4 border-t">
          <button
            onClick={onClose}
            className="px-4 py-2 border rounded-md hover:bg-accent transition-colors"
          >
            Close
          </button>
        </div>

        <DeleteCollectionModal
          isOpen={showDeleteModal}
          collectionName={collection?.name || ''}
          onClose={() => setShowDeleteModal(false)}
          onConfirm={handleDelete}
        />
      </div>
    </div>
  )
}
