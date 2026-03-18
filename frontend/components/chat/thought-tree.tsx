/**
 * Thought Tree Visualization Component
 *
 * Displays the Tree of Thoughts reasoning process with an interactive tree visualization.
 */

'use client'

import React, { useMemo } from 'react'

// Types
interface ThoughtNode {
  id: string
  content: string
  parent_id?: string
  score?: number
  status: 'pending' | 'evaluated' | 'selected' | 'pruned'
  children: ThoughtNode[]
}

interface ToTTreeUpdateEvent {
  type: 'tot_tree_update'
  tree: ThoughtNode[]
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
      <div className="thought-tree-header p-2 bg-gray-50 border-b">
        <h3 className="text-sm font-medium">Reasoning Tree</h3>
        <span className="text-xs text-gray-500 ml-2">
          {countNodes(treeStructure)} thoughts
        </span>
      </div>

      <div className="thought-tree-content p-4 overflow-auto">
        {treeStructure.map((node: ThoughtNode) => (
          <ThoughtTreeNode key={node.id} node={node} level={0} />
        ))}
      </div>
    </div>
  )
}

interface ThoughtTreeNodeProps {
  node: ThoughtNode
  level: number
}

function ThoughtTreeNode({ node, level }: ThoughtTreeNodeProps) {
  const statusColor = getStatusColor(node.status)
  const indent = level * 20

  return (
    <div
      className="thought-node mb-2"
      style={{
        marginLeft: `${indent}px`,
        borderLeft: `3px solid ${statusColor}`,
        paddingLeft: '8px'
      }}
      data-testid="thought-node"
    >
      <div className="thought-content text-sm">
        {truncateText(node.content, 100)}
      </div>

      {node.score !== undefined && (
        <div className="thought-score text-xs text-gray-500 mt-1">
          Score: {node.score.toFixed(2)}
        </div>
      )}

      <div className={`thought-status text-xs mt-1 ${
        node.status === 'selected' ? 'text-green-600' :
        node.status === 'pruned' ? 'text-red-600' :
        'text-gray-500'
      }`}>
        {capitalizeStatus(node.status)}
      </div>

      {node.children && node.children.length > 0 && (
        <div className="thought-children mt-2">
          {node.children.map(child => (
            <ThoughtTreeNode
              key={child.id}
              node={child}
              level={level + 1}
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

function getStatusColor(status: string): string {
  const colors = {
    pending: '#9CA3AF',    // gray
    evaluated: '#3B82F6',  // blue
    selected: '#10B981',   // green
    pruned: '#EF4444'      // red
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
