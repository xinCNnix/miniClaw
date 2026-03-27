"use client"

import { useState, useEffect } from "react"
import { Plus, Edit2, Trash2 } from "lucide-react"
import { apiClient } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { useToastContext } from "@/components/common/ToastContext"

interface LLMConfig {
  id: string
  provider: string
  name: string
  model: string
  base_url: string
  has_api_key: boolean
  api_key_preview: string
  is_current?: boolean
}

interface LLMSettingsProps {
  onConfigChange?: () => void
}

interface LLMFormData {
  id?: string
  provider: string
  name: string
  model: string
  base_url: string
  api_key: string
}

const PROVIDER_OPTIONS = [
  { value: "qwen", label: "通义千问", defaultModel: "qwen-plus", defaultUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1" },
  { value: "openai", label: "OpenAI", defaultModel: "gpt-4o-mini", defaultUrl: "https://api.openai.com/v1" },
  { value: "deepseek", label: "DeepSeek", defaultModel: "deepseek-chat", defaultUrl: "https://api.deepseek.com" },
  { value: "custom", label: "自定义 (Custom)", defaultModel: "", defaultUrl: "" },
  { value: "ollama", label: "Ollama (本地)", defaultModel: "qwen2.5", defaultUrl: "http://localhost:11434/v1" },
]

export function LLMSettings({ onConfigChange }: LLMSettingsProps) {
  const { showToast } = useToastContext()
  const [llms, setLLMs] = useState<LLMConfig[]>([])
  const [currentLLMId, setCurrentLLMId] = useState<string>("")
  const [message, setMessage] = useState("")
  const [switchingLLM, setSwitchingLLM] = useState<string | null>(null)
  const [showAddForm, setShowAddForm] = useState(false)
  const [editingLLM, setEditingLLM] = useState<LLMConfig | null>(null)
  const [formData, setFormData] = useState<LLMFormData>({
    provider: "custom",
    name: "",
    model: "",
    base_url: "",
    api_key: "",
  })
  const [requiresConfirmation, setRequiresConfirmation] = useState(false)
  const [untrustedDomain, setUntrustedDomain] = useState("")

  const loadLLMs = async () => {
    try {
      const response = await apiClient.listLLMs()
      setLLMs(response.llms)
      setCurrentLLMId(response.current_llm_id)
    } catch (error: unknown) {
      console.error("Failed to load LLMs:", error)
      const errorMessage = error instanceof Error ? error.message : 'Unknown error'
      setMessage(`加载失败: ${errorMessage}`)
      setTimeout(() => setMessage(""), 3000)
    }
  }

  useEffect(() => {
    loadLLMs()
  }, [])

  const handleSwitch = async (llmId: string) => {
    if (llmId === currentLLMId) return

    setSwitchingLLM(llmId)
    setMessage("")

    try {
      const result = await apiClient.switchLLM(llmId)
      setCurrentLLMId(result.current_llm_id)
      setMessage(`已切换到 ${llmId}`)
      setTimeout(() => setMessage(""), 2000)

      // 重新加载列表
      await loadLLMs()

      // 通知父组件
      if (onConfigChange) {
        onConfigChange()
      }
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error'
      setMessage(`切换失败: ${errorMessage}`)
      setTimeout(() => setMessage(""), 3000)
    } finally {
      setSwitchingLLM(null)
    }
  }

  const handleDelete = async (llmId: string) => {
    // TODO: Replace with proper confirmation dialog
    // For now, just show a warning toast and proceed
    showToast(`确定要删除 ${llmId} 吗？`, 'warning')

    try {
      await apiClient.deleteLLM(llmId)
      showToast("删除成功", 'success')
      await loadLLMs()
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error'
      showToast(`删除失败: ${errorMessage}`, 'error')
    }
  }

  const handleEdit = (llm: LLMConfig) => {
    setEditingLLM(llm)
    setFormData({
      id: llm.id,
      provider: llm.provider,
      name: llm.name,
      model: llm.model,
      base_url: llm.base_url,
      api_key: "", // 编辑时不显示 API Key，留空表示不修改
    })
    setShowAddForm(true)
  }

  const handleAddNew = () => {
    setEditingLLM(null)
    setFormData({
      provider: "custom",
      name: "",
      model: "",
      base_url: "",
      api_key: "",
    })
    setShowAddForm(true)
  }

  const handleProviderChange = (provider: string) => {
    const selectedProvider = PROVIDER_OPTIONS.find(p => p.value === provider)
    if (selectedProvider) {
      setFormData({
        ...formData,
        provider,
        model: selectedProvider.defaultModel,
        base_url: selectedProvider.defaultUrl,
        name: "",
      })
    }
  }

  const handleSubmit = async (userConfirmed: boolean = false) => {
    setMessage("")

    try {
      const result = await apiClient.saveLLM({
        ...formData,
        user_confirmed: userConfirmed,
      })

      if (result.requires_confirmation) {
        setRequiresConfirmation(true)
        setUntrustedDomain(result.domain || "")
        setMessage(result.message || "域名不在可信列表中，请确认")
        return
      }

      if (result.success) {
        setMessage("保存成功")
        setShowAddForm(false)
        setEditingLLM(null)
        setRequiresConfirmation(false)
        setUntrustedDomain("")
        setFormData({
          provider: "custom",
          name: "",
          model: "",
          base_url: "",
          api_key: "",
        })
        await loadLLMs()
        setTimeout(() => setMessage(""), 2000)
      } else {
        setMessage(result.message || "保存失败")
        setTimeout(() => setMessage(""), 3000)
      }
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error'
      setMessage(`保存失败: ${errorMessage}`)
      setTimeout(() => setMessage(""), 3000)
    }
  }

  const handleConfirmDomain = () => {
    handleSubmit(true)
  }

  const handleCancelForm = () => {
    setShowAddForm(false)
    setEditingLLM(null)
    setRequiresConfirmation(false)
    setUntrustedDomain("")
    setFormData({
      provider: "custom",
      name: "",
      model: "",
      base_url: "",
      api_key: "",
    })
  }

  return (
    <div className="llm-settings">
      {/* 添加/编辑表单 */}
      {showAddForm && (
        <div className="mb-6 p-4 border rounded-lg bg-gray-50">
          <h3 className="text-lg font-semibold mb-3">
            {editingLLM ? "编辑 LLM 配置" : "添加新 LLM 配置"}
          </h3>

          <div className="space-y-3">
            {/* 提供商选择 */}
            <div>
              <label className="block text-sm font-medium mb-1">提供商</label>
              <select
                className={cn(
                  "flex h-10 w-full rounded-md border border-gray-300 bg-transparent px-3 py-2",
                  "focus:outline-none focus:ring-2 focus:ring-[var(--ink-green)] focus:border-transparent",
                  "disabled:cursor-not-allowed disabled:opacity-50"
                )}
                value={formData.provider}
                onChange={(e) => handleProviderChange(e.target.value)}
                disabled={!!editingLLM}
              >
                {PROVIDER_OPTIONS.map(option => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>

            {/* 显示名称 */}
            <div>
              <label className="block text-sm font-medium mb-1">显示名称</label>
              <input
                type="text"
                className={cn(
                  "flex h-10 w-full rounded-md border border-gray-300 bg-transparent px-3 py-2",
                  "focus:outline-none focus:ring-2 focus:ring-[var(--ink-green)] focus:border-transparent",
                  "disabled:cursor-not-allowed disabled:opacity-50"
                )}
                placeholder="例如: GPT-4, Claude 3.5"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              />
              <p className="text-xs text-gray-500 mt-1">
                {formData.provider === "custom" ? "自定义名称，用于区分不同的模型" : "可选，不填则使用默认名称"}
              </p>
            </div>

            {/* 模型名称 */}
            <div>
              <label className="block text-sm font-medium mb-1">模型名称</label>
              <input
                type="text"
                className={cn(
                  "flex h-10 w-full rounded-md border border-gray-300 bg-transparent px-3 py-2",
                  "focus:outline-none focus:ring-2 focus:ring-[var(--ink-green)] focus:border-transparent",
                  "disabled:cursor-not-allowed disabled:opacity-50"
                )}
                placeholder="例如: gpt-4, claude-3-5-sonnet-20241022"
                value={formData.model}
                onChange={(e) => setFormData({ ...formData, model: e.target.value })}
              />
            </div>

            {/* Base URL */}
            {formData.provider === "custom" && (
              <div>
                <label className="block text-sm font-medium mb-1">API 地址</label>
                <input
                  type="text"
                  className={cn(
                    "flex h-10 w-full rounded-md border border-gray-300 bg-transparent px-3 py-2",
                    "focus:outline-none focus:ring-2 focus:ring-[var(--ink-green)] focus:border-transparent",
                    "disabled:cursor-not-allowed disabled:opacity-50"
                  )}
                  placeholder="例如: https://api.openai.com/v1"
                  value={formData.base_url}
                  onChange={(e) => setFormData({ ...formData, base_url: e.target.value })}
                />
              </div>
            )}

            {/* API Key */}
            <div>
              <label className="block text-sm font-medium mb-1">API Key</label>
              <input
                type="password"
                className={cn(
                  "flex h-10 w-full rounded-md border border-gray-300 bg-transparent px-3 py-2",
                  "focus:outline-none focus:ring-2 focus:ring-[var(--ink-green)] focus:border-transparent",
                  "disabled:cursor-not-allowed disabled:opacity-50"
                )}
                placeholder={editingLLM ? "留空表示不修改" : "输入 API Key"}
                value={formData.api_key}
                onChange={(e) => setFormData({ ...formData, api_key: e.target.value })}
              />
            </div>

            {/* 域名确认提示 */}
            {requiresConfirmation && (
              <div className="p-3 bg-yellow-50 border border-yellow-200 rounded-md">
                <p className="text-sm text-yellow-800 mb-2">
                  ⚠️ 域名 <strong>{untrustedDomain}</strong> 不在预置的可信服务商列表中
                </p>
                <p className="text-sm text-yellow-700 mb-3">
                  请确认要使用此 API 吗？
                </p>
                <div className="flex gap-2">
                  <Button
                    variant="primary"
                    onClick={handleConfirmDomain}
                  >
                    确认使用
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={handleCancelForm}
                  >
                    取消
                  </Button>
                </div>
              </div>
            )}

            {/* 操作按钮 */}
            {!requiresConfirmation && (
              <div className="flex gap-2">
                <Button
                  variant="primary"
                  onClick={() => handleSubmit(false)}
                  disabled={!formData.model || (!formData.api_key && !editingLLM)}
                >
                  {editingLLM ? "更新" : "保存"}
                </Button>
                <Button
                  variant="secondary"
                  onClick={handleCancelForm}
                >
                  取消
                </Button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 当前 LLM */}
      <div className="mb-6">
        <h3 className="text-lg font-semibold mb-3">当前使用的 LLM</h3>
        {llms.find(llm => llm.id === currentLLMId) ? (
          <LLMCard
            llm={llms.find(llm => llm.id === currentLLMId)!}
            isCurrent={true}
            onSwitch={null}
            onEdit={handleEdit}
            onDelete={null}
            switching={false}
          />
        ) : (
          <p className="text-gray-500">未配置 LLM</p>
        )}
      </div>

      {/* 所有 LLM 列表 */}
      <div>
        <div className="flex justify-between items-center mb-3">
          <h3 className="text-lg font-semibold">所有 LLM 配置 ({llms.length})</h3>
          <Button
            variant="primary"
            size="sm"
            onClick={handleAddNew}
          >
            <Plus className="w-4 h-4 mr-1" />
            添加配置
          </Button>
        </div>
        <div className="space-y-3">
          {llms.map(llm => (
            llm.id !== currentLLMId && (
              <LLMCard
                key={llm.id}
                llm={llm}
                isCurrent={false}
                onSwitch={() => handleSwitch(llm.id)}
                onEdit={handleEdit}
                onDelete={() => handleDelete(llm.id)}
                switching={switchingLLM === llm.id}
              />
            )
          ))}
        </div>
      </div>

      {/* 消息提示 */}
      {message && (
        <div className={`mt-4 p-3 rounded ${message.includes('失败') ? 'bg-red-50 text-red-700' : 'bg-green-50 text-green-700'}`}>
          {message}
        </div>
      )}
    </div>
  )
}


// LLM 卡片组件
interface LLMCardProps {
  llm: LLMConfig
  isCurrent: boolean
  onSwitch: ((llmId: string) => void) | null
  onEdit: ((llm: LLMConfig) => void) | null
  onDelete: ((llmId: string) => void) | null
  switching?: boolean
}

function LLMCard({ llm, isCurrent, onSwitch, onEdit, onDelete, switching }: LLMCardProps) {
  return (
    <div className={cn(
      "border rounded-lg p-4",
      isCurrent ? "border-[var(--ink-green)] bg-[rgba(var(--ink-green-rgb),0.05)]" : "border-gray-200"
    )}>
      <div className="flex justify-between items-start">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            <h4 className="font-semibold">{llm.name || llm.model}</h4>
            {isCurrent && (
              <span className="text-xs px-2 py-1 bg-[var(--ink-green)] text-white rounded">当前使用</span>
            )}
          </div>

          <div className="text-sm text-gray-600 space-y-1">
            <div>提供商: {llm.provider}</div>
            <div>模型: {llm.model}</div>
            {llm.base_url && <div>URL: {llm.base_url}</div>}
            {llm.has_api_key ? (
              <div className="text-green-600">✓ API Key 已配置</div>
            ) : (
              <div className="text-red-600">✗ API Key 未配置</div>
            )}
          </div>
        </div>

        <div className="flex gap-2">
          {onEdit && (
            <button
              className="p-1 text-gray-600 hover:text-[var(--ink-green)] transition-colors"
              onClick={() => onEdit(llm)}
              title="编辑"
            >
              <Edit2 className="w-4 h-4" />
            </button>
          )}
          {onDelete && (
            <button
              className="p-1 text-gray-600 hover:text-red-600 transition-colors"
              onClick={() => onDelete(llm.id)}
              title="删除"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          )}
          {onSwitch && (
            <Button
              variant="primary"
              size="sm"
              onClick={() => onSwitch(llm.id)}
              disabled={switching}
            >
              {switching ? "切换中..." : "切换"}
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}
