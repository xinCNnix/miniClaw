"use client"

import { useEffect } from "react"
import { IDELayout } from "@/components/layout/IDELayout"
import { Sidebar } from "@/components/layout/Sidebar"
import { ChatArea } from "@/components/layout/ChatArea"
import { TabbedPanel } from "@/components/layout/tabbed-panel.component"
import { useApp } from "@/contexts/AppContext"
import { apiClient } from "@/lib/api"

export default function ChatPage() {
  const { chat, editor, sessions, refreshSessions } = useApp()

  // Restore most recent session on mount
  useEffect(() => {
    const restoreSession = async () => {
      await refreshSessions()

      // Auto-load the most recent session if available
      if (sessions && sessions.length > 0) {
        const mostRecentSession = sessions[0]
        await chat.loadSessionMessages(mostRecentSession.session_id)
      }
    }

    restoreSession()
  }, [])

  const handleNewChat = async () => {
    await chat.newSession()
    // Refresh sessions list to show new session
    await refreshSessions()
  }

  const handleSelectSession = async (sessionId: string) => {
    try {
      await chat.loadSessionMessages(sessionId)
    } catch (error) {
      console.error("Failed to load session:", error)
    }
  }

  const handleDeleteSession = async (sessionId: string) => {
    try {
      await apiClient.deleteSession(sessionId)
      // Refresh sessions list
      await refreshSessions()

      // Clear current session if it was deleted
      if (chat.currentSessionId === sessionId) {
        chat.newSession()
      }
    } catch (error) {
      console.error("Failed to delete session:", error)
    }
  }

  return (
    <IDELayout>
      {/* Left Sidebar - Sessions */}
      <Sidebar
        sessions={sessions}
        currentSessionId={chat.currentSessionId}
        onNewChat={handleNewChat}
        onSelectSession={handleSelectSession}
        onDeleteSession={handleDeleteSession}
      />

      {/* Center - Chat Area */}
      <ChatArea
        messages={chat.messages}
        thinkingEvents={chat.thinkingEvents}
        isLoading={chat.isLoading}
        onSendMessage={chat.sendMessage}
        onStopGeneration={chat.stopGeneration}
      />

      {/* Right Panel - Tabbed Panel (Editor / Knowledge Base) */}
      <TabbedPanel
        files={editor.files}
        directories={editor.directories}
        currentDirectory={editor.currentDirectory}
        currentFile={editor.currentFile}
        onLoadFile={editor.loadFile}
        onSaveFile={editor.saveFile}
        onCloseFile={editor.closeFile}
        onChangeDirectory={editor.changeDirectory}
        onGoUpDirectory={editor.goUpDirectory}
      />
    </IDELayout>
  )
}
