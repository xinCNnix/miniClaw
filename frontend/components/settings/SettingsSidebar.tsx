"use client"

import { useApp } from "@/contexts/AppContext"
import type { SettingsGroup } from "@/types/config"

interface SettingsSidebarProps {
  groups: SettingsGroup[]
  activeGroup: string
  onSelect: (groupId: string) => void
}

export function SettingsSidebar({ groups, activeGroup, onSelect }: SettingsSidebarProps) {
  const { locale } = useApp()

  return (
    <nav className="h-full overflow-y-auto">
      {groups.map((group) => (
        <button
          key={group.id}
          onClick={() => onSelect(group.id)}
          className={`flex w-full items-center gap-2 border-l-3 px-4 py-3 text-left text-sm transition-colors ${
            activeGroup === group.id
              ? "border-[var(--ink-green)] bg-[var(--ink-green)]/10 font-semibold text-[var(--ink-green)]"
              : "border-transparent text-gray-600 hover:bg-gray-50"
          }`}
        >
          <span className="text-base">{group.icon}</span>
          <span>{locale === "zh" ? group.label_zh : group.label_en}</span>
        </button>
      ))}
    </nav>
  )
}
