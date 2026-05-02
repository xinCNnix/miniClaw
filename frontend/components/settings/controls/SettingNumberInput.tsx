"use client"

import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import type { SettingItem } from "@/types/config"
import { SettingTooltip } from "./SettingTooltip"
import { useCallback } from "react"

interface SettingNumberInputProps {
  setting: SettingItem
  onChange: (key: string, value: number) => void
}

export function SettingNumberInput({ setting, onChange }: SettingNumberInputProps) {
  const range = setting.range
  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const val = setting.type === "int" ? parseInt(e.target.value, 10) : parseFloat(e.target.value)
      if (!isNaN(val)) {
        onChange(setting.key, val)
      }
    },
    [setting.key, setting.type, onChange]
  )

  return (
    <div className="py-2 space-y-1">
      <div className="flex items-center gap-2">
        <Label htmlFor={setting.key} className="text-sm font-medium">
          {setting.description_zh}
        </Label>
        <SettingTooltip tooltip_zh={setting.tooltip_zh} tooltip_en={setting.tooltip_en} />
      </div>
      <div className="flex items-center gap-2">
        <Input
          id={setting.key}
          type="number"
          value={setting.value as number}
          onChange={handleChange}
          min={range?.min}
          max={range?.max}
          step={setting.type === "float" ? 0.1 : 1}
          className="w-32"
        />
        {range && (
          <span className="text-xs text-muted-foreground whitespace-nowrap">
            {range.min} ~ {range.max}
          </span>
        )}
      </div>
    </div>
  )
}
