"use client"

import { Globe } from "lucide-react"
import { useApp } from "@/contexts/AppContext"
import { localeNames, type Locale, locales } from "@/lib/i18n"

interface LanguageSwitcherProps {
  className?: string
}

export function LanguageSwitcher({ className = "" }: LanguageSwitcherProps) {
  const { locale, setLocale } = useApp()

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <Globe className="w-4 h-4 text-gray-500" />
      <select
        value={locale}
        onChange={(e) => setLocale(e.target.value as Locale)}
        className="px-2 py-1 text-sm border rounded-md bg-white hover:bg-gray-50 transition-colors cursor-pointer"
      >
        {locales.map((loc) => (
          <option key={loc} value={loc}>
            {localeNames[loc]}
          </option>
        ))}
      </select>
    </div>
  )
}
