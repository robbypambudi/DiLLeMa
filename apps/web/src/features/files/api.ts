import { apiRequest } from '@/shared/api/client'
import type { ApiResponse, PaginatedResponse } from '@/shared/api/types'
import type { DocumentFile } from './types'

const base = '/api/v1/files'

export const filesApi = {
  list: (collectionId: string, signal?: AbortSignal) => apiRequest<PaginatedResponse<DocumentFile>>(`${base}?${new URLSearchParams({ collection_id: collectionId, page: '1', page_size: '100' })}`, { signal }),
  upload: (collectionId: string, file: File) => {
    const body = new FormData()
    body.append('collection_id', collectionId)
    body.append('file', file)
    return apiRequest<ApiResponse<DocumentFile>>(base, { method: 'POST', body })
  },
  retry: (id: string) => apiRequest<ApiResponse<DocumentFile>>(`${base}/${encodeURIComponent(id)}/retry`, { method: 'POST' }),
  remove: (id: string) => apiRequest<ApiResponse<null>>(`${base}/${encodeURIComponent(id)}`, { method: 'DELETE' }),
}
