"use client"

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Label } from "@/components/ui/label"
import type { SettingItem } from "@/types/config"
import { SettingTooltip } from "./SettingTooltip"

interface SettingSelectProps {
  setting: SettingItem
  onChange: (key: string, value: string) => void
  locale: "zh" | "en"
}

export function SettingSelect({ setting, onChange, locale }: SettingSelectProps) {
  const options = setting.options ?? []
  const label = locale === "zh" ? setting.description_zh : setting.description_en
  return (
    <div className="py-2 space-y-1">
      <div className="flex items-center gap-2">
        <Label className="text-sm font-medium">{label}</Label>
        <SettingTooltip setting={setting} locale={locale} />
      </div>
      <Select value={String(setting.value)} onValueChange={(v) => onChange(setting.key, v)}>
        <SelectTrigger className="w-64">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {options.map((opt) => (
            <SelectItem key={opt.value} value={opt.value}>
              {locale === "zh" ? opt.label_zh : opt.label_en}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
