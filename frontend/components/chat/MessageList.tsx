"use client"

import { MessageBubble } from "@/components/chat/MessageBubble"
import { ThinkingChainDisplay } from "@/components/chat/ThinkingChainDisplay"
import { ThoughtTree } from "@/components/chat/thought-tree"
import { PervCard } from "@/components/chat/perv-card"
import type { Message, ThinkingEvent } from "@/types/chat"
import { useTranslation } from "@/hooks/use-translation.hook"

interface MessageListProps {
  messages: Message[]
  thinkingEvents?: ThinkingEvent[]
  isLoading?: boolean
}

export function MessageList({ messages, thinkingEvents = [], isLoading = false }: MessageListProps) {
  const { t } = useTranslation()

  // Check if there are any ToT events
  const hasToTEvents = thinkingEvents.some(event => event.type.startsWith('tot_'))
  // Check if there are any PERV events (mixed pevr_ / perv_ prefixes)
  const hasPervEvents = thinkingEvents.some(event => event.type.startsWith('perv_'))

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

  // 旧代码：每个 assistant 消息前都渲染思维树，历史消息多时导致卡顿
  // 新代码：只为当前最后一条消息显示思维过程，避免历史消息重复渲染导致卡顿
  const lastMsgIndex = messages.length - 1

  return (
    <div className="space-y-4">
      {messages.map((message, index) => (
        <div key={index}>
          {/* 旧代码：每条 assistant 消息前都显示 ThinkingChainDisplay + ThoughtTree */}
          {/* {message.role === "assistant" && thinkingEvents.length > 0 && (
            <>
              {hasToTEvents && (
                <ThoughtTree events={thinkingEvents} maxHeight="300px" data-testid="tot-reasoning-step" />
              )}
              <ThinkingChainDisplay events={thinkingEvents as any[]} isLoading={isLoading && index === messages.length - 1} />
            </>
          )} */}

          <MessageBubble message={message} />

          {/* 旧代码：推理期间在 user 消息下方单独显示思维树 */}
          {/* {message.role === "user" && index === messages.length - 1 && thinkingEvents.length > 0 && isLoading && (
            <>
              {hasToTEvents && (
                <ThoughtTree events={thinkingEvents} maxHeight="300px" data-testid="tot-reasoning-step-inline" />
              )}
              <ThinkingChainDisplay events={thinkingEvents as any[]} isLoading={true} />
            </>
          )} */}

          {/* ToT 模式：思维树卡片；PERV 模式：PervCard；普通模式：工具调用链 */}
          {index === lastMsgIndex && thinkingEvents.length > 0 && (
            hasToTEvents ? (
              <ThoughtTree
                events={thinkingEvents}
                maxHeight="300px"
                data-testid="tot-reasoning-step"
              />
            ) : hasPervEvents ? (
              <PervCard
                events={thinkingEvents}
                maxHeight="300px"
                data-testid="perv-execution-step"
              />
            ) : (
              <ThinkingChainDisplay
                events={thinkingEvents as any[]}
                isLoading={isLoading}
              />
            )
          )}
        </div>
      ))}
    </div>
  )
}
