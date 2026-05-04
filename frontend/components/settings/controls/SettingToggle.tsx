"use client"

import { Switch } from "@/components/ui/switch"
import { Label } from "@/components/ui/label"
import type { SettingItem } from "@/types/config"
import { SettingTooltip } from "./SettingTooltip"

interface SettingToggleProps {
  setting: SettingItem
  onChange: (key: string, value: boolean) => void
  locale: "zh" | "en"
}

export function SettingToggle({ setting, onChange, locale }: SettingToggleProps) {
  const checked = !!setting.value
  const label = locale === "zh" ? setting.description_zh : setting.description_en
  return (
    <div className="flex items-center justify-between py-2">
      <div className="flex items-center gap-2 flex-1 min-w-0">
        <Label htmlFor={setting.key} className="text-sm font-medium truncate">
          {label}
        </Label>
        <SettingTooltip setting={setting} locale={locale} />
      </div>
      <Switch
        id={setting.key}
        checked={checked}
        onCheckedChange={(v) => onChange(setting.key, v)}
      />
    </div>
  )
}
