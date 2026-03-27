/**
 * Research Progress Visualization (Phase 4 Enhanced)
 *
 * Shows progress of deep research with:
 * - Depth progress bar
 * - Research stages
 * - Statistics (thoughts, tools, success rate)
 * - Reasoning trajectory timeline
 */

'use client'

import React from 'react'

interface ResearchProgressProps {
  currentStage: string
  totalStages: number
  currentDepth: number
  maxDepth: number
  stats?: {                    // NEW: Statistics
    total_thoughts?: number
    evaluated_thoughts?: number
    tool_calls?: number
    successful_tools?: number
    average_score?: number
  }
  reasoningTrace?: {            // NEW: Reasoning trajectory
    type: string
    depth?: number
    count?: number
    timestamp?: number
  }[]
  bestPath?: string[]           // NEW: Best path IDs
  thoughts?: {                  // NEW: All thoughts
    id: string
    content: string
    score?: number
    status: string
  }[]
}

interface Stage {
  id: string
  name: string
  description: string
}

const RESEARCH_STAGES: Stage[] = [
  { id: 'initial_exploration', name: 'Initial Exploration', description: 'Broad overview of topic' },
  { id: 'source_identification', name: 'Source Identification', description: 'Finding relevant sources' },
  { id: 'information_extraction', name: 'Information Extraction', description: 'Gathering detailed information' },
  { id: 'cross_referencing', name: 'Cross-Referencing', description: 'Comparing and contrasting sources' },
  { id: 'synthesis', name: 'Synthesis', description: 'Integrating findings' },
  { id: 'refinement', name: 'Refinement', description: 'Polishing final report' }
]

export function ResearchProgress({
  currentStage,
  totalStages,
  currentDepth,
  maxDepth,
  stats,
  reasoningTrace = [],
  bestPath = [],
  thoughts = []
}: ResearchProgressProps) {
  // Find current stage index
  const currentStageIndex = RESEARCH_STAGES.findIndex(s => s.id === currentStage)
  const displayStages = RESEARCH_STAGES.slice(0, totalStages)

  // Calculate progress percentage
  const depthProgress = ((currentDepth + 1) / maxDepth) * 100

  // Get best path thoughts
  const bestPathThoughts = thoughts.filter(t => bestPath.includes(t.id))

  return (
    <div className="research-progress p-4 bg-gradient-to-br from-gray-50 to-blue-50 border border-gray-200 rounded-lg">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-gray-700">Research Progress (ToT)</h3>
        <span className="text-xs text-gray-500">
          Depth {currentDepth + 1} / {maxDepth}
        </span>
      </div>

      {/* Depth Progress Bar */}
      <div className="mb-4">
        <div className="flex items-center justify-between text-xs text-gray-600 mb-1">
          <span>Exploration Depth</span>
          <span className="font-medium">{depthProgress.toFixed(0)}%</span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-2 overflow-hidden">
          <div
            className="bg-gradient-to-r from-blue-500 to-indigo-500 h-2 rounded-full transition-all duration-500 ease-out"
            style={{ width: `${depthProgress}%` }}
            data-testid="research-progress-bar"
          />
        </div>
      </div>

      {/* Statistics Cards (NEW) */}
      {stats && (
        <div className="grid grid-cols-4 gap-2 mb-4">
          <StatCard
            label="Thoughts"
            value={`${stats.evaluated_thoughts || 0}/${stats.total_thoughts || 0}`}
            color="blue"
            sublabel="evaluated"
          />
          <StatCard
            label="Tools"
            value={`${stats.successful_tools || 0}/${stats.tool_calls || 0}`}
            color="green"
            sublabel="succeeded"
          />
          <StatCard
            label="Success Rate"
            value={(stats.tool_calls || 0) > 0 ? `${((stats.successful_tools || 0) / (stats.tool_calls || 1) * 100).toFixed(0)}%` : 'N/A'}
            color="purple"
            sublabel="of tools"
          />
          <StatCard
            label="Avg Score"
            value={stats.average_score ? stats.average_score.toFixed(1) : 'N/A'}
            color="indigo"
            sublabel="quality"
          />
        </div>
      )}

      {/* Stage Indicators */}
      <div className="space-y-2 mb-4">
        {displayStages.map((stage, index) => {
          const isCompleted = index < currentStageIndex
          const isCurrent = index === currentStageIndex
          const isPending = index > currentStageIndex

          return (
            <div
              key={stage.id}
              className={`
                flex items-start p-2 rounded-lg text-sm transition-all
                ${isCompleted ? 'bg-green-50 text-green-800' : ''}
                ${isCurrent ? 'bg-blue-50 text-blue-800 border-2 border-blue-300 shadow-sm' : ''}
                ${isPending ? 'bg-gray-50 text-gray-500' : ''}
              `}
              data-testid={`research-stage-${stage.id}`}
            >
              {/* Status Icon */}
              <div className="flex-shrink-0 mr-3">
                {isCompleted && (
                  <svg className="w-5 h-5 text-green-600" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                  </svg>
                )}
                {isCurrent && (
                  <div className="relative">
                    <svg className="w-5 h-5 text-blue-600 animate-pulse" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-13a1 1 0 10-2 1 1 0 012 0zm0 4a1 1 0 10-2 1 1 0 012 0zm0 4a1 1 0 10-2 1 1 0 012 0z" clipRule="evenodd" />
                    </svg>
                    <div className="absolute inset-0 rounded-full border-2 border-blue-400 animate-ping"></div>
                  </div>
                )}
                {isPending && (
                  <div className="w-5 h-5 rounded-full border-2 border-dashed border-gray-300"></div>
                )}
              </div>

              {/* Stage Info */}
              <div className="flex-grow">
                <div className="font-medium">{stage.name}</div>
                <div className="text-xs opacity-80">{stage.description}</div>
              </div>
            </div>
          )
        })}
      </div>

      {/* Reasoning Trajectory Timeline (NEW) */}
      {reasoningTrace && reasoningTrace.length > 0 && (
        <div className="border-t border-gray-200 pt-3">
          <h4 className="text-xs font-semibold text-gray-600 mb-2">Reasoning Trajectory</h4>
          <div className="space-y-1 max-h-32 overflow-y-auto">
            {reasoningTrace.slice(-5).map((event, idx) => (
              <TimelineEvent key={idx} event={event} />
            ))}
          </div>
        </div>
      )}

      {/* Best Path Preview (NEW) */}
      {bestPathThoughts.length > 0 && (
        <div className="border-t border-gray-200 pt-3">
          <h4 className="text-xs font-semibold text-gray-600 mb-2">Best Path Preview</h4>
          <div className="space-y-1 max-h-32 overflow-y-auto">
            {bestPathThoughts.slice(-5).map((thought, idx) => (
              <div
                key={thought.id}
                className="text-xs p-2 bg-white rounded border border-gray-200"
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="font-medium text-gray-700">Step {idx + 1}</span>
                  {thought.score && (
                    <span className={`font-bold ${
                      thought.score >= 7 ? 'text-green-600' :
                      thought.score >= 5 ? 'text-blue-600' :
                      'text-gray-500'
                    }`}>
                      {thought.score.toFixed(1)}
                    </span>
                  )}
                </div>
                <div className="text-gray-600 truncate">{thought.content}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// NEW: Stat Card Component
interface StatCardProps {
  label: string
  value: string | number
  color: 'blue' | 'green' | 'purple' | 'indigo'
  sublabel: string
}

function StatCard({ label, value, color, sublabel }: StatCardProps) {
  const colorClasses = {
    blue: 'bg-blue-50 text-blue-700 border-blue-200',
    green: 'bg-green-50 text-green-700 border-green-200',
    purple: 'bg-purple-50 text-purple-700 border-purple-200',
    indigo: 'bg-indigo-50 text-indigo-700 border-indigo-200'
  }

  return (
    <div className={`p-2 rounded-lg border ${colorClasses[color]} text-center`}>
      <div className="text-xs text-gray-600 mb-1">{label}</div>
      <div className="text-lg font-bold">{value}</div>
      <div className="text-xs opacity-75">{sublabel}</div>
    </div>
  )
}

// NEW: Timeline Event Component
interface TimelineEventProps {
  event: {
    type: string
    depth?: number
    count?: number
    timestamp?: number
  }
}

function TimelineEvent({ event }: TimelineEventProps) {
  const getEventIcon = () => {
    switch (event.type) {
      case 'thoughts_generated':
        return (
          <svg className="w-3 h-3 text-blue-500" fill="currentColor" viewBox="0 0 20 20">
            <path d="M10 6a2 2 0 110-4 2 2 0 014 0zm0 6a2 2 0 110-4 2 2 0 014 0z" />
          </svg>
        )
      case 'thoughts_evaluated':
        return (
          <svg className="w-3 h-3 text-green-500" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M6.267 3.455a3.066 3.066 0 001.745-.723 3.066 3.066 0 013.976 0 3.066 3.066 0 001.745.723 3.066 3.066 0 00-1.745.723 3.066 3.066 0 00-3.976 0 3.066 3.066 0 00-1.745-.723zm0 3.066a3.066 3.066 0 001.745-.723 3.066 3.066 0 013.976 0 3.066 3.066 0 001.745.723 3.066 3.066 0 00-1.745.723 3.066 3.066 0 00-3.976 0 3.066 3.066 0 00-1.745-.723zm0 3.066a3.066 3.066 0 001.745-.723 3.066 3.066 0 013.976 0 3.066 3.066 0 001.745.723 3.066 3.066 0 00-1.745.723 3.066 3.066 0 00-3.976 0 3.066 3.066 0 00-1.745-.723z" clipRule="evenodd" />
          </svg>
        )
      case 'thought_execution':
        return (
          <svg className="w-3 h-3 text-purple-500" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.02 1.02 0 00-1.29.63c-.38 1.56.52 2.6 2.98 0 .63.63 2.6-.52 2.98-1.56.63-1.56-.52-2.6-2.98 0zm7.03-.08a1.02 1.02 0 00-1.29-.62c-.38-1.56.52-2.6 1.98-2.98.63-1.56-.52-2.6-1.98 0a1.02 1.02 0 00-1.29.62c.38 1.56-.52 2.6-1.98 2.98-.63 1.56.52 2.6 1.98 0zm7.03-.08a1.02 1.02 0 00-1.29-.62c-.38-1.56.52-2.6 1.98-2.98.63-1.56-.52-2.6-1.98 0a1.02 1.02 0 00-1.29.62c.38 1.56-.52 2.6-1.98 2.98-.63 1.56.52 2.6 1.98 0z" clipRule="evenodd" />
          </svg>
        )
      case 'termination':
        return (
          <svg className="w-3 h-3 text-red-500" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414-1.414L8 6.586 6.707 7.793a1 1 0 00-1.414 1.414l1 1a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
          </svg>
        )
      default:
        return (
          <div className="w-3 h-3 rounded-full bg-gray-300"></div>
        )
    }
  }

  return (
    <div className="flex items-start gap-2 text-xs">
      {getEventIcon()}
      <div className="flex-grow">
        <span className="font-medium text-gray-700">
          {event.type.replace(/_/g, ' ').replace(/\b\w/g, w => w.charAt(0).toUpperCase() + w.slice(1))}
        </span>
        {event.depth !== undefined && (
          <span className="text-gray-500 ml-1">(Depth {event.depth})</span>
        )}
        {event.count !== undefined && (
          <span className="text-gray-500 ml-1">({event.count} items)</span>
        )}
      </div>
    </div>
  )
}
