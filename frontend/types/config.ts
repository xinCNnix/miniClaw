/**
 * LLM Configuration Types
 */

export interface LLMConfig {
  id: string
  provider: string
  name: string
  model: string
  base_url: string
  has_api_key: boolean       // 是否已配置 API Key
  api_key_preview: string    // 脱敏预览（sk-1234***）
  is_current?: boolean
}

export interface SaveLLMRequest {
  id?: string                 // 可选，编辑时提供
  provider: string
  name: string
  model: string
  base_url: string
  api_key?: string           // 可选，编辑时不修改则不传
  user_confirmed?: boolean   // 可选，用户确认使用不受信任的域名
}

export interface LLMListResponse {
  current_llm_id: string
  llms: LLMConfig[]
}

export interface SwitchLLMRequest {
  llm_id: string
}

export interface SwitchLLMResponse {
  success: boolean
  current_llm_id: string
}

export interface SaveLLMResponse {
  success: boolean
  llm_id: string
  requires_confirmation?: boolean
  message?: string
  domain?: string
}

export interface DeleteLLMResponse {
  success: boolean
}
