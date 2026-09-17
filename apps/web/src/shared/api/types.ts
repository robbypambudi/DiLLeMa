export interface ApiResponse<T> {
  data: T
  status: string
  message?: string | null
}

export interface PaginatedResponse<T> extends ApiResponse<T[]> {
  metadata: { total_count: number; page: number; page_size: number }
}
