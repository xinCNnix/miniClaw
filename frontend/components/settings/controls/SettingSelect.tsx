"use client"

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Label } from "@/components/ui/label"
import type { SettingItem } from "@/types/config"
import { SettingTooltip } from "./SettingTooltip"

interface SettingSelectProps {
  setting: SettingItem
  onChange: (key: string, value: string) => void
}

export function SettingSelect({ setting, onChange }: SettingSelectProps) {
  const options = setting.options ?? []
  return (
    <div className="py-2 space-y-1">
      <div className="flex items-center gap-2">
        <Label className="text-sm font-medium">{setting.description_zh}</Label>
        <SettingTooltip tooltip_zh={setting.tooltip_zh} tooltip_en={setting.tooltip_en} />
      </div>
      <Select value={String(setting.value)} onValueChange={(v) => onChange(setting.key, v)}>
        <SelectTrigger className="w-64">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {options.map((opt) => (
            <SelectItem key={opt.value} value={opt.value}>
              {opt.label_zh}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
