"use client"

import { createContext, useContext, ReactNode, useEffect, useState } from "react"
import { useChat } from "@/hooks/useChat"
import { useEditor } from "@/hooks/useEditor"
import type { Locale } from "@/lib/i18n"
import type { Session } from "@/types/api"

interface AppContextType {
  chat: ReturnType<typeof useChat>
  editor: Omit<ReturnType<typeof useEditor>, 'loadFile' | 'saveFile' | 'closeFile'>
  apiUrl: string
  locale: Locale
  setLocale: (locale: Locale) => void
  sessions: Session[]
  refreshSessions: () => Promise<void>
  loadFile: (path: string) => Promise<void>
  saveFile: (path: string, content: string) => Promise<void>
  closeFile: () => void
}

export const AppContext = createContext<AppContextType | undefined>(undefined)

const LOCALE_STORAGE_KEY = 'app-locale'

interface AppProviderProps {
  children: ReactNode
  apiUrl?: string
}

function getStoredLocale(): Locale {
  if (typeof window === 'undefined') return 'zh'
  const stored = localStorage.getItem(LOCALE_STORAGE_KEY)
  if (stored === 'zh' || stored === 'en') return stored
  return 'zh'
}

function saveLocale(locale: Locale) {
  if (typeof window !== 'undefined') {
    localStorage.setItem(LOCALE_STORAGE_KEY, locale)
  }
}

export function AppProvider({ children, apiUrl = "" }: AppProviderProps) {
  const [locale, setLocaleState] = useState<Locale>(getStoredLocale())
  const [sessions, setSessions] = useState<Session[]>([])
  const chat = useChat({ apiUrl })
  const editor = useEditor({ apiUrl })

  const setLocale = (newLocale: Locale) => {
    setLocaleState(newLocale)
    saveLocale(newLocale)
  }

  // Load sessions on mount
  const refreshSessions = async () => {
    try {
      const { apiClient } = await import("@/lib/api")
      const response = await apiClient.listSessions()
      setSessions(response.sessions || [])
    } catch (error) {
      console.error("Failed to load sessions:", error)
    }
  }

  // Load files and sessions on mount
  useEffect(() => {
    editor.refreshFiles()
    refreshSessions()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const value = {
    chat,
    editor,
    apiUrl,
    locale,
    setLocale,
    sessions,
    refreshSessions,
    loadFile: editor.loadFile,
    saveFile: editor.saveFile,
    closeFile: editor.closeFile,
  }

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}

export function useApp() {
  const context = useContext(AppContext)
  if (!context) {
    throw new Error("useApp must be used within AppProvider")
  }
  return context
}
