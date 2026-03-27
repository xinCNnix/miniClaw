"use client"

import { useEffect, useRef, useState } from "react"
import type { ParsedSSEEvent } from "@/lib/sse"

interface UseSSEOptions {
  url: string
  request: object
  enabled?: boolean
  onError?: (error: Error) => void
}

interface UseSSEReturn {
  isConnected: boolean
  error: Error | null
  events: ParsedSSEEvent[]
}

export function useSSE({ url, request, enabled = true, onError }: UseSSEOptions): UseSSEReturn {
  const [isConnected, setIsConnected] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [events, setEvents] = useState<ParsedSSEEvent[]>([])

  const abortControllerRef = useRef<AbortController | null>(null)
  const isEnabledRef = useRef(enabled)

  // Update enabled ref
  useEffect(() => {
    isEnabledRef.current = enabled
  }, [enabled])

  useEffect(() => {
    if (!enabled) {
      setIsConnected(false)
      return
    }

    let isMounted = true
    const controller = new AbortController()
    abortControllerRef.current = controller

    const connect = async () => {
      if (!isMounted || !isEnabledRef.current) return

      setIsConnected(true)
      setError(null)
      setEvents([])

      try {
        const response = await fetch(url, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(request),
          signal: controller.signal,
        })

        if (!isMounted || !isEnabledRef.current) return

        if (!response.ok) {
          throw new Error(`SSE request failed: ${response.statusText}`)
        }

        if (!response.body) {
          throw new Error("Response body is null")
        }

        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ""

        while (isMounted && isEnabledRef.current) {
          const { done, value } = await reader.read()

          if (done) {
            if (isMounted) {
              setIsConnected(false)
            }
            break
          }

          if (!isMounted || !isEnabledRef.current) break

          buffer += decoder.decode(value, { stream: true })

          const lines = buffer.split("\n")
          buffer = lines.pop() || ""

          for (const line of lines) {
            if (!line.trim() || line.startsWith(":")) continue

            if (line.startsWith("data: ")) {
              try {
                const data = JSON.parse(line.slice(6))

                if (isMounted && isEnabledRef.current) {
                  setEvents((prev) => [...prev, data])
                }
              } catch (e) {
                console.error("Failed to parse SSE event:", e)
              }
            }
          }
        }
      } catch (err) {
        if (isMounted && isEnabledRef.current) {
          const error = err as Error
          if (error.name !== "AbortError") {
            setError(error)
            setIsConnected(false)
            if (onError) {
              onError(error)
            }
          }
        }
      }
    }

    connect()

    return () => {
      isMounted = false
      controller.abort()
      setIsConnected(false)
    }
  }, [url, JSON.stringify(request), enabled, onError])

  return {
    isConnected,
    error,
    events,
  }
}
