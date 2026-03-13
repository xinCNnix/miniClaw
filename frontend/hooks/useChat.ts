"use client"

import { useState, useCallback, useRef } from "react"
import { apiClient } from "@/lib/api"
import type { Message, ThinkingEvent } from "@/types/chat"
import type { ChatRequest } from "@/types/api"

interface UseChatOptions {
  apiUrl?: string
  onError?: (error: Error) => void
}

interface UseChatReturn {
  messages: Message[]
  thinkingEvents: ThinkingEvent[]
  isLoading: boolean
  currentSessionId: string | null
  sendMessage: (content: string, images?: any[]) => Promise<void>
  stopGeneration: () => void
  clearMessages: () => void
  loadMessages: (messages: Message[]) => void
  loadSessionMessages: (sessionId: string) => Promise<Message[]>
  setSession: (sessionId: string) => void
  newSession: () => Promise<void>
}

export function useChat(options: UseChatOptions = {}): UseChatReturn {
  const { apiUrl, onError } = options

  const [messages, setMessages] = useState<Message[]>([])
  const [thinkingEvents, setThinkingEvents] = useState<ThinkingEvent[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  const sendMessage = useCallback(async (content: string, images: any[] = []) => {
    // Add user message
    const userMessage: Message = {
      role: "user",
      content,
      timestamp: new Date().toISOString(),
      ...(images.length > 0 && { images: images.map(img => ({
        type: "image",
        content: img.base64,
        mime_type: img.file.type,
      })) }),
    }
    setMessages((prev) => [...prev, userMessage])

    // Clear previous thinking events
    setThinkingEvents([])
    setIsLoading(true)

    // Create abort controller
    abortControllerRef.current = new AbortController()

    try {
      const request: ChatRequest = {
        message: content,
        session_id: currentSessionId || "default",
        stream: true,
        ...(images.length > 0 && { images: images.map(img => ({
          type: "image",
          content: img.base64,
          mime_type: img.file.type,
        })) }),
      }

      let assistantContent = ""
      let sessionId = currentSessionId

      // Connect to SSE stream
      const response = await fetch(`${apiUrl || ""}/api/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(request),
        signal: abortControllerRef.current.signal,
      })

      if (!response.ok) {
        throw new Error(`Chat request failed: ${response.statusText}`)
      }

      if (!response.body) {
        throw new Error("Response body is null")
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ""

      while (true) {
        const { done, value } = await reader.read()

        if (done) break

        buffer += decoder.decode(value, { stream: true })

        const lines = buffer.split("\n")
        buffer = lines.pop() || ""

        for (const line of lines) {
          if (!line.trim() || line.startsWith(":")) continue

          if (line.startsWith("data: ")) {
            try {
              const data = JSON.parse(line.slice(6))

              switch (data.type) {
                case "thinking_start":
                  setThinkingEvents((prev) => [
                    ...prev,
                    { type: "thinking_start", timestamp: new Date().toISOString() },
                  ])
                  break

                case "tool_call":
                  if (data.tool_calls && data.tool_calls.length > 0) {
                    const toolCall = data.tool_calls[0]
                    setThinkingEvents((prev) => [
                      ...prev,
                      {
                        type: "tool_use",
                        tool_name: toolCall.name,
                        input: toolCall.arguments,
                        timestamp: new Date().toISOString(),
                      },
                    ])
                  }
                  break

                case "content_delta":
                  if (data.content) {
                    assistantContent += data.content
                    setMessages((prev) => {
                      const lastMessage = prev[prev.length - 1]

                      if (lastMessage && lastMessage.role === "assistant") {
                        // Create new object to ensure React detects the change
                        return [
                          ...prev.slice(0, -1),
                          {
                            ...lastMessage,
                            content: assistantContent,
                          },
                        ]
                      } else {
                        return [
                          ...prev,
                          {
                            role: "assistant",
                            content: assistantContent,
                            timestamp: new Date().toISOString(),
                          },
                        ]
                      }
                    })
                  }
                  break

                case "tool_output":
                  if (data.tool_name && data.output !== undefined) {
                    setThinkingEvents((prev) => [
                      ...prev,
                      {
                        type: "tool_output",
                        tool_name: data.tool_name,
                        output: data.output,
                        status: data.status || "success",
                        timestamp: new Date().toISOString(),
                      },
                    ])
                  }
                  break

                case "session_id":
                  sessionId = data.session_id
                  setCurrentSessionId(sessionId)
                  break

                case "error":
                  throw new Error(data.error || "Unknown error")

                case "done":
                  break
              }
            } catch (e) {
              console.error("Failed to parse SSE event:", e)
            }
          }
        }
      }

      // Update session ID
      if (sessionId) {
        setCurrentSessionId(sessionId)
      }
    } catch (error) {
      if (error instanceof Error && error.name !== "AbortError") {
        if (onError) {
          onError(error)
        } else {
          console.error("Chat error:", error)
        }

        // Add error message
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: `Error: ${error.message}`,
            timestamp: new Date().toISOString(),
          },
        ])
      }
    } finally {
      setIsLoading(false)
      abortControllerRef.current = null
    }
  }, [currentSessionId, apiUrl, onError])

  const stopGeneration = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
    setIsLoading(false)
  }, [])

  const clearMessages = useCallback(() => {
    setMessages([])
    setThinkingEvents([])
  }, [])

  const loadMessages = useCallback((messages: Message[]) => {
    setMessages(messages)
    setThinkingEvents([])
  }, [])

  const loadSessionMessages = useCallback(async (sessionId: string) => {
    try {
      const response = await fetch(`${apiUrl || ""}/api/sessions/${sessionId}/messages`)

      if (!response.ok) {
        throw new Error(`Failed to load session: ${response.statusText}`)
      }

      const data = await response.json()

      // Convert backend messages to frontend format
      const messages: Message[] = data.messages.map((msg: any) => ({
        role: msg.role,
        content: msg.content,
        timestamp: msg.timestamp,
        ...(msg.tool_calls && { tool_calls: msg.tool_calls }),
        ...(msg.images && { images: msg.images }),
      }))

      loadMessages(messages)
      setCurrentSessionId(sessionId)

      return messages
    } catch (error) {
      console.error("Failed to load session messages:", error)
      throw error
    }
  }, [apiUrl, loadMessages])

  const setSession = useCallback((sessionId: string) => {
    setCurrentSessionId(sessionId)
  }, [])

  const newSession = useCallback(async () => {
    clearMessages()
    setCurrentSessionId(null)
  }, [clearMessages])

  return {
    messages,
    thinkingEvents,
    isLoading,
    currentSessionId,
    sendMessage,
    stopGeneration,
    clearMessages,
    loadMessages,
    loadSessionMessages,
    setSession,
    newSession,
  }
}
