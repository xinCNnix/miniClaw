"use client"

import { useEffect, useState, useRef } from "react"
import { IDELayout } from "@/components/layout/IDELayout"
import { Sidebar } from "@/components/layout/Sidebar"
import { ChatArea } from "@/components/layout/ChatArea"
import { TabbedPanel } from "@/components/layout/tabbed-panel.component"
import { useApp } from "@/contexts/AppContext"
import { apiClient } from "@/lib/api"

export default function ChatPage() {
  const { chat, editor, sessions, refreshSessions, loadFile, saveFile, closeFile } = useApp()
  const [sessionRestored, setSessionRestored] = useState(false)
  const sessionRestoreAttempted = useRef(false)

  // Step 1: Refresh sessions list on mount
  useEffect(() => {
    const loadSessions = async () => {
      try {
        await refreshSessions()
        setSessionRestored(true)
      } catch (error) {
        console.error("Failed to load sessions:", error)
        // Still mark as restored to avoid infinite retries
        setSessionRestored(true)
      }
    }

    if (!sessionRestoreAttempted.current) {
      sessionRestoreAttempted.current = true
      loadSessions()
    }
  }, [refreshSessions])

  // Step 2: Auto-load most recent session after sessions are loaded
  useEffect(() => {
    // Only proceed if sessions are loaded and no current session is active
    if (!sessionRestored || !sessions || sessions.length === 0) {
      return
    }

    // Don't auto-load if there's already a session loaded
    if (chat.currentSessionId) {
      return
    }

    // Don't auto-load if user is in the middle of a conversation (has messages or is loading)
    if (chat.messages.length > 0 || chat.isLoading) {
      return
    }

    const mostRecentSession = sessions[0]
    if (mostRecentSession) {
      chat.loadSessionMessages(mostRecentSession.session_id).catch((error) => {
        console.error("Failed to load recent session:", error)
      })
    }
  }, [sessionRestored, sessions, chat.currentSessionId, chat.loadSessionMessages, chat.messages.length, chat.isLoading])

  const handleNewChat = async () => {
    // Create a new session on the backend
    try {
      const newSession = await apiClient.createSession()
      // Clear current messages and set the new session ID
      chat.newSession()
      chat.setSession(newSession.session_id)
      // Refresh sessions list to show the new session
      await refreshSessions()
    } catch (error) {
      console.error("Failed to create new session:", error)
      // Fallback: just clear the current session
      await chat.newSession()
      await refreshSessions()
    }
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
        onLoadFile={loadFile}
        onSaveFile={saveFile}
        onCloseFile={closeFile}
        onChangeDirectory={editor.changeDirectory}
        onGoUpDirectory={editor.goUpDirectory}
      />
    </IDELayout>
  )
}
