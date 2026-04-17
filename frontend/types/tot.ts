/**
 * ToT (Tree of Thoughts) Event Types
 *
 * TypeScript types for ToT reasoning events.
 */

// Base SSE event types
export interface BaseSSEEvent {
  type: string
}

// Thinking events
export interface ThinkingStartEvent extends BaseSSEEvent {
  type: 'thinking_start'
  mode?: 'simple' | 'tot'
}

export interface ThinkingDoneEvent extends BaseSSEEvent {
  type: 'done'
}

// Content events
export interface ContentDeltaEvent extends BaseSSEEvent {
  type: 'content_delta'
  content: string
}

// Error events
export interface ErrorEvent extends BaseSSEEvent {
  type: 'error'
  error: string
}

// ToT-specific events
export interface ToTReasoningStartEvent extends BaseSSEEvent {
  type: 'tot_reasoning_start'
  mode: 'tot'
  max_depth: number
}

export interface ToTThoughtsGeneratedEvent extends BaseSSEEvent {
  type: 'tot_thoughts_generated'
  depth: number
  count: number
  thoughts: Array<{
    id: string
    content: string
    parent_id?: string
  }>
}

export interface ToTThoughtsEvaluatedEvent extends BaseSSEEvent {
  type: 'tot_thoughts_evaluated'
  best_path: string[]
  best_score: number
}

export interface ToTToolsExecutedEvent extends BaseSSEEvent {
  type: 'tot_tools_executed'
  thought_id: string
  content: string
  tool_count: number
}

export interface ToTTerminationEvent extends BaseSSEEvent {
  type: 'tot_termination'
  reason?: string
  score?: number
  depth?: number
}

export interface ToTTreeUpdateEvent extends BaseSSEEvent {
  type: 'tot_tree_update'
  tree: ThoughtTreeNode[]
}

export interface ToTReasoningCompleteEvent extends BaseSSEEvent {
  type: 'tot_reasoning_complete'
  final_answer_length: number
  final_answer_preview: string
  best_path: string[]
  total_thoughts: number
}

// Tree node structure
export interface ThoughtTreeNode {
  id: string
  content: string
  parent_id?: string
  score?: number
  status: 'pending' | 'evaluated' | 'selected' | 'pruned'
  children: ThoughtTreeNode[]
}

// Union type of all ToT events
export type ToTEvent =
  | ToTReasoningStartEvent
  | ToTThoughtsGeneratedEvent
  | ToTThoughtsEvaluatedEvent
  | ToTToolsExecutedEvent
  | ToTTerminationEvent
  | ToTTreeUpdateEvent
  | ToTReasoningCompleteEvent

// Union type of all SSE events
export type SSEEvent =
  | ThinkingStartEvent
  | ThinkingDoneEvent
  | ContentDeltaEvent
  | ErrorEvent
  | ToTEvent

// Type guards
export function isToTEvent(event: SSEEvent): event is ToTEvent {
  return event.type.startsWith('tot_')
}

export function isToTTreeUpdateEvent(event: SSEEvent): event is ToTTreeUpdateEvent {
  return event.type === 'tot_tree_update'
}

export function isToTReasoningCompleteEvent(event: SSEEvent): event is ToTReasoningCompleteEvent {
  return event.type === 'tot_reasoning_complete'
}
