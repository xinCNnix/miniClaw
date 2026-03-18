/**
 * Research Mode UI Component
 *
 * Provides controls for switching to research mode and selecting thinking mode.
 */

'use client'

import React, { useState } from 'react'
import { cn } from '@/lib/utils'
import { useTranslation } from '@/hooks/use-translation.hook'

type ThinkingMode = 'heuristic' | 'analytical' | 'exhaustive'

interface ResearchModeProps {
  onModeChange?: (mode: 'chat' | 'research') => void
  onThinkingModeChange?: (thinkingMode: ThinkingMode, branchingFactor?: number) => void
  disabled?: boolean
}

// Default branching factor for each mode
const DEFAULT_BRANCHING: Record<ThinkingMode, number> = {
  heuristic: 3,
  analytical: 4,
  exhaustive: 6
}

// Depth for each mode
const MODE_DEPTH: Record<ThinkingMode, number> = {
  heuristic: 2,
  analytical: 4,
  exhaustive: 7
}

export function ResearchModeToggle({
  onModeChange,
  onThinkingModeChange,
  disabled = false
}: ResearchModeProps) {
  const { t, locale } = useTranslation()
  const [mode, setMode] = useState<'chat' | 'research'>('chat')
  const [thinkingMode, setThinkingMode] = useState<ThinkingMode>('heuristic')
  const [branching, setBranching] = useState<number>(DEFAULT_BRANCHING.heuristic)
  const [isExpanded, setIsExpanded] = useState(false)

  const handleModeToggle = () => {
    const newMode = mode === 'chat' ? 'research' : 'chat'
    setMode(newMode)
    // Auto-expand when enabling research mode
    if (newMode === 'research') {
      setIsExpanded(true)
    }
    onModeChange?.(newMode)
  }

  const handleThinkingModeChange = (newMode: ThinkingMode) => {
    setThinkingMode(newMode)
    // Reset to default branching factor for this mode
    setBranching(DEFAULT_BRANCHING[newMode])
    onThinkingModeChange?.(newMode, DEFAULT_BRANCHING[newMode])
  }

  const handleBranchingChange = (newBranching: number) => {
    setBranching(newBranching)
    onThinkingModeChange?.(thinkingMode, newBranching)
  }

  const toggleExpand = () => {
    if (mode === 'research') {
      setIsExpanded(!isExpanded)
    }
  }

  return (
    <div className="research-mode-controls">
      {/* Compact Header - Always Visible */}
      <div className="flex items-center justify-between gap-3">
        <button
          onClick={toggleExpand}
          disabled={disabled || mode === 'chat'}
          className={cn(
            "flex items-center gap-2 flex-1 transition-opacity",
            mode === 'chat' && "opacity-50 cursor-not-allowed"
          )}
        >
          <div className={cn(
            "w-2 h-2 rounded-full transition-all duration-300",
            mode === 'research' ? "bg-[var(--ink-green)] shadow-lg shadow-[var(--ink-green)]/30" : "bg-gray-300"
          )} />
          <span className="text-sm font-medium text-gray-700">{t('research_mode.title')}</span>
          {mode === 'research' && (
            <svg
              className={cn(
                "w-4 h-4 text-gray-500 transition-transform duration-200",
                isExpanded && "rotate-180"
              )}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          )}
        </button>

        <button
          onClick={handleModeToggle}
          disabled={disabled}
          data-testid="research-mode-toggle"
          className={cn(
            "relative inline-flex h-6 w-11 items-center rounded-full transition-all duration-300 ease-in-out",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ink-green)] focus-visible:ring-offset-2 flex-shrink-0",
            mode === 'research'
              ? "bg-[var(--ink-green)]"
              : "bg-gray-300 hover:bg-gray-400",
            disabled && "opacity-50 cursor-not-allowed"
          )}
        >
          <span className={cn(
            "inline-block h-4 w-4 transform rounded-full bg-white transition-transform duration-300 ease-in-out shadow-sm",
            mode === 'research' ? "translate-x-6" : "translate-x-1"
          )} />
        </button>
      </div>

      {/* Collapsible Content */}
      {mode === 'research' && isExpanded && (
        <div className="research-options mt-3 animate-in slide-in-from-top-2 fade-in duration-300">
          <label className="block text-xs font-semibold text-gray-600 mb-2 uppercase tracking-wide">
            {t('research_mode.thinking_mode')}
          </label>

          {/* Mode Cards */}
          <div className="space-y-2">
            {renderModeOption('heuristic', thinkingMode, disabled, handleThinkingModeChange, t)}
            {renderModeOption('analytical', thinkingMode, disabled, handleThinkingModeChange, t)}
            {renderModeOption('exhaustive', thinkingMode, disabled, handleThinkingModeChange, t)}
          </div>

          {/* Branching Factor Slider */}
          <div className="mt-4 p-3 bg-white/60 backdrop-blur-sm rounded-lg border border-gray-200/50">
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs font-semibold text-gray-700">{t('research_mode.branching_factor')}</label>
              <span className="text-xs font-mono font-medium text-[var(--ink-green)] bg-[var(--ink-green-light)] px-2 py-0.5 rounded">
                {branching} {t('research_mode.thoughts_per_node')}
              </span>
            </div>
            <input
              type="range"
              min="3"
              max="8"
              step="1"
              value={branching}
              onChange={(e) => handleBranchingChange(parseInt(e.target.value))}
              disabled={disabled}
              data-testid="branching-factor-slider"
              className={cn(
                "w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer",
                "accent-[var(--ink-green)]",
                "disabled:opacity-50 disabled:cursor-not-allowed",
                "[&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4",
                "[&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-[var(--ink-green)]",
                "[&::-webkit-slider-thumb]:shadow-md [&::-webkit-slider-thumb]:cursor-pointer",
                "[&::-webkit-slider-thumb]:transition-transform [&::-webkit-slider-thumb]:hover:scale-110"
              )}
            />
            <div className="flex justify-between mt-1 text-xs text-gray-500">
              <span>3 ({t('research_mode.narrow')})</span>
              <span>8 ({t('research_mode.wide')})</span>
            </div>
          </div>

          {/* Mode Description */}
          <div className="mt-3 p-3 bg-white/60 backdrop-blur-sm rounded-lg border border-gray-200/50">
            <p className="text-xs text-gray-600 leading-relaxed">
              {getThinkingModeDescription(thinkingMode, branching, t)}
            </p>
          </div>
        </div>
      )}
    </div>
  )
}

/**
 * Render a thinking mode option card
 */
function renderModeOption(
  optionMode: ThinkingMode,
  currentMode: ThinkingMode,
  disabled: boolean,
  onChange: (mode: ThinkingMode) => void,
  t: (key: string, params?: Record<string, string | number>) => string
) {
  const isSelected = currentMode === optionMode

  // Get icon from mode
  const getIcon = (mode: ThinkingMode): string => {
    const icons = {
      heuristic: '⚡',
      analytical: '🔬',
      exhaustive: '🌌'
    }
    return icons[mode]
  }

  return (
    <button
      key={optionMode}
      onClick={() => onChange(optionMode)}
      disabled={disabled}
      data-testid={`thinking-mode-${optionMode}`}
      className={cn(
        "w-full text-left p-3 rounded-lg border transition-all duration-200",
        "hover:shadow-md active:scale-[0.98]",
        isSelected
          ? "border-[var(--ink-green)] bg-[var(--ink-green-light)] shadow-sm"
          : "border-gray-200 bg-white/80 hover:bg-gray-50 hover:border-gray-300",
        disabled && "opacity-50 cursor-not-allowed hover:shadow-none hover:scale-100"
      )}
    >
      <div className="flex items-start gap-3">
        <span className="text-xl flex-shrink-0">{getIcon(optionMode)}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <span className="text-sm font-semibold text-gray-900">{t(`research_mode.${optionMode}.name`)}</span>
            <span className="text-xs text-gray-500">·</span>
            <span className="text-xs text-gray-500">{t(`research_mode.${optionMode}.name_en`)}</span>
          </div>
          <p className="text-xs text-gray-600">{t(`research_mode.${optionMode}.short_desc`)}</p>
        </div>
        {isSelected && (
          <div className="flex-shrink-0 w-5 h-5 rounded-full bg-[var(--ink-green)] flex items-center justify-center">
            <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
            </svg>
          </div>
        )}
      </div>
    </button>
  )
}

/**
 * Get thinking mode description with dynamic branching factor
 */
function getThinkingModeDescription(
  mode: ThinkingMode,
  branching: number,
  t: (key: string, params?: Record<string, string | number>) => string
): string {
  const depth = MODE_DEPTH[mode]

  // Estimate time based on depth × branching
  const complexity = depth * branching
  let timeKey = 'research_mode.time_estimate.very_fast'

  if (complexity <= 6) {
    timeKey = 'research_mode.time_estimate.very_fast'
  } else if (complexity <= 16) {
    timeKey = 'research_mode.time_estimate.fast'
  } else if (complexity <= 28) {
    timeKey = 'research_mode.time_estimate.medium'
  } else if (complexity <= 42) {
    timeKey = 'research_mode.time_estimate.slow'
  } else {
    timeKey = 'research_mode.time_estimate.very_slow'
  }

  // Get icon from mode
  const getIcon = (mode: ThinkingMode): string => {
    const icons = {
      heuristic: '⚡',
      analytical: '🔬',
      exhaustive: '🌌'
    }
    return icons[mode]
  }

  const icon = getIcon(mode)
  const timeEstimate = t(timeKey)
  const description = t(`research_mode.${mode}.description`, {
    depth: depth.toString(),
    branching: branching.toString(),
    time: timeEstimate
  })

  return `${icon} ${description}`
}

// Hook for managing research mode state
export function useResearchMode() {
  const [mode, setMode] = useState<'chat' | 'research'>('chat')
  const [thinkingMode, setThinkingMode] = useState<ThinkingMode>('heuristic')

  const enableResearch = () => setMode('research')
  const disableResearch = () => setMode('chat')
  const setThinkingModeValue = (newMode: ThinkingMode) => setThinkingMode(newMode)

  const isResearchEnabled = mode === 'research'

  return {
    mode,
    thinkingMode,
    isResearchEnabled,
    enableResearch,
    disableResearch,
    setThinkingMode: setThinkingModeValue
  }
}
