"use client"

import { apiClient } from "@/lib/api"
import { useEffect, useState } from "react"
import type { SettingItem } from "@/types/config"
import { SettingToggle } from "../controls/SettingToggle"
import { SettingNumberInput } from "../controls/SettingNumberInput"
import { SettingTextInput } from "../controls/SettingTextInput"

interface LLMSectionProps {
  settings: SettingItem[]
  onChange: (key: string, value: unknown) => void
}

export function LLMSection({ settings, onChange }: LLMSectionProps) {
  return (
    <div className="space-y-2">
      {settings.map((s) => {
        switch (s.type) {
          case "bool":
            return <SettingToggle key={s.key} setting={s} onChange={(k, v) => onChange(k, v)} />
          case "int":
            return <SettingNumberInput key={s.key} setting={s} onChange={(k, v) => onChange(k, v)} />
          case "str":
            return <SettingTextInput key={s.key} setting={s} onChange={(k, v) => onChange(k, v)} />
          default:
            return null
        }
      })}
    </div>
  )
}
