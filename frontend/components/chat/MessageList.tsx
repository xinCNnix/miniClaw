"use client"

import { MessageBubble } from "@/components/chat/MessageBubble"
import { ThinkingChainDisplay } from "@/components/chat/ThinkingChainDisplay"
import type { Message } from "@/types/chat"
import { useTranslation } from "@/hooks/use-translation.hook"

interface MessageListProps {
  messages: Message[]
  thinkingEvents?: unknown[]
  isLoading?: boolean
}

export function MessageList({ messages, thinkingEvents = [], isLoading = false }: MessageListProps) {
  const { t } = useTranslation()

  if (messages.length === 0) {
    return (
      <div className="text-center text-gray-400 py-12">
        <p className="text-lg font-medium mb-2">{t('chat.welcome_title')}</p>
        <p className="text-sm">{t('chat.welcome_subtitle')}</p>
        <div className="mt-6 space-y-2 text-sm text-left max-w-md mx-auto">
          <p className="font-medium text-gray-600">{t('chat.try_asking')}</p>
          <ul className="list-disc list-inside space-y-1 text-gray-500">
            <li>{t('chat.try_terminal')}</li>
            <li>{t('chat.try_python')}</li>
            <li>{t('chat.try_web')}</li>
            <li>{t('chat.try_kb')}</li>
            <li>{t('chat.try_skills')}</li>
          </ul>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {messages.map((message, index) => (
        <div key={index}>
          {/* Show thinking chain before assistant messages */}
          {message.role === "assistant" && thinkingEvents.length > 0 && (
            <ThinkingChainDisplay
              events={thinkingEvents as any[]}
              isLoading={isLoading && index === messages.length - 1}
            />
          )}

          <MessageBubble message={message} />
        </div>
      ))}
    </div>
  )
}
