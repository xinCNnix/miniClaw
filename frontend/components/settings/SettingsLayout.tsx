"use client"

import { useState, useEffect, useCallback } from "react"
import { useRouter } from "next/navigation"
import { useApp } from "@/contexts/AppContext"
import { apiClient } from "@/lib/api"
import { SettingsSidebar } from "./SettingsSidebar"
import { ExternalServicesSection } from "./sections/ExternalServicesSection"
import { SkillsSection } from "./sections/SkillsSection"
import { FormSection } from "./sections/FormSection"
import { LLMSection } from "./sections/LLMSection"
import { LanguageSwitcher } from "@/components/ui/language-switcher"
import { Button } from "@/components/ui/button"
import type { SettingsGroup, SettingItem } from "@/types/config"
import { RotateCcw, AlertTriangle, CheckCircle } from "lucide-react"

export function SettingsLayout() {
  const router = useRouter()
  const { locale } = useApp()
  const [groups, setGroups] = useState<SettingsGroup[]>([])
  const [activeGroup, setActiveGroup] = useState("llm")
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [restartRequired, setRestartRequired] = useState(false)
  const [resetting, setResetting] = useState(false)
  const [toast, setToast] = useState<{ type: "success" | "error"; message: string } | null>(null)

  const isZh = locale === "zh"

  useEffect(() => {
    loadSettings()
  }, [])

  useEffect(() => {
    if (toast) {
      const t = setTimeout(() => setToast(null), 3000)
      return () => clearTimeout(t)
    }
  }, [toast])

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
      const result = await apiClient.updateSettings({ [key]: value })
      if (result.restart_required) {
        setRestartRequired(true)
      }
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
      showToast("error", isZh ? "保存失败" : "Save failed")
    } finally {
      setSaving(false)
    }
  }, [isZh])

  async function handleReset() {
    const confirmed = window.confirm(
      isZh ? "确定重置所有设置为默认值？" : "Reset all settings to defaults?"
    )
    if (!confirmed) return

    setResetting(true)
    try {
      await apiClient.resetSettings()
      setRestartRequired(true)
      showToast("success", isZh ? "已重置为默认值，重启后生效" : "Reset to defaults, restart required")
      await loadSettings()
    } catch (e) {
      console.error("Failed to reset settings:", e)
      showToast("error", isZh ? "重置失败" : "Reset failed")
    } finally {
      setResetting(false)
    }
  }

  function showToast(type: "success" | "error", message: string) {
    setToast({ type, message })
  }

  function renderContent() {
    if (loading) {
      return (
        <div className="flex h-64 items-center justify-center text-gray-400">
          {isZh ? "加载中..." : "Loading..."}
        </div>
      )
    }

    const group = groups.find((g) => g.id === activeGroup)
    if (!group) return null

    const filteredSections = activeGroup === "thinking"
      ? group.sections.filter((s) => s.id !== "tot")
      : group.sections
    const allSettings = filteredSections.flatMap((s) => s.settings)

    // Special groups with custom UI
    if (activeGroup === "llm") {
      return <LLMSection settings={allSettings} onChange={handleSettingChange} locale={locale} />
    }
    if (activeGroup === "external_services") return <ExternalServicesSection />
    if (activeGroup === "skills") {
      const depSettings = group.sections.find((s) => s.id === "dependency")?.settings ?? []
      return <SkillsSection settings={depSettings} onChange={handleSettingChange} locale={locale} />
    }
    // Interface group — language switcher + any settings
    if (activeGroup === "interface") {
      return (
        <div className="space-y-6">
          <div>
            <h3 className="text-sm font-medium mb-3">
              {isZh ? "语言 / Language" : "Language"}
            </h3>
            <LanguageSwitcher />
          </div>
          {allSettings.length > 0 && (
            <FormSection
              settings={allSettings}
              onChange={handleSettingChange}
              locale={locale}
            />
          )}
        </div>
      )
    }

    // Generic form groups
    return <FormSection settings={allSettings} onChange={handleSettingChange} locale={locale} />
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
            &larr;
          </button>
          <h1 className="text-sm font-semibold text-[var(--ink-green)]">
            {isZh ? "设置" : "Settings"}
          </h1>
        </div>
        <SettingsSidebar groups={groups} activeGroup={activeGroup} onSelect={setActiveGroup} />

        {/* Reset button */}
        <div className="border-t border-gray-100 p-3">
          <Button
            variant="ghost"
            size="sm"
            className="w-full text-xs text-gray-500"
            onClick={handleReset}
            disabled={resetting}
          >
            <RotateCcw className="h-3.5 w-3.5 mr-1.5" />
            {resetting
              ? (isZh ? "重置中..." : "Resetting...")
              : (isZh ? "重置为默认" : "Reset to Defaults")}
          </Button>
        </div>
      </aside>

      {/* Content */}
      <main className="flex-1 overflow-y-auto bg-white/40 backdrop-blur-xl">
        <div className="mx-auto max-w-2xl px-8 py-6">
          {/* Group title */}
          {groups.length > 0 && (
            <h2 className="mb-6 text-lg font-semibold text-[var(--ink-green)]">
              {(() => {
                const g = groups.find((g) => g.id === activeGroup)
                return g ? (isZh ? g.label_zh : g.label_en) : ""
              })()}
            </h2>
          )}

          {/* Restart required hint */}
          {restartRequired && (
            <div className="mb-4 flex items-center gap-2 rounded-md bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-700">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              <span>{isZh ? "部分修改需要重启后端生效" : "Some changes require a backend restart to take effect"}</span>
            </div>
          )}

          {renderContent()}
        </div>
      </main>

      {/* Toast */}
      {toast && (
        <div className={`fixed bottom-6 right-6 flex items-center gap-2 rounded-md px-4 py-2 text-sm shadow-lg transition-all ${
          toast.type === "success"
            ? "bg-emerald-600 text-white"
            : "bg-red-600 text-white"
        }`}>
          {toast.type === "success" ? (
            <CheckCircle className="h-4 w-4" />
          ) : (
            <AlertTriangle className="h-4 w-4" />
          )}
          {toast.message}
        </div>
      )}
    </div>
  )
}
