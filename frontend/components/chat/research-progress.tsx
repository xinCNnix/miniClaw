/**
 * Research Progress Visualization
 *
 * Shows progress of deep research with stage indicators.
 */

'use client'

import React from 'react'

interface ResearchProgressProps {
  currentStage: string
  totalStages: number
  currentDepth: number
  maxDepth: number
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
  maxDepth
}: ResearchProgressProps) {
  // Find current stage index
  const currentStageIndex = RESEARCH_STAGES.findIndex(s => s.id === currentStage)
  const displayStages = RESEARCH_STAGES.slice(0, totalStages)

  return (
    <div className="research-progress p-4 bg-gray-50 border rounded">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium">Research Progress</h3>
        <span className="text-xs text-gray-500">
          Step {currentDepth + 1} of {maxDepth}
        </span>
      </div>

      {/* Progress Bar */}
      <div className="mb-4">
        <div className="w-full bg-gray-200 rounded-full h-2">
          <div
            className="bg-blue-500 h-2 rounded-full transition-all duration-300"
            style={{ width: `${((currentDepth + 1) / maxDepth) * 100}%` }}
            data-testid="research-progress-bar"
          />
        </div>
      </div>

      {/* Stage Indicators */}
      <div className="space-y-2">
        {displayStages.map((stage, index) => {
          const isCompleted = index < currentStageIndex
          const isCurrent = index === currentStageIndex
          const isPending = index > currentStageIndex

          return (
            <div
              key={stage.id}
              className={`
                flex items-start p-2 rounded text-sm
                ${isCompleted ? 'bg-green-50 text-green-800' : ''}
                ${isCurrent ? 'bg-blue-50 text-blue-800 border border-blue-200' : ''}
                ${isPending ? 'bg-gray-50 text-gray-500' : ''}
              `}
              data-testid={`research-stage-${stage.id}`}
            >
              {/* Status Icon */}
              <div className="flex-shrink-0 mr-2">
                {isCompleted && (
                  <svg className="w-4 h-4 text-green-600" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                  </svg>
                )}
                {isCurrent && (
                  <svg className="w-4 h-4 text-blue-600 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                )}
                {isPending && (
                  <div className="w-4 h-4 rounded-full border-2 border-gray-300" />
                )}
              </div>

              {/* Stage Info */}
              <div className="flex-grow">
                <div className="font-medium">{stage.name}</div>
                <div className="text-xs opacity-75">{stage.description}</div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
