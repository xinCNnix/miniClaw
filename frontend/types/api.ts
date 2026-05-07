/**
 * Type definitions for API requests/responses
 */

export interface File {
  name: string;
  path: string;
  type: 'file' | 'directory';
  size?: number;
  modified_time?: string;
}

export interface FileContent extends File {
  content?: string;
}

export interface FileListResponse {
  files: File[];
  current_path: string;
}

export interface Session {
  session_id: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  metadata: Record<string, any>;
}

export interface SessionListResponse {
  sessions: Session[];
  total: number;
}

export interface ChatRequest {
  message: string;
  session_id?: string;
  stream?: boolean;
  context?: Record<string, any>;
  attachments?: Array<{
    type: string;
    content: string;
    mime_type: string;
    filename: string;
  }>;
}

export interface ChatResponse {
  role: string;
  content: string;
  tool_calls?: any[];
}
