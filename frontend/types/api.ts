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

export interface ToolCall {
  id: string;
  name: string;
  args: Record<string, unknown>;
}

export interface Session {
  session_id: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  metadata: Record<string, unknown>;
}

export interface SessionListResponse {
  sessions: Session[];
  total: number;
}

export interface ChatRequest {
  message: string;
  session_id?: string;
  stream?: boolean;
  context?: Record<string, unknown>;
}

export interface ChatResponse {
  role: string;
  content: string;
  tool_calls?: ToolCall[];
}
