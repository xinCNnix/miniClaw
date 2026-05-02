"use client"

import { useState, useEffect, useContext, useCallback } from "react"
import { useRouter } from "next/navigation"
import { AppContext } from "@/contexts/AppContext"
import { apiClient } from "@/lib/api"
import { SettingsSidebar } from "./SettingsSidebar"
import { ExternalServicesSection } from "./sections/ExternalServicesSection"
import { SkillsSection } from "./sections/SkillsSection"
import { FormSection } from "./sections/FormSection"
import type { SettingsGroup, SettingItem } from "@/types/config"

export function SettingsLayout() {
  const router = useRouter()
  const { locale } = useContext(AppContext)
  const [groups, setGroups] = useState<SettingsGroup[]>([])
  const [activeGroup, setActiveGroup] = useState("llm")
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    loadSettings()
  }, [])

  async function loadSettings() {
    try {
      const res = await apiClient.getSettings()
      setGroups(res.groups)
    } catch (e) {
      console.error("Failed to load settings:", e)
    } finally {
      setLoading(false)
    }
  }

  const handleSettingChange = useCallback(async (key: string, value: unknown) => {
    setSaving(true)
    try {
      await apiClient.updateSettings({ [key]: value })
      // Update local state
      setGroups((prev) =>
        prev.map((group) => ({
          ...group,
          sections: group.sections.map((section) => ({
            ...section,
            settings: section.settings.map((s) =>
              s.key === key ? { ...s, value } : s
            ),
          })),
        }))
      )
    } catch (e) {
      console.error("Failed to save setting:", e)
    } finally {
      setSaving(false)
    }
  }, [])

  function renderContent() {
    if (loading) {
      return (
        <div className="flex h-64 items-center justify-center text-gray-400">
          {locale === "zh" ? "加载中..." : "Loading..."}
        </div>
      )
    }

    const group = groups.find((g) => g.id === activeGroup)
    if (!group) return null

    // Special groups with custom UI
    if (activeGroup === "llm") {
      const allSettings = group.sections.flatMap((s) => s.settings)
      return <FormSection settings={allSettings} onChange={handleSettingChange} />
    }
    if (activeGroup === "external_services") return <ExternalServicesSection />
    if (activeGroup === "skills") {
      const depSettings = group.sections.find((s) => s.id === "dependency")?.settings ?? []
      return <SkillsSection settings={depSettings} onChange={handleSettingChange} />
    }
    // Interface group — language hint
    if (activeGroup === "interface") {
      return (
        <div className="space-y-4">
          <p className="text-sm text-gray-500">
            {locale === "zh" ? "语言设置在侧边栏底部切换" : "Language can be switched at the bottom of the sidebar"}
          </p>
          <FormSection
            settings={group.sections.flatMap((s) => s.settings)}
            onChange={handleSettingChange}
          />
        </div>
      )
    }

    // Generic form groups
    return <FormSection settings={group.sections.flatMap((s) => s.settings)} onChange={handleSettingChange} />
  }

  return (
    <div className="flex h-screen">
      {/* Sidebar */}
      <aside className="flex w-60 shrink-0 flex-col border-r border-gray-200/60 bg-white/60 backdrop-blur-xl">
        {/* Header with back button */}
        <div className="flex items-center gap-2 border-b border-gray-100 px-4 py-3">
          <button
            onClick={() => router.push("/chat")}
            className="text-gray-500 hover:text-[var(--ink-green)]"
          >
            ←
          </button>
          <h1 className="text-sm font-semibold text-[var(--ink-green)]">
            {locale === "zh" ? "设置" : "Settings"}
          </h1>
        </div>
        <SettingsSidebar groups={groups} activeGroup={activeGroup} onSelect={setActiveGroup} />
      </aside>

      {/* Content */}
      <main className="flex-1 overflow-y-auto bg-white/40 backdrop-blur-xl">
        <div className="mx-auto max-w-2xl px-8 py-6">
          {/* Group title */}
          {groups.length > 0 && (
            <h2 className="mb-6 text-lg font-semibold text-[var(--ink-green)]">
              {(() => {
                const g = groups.find((g) => g.id === activeGroup)
                return g ? (locale === "zh" ? g.label_zh : g.label_en) : ""
              })()}
            </h2>
          )}
          {renderContent()}
        </div>
      </main>
    </div>
  )
}
