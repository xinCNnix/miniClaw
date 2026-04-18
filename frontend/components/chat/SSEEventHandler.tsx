"use client"

import { useEffect, useRef } from "react"
import type { ParsedSSEEvent } from "@/lib/sse"

interface SSEEventHandlerProps {
  url: string
  request: object
  onThinkingStart: () => void
  onToolCall: (toolName: string, input: any) => void
  onContentDelta: (content: string) => void
  onToolOutput: (toolName: string, output: any, status: string) => void
  onError: (error: string) => void
  onDone: () => void
  enabled?: boolean
}

export function SSEEventHandler({
  url,
  request,
  onThinkingStart,
  onToolCall,
  onContentDelta,
  onToolOutput,
  onError,
  onDone,
  enabled = true,
}: SSEEventHandlerProps) {
  const abortControllerRef = useRef<AbortController | null>(null)

  useEffect(() => {
    if (!enabled) return

    let isMounted = true

    const processEvents = async () => {
      abortControllerRef.current = new AbortController()

      try {
        const response = await fetch(url, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(request),
          signal: abortControllerRef.current.signal,
        })

        if (!response.ok) {
          throw new Error(`SSE request failed: ${response.statusText}`)
        }

        if (!response.body) {
          throw new Error("Response body is null")
        }

        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ""

        while (isMounted) {
          const { done, value } = await reader.read()

          if (done) {
            if (isMounted) onDone()
            break
          }

          buffer += decoder.decode(value, { stream: true })

          const lines = buffer.split("\n")
          buffer = lines.pop() || ""

          for (const line of lines) {
            if (!line.trim() || line.startsWith(":")) continue

            if (line.startsWith("data: ")) {
              try {
                const data = JSON.parse(line.slice(6))
                const event = data as ParsedSSEEvent

                if (!isMounted) break

                switch (event.type) {
                  case "thinking_start":
                    onThinkingStart()
                    break
                  case "tool_call":
                    if (event.tool_calls && event.tool_calls.length > 0) {
                      const toolCall = event.tool_calls[0]
                      onToolCall(toolCall.name, toolCall.arguments)
                    }
                    break
                  case "content_delta":
                    if (event.content) {
                      onContentDelta(event.content)
                    }
                    break
                  case "tool_output":
                    if (event.tool_name && event.output !== undefined) {
                      onToolOutput(
                        event.tool_name,
                        event.output,
                        event.status || "success"
                      )
                    }
                    break
                  case "error":
                    if (event.error) {
                      onError(event.error)
                    }
                    break
                  case "done":
                    onDone()
                    return
                }
              } catch (e) {
                console.error("Failed to parse SSE event:", e)
              }
            }
          }
        }
      } catch (error) {
        if (isMounted && error instanceof Error) {
          if (error.name !== "AbortError") {
            onError(error.message)
          }
        }
      }
    }

    processEvents()

    return () => {
      isMounted = false
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
    }
  }, [url, JSON.stringify(request), enabled])

  return null
}
