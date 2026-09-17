export interface DocumentFile {
  id: string
  file_name: string
  file_type: string
  file_size: number
  status: string
  processing_ended_at?: string | null
}
