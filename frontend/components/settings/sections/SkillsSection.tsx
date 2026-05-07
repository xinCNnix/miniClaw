"use client"

import { apiClient } from "@/lib/api"
import { useEffect, useState } from "react"
import type { SkillMetadata } from "@/lib/api"
import { Badge } from "@/components/ui/badge"
import { Switch } from "@/components/ui/switch"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import type { SettingItem } from "@/types/config"
import { FormSection } from "./FormSection"
import { Plus, Trash2, X, Check } from "lucide-react"

interface SkillsSectionProps {
  settings: SettingItem[]
  onChange: (key: string, value: unknown) => void
  locale: "zh" | "en"
}

export function SkillsSection({ settings, onChange, locale }: SkillsSectionProps) {
  const [skills, setSkills] = useState<SkillMetadata[]>([])
  const [addingSkill, setAddingSkill] = useState(false)
  const [newSkillName, setNewSkillName] = useState("")
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)

  const isZh = locale === "zh"

  useEffect(() => {
    loadSkills()
  }, [])

  async function loadSkills() {
    try {
      const res = await apiClient.listSkills()
      setSkills(res.skills)
    } catch (e) {
      console.error("Failed to load skills:", e)
    }
  }

  async function handleAddSkill() {
    if (!newSkillName.trim()) return
    try {
      await apiClient.createSkill({ name: newSkillName.trim(), description: "" })
      setNewSkillName("")
      setAddingSkill(false)
      await loadSkills()
    } catch (e) {
      console.error("Failed to create skill:", e)
    }
  }

  async function handleDeleteSkill(name: string) {
    try {
      await apiClient.deleteSkill(name)
      setConfirmDelete(null)
      await loadSkills()
    } catch (e) {
      console.error("Failed to delete skill:", e)
    }
  }

  return (
    <div className="space-y-6">
      {/* Skills list */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-medium">
            {isZh ? "已安装技能" : "Installed Skills"}
          </h3>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => setAddingSkill(true)}
          >
            <Plus className="h-3.5 w-3.5 mr-1" />
            {isZh ? "添加技能" : "Add Skill"}
          </Button>
        </div>

        {addingSkill && (
          <div className="flex items-center gap-2 mb-3 py-2">
            <Input
              value={newSkillName}
              onChange={(e) => setNewSkillName(e.target.value)}
              placeholder={isZh ? "技能名称" : "Skill name"}
              className="max-w-xs"
              onKeyDown={(e) => {
                if (e.key === "Enter") handleAddSkill()
                if (e.key === "Escape") { setAddingSkill(false); setNewSkillName("") }
              }}
            />
            <Button size="sm" variant="ghost" onClick={handleAddSkill}>
              <Check className="h-4 w-4 text-green-600" />
            </Button>
            <Button size="sm" variant="ghost" onClick={() => { setAddingSkill(false); setNewSkillName("") }}>
              <X className="h-4 w-4" />
            </Button>
          </div>
        )}

        {skills.length === 0 ? (
          <p className="text-sm text-gray-400">{isZh ? "加载中..." : "Loading..."}</p>
        ) : (
          <div className="space-y-2">
            {skills.map((skill) => (
              <div key={skill.name} className="flex items-center gap-3 py-1.5">
                <Switch
                  checked={skill.enabled}
                  onCheckedChange={(enabled) => {
                    apiClient.toggleSkill(skill.name, enabled).then((updated) => {
                      setSkills((prev) =>
                        prev.map((s) => (s.name === updated.name ? updated : s))
                      )
                    })
                  }}
                />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium truncate">{skill.name}</div>
                  <div className="text-xs text-gray-400 truncate">
                    {isZh
                      ? (skill.description || skill.description_en)
                      : (skill.description_en || skill.description)}
                  </div>
                </div>
                <div className="flex gap-1 shrink-0">
                  {skill.tags?.slice(0, 2).map((tag) => (
                    <Badge key={tag} variant="secondary" className="text-xs">
                      {tag}
                    </Badge>
                  ))}
                </div>
                {confirmDelete === skill.name ? (
                  <div className="flex items-center gap-1">
                    <Button size="sm" variant="ghost" onClick={() => handleDeleteSkill(skill.name)}>
                      <Check className="h-3.5 w-3.5 text-red-500" />
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setConfirmDelete(null)}>
                      <X className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                ) : (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setConfirmDelete(skill.name)}
                  >
                    <Trash2 className="h-3.5 w-3.5 text-gray-400 hover:text-red-500" />
                  </Button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Dependency settings */}
      {settings.length > 0 && (
        <div>
          <h3 className="text-sm font-medium mb-3">
            {isZh ? "依赖管理" : "Dependency Settings"}
          </h3>
          <FormSection settings={settings} onChange={onChange} locale={locale} />
        </div>
      )}
    </div>
  )
}
