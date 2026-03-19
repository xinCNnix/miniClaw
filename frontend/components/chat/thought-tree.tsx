/**
 * Thought Tree Visualization Component (Phase 4 Enhanced)
 *
 * Displays the Tree of Thoughts reasoning process with an interactive tree visualization.
 *
 * Enhancements:
 * - Highlight best path
 * - Display candidate paths with different colors
 * - Mark backtracked nodes
 * - Show tool execution status and scores
 * - Display Beam Search candidates
 */

'use client'

import React, { useMemo } from 'react'

// Types (Extended for Phase 4)
interface ThoughtNode {
  id: string
  content: string
  parent_id?: string
  score?: number
  status: 'pending' | 'evaluated' | 'selected' | 'pruned' | 'backtracked'
  is_best_path?: boolean        // NEW: Part of best path
  is_beam_candidate?: boolean    // NEW: Part of beam search candidates
  tool_calls?: ToolCall[]        // NEW: Tool calls info
  tool_results?: ToolResult[]    // NEW: Tool execution results
  beam_rank?: number            // NEW: Rank in beam search (0 = best)
  children: ThoughtNode[]
}

interface ToolCall {
  name: string
  args: Record<string, any>
}

interface ToolResult {
  tool: string
  status: 'success' | 'error' | 'pending'
  output?: string
}

interface ToTTreeUpdateEvent {
  type: 'tot_tree_update'
  tree: ThoughtNode[]
  best_path?: string[]          // NEW: IDs of thoughts in best path
  beam_candidates?: string[][]   // NEW: IDs of candidate paths
  stats?: {
    total_thoughts: number
    evaluated_thoughts: number
    tool_calls: number
    successful_tools: number
  }
}

interface ThoughtTreeProps {
  events: any[]
  maxHeight?: string
  'data-testid'?: string
}

export function ThoughtTree({ events, maxHeight = '400px', 'data-testid': testId }: ThoughtTreeProps) {
  // Build tree from latest event
  const treeStructure = useMemo(() => {
    if (events.length === 0) return null

    // Find latest tree update event
    const latestTreeEvent = events.find(e => e.type === 'tot_tree_update')
    return latestTreeEvent?.tree || null
  }, [events])

  // Extract additional info
  const latestEvent = useMemo(() => {
    return events.find(e => e.type === 'tot_tree_update')
  }, [events])

  const bestPathIds = latestEvent?.best_path || []
  const beamCandidates = latestEvent?.beam_candidates || []
  const stats = latestEvent?.stats

  if (!treeStructure || treeStructure.length === 0) {
    return (
      <div className="thought-tree-container mb-3 border border-gray-200 rounded-lg bg-gray-50" style={{ maxHeight }} data-testid={testId}>
        <div className="text-sm text-gray-500 p-4">
          Waiting for reasoning tree...
        </div>
      </div>
    )
  }

  return (
    <div className="thought-tree-container mb-3 border border-gray-200 rounded-lg bg-gray-50" style={{ maxHeight }} data-testid={testId}>
      {/* Enhanced Header with Stats */}
      <div className="thought-tree-header p-3 bg-gradient-to-r from-blue-50 to-indigo-50 border-b">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-semibold text-gray-700">Reasoning Tree (ToT)</h3>
          <span className="text-xs text-gray-500">
            {countNodes(treeStructure)} thoughts
          </span>
        </div>

        {/* NEW: Statistics Bar */}
        {stats && (
          <div className="flex items-center gap-4 text-xs text-gray-600">
            <span>
              <span className="font-medium">{stats.evaluated_thoughts}</span> / {stats.total_thoughts} evaluated
            </span>
            <span>•</span>
            <span>
              <span className="font-medium">{stats.successful_tools}</span> / {stats.tool_calls} tools succeeded
            </span>
            {stats.tool_calls > 0 && (
              <>
                <span>•</span>
                <span className={stats.successful_tools / stats.tool_calls > 0.7 ? 'text-green-600' : stats.successful_tools / stats.tool_calls > 0.4 ? 'text-yellow-600' : 'text-red-600'}>
                  {((stats.successful_tools / stats.tool_calls) * 100).toFixed(0)}% success rate
                </span>
              </>
            )}
          </div>
        )}
      </div>

      {/* Legend */}
      <div className="px-3 py-2 bg-gray-100 border-b text-xs flex items-center gap-3">
        <span className="font-medium text-gray-600">Legend:</span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded-full bg-green-500"></span>
          <span className="text-gray-600">Best Path</span>
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded-full bg-blue-400"></span>
          <span className="text-gray-600">Beam Candidate</span>
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded-full bg-orange-400"></span>
          <span className="text-gray-600">Backtracked</span>
        </span>
      </div>

      <div className="thought-tree-content p-4 overflow-auto">
        {treeStructure.map((node: ThoughtNode) => (
          <ThoughtTreeNode
            key={node.id}
            node={node}
            level={0}
            bestPathIds={bestPathIds}
            beamCandidates={beamCandidates}
          />
        ))}
      </div>
    </div>
  )
}

interface ThoughtTreeNodeProps {
  node: ThoughtNode
  level: number
  bestPathIds: string[]
  beamCandidates: string[][]
}

function ThoughtTreeNode({ node, level, bestPathIds, beamCandidates }: ThoughtTreeNodeProps) {
  const statusColor = getStatusColor(node.status)
  const indent = level * 24

  // Determine path highlighting
  const isBestPath = bestPathIds.includes(node.id)
  const beamRank = getBeamRank(node.id, beamCandidates)

  return (
    <div
      className={`thought-node mb-3 rounded-lg transition-all ${
        isBestPath ? 'bg-green-50 border-l-4 border-green-500' :
        beamRank !== undefined ? 'bg-blue-50 border-l-4 border-blue-400' :
        'bg-gray-50 border-l-4 border-gray-300'
      }`}
      style={{
        marginLeft: `${indent}px`,
        paddingLeft: '12px',
        paddingRight: '12px',
        paddingTop: '8px',
        paddingBottom: '8px'
      }}
      data-testid="thought-node"
    >
      {/* Header: Status + Beam Rank */}
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          {/* Status Badge */}
          <span className={`text-xs px-2 py-0.5 rounded font-medium ${
            node.status === 'selected' ? 'bg-green-100 text-green-800' :
            node.status === 'evaluated' ? 'bg-blue-100 text-blue-800' :
            node.status === 'backtracked' ? 'bg-orange-100 text-orange-800' :
            'bg-gray-100 text-gray-600'
          }`}>
            {capitalizeStatus(node.status)}
          </span>

          {/* Beam Rank Badge */}
          {beamRank !== undefined && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-blue-100 text-blue-700 font-medium">
              #{beamRank + 1}
            </span>
          )}

          {/* Best Path Badge */}
          {isBestPath && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-700 font-medium">
              ★ Best
            </span>
          )}
        </div>

        {/* Score */}
        {node.score !== undefined && (
          <div className={`text-sm font-bold ${
            node.score >= 7 ? 'text-green-700' :
            node.score >= 5 ? 'text-blue-700' :
            'text-gray-600'
          }`}>
            {node.score.toFixed(1)}
          </div>
        )}
      </div>

      {/* Content */}
      <div className="thought-content text-sm text-gray-800 mb-2">
        {truncateText(node.content, 120)}
      </div>

      {/* Tool Calls (NEW) */}
      {node.tool_calls && node.tool_calls.length > 0 && (
        <div className="tool-calls mb-2">
          <div className="text-xs text-gray-500 mb-1">Tools:</div>
          {node.tool_calls.map((call, idx) => (
            <div key={idx} className="text-xs bg-gray-100 px-2 py-1 rounded mb-1 font-mono">
              {call.name}({formatToolArgs(call.args)})
            </div>
          ))}
        </div>
      )}

      {/* Tool Results (NEW) */}
      {node.tool_results && node.tool_results.length > 0 && (
        <div className="tool-results mb-2">
          <div className="text-xs text-gray-500 mb-1">Results:</div>
          {node.tool_results.map((result, idx) => (
            <div
              key={idx}
              className={`text-xs px-2 py-1 rounded mb-1 flex items-center gap-2 ${
                result.status === 'success' ? 'bg-green-50 text-green-700' :
                result.status === 'error' ? 'bg-red-50 text-red-700' :
                'bg-yellow-50 text-yellow-700'
              }`}
            >
              <span className="font-medium">{result.tool}</span>
              <span className="capitalize">{result.status}</span>
            </div>
          ))}
        </div>
      )}

      {/* Children */}
      {node.children && node.children.length > 0 && (
        <div className="thought-children">
          {node.children.map(child => (
            <ThoughtTreeNode
              key={child.id}
              node={child}
              level={level + 1}
              bestPathIds={bestPathIds}
              beamCandidates={beamCandidates}
            />
          ))}
        </div>
      )}
    </div>
  )
}

// Utility functions

function countNodes(nodes: ThoughtNode[]): number {
  let count = 0
  function traverse(nodeList: ThoughtNode[]) {
    for (const node of nodeList) {
      count += 1
      if (node.children) {
        traverse(node.children)
      }
    }
  }
  traverse(nodes)
  return count
}

function getBeamRank(nodeId: string, beamCandidates: string[][]): number | undefined {
  // Find which beam path this node is in and return its rank
  for (let rank = 0; rank < beamCandidates.length; rank++) {
    if (beamCandidates[rank].includes(nodeId)) {
      return rank
    }
  }
  return undefined
}

function getStatusColor(status: string): string {
  const colors = {
    pending: '#9CA3AF',      // gray
    evaluated: '#3B82F6',    // blue
    selected: '#10B981',     // green
    pruned: '#EF4444',       // red
    backtracked: '#F97316'   // orange (NEW)
  }
  return colors[status as keyof typeof colors] || colors.pending
}

function capitalizeStatus(status: string): string {
  return status.charAt(0).toUpperCase() + status.slice(1)
}

function truncateText(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text
  return text.substring(0, maxLength) + '...'
}

function formatToolArgs(args: Record<string, any>): string {
  const keys = Object.keys(args)
  if (keys.length === 0) return ''
  if (keys.length === 1) {
    const val = args[keys[0]]
    return typeof val === 'string' ? `"${val.length > 20 ? val.substring(0, 20) + '...' : val}"` : '...'
  }
  return `{${keys.length} args}`
}

// Hook for managing thought tree state
export function useThoughtTree() {
  const [treeEvents, setTreeEvents] = React.useState<ToTTreeUpdateEvent[]>([])

  const addTreeEvent = (event: ToTTreeUpdateEvent) => {
    if (event.type === 'tot_tree_update') {
      setTreeEvents(prev => [...prev, event])
    }
  }

  const clearTree = () => {
    setTreeEvents([])
  }

  return {
    treeEvents,
    addTreeEvent,
    clearTree,
    latestTree: treeEvents.length > 0 ? treeEvents[treeEvents.length - 1].tree : null
  }
}
