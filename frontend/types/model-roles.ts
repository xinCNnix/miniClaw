/**
 * Multi-Model Roles 类型定义
 */

export interface RoleInfo {
  role_id: string
  name_zh: string
  name_en: string
  category: "chat" | "speech" | "vision"
  description: string
  fallback: string | null
  required: boolean
  bound_llm_ids: string[]
  bound_llm_names: string[]
  is_configured: boolean
}

export interface Capabilities {
  asr: boolean
  tts: boolean
  ocr: boolean
  supervisor: boolean
  planner: boolean
}
