"use client"

import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import type { SettingItem } from "@/types/config"
import { SettingTooltip } from "./SettingTooltip"
import { useCallback } from "react"

interface SettingTextInputProps {
  setting: SettingItem
  onChange: (key: string, value: string) => void
  locale: "zh" | "en"
}

export function SettingTextInput({ setting, onChange, locale }: SettingTextInputProps) {
  const label = locale === "zh" ? setting.description_zh : setting.description_en
  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      onChange(setting.key, e.target.value)
    },
    [setting.key, onChange]
  )

  return (
    <div className="py-2 space-y-1">
      <div className="flex items-center gap-2">
        <Label htmlFor={setting.key} className="text-sm font-medium">
          {label}
        </Label>
        <SettingTooltip setting={setting} locale={locale} />
      </div>
      <Input
        id={setting.key}
        type="text"
        value={setting.value as string}
        onChange={handleChange}
        className="max-w-md"
      />
    </div>
  )
}
