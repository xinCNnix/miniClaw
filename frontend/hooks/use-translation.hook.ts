/**
 * Hook for using translations
 */

import { useApp } from "@/contexts/AppContext"
import { getTranslation, type Locale, defaultLocale } from "@/lib/i18n"

export function useTranslation() {
  // Try to get locale from AppContext, fallback to default
  let locale: Locale = defaultLocale

  try {
    const app = useApp()
    locale = app.locale
  } catch {
    // useApp must be used within AppProvider
    // Use default locale when context is not available
    locale = defaultLocale
  }

  return {
    t: (key: string, params?: Record<string, string | number>) => getTranslation(locale, key, params),
    locale,
  }
}
