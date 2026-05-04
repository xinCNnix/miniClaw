"use client"

import { apiClient } from "@/lib/api"
import { useEffect, useState } from "react"
import type { SettingItem } from "@/types/config"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Plus, Trash2, Check, X, Edit3, Zap } from "lucide-react"
import { FormSection } from "./FormSection"

interface LLMEntry {
  id: string
  provider: string
  name: string
  model: string
  base_url: string
  has_api_key: boolean
  api_key_preview: string
  is_current: boolean
  context_window?: number
}

interface LLMSectionProps {
  settings: SettingItem[]
  onChange: (key: string, value: unknown) => void
  locale: "zh" | "en"
}

type EditState = {
  mode: "add" | "edit"
  id?: string
  provider: string
  name: string
  model: string
  base_url: string
  api_key: string
  context_window: string
  domainWarning?: string
}

const PROVIDERS = [
  { value: "qwen", label_zh: "通义千问", label_en: "Qwen", url: "https://dashscope.aliyuncs.com/compatible-mode/v1" },
  { value: "deepseek", label_zh: "DeepSeek", label_en: "DeepSeek", url: "https://api.deepseek.com/v1" },
  { value: "openai", label_zh: "OpenAI", label_en: "OpenAI", url: "https://api.openai.com/v1" },
  { value: "claude", label_zh: "Claude", label_en: "Claude", url: "" },
  { value: "gemini", label_zh: "Gemini", label_en: "Gemini", url: "https://generativelanguage.googleapis.com/v1beta/openai" },
  { value: "ollama", label_zh: "Ollama", label_en: "Ollama", url: "http://localhost:11434/v1" },
  { value: "custom", label_zh: "自定义", label_en: "Custom", url: "" },
]

function parseContextWindow(value: string): number {
  if (!value || value.trim() === "") return 128_000
  const cleaned = value.trim().toUpperCase()
  if (cleaned.endsWith("M")) return parseFloat(cleaned) * 1_000_000
  if (cleaned.endsWith("K")) return parseFloat(cleaned) * 1_000
  return parseInt(cleaned, 10) || 128_000
}

function formatContextWindow(value: number | undefined): string {
  if (!value) return ""
  if (value >= 1_000_000 && value % 1_000_000 === 0) return `${value / 1_000_000}M`
  if (value >= 1_000 && value % 1_000 === 0) return `${value / 1_000}K`
  return String(value)
}

export function LLMSection({ settings, onChange, locale }: LLMSectionProps) {
  const [llms, setLLMs] = useState<LLMEntry[]>([])
  const [edit, setEdit] = useState<EditState | null>(null)
  const isZh = locale === "zh"

  useEffect(() => {
    loadLLMs()
  }, [])

  async function loadLLMs() {
    try {
      const res = await apiClient.listLLMs()
      setLLMs(
        res.llms
          .map((l) => ({
            id: l.id,
            provider: l.provider,
            name: l.name,
            model: l.model,
            base_url: l.base_url,
            has_api_key: l.has_api_key,
            api_key_preview: l.api_key_preview,
            is_current: l.is_current,
            context_window: l.context_window,
          }))
          .sort((a, b) => (a.is_current === b.is_current ? 0 : a.is_current ? -1 : 1))
      )
    } catch (e) {
      console.error("Failed to load LLMs:", e)
    }
  }

  async function handleSave() {
    if (!edit) return
    try {
      const res = await apiClient.saveLLM({
        ...(edit.mode === "edit" ? { id: edit.id } : {}),
        provider: edit.provider,
        name: edit.name || edit.provider,
        model: edit.model,
        base_url: edit.base_url,
        api_key: edit.api_key || undefined,
        user_confirmed: !edit.domainWarning,
        context_window: parseContextWindow(edit.context_window),
      })
      if (res.requires_confirmation) {
        setEdit({ ...edit, domainWarning: res.domain })
        return
      }
      setEdit(null)
      await loadLLMs()
    } catch (e) {
      console.error("Failed to save LLM:", e)
    }
  }

  async function handleSwitch(llmId: string) {
    try {
      await apiClient.switchLLM(llmId)
      await loadLLMs()
    } catch (e) {
      console.error("Failed to switch LLM:", e)
    }
  }

  async function handleDelete(llmId: string) {
    try {
      await apiClient.deleteLLM(llmId)
      await loadLLMs()
    } catch (e) {
      console.error("Failed to delete LLM:", e)
    }
  }

  function startAdd() {
    setEdit({
      mode: "add",
      provider: "qwen",
      name: "",
      model: "",
      base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
      api_key: "",
      context_window: "",
    })
  }

  function startEdit(llm: LLMEntry) {
    setEdit({
      mode: "edit",
      id: llm.id,
      provider: llm.provider,
      name: llm.name,
      model: llm.model,
      base_url: llm.base_url,
      api_key: "",
      context_window: formatContextWindow(llm.context_window),
    })
  }

  return (
    <div className="space-y-6">
      {/* Add/Edit form */}
      {edit && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50/30 p-4 space-y-3">
          <h3 className="text-sm font-medium">
            {edit.mode === "add"
              ? (isZh ? "添加 LLM" : "Add LLM")
              : (isZh ? "编辑 LLM" : "Edit LLM")}
          </h3>

          <div className="space-y-2">
            <div>
              <label className="text-xs text-gray-500 mb-1 block">
                {isZh ? "服务商" : "Provider"}
              </label>
              <div className="flex flex-wrap gap-1.5">
                {PROVIDERS.map((p) => (
                  <button
                    key={p.value}
                    type="button"
                    onClick={() => setEdit({
                      ...edit,
                      provider: p.value,
                      base_url: edit.base_url || p.url,
                    })}
                    className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
                      edit.provider === p.value
                        ? "bg-emerald-600 text-white"
                        : "bg-white border border-gray-200 text-gray-600 hover:bg-gray-50"
                    }`}
                  >
                    {isZh ? p.label_zh : p.label_en}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="text-xs text-gray-500 mb-1 block">
                {isZh ? "显示名称" : "Name"}
              </label>
              <Input
                value={edit.name}
                onChange={(e) => setEdit({ ...edit, name: e.target.value })}
                placeholder={isZh ? "例：我的 Qwen" : "e.g. My Qwen"}
                className="max-w-xs"
              />
            </div>

            <div>
              <label className="text-xs text-gray-500 mb-1 block">
                {isZh ? "模型名称" : "Model"}
              </label>
              <Input
                value={edit.model}
                onChange={(e) => setEdit({ ...edit, model: e.target.value })}
                placeholder={isZh ? "例：qwen-plus" : "e.g. qwen-plus"}
                className="max-w-xs"
              />
            </div>

            <div>
              <label className="text-xs text-gray-500 mb-1 block">
                {isZh ? "API Base URL" : "Base URL"}
              </label>
              <Input
                value={edit.base_url}
                onChange={(e) => setEdit({ ...edit, base_url: e.target.value, domainWarning: undefined })}
                placeholder="https://..."
                className="max-w-md"
              />
            </div>

            <div>
              <label className="text-xs text-gray-500 mb-1 block">
                {isZh ? "上下文窗口" : "Context Window"}
              </label>
              <Input
                value={edit.context_window}
                onChange={(e) => setEdit({ ...edit, context_window: e.target.value })}
                placeholder={isZh ? "128K（默认）" : "128K (default)"}
                className="max-w-xs"
              />
            </div>

            <div>
              <label className="text-xs text-gray-500 mb-1 block">
                API Key {edit.mode === "edit" && `(${isZh ? "留空不修改" : "leave empty to keep"})`}
              </label>
              <Input
                type="password"
                value={edit.api_key}
                onChange={(e) => setEdit({ ...edit, api_key: e.target.value })}
                placeholder={isZh ? "输入 API Key" : "Enter API Key"}
                className="max-w-md"
              />
            </div>
          </div>

          {edit.domainWarning && (
            <div className="rounded-md bg-amber-50 border border-amber-200 p-3 text-xs text-amber-700">
              {isZh
                ? `⚠️ 域名 ${edit.domainWarning} 不在预置可信列表中，确认使用？`
                : `⚠️ Domain ${edit.domainWarning} is not in trusted list. Confirm?`}
            </div>
          )}

          <div className="flex items-center gap-2 pt-1">
            <Button size="sm" variant="primary" onClick={handleSave}>
              <Check className="h-3.5 w-3.5 mr-1" />
              {isZh ? "保存" : "Save"}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setEdit(null)}>
              <X className="h-3.5 w-3.5 mr-1" />
              {isZh ? "取消" : "Cancel"}
            </Button>
          </div>
        </div>
      )}

      {/* LLM cards */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-medium">
            {isZh ? "已配置的 LLM" : "Configured LLMs"}
          </h3>
          <Button size="sm" variant="secondary" onClick={startAdd}>
            <Plus className="h-3.5 w-3.5 mr-1" />
            {isZh ? "添加" : "Add"}
          </Button>
        </div>

        {llms.length === 0 && !edit && (
          <p className="text-sm text-gray-400 py-4 text-center">
            {isZh ? "暂无 LLM 配置，点击添加" : "No LLMs configured. Click Add."}
          </p>
        )}

        <div className="space-y-3">
          {llms.map((llm) => (
            <div
              key={llm.id}
              className={`rounded-lg border p-4 transition-colors ${
                llm.is_current
                  ? "border-emerald-300 bg-emerald-50/50"
                  : "border-gray-200 bg-white"
              }`}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-semibold">{llm.name}</span>
                    {llm.is_current && (
                      <Badge variant="default">
                        <Zap className="h-3 w-3 mr-1" />
                        {isZh ? "当前" : "Active"}
                      </Badge>
                    )}
                    <Badge variant="secondary">{llm.provider}</Badge>
                  </div>
                  <div className="text-xs text-gray-500 space-y-0.5">
                    <div>{isZh ? "模型" : "Model"}: {llm.model}</div>
                    {llm.base_url && <div className="truncate">URL: {llm.base_url}</div>}
                    <div className="flex items-center gap-1">
                      {llm.has_api_key ? (
                        <><Check className="h-3 w-3 text-green-500" /> {llm.api_key_preview}</>
                      ) : (
                        <span className="text-amber-500">{isZh ? "未配置 API Key" : "No API Key"}</span>
                      )}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-1 shrink-0 ml-2">
                  {!llm.is_current && (
                    <Button size="sm" variant="secondary" onClick={() => handleSwitch(llm.id)}>
                      <Zap className="h-3.5 w-3.5 mr-1" />
                      {isZh ? "切换" : "Switch"}
                    </Button>
                  )}
                  <Button size="sm" variant="ghost" onClick={() => startEdit(llm)}>
                    <Edit3 className="h-3.5 w-3.5" />
                  </Button>
                  {!llm.is_current && (
                    <Button size="sm" variant="ghost" onClick={() => handleDelete(llm.id)}>
                      <Trash2 className="h-3.5 w-3.5 text-red-400" />
                    </Button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Runtime settings (e.g. temperature, max_tokens) */}
      {settings.length > 0 && (
        <div>
          <h3 className="text-sm font-medium mb-3">
            {isZh ? "运行参数" : "Runtime Parameters"}
          </h3>
          <FormSection settings={settings} onChange={onChange} locale={locale} />
        </div>
      )}
    </div>
  )
}
