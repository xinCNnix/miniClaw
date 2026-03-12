/**
 * Knowledge Base Type Definitions
 */

export interface KBDocument {
  id: string
  filename: string
  file_type: string
  size: number
  upload_date: string
  chunk_count: number
}

export interface KBUploadResponse {
  success: boolean
  document: KBDocument
  message: string
}

export interface KBDocumentListResponse {
  documents: KBDocument[]
  total: number
}

export interface KBStats {
  total_documents: number
  total_chunks: number
  total_size: number
  last_updated: string | null
}

export interface KBDeleteResponse {
  success: boolean
  message: string
}

export interface KBUploadStatus {
  isUploading: boolean
  progress: number
  currentFile: string | null
  error: string | null
}

/**
 * Large file upload types
 */
export interface KBLargeFileUploadRequest {
  filename: string
  file_size: number
  confirm: boolean
}

export interface KBLargeFileUploadResponse {
  requires_authorization: boolean
  file_size: number
  file_size_mb: number
  threshold_mb: number
  message: string
  upload_token?: string
}

/**
 * Batch upload types
 */
export interface KBBatchUploadRequest {
  confirm: boolean
  file_count: number
  total_size: number
}

export interface KBBatchUploadResponse {
  requires_authorization: boolean
  file_count: number
  total_size_mb: number
  threshold_mb: number
  message: string
  upload_token?: string
}

export interface KBRejectedFile {
  filename: string
  path: string
  reason: string
}

export interface KBBatchUploadComplete {
  task_id: string
  total: number
  successful: number
  failed: number
  failed_files: KBRejectedFile[]
  message: string
}
