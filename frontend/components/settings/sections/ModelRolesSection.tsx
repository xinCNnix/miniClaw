"use client"

import { useState, useEffect, useCallback } from "react"
import { Plus, X, ChevronUp, ChevronDown } from "lucide-react"
import { apiClient } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import type { RoleInfo } from "@/types/model-roles"

interface LLMOption {
  id: string
  name: string
  model: string
}

interface ModelRolesSectionProps {
  /** 已配置的 LLM 列表（从 LLMSettings 传入） */
  llms: LLMOption[]
  onRoleChange?: () => void
}

export function ModelRolesSection({ llms, onRoleChange }: ModelRolesSectionProps) {
  const [roles, setRoles] = useState<RoleInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState("")
  const [saving, setSaving] = useState<string | null>(null)

  const loadRoles = useCallback(async () => {
    try {
      const response = await apiClient.listRoles()
      setRoles(response.roles)
    } catch (error) {
      console.error("Failed to load roles:", error)
      setMessage("加载角色失败")
      setTimeout(() => setMessage(""), 3000)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadRoles()
  }, [loadRoles])

  const handleUnbind = async (roleId: string) => {
    setSaving(roleId)
    try {
      await apiClient.unbindRole(roleId)
      setMessage(`已解绑 ${roleId}`)
      await loadRoles()
      onRoleChange?.()
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : String(error)
      setMessage(`解绑失败: ${msg}`)
    } finally {
      setSaving(null)
      setTimeout(() => setMessage(""), 3000)
    }
  }

  // === 通用角色多行管理 ===
  const handleRoleSave = async (roleId: string, llmIds: string[]) => {
    setSaving(roleId)
    try {
      await apiClient.bindRole(roleId, llmIds)
      await loadRoles()
      onRoleChange?.()
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : String(error)
      setMessage(`保存失败: ${msg}`)
    } finally {
      setSaving(null)
    }
  }

  const handleRoleAddRow = (roleId: string) => {
    const role = roles.find(r => r.role_id === roleId)
    if (!role) return
    const currentIds = role.bound_llm_ids
    // 找到尚未在列表中的 LLM
    const available = llms.find(l => !currentIds.includes(l.id))
    if (!available) return
    handleRoleSave(roleId, [...currentIds, available.id])
  }

  const handleRoleRemoveRow = (roleId: string, index: number) => {
    const role = roles.find(r => r.role_id === roleId)
    if (!role) return
    const newIds = role.bound_llm_ids.filter((_, i) => i !== index)
    if (newIds.length === 0) {
      // 如果删除后为空，解绑该角色
      handleUnbind(roleId)
    } else {
      handleRoleSave(roleId, newIds)
    }
  }

  const handleRoleSelectChange = (roleId: string, index: number, llmId: string) => {
    const role = roles.find(r => r.role_id === roleId)
    if (!role) return
    const newIds = [...role.bound_llm_ids]
    newIds[index] = llmId
    // 去重
    const seen = new Set<string>()
    const deduped = newIds.filter(id => {
      if (seen.has(id)) return false
      seen.add(id)
      return true
    })
    handleRoleSave(roleId, deduped)
  }

  const handleRoleMoveUp = (roleId: string, index: number) => {
    const role = roles.find(r => r.role_id === roleId)
    if (!role || index <= 0) return
    const newIds = [...role.bound_llm_ids]
    ;[newIds[index - 1], newIds[index]] = [newIds[index], newIds[index - 1]]
    handleRoleSave(roleId, newIds)
  }

  const handleRoleMoveDown = (roleId: string, index: number) => {
    const role = roles.find(r => r.role_id === roleId)
    if (!role || index >= role.bound_llm_ids.length - 1) return
    const newIds = [...role.bound_llm_ids]
    ;[newIds[index], newIds[index + 1]] = [newIds[index + 1], newIds[index]]
    handleRoleSave(roleId, newIds)
  }

  // === Main 角色多行管理 ===
  const mainRole = roles.find(r => r.role_id === "main")
  const mainLlmIds = mainRole?.bound_llm_ids ?? []

  const handleMainAddRow = () => {
    // 找到尚未在列表中的 LLM
    const available = llms.find(l => !mainLlmIds.includes(l.id))
    if (!available) return
    const newIds = [...mainLlmIds, available.id]
    handleMainSave(newIds)
  }

  const handleMainRemoveRow = (index: number) => {
    if (index === 0) return // 主力不可删除
    const newIds = mainLlmIds.filter((_, i) => i !== index)
    handleMainSave(newIds)
  }

  const handleMainSelectChange = (index: number, llmId: string) => {
    const newIds = [...mainLlmIds]
    newIds[index] = llmId
    // 去重
    const seen = new Set<string>()
    const deduped = newIds.filter(id => {
      if (seen.has(id)) return false
      seen.add(id)
      return true
    })
    handleMainSave(deduped)
  }

  const handleMainMoveUp = (index: number) => {
    if (index <= 0) return
    const newIds = [...mainLlmIds]
    ;[newIds[index - 1], newIds[index]] = [newIds[index], newIds[index - 1]]
    handleMainSave(newIds)
  }

  const handleMainMoveDown = (index: number) => {
    if (index >= mainLlmIds.length - 1) return
    const newIds = [...mainLlmIds]
    ;[newIds[index], newIds[index + 1]] = [newIds[index + 1], newIds[index]]
    handleMainSave(newIds)
  }

  const handleMainSave = async (llmIds: string[]) => {
    setSaving("main")
    try {
      await apiClient.bindRole("main", llmIds)
      await loadRoles()
      onRoleChange?.()
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : String(error)
      setMessage(`保存失败: ${msg}`)
    } finally {
      setSaving(null)
    }
  }

  if (loading) {
    return <div className="text-gray-500 text-sm">加载角色配置...</div>
  }

  const selectClass = cn(
    "flex h-9 w-full rounded-md border border-gray-300 bg-transparent px-3 py-1.5 text-sm",
    "focus:outline-none focus:ring-2 focus:ring-[var(--ink-green)] focus:border-transparent"
  )

  return (
    <div className="mt-6">
      <h3 className="text-lg font-semibold mb-4">角色分配</h3>

      {/* Main 角色 — 多行列表（支持 failover） */}
      {mainRole && (
        <div className="mb-4 p-3 border rounded-lg">
          <div className="flex items-center gap-2 mb-2">
            <span className="font-medium">{mainRole.name_zh}</span>
            <span className="text-xs text-gray-500">(必选，支持 failover)</span>
          </div>
          {mainLlmIds.map((llmId, idx) => (
            <div key={idx} className="flex items-center gap-2 mb-2">
              <span className="text-xs text-gray-400 w-6 text-right">{idx + 1}.</span>
              <select
                className={cn(selectClass, "max-w-[280px]")}
                value={llmId}
                onChange={(e) => handleMainSelectChange(idx, e.target.value)}
                disabled={saving === "main"}
              >
                {llms.map(llm => (
                  <option key={llm.id} value={llm.id}>
                    {llm.name || llm.model}
                  </option>
                ))}
              </select>
              <button
                className="p-1 text-gray-400 hover:text-blue-600 disabled:opacity-30"
                onClick={() => handleMainMoveUp(idx)}
                disabled={idx === 0 || saving === "main"}
                title="上移"
              >
                <ChevronUp className="w-4 h-4" />
              </button>
              <button
                className="p-1 text-gray-400 hover:text-blue-600 disabled:opacity-30"
                onClick={() => handleMainMoveDown(idx)}
                disabled={idx >= mainLlmIds.length - 1 || saving === "main"}
                title="下移"
              >
                <ChevronDown className="w-4 h-4" />
              </button>
              {idx > 0 && (
                <button
                  className="p-1 text-gray-400 hover:text-red-600"
                  onClick={() => handleMainRemoveRow(idx)}
                  disabled={saving === "main"}
                  title="移除"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>
          ))}
          <Button
            variant="secondary"
            size="sm"
            onClick={handleMainAddRow}
            disabled={saving === "main" || llms.length <= mainLlmIds.length}
          >
            <Plus className="w-3 h-3 mr-1" />
            添加备选
          </Button>
        </div>
      )}

      {/* 其他角色 — 多行 failover 列表（与 main 相同模式） */}
      {roles
        .filter(r => r.role_id !== "main")
        .map(role => {
          const roleLlmIds = role.bound_llm_ids
          const isChatRole = role.category === "chat"
          const fallbackHint = !roleLlmIds.length && isChatRole
            ? "→ 回落主"
            : !roleLlmIds.length
              ? "→ 不可用"
              : null

          return (
            <div key={role.role_id} className="mb-4 p-3 border rounded-lg">
              <div className="flex items-center gap-2 mb-2">
                <span className="font-medium">{role.name_zh}</span>
                {fallbackHint && (
                  <span className="text-xs text-gray-500">({fallbackHint})</span>
                )}
              </div>
              {roleLlmIds.length === 0 && (
                <div className="text-sm text-gray-400 mb-2">未配置 — 自动回落</div>
              )}
              {roleLlmIds.map((llmId, idx) => (
                <div key={idx} className="flex items-center gap-2 mb-2">
                  <span className="text-xs text-gray-400 w-6 text-right">{idx + 1}.</span>
                  <select
                    className={cn(selectClass, "max-w-[280px]")}
                    value={llmId}
                    onChange={(e) => handleRoleSelectChange(role.role_id, idx, e.target.value)}
                    disabled={saving === role.role_id}
                  >
                    {llms.map(llm => (
                      <option key={llm.id} value={llm.id}>
                        {llm.name || llm.model}
                      </option>
                    ))}
                  </select>
                  <button
                    className="p-1 text-gray-400 hover:text-blue-600 disabled:opacity-30"
                    onClick={() => handleRoleMoveUp(role.role_id, idx)}
                    disabled={idx === 0 || saving === role.role_id}
                    title="上移"
                  >
                    <ChevronUp className="w-4 h-4" />
                  </button>
                  <button
                    className="p-1 text-gray-400 hover:text-blue-600 disabled:opacity-30"
                    onClick={() => handleRoleMoveDown(role.role_id, idx)}
                    disabled={idx >= roleLlmIds.length - 1 || saving === role.role_id}
                    title="下移"
                  >
                    <ChevronDown className="w-4 h-4" />
                  </button>
                  <button
                    className="p-1 text-gray-400 hover:text-red-600"
                    onClick={() => handleRoleRemoveRow(role.role_id, idx)}
                    disabled={saving === role.role_id}
                    title="移除"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              ))}
              <Button
                variant="secondary"
                size="sm"
                onClick={() => handleRoleAddRow(role.role_id)}
                disabled={saving === role.role_id || llms.length <= roleLlmIds.length}
              >
                <Plus className="w-3 h-3 mr-1" />
                添加备选
              </Button>
            </div>
          )
        })}

      {/* 消息提示 */}
      {message && (
        <div className={cn(
          "mt-3 p-2 rounded text-sm",
          message.includes("失败") ? "bg-red-50 text-red-700" : "bg-green-50 text-green-700"
        )}>
          {message}
        </div>
      )}
    </div>
  )
}
