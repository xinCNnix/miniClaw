"use client"

import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import type { SettingItem } from "@/types/config"
import { SettingTooltip } from "./SettingTooltip"
import { useCallback } from "react"

interface SettingNumberInputProps {
  setting: SettingItem
  onChange: (key: string, value: number) => void
  locale: "zh" | "en"
}

export function SettingNumberInput({ setting, onChange, locale }: SettingNumberInputProps) {
  const range = setting.range
  const label = locale === "zh" ? setting.description_zh : setting.description_en
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
          {label}
        </Label>
        <SettingTooltip setting={setting} locale={locale} />
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
          <span className="text-xs text-gray-400 whitespace-nowrap">
            {range.min} ~ {range.max}
          </span>
        )}
      </div>
    </div>
  )
}
