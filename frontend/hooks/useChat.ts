"use client"

import { useState, useCallback, useRef } from "react"
import { apiClient } from "@/lib/api"
import type { Message, ThinkingEvent, GeneratedImage } from "@/types/chat"
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
  sendMessage: (content: string, images?: any[], context?: Record<string, any>) => Promise<void>
  stopGeneration: () => void
  clearMessages: () => void
  loadMessages: (messages: Message[]) => void
  loadSessionMessages: (sessionId: string) => Promise<Message[]>
  setSession: (sessionId: string) => void
  newSession: () => Promise<void>
}

/** Extract base64 image markdown from text and convert to GeneratedImage[]. */
function extractBase64Images(text: string): GeneratedImage[] {
  const images: GeneratedImage[] = []
  const regex = /!\[([^\]]*)\]\(data:image\/([^;]+);base64,([A-Za-z0-9+/=]+)\)/g
  let match: RegExpExecArray | null
  let idx = 0
  while ((match = regex.exec(text)) !== null) {
    images.push({
      media_id: `temp_${Date.now()}_${idx}`,
      api_url: `data:image/${match[2]};base64,${match[3]}`,
      name: match[1] || `image_${idx}`,
      mime_type: `image/${match[2]}`,
    })
    idx++
  }
  return images
}

export function useChat(options: UseChatOptions = {}): UseChatReturn {
  const { apiUrl, onError } = options

  const [messages, setMessages] = useState<Message[]>([])
  const [thinkingEvents, setThinkingEvents] = useState<ThinkingEvent[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  const sendMessage = useCallback(async (content: string, images: any[] = [], context: Record<string, any> = {}) => {
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
        context: Object.keys(context).length > 0 ? context : undefined,
        ...(images.length > 0 && { images: images.map(img => ({
          type: "image",
          content: img.base64,
          mime_type: img.file.type,
        })) }),
      }

      let assistantContent = ""
      let collectedImages: GeneratedImage[] = []
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
              const jsonStr = line.slice(6)
              const data = JSON.parse(jsonStr)
              // Log large events that might contain images
              if (jsonStr.length > 10000) {
                console.log(`[SSE] Large event: type=${data.type}, jsonLen=${jsonStr.length}`)
              }

              switch (data.type) {
                case "thinking_start":
                  setThinkingEvents((prev) => [
                    ...prev,
                    {
                      type: "thinking_start",
                      timestamp: new Date().toISOString(),
                      mode: data.mode || 'simple'
                    },
                  ])
                  break

                // ToT events
                case "tot_reasoning_start":
                  // 去重：只保留最新的 reasoning_start
                  setThinkingEvents((prev) => {
                    const filtered = prev.filter(e => e.type !== 'tot_reasoning_start')
                    return [...filtered, {
                      type: "tot_reasoning_start",
                      mode: "tot",
                      max_depth: data.max_depth,
                      timestamp: new Date().toISOString(),
                    }]
                  })
                  break

                case "tot_status":
                  // 去重：同一 node 只保留最新状态
                  setThinkingEvents((prev) => {
                    const filtered = prev.filter(e =>
                      !(e.type === 'tot_status' && (e as any).node === data.node)
                    )
                    return [...filtered, {
                      type: "tot_status",
                      status_message: data.status_message,
                      node: data.node,
                      timestamp: new Date().toISOString(),
                    }]
                  })
                  break

                case "tot_thoughts_generated":
                  // 旧代码：每个事件都追加，导致数组无限增长
                  // setThinkingEvents((prev) => [
                  //   ...prev,
                  //   {
                  //     type: "tot_thoughts_generated",
                  //     depth: data.depth,
                  //     count: data.count,
                  //     thoughts: data.thoughts,
                  //     timestamp: new Date().toISOString(),
                  //   },
                  // ])
                  // 新代码：去重，同一 depth 只保留最新的生成事件
                  setThinkingEvents((prev) => {
                    const filtered = prev.filter(e =>
                      !(e.type === 'tot_thoughts_generated' && (e as any).depth === data.depth)
                    )
                    return [...filtered, {
                      type: "tot_thoughts_generated",
                      depth: data.depth,
                      count: data.count,
                      thoughts: data.thoughts,
                      timestamp: new Date().toISOString(),
                    }]
                  })
                  break

                case "tot_thoughts_evaluated":
                  // 旧代码：每个事件都追加
                  // setThinkingEvents((prev) => [
                  //   ...prev,
                  //   {
                  //     type: "tot_thoughts_evaluated",
                  //     best_path: data.best_path,
                  //     best_score: data.best_score,
                  //     timestamp: new Date().toISOString(),
                  //   },
                  // ])
                  // 新代码：去重，只保留最新的评估事件
                  setThinkingEvents((prev) => {
                    const filtered = prev.filter(e => e.type !== 'tot_thoughts_evaluated')
                    return [...filtered, {
                      type: "tot_thoughts_evaluated",
                      best_path: data.best_path,
                      best_score: data.best_score,
                      // Phase 10: beam fields
                      active_beams: data.active_beams,
                      beam_scores: data.beam_scores,
                      timestamp: new Date().toISOString(),
                    }]
                  })
                  break

                case "tot_tools_executed":
                  // BUG FIX: ToT 模式下需要收集 generated_images
                  if (data.generated_images && data.generated_images.length > 0) {
                    collectedImages.push(...data.generated_images)
                    console.log(`[SSE] tot_tools_executed: ${data.generated_images.length} generated_images received`)
                  }
                  // 去重：同一 thought_id 只保留最新
                  setThinkingEvents((prev) => {
                    const filtered = prev.filter(e =>
                      !(e.type === 'tot_tools_executed' && (e as any).thought_id === data.thought_id)
                    )
                    return [...filtered, {
                      type: "tot_tools_executed",
                      thought_id: data.thought_id,
                      content: data.content,
                      tool_count: data.tool_count,
                      timestamp: new Date().toISOString(),
                    }]
                  })
                  break

                case "tot_tree_update":
                  // 旧代码：每个树更新都追加，导致完整树结构反复堆积
                  // setThinkingEvents((prev) => [
                  //   ...prev,
                  //   {
                  //     type: "tot_tree_update",
                  //     tree: data.tree,
                  //     timestamp: new Date().toISOString(),
                  //   },
                  // ])
                  // 新代码：替换而非追加，只保留最新的树结构，避免内存堆积
                  setThinkingEvents((prev) => {
                    const filtered = prev.filter(e => e.type !== 'tot_tree_update')
                    return [...filtered, {
                      type: "tot_tree_update",
                      tree: data.tree,
                      timestamp: new Date().toISOString(),
                    }]
                  })
                  break

                case "tot_termination":
                  setThinkingEvents((prev) => [
                    ...prev,
                    {
                      type: "tot_termination",
                      reason: data.reason,
                      score: data.score,
                      depth: data.depth,
                      timestamp: new Date().toISOString(),
                    },
                  ])
                  break

                // Phase 10: beam search events
                case "tot_backtrack":
                  setThinkingEvents((prev) => [
                    ...prev,
                    {
                      type: "tot_backtrack",
                      reason: data.reason,
                      depth: data.depth,
                      beam_idx: data.beam_idx,
                      from_root: data.from_root,
                      to_root: data.to_root,
                      timestamp: new Date().toISOString(),
                    },
                  ])
                  break

                case "tot_thoughts_regenerated":
                  setThinkingEvents((prev) => [
                    ...prev,
                    {
                      type: "tot_thoughts_regenerated",
                      depth: data.depth,
                      beam_indices: data.beam_indices,
                      count: data.count,
                      timestamp: new Date().toISOString(),
                    },
                  ])
                  break

                case "tot_reasoning_complete":
                  setThinkingEvents((prev) => [
                    ...prev,
                    {
                      type: "tot_reasoning_complete",
                      final_answer_length: data.final_answer_length,
                      final_answer_preview: data.final_answer_preview,
                      best_path: data.best_path,
                      total_thoughts: data.total_thoughts,
                      timestamp: new Date().toISOString(),
                    },
                  ])
                  // BUG FIX: ToT 完成时把收集到的图片附到最终消息
                  if (collectedImages.length > 0) {
                    setMessages((prev) => {
                      const lastMessage = prev[prev.length - 1]
                      if (lastMessage?.role === "assistant") {
                        return [
                          ...prev.slice(0, -1),
                          { ...lastMessage, generated_images: [...collectedImages] },
                        ]
                      }
                      return [
                        ...prev,
                        {
                          role: "assistant" as const,
                          content: assistantContent,
                          generated_images: [...collectedImages],
                          timestamp: new Date().toISOString(),
                        },
                      ]
                    })
                  }
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
                    // Log every 20th delta to avoid spam
                    if (assistantContent.length % 2000 < data.content.length) {
                      console.log(`[SSE] content_delta: totalLen=${assistantContent.length}, hasImage=${assistantContent.includes("data:image/")}`)
                    }
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
                    const outputStr = typeof data.output === "string" ? data.output : String(data.output)

                    // New pipeline: structured generated_images from v2 backend
                    const eventImages: GeneratedImage[] = data.generated_images || []
                    if (eventImages.length > 0) {
                      collectedImages.push(...eventImages)
                      console.log(`[SSE] tool_output: ${eventImages.length} generated_images received`)
                    }

                    // Legacy compat: detect base64 in output
                    const hasImage = outputStr.includes("data:image/")
                    if (hasImage) {
                      const imgMatch = outputStr.match(/data:image\/[^;]+;base64,[A-Za-z0-9+/]+/)
                      if (imgMatch) {
                        const uri = imgMatch[0]
                        console.log(`[SSE] image URI (legacy): mime=${uri.slice(0, uri.indexOf(";"))}, base64Len=${uri.length - uri.indexOf(",") - 1}`)
                      }
                      // Extract base64 images into GeneratedImage format
                      const legacyImages = extractBase64Images(outputStr)
                      if (legacyImages.length > 0) {
                        collectedImages.push(...legacyImages)
                        console.log(`[SSE] Extracted ${legacyImages.length} base64 image(s) (legacy path)`)
                      }
                      // Clean text without base64 for assistantContent
                      const cleanText = outputStr.replace(/!\[[^\]]*\]\(data:image\/[^)]+\)/g, "").trim()
                      if (cleanText) {
                        assistantContent += `\n\n${cleanText}\n\n`
                      }
                    }

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
                    // Update message with generated_images
                    setMessages((prev) => {
                      const lastMessage = prev[prev.length - 1]
                      const updatedMsg = lastMessage?.role === "assistant"
                        ? { ...lastMessage, content: assistantContent, generated_images: [...collectedImages] }
                        : {
                            role: "assistant" as const,
                            content: assistantContent,
                            generated_images: [...collectedImages],
                            timestamp: new Date().toISOString(),
                          }
                      return lastMessage?.role === "assistant"
                        ? [...prev.slice(0, -1), updatedMsg]
                        : [...prev, updatedMsg]
                    })
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

                case "self_correction":
                  console.log("[SSE] Self-correction event received:", data)
                  // 将自我纠正内容追加到当前 assistant 消息
                  if (data.correction) {
                    const correctionText = `\n\n---\n**自我纠正**（质量分：${data.quality_score?.toFixed(1) ?? "N/A"}/10）\n\n${data.correction}`
                    assistantContent += correctionText
                    setMessages((prev) => {
                      const lastMsg = prev[prev.length - 1]
                      if (lastMsg && lastMsg.role === "assistant") {
                        const updatedMsg = {
                          ...lastMsg,
                          content: (lastMsg.content || "") + correctionText,
                        }
                        return [...prev.slice(0, -1), updatedMsg]
                      }
                      return prev
                    })
                  }
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

      // Final content summary
      console.log(`[SSE] Stream complete: ${collectedImages.length} images, contentLen=${assistantContent.length}`)
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
        ...(msg.generated_images && { generated_images: msg.generated_images }),
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
