export interface Collection {
  id: string
  collection_name: string
  description?: string | null
  vectordb_collection_name: string
  file_count: number
  created_at?: string | null
}

export interface CollectionInput {
  collection_name: string
  description?: string | null
}
