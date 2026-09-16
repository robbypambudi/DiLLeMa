import { useState, useEffect } from 'react'
import { Button } from './ui/Button'
import { Input } from './ui/Input'
import { DeleteCollectionModal } from './DeleteCollectionModal'

interface Collection {
  id: string
  collection_name: string
  vectordb_collection_name: string
  description?: string
}

import { BACKEND_URL } from '@/config'

export function CollectionManager() {
  const [collections, setCollections] = useState<Collection[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [deleteModal, setDeleteModal] = useState<{ isOpen: boolean; collectionName: string }>({
    isOpen: false,
    collectionName: ''
  })
  const [formData, setFormData] = useState({
    collection_name: '',
    vectordb_collection_name: '',
    description: ''
  })

  const fetchCollections = async () => {
    setIsLoading(true)
    try {
      const response = await fetch(`${BACKEND_URL}/api/v1/collection?page=1&collection_name&vectordb_collection_name`)
      const data = await response.json()
      if (data.status === 'success') {
        setCollections(data.data)
      }
    } catch (error) {
      console.error('Failed to fetch collections:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const createCollection = async () => {
    try {
      const formDataObj = new FormData()
      formDataObj.append('collection_name', formData.collection_name)
      formDataObj.append('vectordb_collection_name', formData.vectordb_collection_name)
      formDataObj.append('description', formData.description)

      const response = await fetch(`${BACKEND_URL}/api/v1/collection`, {
        method: 'POST',
        body: formDataObj
      })

      if (response.ok) {
        setFormData({ collection_name: '', vectordb_collection_name: '', description: '' })
        setShowForm(false)
        fetchCollections()
      }
    } catch (error) {
      console.error('Failed to create collection:', error)
    }
  }

  const deleteCollection = async (collectionName: string) => {
    try {
      const response = await fetch(`${BACKEND_URL}/api/v1/collection/${collectionName}`, {
        method: 'DELETE'
      })

      if (response.ok) {
        fetchCollections()
        setDeleteModal({ isOpen: false, collectionName: '' })
      }
    } catch (error) {
      console.error('Failed to delete collection:', error)
    }
  }

  useEffect(() => {
    fetchCollections()
  }, [])

  return (
    <div className="p-6 space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold">Collection Management</h2>
        <Button onClick={() => setShowForm(!showForm)}>
          {showForm ? 'Cancel' : 'Add Collection'}
        </Button>
      </div>

      {showForm && (
        <div className="border rounded-lg p-4 space-y-4">
          <Input
            placeholder="Collection Name"
            value={formData.collection_name}
            onChange={(e) => setFormData({ ...formData, collection_name: e.target.value })}
          />
          <Input
            placeholder="Vector DB Collection Name"
            value={formData.vectordb_collection_name}
            onChange={(e) => setFormData({ ...formData, vectordb_collection_name: e.target.value })}
          />
          <Input
            placeholder="Description (optional)"
            value={formData.description}
            onChange={(e) => setFormData({ ...formData, description: e.target.value })}
          />
          <Button onClick={createCollection}>Create Collection</Button>
        </div>
      )}

      {isLoading ? (
        <div>Loading...</div>
      ) : (
        <div className="space-y-2">
          {collections.map((collection) => (
            <div key={collection.id} className="border rounded-lg p-4 flex justify-between items-center">
              <div>
                <h3 className="font-semibold">{collection.collection_name}</h3>
                <p className="text-sm text-muted-foreground">{collection.description}</p>
                <p className="text-xs text-muted-foreground">Vector DB: {collection.vectordb_collection_name}</p>
              </div>
              <Button 
                variant="destructive" 
                onClick={() => setDeleteModal({ isOpen: true, collectionName: collection.collection_name })}
              >
                Delete
              </Button>
            </div>
          ))}
        </div>
      )}

      <DeleteCollectionModal
        isOpen={deleteModal.isOpen}
        collectionName={deleteModal.collectionName}
        onClose={() => setDeleteModal({ isOpen: false, collectionName: '' })}
        onConfirm={() => deleteCollection(deleteModal.collectionName)}
      />
    </div>
  )
}
