"use client"

import { apiClient } from "@/lib/api"
import { useEffect, useState } from "react"
import type { SkillMetadata } from "@/lib/api"
import { Badge } from "@/components/ui/badge"
import { Switch } from "@/components/ui/switch"
import type { SettingItem } from "@/types/config"
import { FormSection } from "./FormSection"

interface SkillsSectionProps {
  settings: SettingItem[]
  onChange: (key: string, value: unknown) => void
}

export function SkillsSection({ settings, onChange }: SkillsSectionProps) {
  const [skills, setSkills] = useState<SkillMetadata[]>([])

  useEffect(() => {
    apiClient.listSkills().then((res) => setSkills(res.skills))
  }, [])

  return (
    <div className="space-y-6">
      {/* Skills list */}
      <div>
        <h3 className="text-sm font-medium mb-3">已安装技能</h3>
        {skills.length === 0 ? (
          <p className="text-sm text-muted-foreground">加载中...</p>
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
                  <div className="text-xs text-muted-foreground truncate">
                    {skill.description}
                  </div>
                </div>
                <div className="flex gap-1 shrink-0">
                  {skill.tags?.slice(0, 2).map((tag) => (
                    <Badge key={tag} variant="secondary" className="text-xs">
                      {tag}
                    </Badge>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Dependency settings */}
      {settings.length > 0 && (
        <div>
          <h3 className="text-sm font-medium mb-3">依赖管理</h3>
          <FormSection settings={settings} onChange={onChange} />
        </div>
      )}
    </div>
  )
}
