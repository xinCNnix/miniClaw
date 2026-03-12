"use client"

import { useState } from "react"
import { X, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { apiClient } from "@/lib/api"
import { useTranslation } from "@/hooks/use-translation.hook"

interface AddSkillDialogProps {
  open: boolean
  onClose: () => void
  onSkillAdded: () => void
}

interface FormData {
  name: string
  description: string
  author: string
  tags: string
  version: string
}

export function AddSkillDialog({ open, onClose, onSkillAdded }: AddSkillDialogProps) {
  const { t } = useTranslation()
  const [formData, setFormData] = useState<FormData>({
    name: "",
    description: "",
    author: "",
    tags: "",
    version: "1.0.0",
  })
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState("")

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")

    // Validate
    if (!formData.name.trim()) {
      setError("请输入技能名称")
      return
    }

    if (!formData.description.trim()) {
      setError("请输入技能描述")
      return
    }

    // Validate skill name format
    const nameRegex = /^[a-zA-Z][a-zA-Z0-9_]*$/
    if (!nameRegex.test(formData.name)) {
      setError("技能名称必须以字母开头，只能包含字母、数字和下划线")
      return
    }

    setIsLoading(true)

    try {
      const response = await apiClient.createSkill({
        name: formData.name.trim(),
        description: formData.description.trim(),
        author: formData.author.trim(),
        tags: formData.tags
          .split(",")
          .map(t => t.trim())
          .filter(t => t),
        version: formData.version || "1.0.0",
      })

      if (response.success) {
        onSkillAdded()
        handleClose()
      }
    } catch (err: any) {
      setError(err.message || "创建技能失败")
    } finally {
      setIsLoading(false)
    }
  }

  const handleClose = () => {
    if (!isLoading) {
      setFormData({
        name: "",
        description: "",
        author: "",
        tags: "",
        version: "1.0.0",
      })
      setError("")
      onClose()
    }
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[60]">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b">
          <h2 className="text-lg font-semibold">{t('settings.add_skill')}</h2>
          <Button variant="ghost" size="sm" onClick={handleClose} disabled={isLoading}>
            <X className="w-4 h-4" />
          </Button>
        </div>

        {/* Content */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-6 space-y-4">
          {/* Error Message */}
          {error && (
            <div className="p-3 bg-red-50 border border-red-200 rounded text-sm text-red-600">
              {error}
            </div>
          )}

          {/* Skill Name */}
          <div>
            <label className="block text-sm font-medium mb-2">
              技能名称 <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              className="w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-[var(--ink-green)]"
              placeholder="例如: file_manager"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              disabled={isLoading}
              pattern="^[a-zA-Z][a-zA-Z0-9_]*$"
              required
            />
            <p className="text-xs text-gray-500 mt-1">
              必须以字母开头，只能包含字母、数字和下划线
            </p>
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium mb-2">
              技能描述 <span className="text-red-500">*</span>
            </label>
            <textarea
              className="w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-[var(--ink-green)] resize-none"
              placeholder="详细描述这个技能的功能和使用方法..."
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              disabled={isLoading}
              rows={4}
              required
            />
            <p className="text-xs text-gray-500 mt-1">
              描述会自动精炼为简短摘要供界面显示
            </p>
          </div>

          {/* Author */}
          <div>
            <label className="block text-sm font-medium mb-2">作者</label>
            <input
              type="text"
              className="w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-[var(--ink-green)]"
              placeholder="例如: Your Name"
              value={formData.author}
              onChange={(e) => setFormData({ ...formData, author: e.target.value })}
              disabled={isLoading}
            />
          </div>

          {/* Tags */}
          <div>
            <label className="block text-sm font-medium mb-2">标签</label>
            <input
              type="text"
              className="w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-[var(--ink-green)]"
              placeholder="例如: files, utility (用逗号分隔)"
              value={formData.tags}
              onChange={(e) => setFormData({ ...formData, tags: e.target.value })}
              disabled={isLoading}
            />
            <p className="text-xs text-gray-500 mt-1">
              用逗号分隔多个标签
            </p>
          </div>

          {/* Version */}
          <div>
            <label className="block text-sm font-medium mb-2">版本</label>
            <input
              type="text"
              className="w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-[var(--ink-green)]"
              placeholder="1.0.0"
              value={formData.version}
              onChange={(e) => setFormData({ ...formData, version: e.target.value })}
              disabled={isLoading}
            />
          </div>
        </form>

        {/* Footer */}
        <div className="flex items-center justify-between p-4 border-t bg-gray-50">
          <span className="text-sm text-gray-500">
            技能将自动添加到系统中
          </span>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={handleClose} disabled={isLoading}>
              取消
            </Button>
            <Button type="submit" onClick={handleSubmit} disabled={isLoading}>
              {isLoading ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  创建中...
                </>
              ) : (
                "创建"
              )}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
