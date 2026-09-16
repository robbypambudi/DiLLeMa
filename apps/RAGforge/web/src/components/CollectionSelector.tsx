import { useEffect } from 'react'
import { BookOpen } from 'lucide-react'
import { AppState, Collection } from '@/App'
// import { AddCollectionModal } from './AddCollectionModal'
// import { ManageCollectionModal } from './ManageCollectionModal'

import { BACKEND_URL } from '@/config'

interface CollectionSelectorProps {
  appState: AppState
  updateState: (updates: Partial<AppState>) => void
  // onManageCollections: () => void
}

// export function CollectionSelector({ appState, updateState, onManageCollections }: CollectionSelectorProps) {
export function CollectionSelector({ appState, updateState }: CollectionSelectorProps) {
  const { collections, selectedCollection } = appState
  // const [showAddModal, setShowAddModal] = useState(false)
  // const [showManageModal, setShowManageModal] = useState(false)
  // const [managingCollection, setManagingCollection] = useState<Collection | null>(null)

  useEffect(() => {
    fetchCollections()
  }, [])

  const fetchCollections = async () => {
    try {
      const response = await fetch(`${BACKEND_URL}/api/v1/collection?page=1&collection_name&vectordb_collection_name`)
      const data = await response.json()
      
      console.log('API Response:', data) // Debug log
      
      if (data.status === 'success' && data.data) {
        const fetchedCollections = data.data.map((col: any) => ({
          id: col.id,
          name: col.collection_name,
          description: col.description
        }))
        console.log('Fetched collections:', fetchedCollections) // Debug log
        updateState({ collections: fetchedCollections })
      }
    } catch (error) {
      console.error('Failed to fetch collections:', error)
    }
  }

  const handleCollectionChange = (collection: Collection) => {
    updateState({ 
      selectedCollection: collection,
      messages: [{
        role: 'assistant',
        content: '👋 Welcome to our chatbot! Feel free to ask about anything.'
      }]
    })
  }

  // const handleManageCollection = (collection: Collection, e: React.MouseEvent) => {
  //   e.stopPropagation()
  //   setManagingCollection(collection)
  //   setShowManageModal(true)
  // }

  return (
    <div className="w-80 border-r bg-muted/30 p-4">
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <BookOpen className="w-5 h-5" />
            <h2 className="font-semibold">Collections</h2>
          </div>
          {/* <button
            onClick={() => setShowAddModal(true)}
            className="p-1 hover:bg-accent rounded-md transition-colors"
            title="Add Collection"
          >
            <Plus className="w-4 h-4" />
          </button> */}
        </div>
        
        <div className="space-y-2">
          {collections.map((collection) => (
            <div
              key={collection.id}
              className={`relative group rounded-lg border transition-colors ${
                selectedCollection?.id === collection.id
                  ? 'bg-primary/20 border-primary/50 text-foreground'
                  : 'bg-background hover:bg-accent/50 border-border hover:border-accent-foreground/20'
              }`}
            >
              <button
                onClick={() => handleCollectionChange(collection)}
                className="w-full text-left p-3 pr-10"
              >
                <div className="font-medium text-sm">{collection.name}</div>
                <div className="text-xs opacity-70 mt-1">{collection.description}</div>
              </button>
              {/* <button
                onClick={(e) => handleManageCollection(collection, e)}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 opacity-0 group-hover:opacity-100 hover:bg-accent rounded transition-all"
              >
                <MoreVertical className="w-4 h-4" />
              </button> */}
            </div>
          ))}
        </div>
        
        {collections.length === 0 && (
          <div className="text-center text-muted-foreground text-sm py-8">
            No collections available
          </div>
        )}

        {/* <div className="pt-4 border-t">
          <button
            onClick={onManageCollections}
            className="w-full flex items-center space-x-2 p-2 text-sm text-muted-foreground hover:text-foreground hover:bg-accent rounded-md transition-colors"
          >
            <Settings className="w-4 h-4" />
            <span>Manage Collections</span>
          </button>
        </div> */}
      </div>

      {/* <AddCollectionModal 
        isOpen={showAddModal}
        onClose={() => setShowAddModal(false)}
        onSuccess={fetchCollections}
      />

      <ManageCollectionModal
        isOpen={showManageModal}
        onClose={() => setShowManageModal(false)}
        collection={managingCollection}
        onSuccess={fetchCollections}
      /> */}
    </div>
  )
}
