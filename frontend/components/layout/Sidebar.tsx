"use client"

import { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { MessageSquare, Plus, Trash2, Settings } from "lucide-react"
import { cn } from "@/lib/utils"
import { SettingsDialog } from "./SettingsDialog"
import { useTranslation } from "@/hooks/use-translation.hook"
import type { Session } from "@/types/api"

interface SidebarProps {
  className?: string
  sessions: Session[]
  currentSessionId: string | null
  onNewChat: () => void
  onSelectSession: (sessionId: string) => void
  onDeleteSession: (sessionId: string) => void
}

export function Sidebar({
  className,
  sessions,
  currentSessionId,
  onNewChat,
  onSelectSession,
  onDeleteSession,
}: SidebarProps) {
  const { t } = useTranslation()
  const [isDeleting, setIsDeleting] = useState<string | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)

  const handleDelete = async (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation()
    setIsDeleting(sessionId)
    try {
      await onDeleteSession(sessionId)
    } finally {
      setIsDeleting(null)
    }
  }

  return (
    <aside
      className={cn(
        "w-1/6 min-w-48 max-w-72 h-full glass border-r border-gray-200 flex flex-col",
        className
      )}
    >
      {/* Header */}
      <div className="p-4 border-b border-gray-200">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-xl font-bold text-[var(--ink-green)]">
            MiNiCLAW
          </h1>
          <Button variant="ghost" size="sm" onClick={() => setSettingsOpen(true)}>
            <Settings className="w-4 h-4" />
          </Button>
        </div>
        <Button
          variant="primary"
          className="w-full"
          onClick={onNewChat}
        >
          <Plus className="w-4 h-4 mr-2" />
          {t('sidebar.new_chat')}
        </Button>
      </div>

      {/* Sessions List */}
      <div className="flex-1 overflow-y-auto p-2">
        <div className="space-y-1">
          {sessions.map((session) => (
            <div
              key={session.session_id}
              className={cn(
                "group flex items-center gap-2 p-3 rounded-md cursor-pointer transition-colors",
                "hover:bg-gray-100",
                currentSessionId === session.session_id && "bg-emerald-50"
              )}
              onClick={() => onSelectSession(session.session_id)}
            >
              <MessageSquare className="w-4 h-4 flex-shrink-0 text-gray-500" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">
                  {(session.metadata?.title as string | undefined) || t('sidebar.new_conversation')}
                </p>
                <p className="text-xs text-gray-500">
                  {new Date(session.created_at).toLocaleDateString()}
                </p>
              </div>
              <Button
                variant="ghost"
                size="sm"
                className="opacity-0 group-hover:opacity-100 transition-opacity"
                onClick={(e) => handleDelete(e, session.session_id)}
                disabled={isDeleting === session.session_id}
              >
                <Trash2 className="w-4 h-4 text-red-500" />
              </Button>
            </div>
          ))}
        </div>
      </div>

      {/* Footer */}
      <div className="p-4 border-t border-gray-200 text-xs text-gray-500">
        <p>{t('sidebar.powered_by')}</p>
      </div>

      {/* Settings Dialog */}
      <SettingsDialog open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </aside>
  )
}
