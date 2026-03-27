/**
 * Type definitions for the chat system
 */

export interface Message {
  id: string;
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
  args: Record<string, unknown>;
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
  output?: unknown;
  status?: string;
  session_id?: string;
}

export interface ThoughtTreeNode {
  id: string
  content: string
  parent_id?: string
  score?: number
  status: 'pending' | 'evaluated' | 'selected' | 'pruned'
  children: ThoughtTreeNode[]
}

export type ThinkingEvent =
  | { type: 'thinking_start'; timestamp: string; mode?: 'simple' | 'tot' }
  | {
      type: 'tool_use'
      tool_name: string
      input: unknown
      timestamp: string
    }
  | {
      type: 'tool_output'
      tool_name: string
      output: unknown
      status: string
      timestamp: string
    }
  | {
      type: 'error'
      error: string
      timestamp: string
    }
  // ToT-specific events
  | {
      type: 'tot_reasoning_start'
      mode: 'tot'
      max_depth: number
      timestamp: string
    }
  | {
      type: 'tot_thoughts_generated'
      depth: number
      count: number
      thoughts: Array<{
        id: string
        content: string
        parent_id?: string
      }>
      timestamp: string
    }
  | {
      type: 'tot_thoughts_evaluated'
      best_path: string[]
      best_score: number
      timestamp: string
    }
  | {
      type: 'tot_tools_executed'
      thought_id: string
      content: string
      tool_count: number
      timestamp: string
    }
  | {
      type: 'tot_tree_update'
      tree: ThoughtTreeNode[]
      timestamp: string
    }
  | {
      type: 'tot_reasoning_complete'
      final_answer: string
      best_path: string[]
      total_thoughts: number
      timestamp: string
    }
  | {
      type: 'tot_termination'
      reason?: string
      score?: number
      depth?: number
      timestamp: string
    }
