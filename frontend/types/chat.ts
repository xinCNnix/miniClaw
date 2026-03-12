/**
 * Type definitions for the chat system
 */

export interface Message {
  role: 'user' | 'assistant' | 'tool';
  content: string;
  tool_calls?: ToolCall[];
  timestamp?: string;
  images?: ImageAttachment[];
}

export interface ImageAttachment {
  type: 'image';
  content: string; // base64 data
  mime_type: string; // e.g. "image/png", "image/jpeg"
}

export interface ToolCall {
  id: string;
  name: string;
  args: Record<string, any>;
}

export interface ChatState {
  messages: Message[];
  isLoading: boolean;
  error: string | null;
  sessionId: string;
}

export interface SSEEvent {
  type: 'thinking_start' | 'tool_call' | 'content_delta' | 'tool_output' | 'error' | 'done';
  content?: string;
  tool_calls?: ToolCall[];
  error?: string;
  tool_name?: string;
  output?: any;
  status?: string;
  session_id?: string;
}

export type ThinkingEvent =
  | { type: 'thinking_start'; timestamp: string }
  | {
      type: 'tool_use'
      tool_name: string
      input: any
      timestamp: string
    }
  | {
      type: 'tool_output'
      tool_name: string
      output: any
      status: string
      timestamp: string
    }
  | {
      type: 'error'
      error: string
      timestamp: string
    }
