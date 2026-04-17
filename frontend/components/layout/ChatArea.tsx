"use client"

import { useEffect, useRef, useState } from "react"
import { MessageList } from "@/components/chat/MessageList"
import { InputBox } from "@/components/chat/InputBox"
import { ResearchModeToggle } from "@/components/chat/research-mode"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { cn } from "@/lib/utils"
import type { Message, ThinkingEvent } from "@/types/chat"

interface ChatAreaProps {
  className?: string
  messages: Message[]
  thinkingEvents: ThinkingEvent[]
  isLoading: boolean
  onSendMessage: (content: string, images?: unknown[], context?: Record<string, any>) => void
  onStopGeneration?: () => void
}

export function ChatArea({
  className,
  messages,
  thinkingEvents,
  isLoading,
  onSendMessage,
  onStopGeneration,
}: ChatAreaProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const [researchMode, setResearchMode] = useState<'chat' | 'research'>('chat')
  const [thinkingMode, setThinkingMode] = useState<'heuristic' | 'analytical' | 'exhaustive'>('heuristic')
  const [branchingFactor, setBranchingFactor] = useState<number>(3)
  const [searchDepth, setSearchDepth] = useState<number>(3)
  const [deepPlanning, setDeepPlanning] = useState<boolean>(false)

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, thinkingEvents])

  const handleSendMessage = (content: string, images?: unknown[]) => {
    // Build context based on active mode
    const context: Record<string, any> = {}
    if (researchMode === 'research') {
      context.research_mode = thinkingMode
      context.branching_factor = branchingFactor
      context.depth = searchDepth
    }
    if (deepPlanning) {
      context.deep_planning = true
    }
    onSendMessage(content, images, Object.keys(context).length > 0 ? context : undefined)
  }

  const handleThinkingModeChange = (mode: 'heuristic' | 'analytical' | 'exhaustive', branching?: number, depth?: number) => {
    setThinkingMode(mode)
    if (branching !== undefined) {
      setBranchingFactor(branching)
    }
    if (depth !== undefined) {
      setSearchDepth(depth)
    }
  }

  const handleResearchModeChange = (mode: 'chat' | 'research') => {
    setResearchMode(mode)
    // 互斥：开启深度研究时关闭深度规划
    if (mode === 'research' && deepPlanning) {
      setDeepPlanning(false)
    }
  }

  const handleDeepPlanningChange = (enabled: boolean) => {
    setDeepPlanning(enabled)
    // 互斥：开启深度规划时关闭深度研究
    if (enabled && researchMode === 'research') {
      setResearchMode('chat')
    }
  }

  return (
    <main
      className={cn(
        "flex-1 min-w-96 flex flex-col glass",
        className
      )}
    >
      {/* Research Mode Controls */}
      <div className="border-b border-gray-200 bg-white bg-opacity-50">
        <div className="max-w-3xl mx-auto p-2">
          <ResearchModeToggle
            onModeChange={handleResearchModeChange}
            onThinkingModeChange={handleThinkingModeChange}
            onDeepPlanningChange={handleDeepPlanningChange}
            disabled={isLoading}
          />
        </div>
      </div>

      {/* Messages and Thinking Chain */}
      <div className="flex-1 overflow-y-auto p-4">
        <div className="max-w-3xl mx-auto">
          {/* Messages */}
          <MessageList
            messages={messages}
            thinkingEvents={thinkingEvents}
            isLoading={isLoading}
          />

          {/* Loading Indicator */}
          {isLoading && (
            <div className="flex items-center gap-3 text-gray-500">
              <LoadingSpinner size="md" />
              <span className="text-sm">Agent is thinking...</span>
              {onStopGeneration && (
                <button
                  onClick={onStopGeneration}
                  className="text-xs text-red-500 hover:underline ml-2"
                >
                  Stop
                </button>
              )}
            </div>
          )}

          {/* Scroll Anchor */}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input Box */}
      <div className="border-t border-gray-200 p-4 bg-white bg-opacity-50">
        <div className="max-w-3xl mx-auto">
          <InputBox
            onSend={handleSendMessage}
            disabled={isLoading}
          />
        </div>
      </div>
    </main>
  )
}
