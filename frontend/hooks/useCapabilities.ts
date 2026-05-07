"use client"

import { useState, useEffect, useCallback } from "react"
import { apiClient } from "@/lib/api"
import type { Capabilities } from "@/types/model-roles"

const DEFAULT_CAPABILITIES: Capabilities = {
  asr: false,
  tts: false,
  ocr: false,
  supervisor: false,
  planner: false,
}

/**
 * 查询并缓存后端能力状态（ASR/TTS/OCR 等）。
 * 用于条件渲染：未配置的角色的 UI 元素不显示。
 */
export function useCapabilities() {
  const [capabilities, setCapabilities] = useState<Capabilities>(DEFAULT_CAPABILITIES)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      const caps = await apiClient.getCapabilities()
      setCapabilities(caps)
    } catch (error) {
      console.error("Failed to load capabilities:", error)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  return { capabilities, loading, refresh }
}
