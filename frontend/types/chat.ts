/**
 * Type definitions for the chat system
 */

export interface GeneratedImage {
  media_id: string;
  api_url: string;
  name: string;
  mime_type: string;
}

export type FileCategory = 'image' | 'document' | 'audio' | 'video'

export interface FileAttachment {
  type: FileCategory
  content: string       // base64 data
  mime_type: string
  filename: string
}

export interface ActionButton {
  id: string
  label: string
  variant: 'primary' | 'secondary' | 'danger'
}

export interface Message {
  role: 'user' | 'assistant' | 'tool' | 'system';
  content: string;
  tool_calls?: ToolCall[];
  timestamp?: string;
  images?: FileAttachment[];
  attachments?: FileAttachment[];
  generated_images?: GeneratedImage[];
  actions?: ActionButton[];
  onAction?: (actionId: string) => void
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
  type: 'thinking_start' | 'tool_call' | 'content_delta' | 'tool_output' | 'error' | 'done' | 'self_correction' | 'run_id' | 'cancelled';
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
  run_id?: string;
  reason?: string;
  round?: number;
  node?: string;
}

export interface ThoughtTreeNode {
  id: string
  content: string
  parent_id?: string
  score?: number
  status: 'pending' | 'evaluated' | 'selected' | 'pruned' | 'executing' | 'done'
  skill_name?: string
  tool_calls?: Array<{ name: string; args: Record<string, unknown> }>
  tool_statuses?: Array<{ tool: string; status: string }>
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
  // PERV events
  | { type: 'perv_start'; timestamp: string }
  | {
      type: 'perv_router_decision'
      decision: { mode?: string; risk_level?: string; [k: string]: unknown }
      duration_ms: number
      timestamp: string
    }
  | {
      type: 'perv_planning'
      plan: Array<{ id: string; name: string; tool: string; purpose: string; skill?: string }>
      timestamp: string
    }
  | {
      type: 'perv_layer_start'
      layers: unknown[]
      total_steps: number
      timestamp: string
    }
  | {
      type: 'perv_step_complete'
      step_id: string
      status: string
      tool: string
      timestamp: string
    }
  | {
      type: 'perv_execution_complete'
      steps_completed: number
      parallel: boolean
      timestamp: string
    }
  | {
      type: 'perv_verification'
      report: { verdict: string; confidence: number; checks: unknown[]; coverage?: number }
      timestamp: string
    }
  | {
      type: 'perv_replan'
      retry_count: number
      timestamp: string
    }
  | {
      type: 'perv_skill_policy'
      matched: number
      compiled: number
      timestamp: string
    }
  | {
      type: 'perv_summarized'
      summary_count: number
      timestamp: string
    }
