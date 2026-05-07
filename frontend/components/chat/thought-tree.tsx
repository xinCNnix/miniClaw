/**
 * Thought Tree — Progressive Card Display
 *
 * Shows one depth level at a time. When evaluation picks the best thought,
 * the display replaces with the next depth's candidates.
 * A breadcrumb trail shows previous best thoughts.
 */

'use client'

import React, { useMemo, memo } from 'react'
import type { ThinkingEvent } from '@/types/chat'
import { useTranslation } from '@/hooks/use-translation.hook'

// Types
interface ThoughtNode {
  id: string
  content: string
  parent_id?: string
  score?: number
  status: 'pending' | 'evaluated' | 'selected' | 'pruned' | 'executing' | 'done'
  skill_name?: string
  tool_calls?: Array<{ name: string; args: Record<string, unknown> }>
  tool_statuses?: Array<{ tool: string; status: string }>
  children: ThoughtNode[]
}

interface ThoughtTreeProps {
  events: ThinkingEvent[]
  maxHeight?: string
  'data-testid'?: string
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

const ThoughtTreeInner = ({ events, maxHeight = '400px', 'data-testid': testId }: ThoughtTreeProps) => {
  const { t } = useTranslation()
  const {
    tree,
    bestPathSet,
    activeBeamSet,
    beamCount,
    maxDepth,
    currentDepth,
    isComplete,
    currentThoughts,
    bestHistory,
    phaseLabel,
  } = useMemo(() => extractState(events), [events])

  // No tree data yet
  if (!tree || tree.length === 0) {
    return (
      <div className="thought-tree-container mb-3 rounded-xl bg-white/60 backdrop-blur border border-green-200/50" style={{ maxHeight }} data-testid={testId}>
        <div className="text-sm text-gray-500 p-4">
          {t('thought_tree.waiting')}
        </div>
      </div>
    )
  }

  // --- Completion view ---
  if (isComplete && bestHistory.length > 0) {
    return (
      <div className="thought-tree-container mb-3 rounded-xl bg-white/60 backdrop-blur border border-green-200/50" data-testid={testId}>
        <Header step={currentDepth + 1} total={maxDepth} label={t('thought_tree.complete')} labelKey="complete" />
        <div className="p-3 space-y-1">
          {bestHistory.map((node, idx) => (
            <div key={node.id} className="flex items-center gap-2 text-sm py-1">
              <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-green-100 text-green-700 text-xs font-medium flex-shrink-0">
                {idx + 1}
              </span>
              <span className="flex-1 text-gray-700 truncate">{truncateText(node.content, 80)}</span>
              <ToolBadge toolCalls={node.tool_calls} skillName={node.skill_name} toolStatuses={node.tool_statuses} />
              {node.score != null && <ScoreBadge score={node.score} />}
            </div>
          ))}
        </div>
      </div>
    )
  }

  // --- Progressive card view ---
  return (
    <div className="thought-tree-container mb-3 rounded-xl bg-white/60 backdrop-blur border border-green-200/50" style={{ maxHeight }} data-testid={testId}>
      <Header step={currentDepth + 1} total={maxDepth} label={t(`thought_tree.${phaseLabelKey(phaseLabel)}`)} labelKey={phaseLabelKey(phaseLabel)} />

      {/* Breadcrumb — previous best thoughts */}
      {bestHistory.length > 0 && <Breadcrumb history={bestHistory} />}

      {/* Beam indicator (Phase 10) */}
      {beamCount > 1 && (
        <div className="px-3 pt-1 pb-1">
          <span className="text-xs font-medium text-blue-700 bg-blue-50 px-2 py-0.5 rounded-full">
            {beamCount} beams active
          </span>
        </div>
      )}

      {/* Current depth cards */}
      <div className="px-3 pb-3 space-y-2 overflow-auto">
        {currentThoughts.map((node) => {
          const isBest = bestPathSet.has(node.id)
          const isActive = activeBeamSet.has(node.id)
          return (
            <ThoughtCard key={node.id} node={node} isBest={isBest} isActive={isActive} />
          )
        })}
      </div>
    </div>
  )
}

export const ThoughtTree = memo(ThoughtTreeInner)

// ---------------------------------------------------------------------------
// Sub-components// ---------------------------------------------------------------------------

function Header({ step, total, label, labelKey }: { step: number; total: number; label: string; labelKey: string }) {
  return (
    <div className="flex items-center justify-between px-3 py-2 border-b border-green-100">
      <div className="flex items-center gap-2">
        {/* Step dots */}
        <div className="flex gap-1">
          {Array.from({ length: total }, (_, i) => (
            <div
              key={i}
              className={`w-2 h-2 rounded-full ${
                i < step ? 'bg-green-500' : 'bg-green-200'
              }`}
            />
          ))}
        </div>
        <span className="text-xs font-medium text-green-800">
          Depth {step - 1}/{total}
        </span>
      </div>
      <span className={`text-xs px-2 py-0.5 rounded-full ${
        labelKey === 'complete'
          ? 'bg-green-100 text-green-700'
          : labelKey === 'evaluating'
            ? 'bg-amber-50 text-amber-600'
            : 'bg-green-50 text-green-600'
      }`}>
        {label}
      </span>
    </div>
  )
}

function Breadcrumb({ history }: { history: ThoughtNode[] }) {
  return (
    <div className="flex items-center gap-1 px-3 py-1.5 bg-green-50/50 border-b border-green-100 text-xs text-green-700 overflow-x-auto">
      {history.map((node, idx) => (
        <React.Fragment key={node.id}>
          {idx > 0 && <span className="text-green-300 flex-shrink-0">&rsaquo;</span>}
          <span className="whitespace-nowrap">
            D{idx + 1}: {truncateText(node.content, 30)}
            {node.score != null && <span className="ml-1 text-green-500">({node.score.toFixed(1)})</span>}
          </span>
        </React.Fragment>
      ))}
    </div>
  )
}

function ThoughtCard({ node, isBest, isActive }: { node: ThoughtNode; isBest: boolean; isActive: boolean }) {
  const { t } = useTranslation()
  return (
    <div
      className={`rounded-lg bg-white/80 p-3 transition-all ${
        isBest
          ? 'border-l-4 border-green-500 bg-green-50/60 shadow-sm'
          : isActive
            ? 'border-l-4 border-blue-400 bg-blue-50/40'
            : 'border border-gray-100 opacity-40'
      }`}
    >
      {/* Row 1: content + best indicator */}
      <div className="flex items-start gap-2">
        {isBest && (
          <span className="text-green-500 text-xs mt-0.5 flex-shrink-0 font-bold">&#9733;</span>
        )}
        <p className="flex-1 text-sm text-gray-800 leading-relaxed">
          {truncateText(node.content, 120)}
        </p>
      </div>

      {/* Row 2: tool badge + score */}
      <div className="flex items-center gap-2 mt-2">
        <ToolBadge toolCalls={node.tool_calls} skillName={node.skill_name} toolStatuses={node.tool_statuses} />
        {node.score != null ? (
          <ScoreBadge score={node.score} />
        ) : (
          <span className="text-xs text-gray-300 animate-pulse">{t('thought_tree.pending')}</span>
        )}
      </div>
    </div>
  )
}

function ToolBadge({ toolCalls, skillName, toolStatuses }: {
  toolCalls?: ThoughtNode['tool_calls']
  skillName?: string
  toolStatuses?: ThoughtNode['tool_statuses']
}) {
  if (!toolCalls || toolCalls.length === 0) return null

  const hasError = toolStatuses?.some(ts => ts.status === 'error')
  const hasSuccess = toolStatuses?.some(ts => ts.status === 'success')
  const label = skillName || toolCalls[0].name

  if (toolCalls.length === 1) {
    return (
      <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-mono ${
        hasError ? 'bg-red-50 text-red-700' : hasSuccess ? 'bg-green-50 text-green-700' : 'bg-gray-50 text-gray-700'
      }`}>
        {hasError ? '✗' : hasSuccess ? '✓' : '○'} {label}
      </span>
    )
  }

  return (
    <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-mono ${
      hasError ? 'bg-red-50 text-red-700' : 'bg-green-50 text-green-700'
    }`}>
      {skillName || `${toolCalls.length} tools`}
    </span>
  )
}

function ScoreBadge({ score }: { score: number }) {
  const color = getScoreColor(score)
  return (
    <span className={`text-xs font-medium ${color}`}>
      {score.toFixed(1)}/10
    </span>
  )
}

// ---------------------------------------------------------------------------
// State extraction
// ---------------------------------------------------------------------------

interface TreeState {
  tree: ThoughtNode[] | null
  bestPathSet: Set<string>
  activeBeamSet: Set<string>   // Phase 10: all IDs on active beams (top 3)
  beamCount: number            // Phase 10: number of active beams
  maxDepth: number
  currentDepth: number
  isComplete: boolean
  currentThoughts: ThoughtNode[]
  bestHistory: ThoughtNode[]
  phaseLabel: string
}

function extractState(events: ThinkingEvent[]): TreeState {
  let tree: ThoughtNode[] | null = null
  let bestPath: string[] = []
  let activeBeams: string[][] = []
  let maxDepth = 3
  let maxGeneratedDepth = -1
  let isComplete = false
  let hasEvaluated = false

  for (let i = events.length - 1; i >= 0; i--) {
    const e = events[i] as Record<string, unknown>
    const type = e.type as string

    if (!tree && type === 'tot_tree_update' && Array.isArray(e.tree)) {
      tree = e.tree as ThoughtNode[]
    }
    if (bestPath.length === 0 && type === 'tot_thoughts_evaluated' && Array.isArray(e.best_path)) {
      bestPath = e.best_path as string[]
      hasEvaluated = true
      // Phase 10: extract beam info
      if (Array.isArray(e.active_beams) && (e.active_beams as string[][]).length > 0) {
        activeBeams = e.active_beams as string[][]
      }
    }
    if (type === 'tot_reasoning_start' && typeof e.max_depth === 'number') {
      maxDepth = e.max_depth
    }
    if (type === 'tot_thoughts_generated' && typeof e.depth === 'number') {
      maxGeneratedDepth = Math.max(maxGeneratedDepth, e.depth as number)
    }
    if (type === 'tot_reasoning_complete' || type === 'tot_termination') {
      isComplete = true
    }
  }

  // 去重 tree 节点（防御性）
  if (tree) {
    tree = dedupTree(tree)
  }

  const bestPathSet = new Set(bestPath)

  // Phase 10: Build activeBeamSet from top-3 beams (backward compat: fallback to bestPathSet)
  const topBeams = activeBeams.slice(0, 3)
  const activeBeamSet = topBeams.length > 0
    ? new Set(topBeams.flatMap(beam => beam))
    : bestPathSet  // backward compat: no beam info → treat best_path as active
  const beamCount = topBeams.length

  const currentDepth = maxGeneratedDepth >= 0 ? maxGeneratedDepth : 0
  const currentThoughts = tree ? getThoughtsAtDepth(tree, currentDepth) : []
  const bestHistory = tree ? getBestHistory(tree, bestPathSet, currentDepth) : []

  // Determine phase label
  let phaseLabel = 'Generating...'
  if (isComplete) {
    phaseLabel = 'Complete'
  } else if (currentThoughts.length > 0 && currentThoughts.some(t => t.score != null)) {
    phaseLabel = hasEvaluated ? 'Evaluated' : 'Evaluating...'
  }

  return { tree, bestPathSet, activeBeamSet, beamCount, maxDepth, currentDepth, isComplete, currentThoughts, bestHistory, phaseLabel }
}

/** Map phaseLabel to i18n key */
function phaseLabelKey(label: string): string {
  switch (label) {
    case 'Complete': return 'complete'
    case 'Generating...': return 'generating'
    case 'Evaluating...': return 'evaluating'
    case 'Evaluated': return 'evaluated'
    default: return 'generating'
  }
}

// ---------------------------------------------------------------------------
// Helper functions
// ---------------------------------------------------------------------------

/** Extract thoughts at a specific depth from the hierarchical tree */
function getThoughtsAtDepth(
  nodes: ThoughtNode[],
  targetDepth: number,
  currentDepth: number = 0
): ThoughtNode[] {
  const results: ThoughtNode[] = []

  for (const node of nodes) {
    if (currentDepth === targetDepth) {
      results.push(node)
    } else if (node.children && node.children.length > 0) {
      // 递归搜索所有子分支，不提前 return
      const childResults = getThoughtsAtDepth(
        node.children,
        targetDepth,
        currentDepth + 1
      )
      results.push(...childResults)
    }
  }

  return results
}

/** 去重 tree 节点（防御性，防止重复 id） */
function dedupTree(nodes: ThoughtNode[]): ThoughtNode[] {
  const seen = new Set<string>()
  return nodes
    .filter(n => {
      if (seen.has(n.id)) return false
      seen.add(n.id)
      return true
    })
    .map(n => ({
      ...n,
      children: n.children && n.children.length > 0
        ? dedupTree(n.children)
        : n.children,
    }))
}

/** Collect best thought from each previous depth (for breadcrumb) */
function getBestHistory(
  nodes: ThoughtNode[],
  bestPathSet: Set<string>,
  currentDepth: number
): ThoughtNode[] {
  const history: ThoughtNode[] = []
  let currentNodes = nodes
  for (let d = 0; d < currentDepth && currentNodes.length > 0; d++) {
    const best = currentNodes.find(n => bestPathSet.has(n.id))
    if (best) {
      history.push(best)
      currentNodes = best.children || []
    } else {
      break
    }
  }
  return history
}

/** Green gradient: high score → deep green, low score → pale */
function getScoreColor(score: number): string {
  if (score >= 8.0) return 'text-green-700 font-semibold'
  if (score >= 6.0) return 'text-green-600'
  if (score >= 4.0) return 'text-green-500'
  return 'text-green-400'
}

function truncateText(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text
  return text.substring(0, maxLength) + '...'
}
