"use client"

import { HelpCircle } from "lucide-react"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import type { SettingItem } from "@/types/config"

interface SettingTooltipProps {
  setting: SettingItem
  locale: "zh" | "en"
}

export function SettingTooltip({ setting, locale }: SettingTooltipProps) {
  const title = locale === "zh" ? setting.description_zh : setting.description_en
  const desc = locale === "zh" ? setting.tooltip_zh : setting.tooltip_en
  const isZh = locale === "zh"

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger>
          <HelpCircle className="h-3.5 w-3.5 text-gray-400 cursor-help shrink-0" />
        </TooltipTrigger>
        <TooltipContent side="right" className="space-y-1.5">
          {desc && <div>{desc}</div>}
          {setting.range && (
            <div className="text-gray-300">
              {isZh ? "范围" : "Range"}: {setting.range.min} ~ {setting.range.max}
            </div>
          )}
          {setting.default !== undefined && setting.default !== null && (
            <div className="text-gray-300">
              {isZh ? "默认值" : "Default"}: {String(setting.default)}
            </div>
          )}
          {setting.type === "select" && setting.options && (
            <div className="text-gray-300">
              {isZh ? "可选值" : "Options"}: {setting.options.map((o) => locale === "zh" ? o.label_zh : o.label_en).join(", ")}
            </div>
          )}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}
