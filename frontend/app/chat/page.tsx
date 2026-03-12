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

  const handleNewChat = async () => {
    await chat.newSession()
    // Refresh sessions list to show new session
    await refreshSessions()
  }

  const handleSelectSession = async (sessionId: string) => {
    try {
      const session = await apiClient.getSession(sessionId)

      // Load messages from session
      if (session.messages && Array.isArray(session.messages)) {
        const messages = session.messages.map((msg: any) => ({
          role: msg.role,
          content: msg.content,
          timestamp: msg.timestamp || new Date().toISOString(),
        }))
        chat.loadMessages(messages)
      } else {
        chat.clearMessages()
      }

      chat.setSession(sessionId)
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
