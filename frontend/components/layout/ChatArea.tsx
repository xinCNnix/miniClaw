"use client"

import { useEffect, useRef } from "react"
import { MessageList } from "@/components/chat/MessageList"
import { InputBox } from "@/components/chat/InputBox"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { cn } from "@/lib/utils"
import type { Message, ThinkingEvent } from "@/types/chat"

interface ChatAreaProps {
  className?: string
  messages: Message[]
  thinkingEvents: ThinkingEvent[]
  isLoading: boolean
  onSendMessage: (content: string, images?: unknown[]) => void
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

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, thinkingEvents])

  return (
    <main
      className={cn(
        "flex-1 min-w-96 flex flex-col glass",
        className
      )}
    >
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
            onSend={onSendMessage}
            disabled={isLoading}
          />
        </div>
      </div>
    </main>
  )
}
