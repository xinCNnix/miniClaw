"use client"

import { createContext, useContext, ReactNode, useEffect, useState, useCallback, useMemo } from "react"
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

const AppContext = createContext<AppContextType | undefined>(undefined)

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

  // Load sessions on mount - use useCallback to prevent re-creation
  const refreshSessions = useCallback(async () => {
    try {
      const { apiClient } = await import("@/lib/api")
      const response = await apiClient.listSessions()
      setSessions(response.sessions || [])
    } catch (error) {
      console.error("Failed to load sessions:", error)
    }
  }, []) // Empty deps - this function should be stable

  // Load files and sessions on mount
  useEffect(() => {
    editor.refreshFiles()
    refreshSessions()
    // editor.refreshFiles changes on every render, so we disable the warning
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshSessions])

  // Use useMemo to prevent unnecessary re-renders of consumers
  const value = useMemo(() => ({
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
  }), [chat, editor, apiUrl, locale, sessions, refreshSessions])

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}

export function useApp() {
  const context = useContext(AppContext)
  if (!context) {
    throw new Error("useApp must be used within AppProvider")
  }
  return context
}
