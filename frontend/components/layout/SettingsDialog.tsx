"use client"

import { useState, useEffect } from "react"
import { X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { apiClient } from "@/lib/api"
import { useTranslation } from "@/hooks/use-translation.hook"
import { LLMSettings } from "@/components/chat/llm-settings"
import { AddSkillDialog } from "./AddSkillDialog"
import { LanguageSwitcher } from "@/components/ui/language-switcher"

interface SettingsDialogProps {
  open: boolean
  onClose: () => void
}

interface Skill {
  name: string
  description: string
  description_en: string
  enabled: boolean
  version: string
  author: string
  tags: string[]
  installed_at?: string
}

export function SettingsDialog({ open, onClose }: SettingsDialogProps) {
  const { t } = useTranslation()
  const [activeTab, setActiveTab] = useState<"llm" | "skills" | "language">("llm")
  const [skills, setSkills] = useState<Skill[]>([])
  const [showAddSkillDialog, setShowAddSkillDialog] = useState(false)

  // Load skills when dialog opens
  useEffect(() => {
    if (open) {
      loadSkills()
    }
  }, [open])

  const loadSkills = async () => {
    try {
      const response = await apiClient.listSkills()
      setSkills(response.skills)
    } catch (error) {
      console.error("Failed to load skills:", error)
    }
  }

  // Only render when open
  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-4xl h-[80vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b">
          <h2 className="text-xl font-semibold">设置</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b">
          <button
            className={`flex-1 px-6 py-3 text-center font-medium transition-colors ${
              activeTab === "llm"
                ? "text-blue-600 border-b-2 border-blue-600 bg-blue-50"
                : "text-gray-600 hover:text-gray-800"
            }`}
            onClick={() => setActiveTab("llm")}
          >
            LLM 配置
          </button>
          <button
            className={`flex-1 px-6 py-3 text-center font-medium transition-colors ${
              activeTab === "skills"
                ? "text-blue-600 border-b-2 border-blue-600 bg-blue-50"
                : "text-gray-600 hover:text-gray-800"
            }`}
            onClick={() => setActiveTab("skills")}
          >
            Skills 管理
          </button>
          <button
            className={`flex-1 px-6 py-3 text-center font-medium transition-colors ${
              activeTab === "language"
                ? "text-blue-600 border-b-2 border-blue-600 bg-blue-50"
                : "text-gray-600 hover:text-gray-800"
            }`}
            onClick={() => setActiveTab("language")}
          >
            语言
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {activeTab === "llm" ? (
            <LLMSettings onConfigChange={() => {}} />
          ) : activeTab === "skills" ? (
            <div>
              <div className="flex justify-between items-center mb-4">
                <h3 className="text-lg font-semibold">已安装的 Skills</h3>
                <Button
                  size="sm"
                  onClick={() => setShowAddSkillDialog(true)}
                >
                  添加 Skill
                </Button>
              </div>

              <div className="space-y-2">
                {skills.map((skill) => (
                  <div
                    key={skill.name}
                    className="flex items-center justify-between p-3 border rounded-md"
                  >
                    <div>
                      <div className="font-medium">{skill.name}</div>
                      <div className="text-sm text-gray-600">{skill.description}</div>
                      <div className="text-xs text-gray-500 mt-1">
                        版本: {skill.version} | 作者: {skill.author}
                      </div>
                    </div>
                    <div className="text-xs px-2 py-1 rounded bg-green-100 text-green-800">
                      {skill.enabled ? "已启用" : "已禁用"}
                    </div>
                  </div>
                ))}
              </div>

              {showAddSkillDialog && (
                <AddSkillDialog
                  open={showAddSkillDialog}
                  onClose={() => setShowAddSkillDialog(false)}
                  onSkillAdded={loadSkills}
                />
              )}
            </div>
          ) : (
            <div className="space-y-6">
              <h3 className="text-lg font-semibold">语言设置</h3>
              <LanguageSwitcher className="w-full" />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
