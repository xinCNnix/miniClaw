/**
 * PervCard — PERV (Plan-Execute-Verify-Reflect) Execution Card
 *
 * Collapsible card showing PERV pipeline progress:
 * Routing → Planning → Executing → Verifying → Done
 *
 * Uses frosty glass theme matching ThoughtTree.
 */

'use client'

import React, { useMemo, useState, memo } from 'react'
import type { ThinkingEvent } from '@/types/chat'
import { useTranslation } from '@/hooks/use-translation.hook'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PervPlanStep {
  id: string
  name: string
  tool: string
  purpose: string
  skill?: string
  status: 'pending' | 'success' | 'fail'
}

type PervPhase = 'routing' | 'planning' | 'executing' | 'verifying' | 'replanning' | 'done'

interface PervState {
  phase: PervPhase
  routerDecision: { mode?: string; risk_level?: string; [k: string]: unknown } | null
  durationMs: number
  planSteps: PervPlanStep[]
  verificationReport: { verdict: string; confidence: number; checks: unknown[]; coverage?: number } | null
  retryCount: number
  skillsMatched: number
  skillsCompiled: number
  summaryCount: number
  isComplete: boolean
}

interface PervCardProps {
  events: ThinkingEvent[]
  maxHeight?: string
  'data-testid'?: string
}

// ---------------------------------------------------------------------------
// Phase order for progress bar
// ---------------------------------------------------------------------------

const PHASE_ORDER: PervPhase[] = ['routing', 'planning', 'executing', 'verifying', 'done']

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

const PervCardInner = ({ events, maxHeight = '400px', 'data-testid': testId }: PervCardProps) => {
  const { t } = useTranslation()
  const [collapsed, setCollapsed] = useState(false)
  const state = useMemo(() => extractPervState(events), [events])

  const phaseIdx = PHASE_ORDER.indexOf(state.phase)

  return (
    <div
      className="mb-3 rounded-xl bg-white/60 backdrop-blur border border-green-200/50"
      style={collapsed ? undefined : { maxHeight }}
      data-testid={testId ?? 'perv-execution-card'}
    >
      {/* Header with phase progress */}
      <PervHeader
        phase={state.phase}
        phaseIdx={phaseIdx}
        collapsed={collapsed}
        onToggle={() => setCollapsed(c => !c)}
        t={t}
      />

      {/* Content (collapsible) */}
      {!collapsed && (
        <div className="p-3 space-y-2 overflow-auto">
          {/* Router decision */}
          {state.routerDecision && (
            <RouterDecision decision={state.routerDecision} durationMs={state.durationMs} t={t} />
          )}

          {/* Plan steps */}
          {state.planSteps.length > 0 && (
            <PlanStepList steps={state.planSteps} t={t} />
          )}

          {/* Verification result */}
          {state.verificationReport && (
            <VerificationBadge report={state.verificationReport} t={t} />
          )}

          {/* Replan indicator */}
          {state.retryCount > 0 && (
            <div className="text-xs text-amber-600 bg-amber-50 px-2 py-1 rounded inline-block">
              {t('perv.retry_count', { count: state.retryCount })}
            </div>
          )}

          {/* Skill policy stats */}
          {(state.skillsMatched > 0 || state.skillsCompiled > 0) && (
            <div className="text-xs text-blue-600 bg-blue-50 px-2 py-1 rounded inline-block">
              {t('perv.skills_matched', { matched: state.skillsMatched, compiled: state.skillsCompiled })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export const PervCard = memo(PervCardInner)

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function PervHeader({
  phase,
  phaseIdx,
  collapsed,
  onToggle,
  t,
}: {
  phase: PervPhase
  phaseIdx: number
  collapsed: boolean
  onToggle: () => void
  t: (key: string, params?: Record<string, string | number>) => string
}) {
  return (
    <div
      className="flex items-center justify-between px-3 py-2 border-b border-green-100 cursor-pointer select-none"
      onClick={onToggle}
    >
      <div className="flex items-center gap-2">
        {/* Phase progress dots */}
        <div className="flex gap-1">
          {PHASE_ORDER.map((p, i) => (
            <div
              key={p}
              className={`w-2 h-2 rounded-full ${
                i < phaseIdx
                  ? 'bg-green-500'
                  : i === phaseIdx
                    ? 'bg-green-400 animate-pulse'
                    : 'bg-green-200'
              }`}
            />
          ))}
        </div>
        <span className="text-xs font-medium text-green-800">
          PERV
        </span>
      </div>
      <div className="flex items-center gap-2">
        <span className={`text-xs px-2 py-0.5 rounded-full ${
          phase === 'done'
            ? 'bg-green-100 text-green-700'
            : phase === 'verifying'
              ? 'bg-amber-50 text-amber-600'
              : 'bg-green-50 text-green-600'
        }`}>
          {t(`perv.phase.${phase}`)}
        </span>
        <span className="text-gray-400 text-xs">{collapsed ? '▸' : '▾'}</span>
      </div>
    </div>
  )
}

function RouterDecision({
  decision,
  durationMs,
  t,
}: {
  decision: { mode?: string; risk_level?: string; [k: string]: unknown }
  durationMs: number
  t: (key: string, params?: Record<string, string | number>) => string
}) {
  const riskLevel = decision.risk_level ?? 'low'
  const riskColor =
    riskLevel === 'high' ? 'bg-red-50 text-red-700' :
    riskLevel === 'medium' ? 'bg-amber-50 text-amber-700' :
    'bg-green-50 text-green-700'

  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="text-gray-500">{decision.mode ?? 'standard'}</span>
      <span className={`px-1.5 py-0.5 rounded ${riskColor}`}>
        {t('perv.risk_level')}: {riskLevel}
      </span>
      {durationMs > 0 && (
        <span className="text-gray-400">{durationMs}ms</span>
      )}
    </div>
  )
}

function PlanStepList({
  steps,
  t,
}: {
  steps: PervPlanStep[]
  t: (key: string, params?: Record<string, string | number>) => string
}) {
  return (
    <div className="space-y-1">
      {steps.map((step) => (
        <PlanStepRow key={step.id} step={step} t={t} />
      ))}
    </div>
  )
}

function PlanStepRow({
  step,
  t,
}: {
  step: PervPlanStep
  t: (key: string, params?: Record<string, string | number>) => string
}) {
  const icon =
    step.status === 'success' ? '✓' :
    step.status === 'fail' ? '✗' :
    '○'

  const iconColor =
    step.status === 'success' ? 'text-green-600' :
    step.status === 'fail' ? 'text-red-500' :
    'text-gray-400'

  const label = step.skill || step.name || step.tool

  return (
    <div className="flex items-center gap-2 text-sm py-0.5">
      <span className={`${iconColor} text-xs flex-shrink-0`}>{icon}</span>
      <span className="font-mono text-xs bg-gray-50 px-1.5 py-0.5 rounded text-gray-700 flex-shrink-0">
        {label}
      </span>
      {step.purpose && (
        <span className="text-gray-500 text-xs truncate">{step.purpose}</span>
      )}
    </div>
  )
}

function VerificationBadge({
  report,
  t,
}: {
  report: { verdict: string; confidence: number; checks: unknown[]; coverage?: number }
  t: (key: string, params?: Record<string, string | number>) => string
}) {
  const passed = report.verdict === 'pass' || report.verdict === 'approved'
  const confidencePct = Math.round(report.confidence * 100)

  return (
    <div className={`flex items-center gap-2 text-xs px-2 py-1 rounded ${
      passed ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
    }`}>
      <span>{passed ? '✓' : '✗'}</span>
      <span>
        {t(`perv.verification.${passed ? 'pass' : 'fail'}`)}
      </span>
      <span className="text-gray-400">
        {t('perv.verification.confidence')}: {confidencePct}%
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// State extraction
// ---------------------------------------------------------------------------

function extractPervState(events: ThinkingEvent[]): PervState {
  let phase: PervPhase = 'routing'
  let routerDecision: PervState['routerDecision'] = null
  let durationMs = 0
  const planSteps: PervPlanStep[] = []
  let verificationReport: PervState['verificationReport'] = null
  let retryCount = 0
  let skillsMatched = 0
  let skillsCompiled = 0
  let summaryCount = 0
  let isComplete = false

  for (const e of events) {
    const ev = e as Record<string, unknown>
    const type = ev.type as string

    if (!type.startsWith('perv_')) continue

    switch (type) {
      case 'perv_start':
        phase = 'routing'
        break

      case 'perv_router_decision':
        routerDecision = ev.decision as PervState['routerDecision']
        durationMs = (ev.duration_ms as number) ?? 0
        phase = 'planning'
        break

      case 'perv_planning': {
        const plan = ev.plan as Array<{ id: string; name: string; tool: string; purpose: string; skill?: string }> | undefined
        if (plan) {
          planSteps.length = 0
          for (const p of plan) {
            planSteps.push({ ...p, status: 'pending' })
          }
        }
        phase = 'executing'
        break
      }

      case 'perv_step_complete': {
        const stepId = ev.step_id as string
        const status = ev.status as string
        const idx = planSteps.findIndex(s => s.id === stepId)
        if (idx >= 0) {
          planSteps[idx].status = status === 'success' ? 'success' : status === 'error' || status === 'fail' ? 'fail' : 'pending'
        }
        break
      }

      case 'perv_execution_complete':
        phase = 'verifying'
        break

      case 'perv_verification':
        verificationReport = ev.report as PervState['verificationReport']
        phase = 'done'
        isComplete = true
        break

      case 'perv_replan':
        retryCount = (ev.retry_count as number) ?? 0
        phase = 'replanning'
        break

      case 'perv_skill_policy':
        skillsMatched = (ev.matched as number) ?? 0
        skillsCompiled = (ev.compiled as number) ?? 0
        break

      case 'perv_summarized':
        summaryCount = (ev.summary_count as number) ?? 0
        break
    }
  }

  return {
    phase,
    routerDecision,
    durationMs,
    planSteps,
    verificationReport,
    retryCount,
    skillsMatched,
    skillsCompiled,
    summaryCount,
    isComplete,
  }
}
