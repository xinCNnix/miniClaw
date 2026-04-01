"use client"

import { ChevronDown, ChevronRight, Terminal, Loader2 } from "lucide-react"
import { useState } from "react"
import { clsx } from "clsx"

interface ThinkingEvent {
  type: string
  tool_name?: string
  input?: Record<string, unknown>
  output?: string | Record<string, unknown>
  status?: string
  timestamp?: string
  error_code?: string
  error_message?: string
  attempt?: number
  max_retries?: number
  delay?: number
  exhausted?: boolean
  context?: string
}

interface ThinkingChainDisplayProps {
  events: ThinkingEvent[]
  isLoading?: boolean
}

export function ThinkingChainDisplay({ events, isLoading = false }: ThinkingChainDisplayProps) {
  const [isExpanded, setIsExpanded] = useState(true)

  // Filter only relevant events
  const relevantEvents = events.filter(
    (event) => event.type === "tool_use" || event.type === "tool_output" || event.type === "llm_retry" || event.type === "llm_error"
  )

  if (relevantEvents.length === 0 && !isLoading) {
    return null
  }

  const getToolIcon = () => {
    return <Terminal className="w-4 h-4" />
  }

  const getStatusColor = (status?: string) => {
    switch (status) {
      case "success":
        return "text-green-600"
      case "error":
        return "text-red-600"
      default:
        return "text-gray-600"
    }
  }

  const getStatusIcon = (status?: string) => {
    switch (status) {
      case "success":
        return "✓"
      case "error":
        return "✗"
      default:
        return "→"
    }
  }

  return (
    <div className="mb-3 border border-gray-200 rounded-lg bg-gray-50 overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-3 py-2 flex items-center justify-between text-sm text-gray-700 hover:bg-gray-100 transition-colors"
      >
        <div className="flex items-center gap-2">
          {isExpanded ? (
            <ChevronDown className="w-4 h-4" />
          ) : (
            <ChevronRight className="w-4 h-4" />
          )}
          <span className="font-medium">
            思考过程
            {isLoading && <Loader2 className="w-3 h-3 ml-2 animate-spin inline" />}
          </span>
          <span className="text-gray-500">
            ({relevantEvents.filter(e => e.type === "tool_use" || e.type === "tool_output").length} 个工具调用{(() => { const retryCount = relevantEvents.filter(e => e.type === "llm_retry").length; const errorCount = relevantEvents.filter(e => e.type === "llm_error").length; const parts = []; if (retryCount > 0) parts.push(`${retryCount} 次重试`); if (errorCount > 0) parts.push(`${errorCount} 个错误`); return parts.length > 0 ? `，${parts.join('、')}` : ''; })()})
          </span>
        </div>
      </button>

      {/* Content */}
      {isExpanded && (
        <div className="px-3 pb-3 space-y-2">
          {relevantEvents.map((event, index) => {
            const isToolCall = event.type === "tool_use"
            const isToolOutput = event.type === "tool_output"

            return (
              <div key={index} className="text-sm">
                {isToolCall && (
                  <div data-type="tool_call" className="flex items-start gap-2 p-2 bg-white rounded border border-gray-200">
                    <div className="text-blue-600 mt-0.5">
                      {getToolIcon()}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-gray-900">
                        {event.tool_name}
                      </div>
                      {event.input && (
                        <div className="mt-1 text-xs text-gray-600">
                          <span className="font-mono bg-gray-100 px-1.5 py-0.5 rounded">
                            {JSON.stringify(event.input)}
                          </span>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {isToolOutput && (
                  <div data-type="tool_output" className="flex items-start gap-2 p-2 bg-white rounded border border-gray-200 ml-6">
                    <div className={clsx("mt-0.5", getStatusColor(event.status))}>
                      {getStatusIcon(event.status)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-xs text-gray-500 mb-1">
                        结果
                      </div>
                      <div className="text-xs text-gray-700 max-h-32 overflow-y-auto">
                        {typeof event.output === "string" ? (
                          <pre className="whitespace-pre-wrap break-words font-mono bg-gray-50 p-2 rounded">
                            {event.output.length > 500
                              ? event.output.slice(0, 500) + "..."
                              : event.output}
                          </pre>
                        ) : (
                          <span className="font-mono bg-gray-50 px-1.5 py-0.5 rounded">
                            {JSON.stringify(event.output)}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                )}

                {event.type === "llm_retry" && (
                  <div className="flex items-start gap-2 p-2 bg-amber-50 rounded border border-amber-200 ml-3">
                    <div className="text-amber-500 mt-0.5 text-xs">
                      ⟳
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-xs text-amber-700">
                        LLM 请求失败 <span className="font-mono font-bold">[{event.error_code}]</span>，第 {event.attempt}/{event.max_retries} 次重试 ({event.delay?.toFixed(1)}s 后)...
                      </div>
                      {event.context && (
                        <div className="text-xs text-amber-500 mt-0.5">上下文: {event.context}</div>
                      )}
                    </div>
                  </div>
                )}

                {event.type === "llm_error" && (
                  <div className="flex items-start gap-2 p-2 bg-red-50 rounded border border-red-200 ml-3">
                    <div className="text-red-500 mt-0.5 text-xs">
                      ✗
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-xs text-red-700 font-medium">
                        LLM 请求失败 <span className="font-mono">[{event.error_code}]</span>，重试已耗尽
                      </div>
                      <div className="text-xs text-red-500 mt-0.5">
                        {(event.error_message ?? "").length > 100 ? (event.error_message ?? "").slice(0, 100) + "..." : (event.error_message ?? "")}
                      </div>
                      {event.context && (
                        <div className="text-xs text-red-400 mt-0.5">上下文: {event.context}</div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )
          })}

          {isLoading && relevantEvents.length > 0 && (
            <div className="text-center text-xs text-gray-500 py-2">
              正在执行...
            </div>
          )}
        </div>
      )}
    </div>
  )
}
