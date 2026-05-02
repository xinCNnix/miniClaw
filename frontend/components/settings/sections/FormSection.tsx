"use client"

import type { SettingItem } from "@/types/config"
import { SettingToggle } from "../controls/SettingToggle"
import { SettingNumberInput } from "../controls/SettingNumberInput"
import { SettingSelect } from "../controls/SettingSelect"
import { SettingTextInput } from "../controls/SettingTextInput"

interface FormSectionProps {
  settings: SettingItem[]
  onChange: (key: string, value: unknown) => void
}

export function FormSection({ settings, onChange }: FormSectionProps) {
  return (
    <div className="space-y-1">
      {settings.map((s) => {
        switch (s.type) {
          case "bool":
            return <SettingToggle key={s.key} setting={s} onChange={(k, v) => onChange(k, v)} />
          case "int":
            return <SettingNumberInput key={s.key} setting={s} onChange={(k, v) => onChange(k, v)} />
          case "float":
            return <SettingNumberInput key={s.key} setting={s} onChange={(k, v) => onChange(k, v)} />
          case "select":
            return <SettingSelect key={s.key} setting={s} onChange={(k, v) => onChange(k, v)} />
          case "str":
            return <SettingTextInput key={s.key} setting={s} onChange={(k, v) => onChange(k, v)} />
          default:
            return null
        }
      })}
    </div>
  )
}
