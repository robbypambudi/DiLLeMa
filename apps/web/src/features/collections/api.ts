import { apiRequest } from '@/shared/api/client'
import type { ApiResponse, PaginatedResponse } from '@/shared/api/types'
import type { Collection, CollectionInput } from './types'

const base = '/api/v1/collection'

export const collectionsApi = {
  list: (signal?: AbortSignal) => apiRequest<PaginatedResponse<Collection>>(`${base}?page=1&page_size=100`, { signal }),
  get: (id: string, signal?: AbortSignal) => apiRequest<ApiResponse<Collection>>(`${base}/${encodeURIComponent(id)}`, { signal }),
  create: (input: CollectionInput) => apiRequest<ApiResponse<Collection>>(base, { method: 'POST', body: JSON.stringify(input) }),
  update: (id: string, input: Partial<CollectionInput>) => apiRequest<ApiResponse<Collection>>(`${base}/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(input) }),
  remove: (id: string) => apiRequest<ApiResponse<null>>(`${base}/${encodeURIComponent(id)}`, { method: 'DELETE' }),
}
