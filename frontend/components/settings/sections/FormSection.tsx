"use client"

import type { SettingItem } from "@/types/config"
import { SettingToggle } from "../controls/SettingToggle"
import { SettingNumberInput } from "../controls/SettingNumberInput"
import { SettingSelect } from "../controls/SettingSelect"
import { SettingTextInput } from "../controls/SettingTextInput"

interface FormSectionProps {
  settings: SettingItem[]
  onChange: (key: string, value: unknown) => void
  locale: "zh" | "en"
}

export function FormSection({ settings, onChange, locale }: FormSectionProps) {
  return (
    <div className="space-y-1">
      {settings.map((s) => {
        switch (s.type) {
          case "bool":
            return <SettingToggle key={s.key} setting={s} onChange={(k, v) => onChange(k, v)} locale={locale} />
          case "int":
            return <SettingNumberInput key={s.key} setting={s} onChange={(k, v) => onChange(k, v)} locale={locale} />
          case "float":
            return <SettingNumberInput key={s.key} setting={s} onChange={(k, v) => onChange(k, v)} locale={locale} />
          case "select":
            return <SettingSelect key={s.key} setting={s} onChange={(k, v) => onChange(k, v)} locale={locale} />
          case "str":
            return <SettingTextInput key={s.key} setting={s} onChange={(k, v) => onChange(k, v)} locale={locale} />
          default:
            return null
        }
      })}
    </div>
  )
}
