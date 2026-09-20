/** Which part of ingestion is running, while the file is still processing. */
export interface IngestProgress {
  stage: string
  sections?: number
  done?: number
  total?: number
}

export interface DocumentFile {
  id: string
  file_name: string
  file_type: string
  file_size: number
  status: string
  processing_ended_at?: string | null
  progress?: IngestProgress | null
}
