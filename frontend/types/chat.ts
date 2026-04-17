/**
 * Type definitions for the chat system
 */

export interface GeneratedImage {
  media_id: string;
  api_url: string;
  name: string;
  mime_type: string;
}

export interface Message {
  role: 'user' | 'assistant' | 'tool';
  content: string;
  tool_calls?: ToolCall[];
  timestamp?: string;
  images?: ImageAttachment[];
  generated_images?: GeneratedImage[];
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
  type: 'thinking_start' | 'tool_call' | 'content_delta' | 'tool_output' | 'error' | 'done' | 'self_correction';
  content?: string;
  tool_calls?: ToolCall[];
  error?: string;
  tool_name?: string;
  output?: any;
  status?: string;
  session_id?: string;
  generated_images?: GeneratedImage[];
  correction?: string;
  quality_score?: number;
}

export interface ThoughtTreeNode {
  id: string
  content: string
  parent_id?: string
  score?: number
  status: 'pending' | 'evaluated' | 'selected' | 'pruned'
  tool_calls?: Array<{ name: string; args: Record<string, unknown> }>
  children: ThoughtTreeNode[]
}

export type ThinkingEvent =
  | { type: 'thinking_start'; timestamp: string; mode?: 'simple' | 'tot' }
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
  // ToT-specific events
  | {
      type: 'tot_reasoning_start'
      mode: 'tot'
      max_depth: number
      timestamp: string
    }
  | {
      type: 'tot_status'
      status_message: string
      node: string
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
      active_beams?: string[][]   // Phase 10: active beam paths
      beam_scores?: number[]      // Phase 10: scores for each beam
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
      final_answer_length: number
      final_answer_preview: string
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
  // Phase 10: Beam search events
  | {
      type: 'tot_backtrack'
      reason?: string
      depth?: number
      beam_idx?: number
      from_root?: string
      to_root?: string
      timestamp: string
    }
  | {
      type: 'tot_thoughts_regenerated'
      depth: number
      beam_indices?: number[]
      count: number
      timestamp: string
    }
