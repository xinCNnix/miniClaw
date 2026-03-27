"use client"

import React, { createContext, useContext, ReactNode } from "react"
import { useToast, ToastType } from "@/hooks/useToast"

interface ToastContextType {
  showToast: (message: string, type?: ToastType, options?: { duration?: number }) => void
}

const ToastContext = createContext<ToastContextType | undefined>(undefined)

/**
 * useToast Hook (Context version)
 *
 * Provides access to the toast notification system from any component.
 * This is a convenience wrapper around the useToast hook.
 *
 * Usage:
 * ```tsx
 * const { showToast } = useToastContext()
 * showToast("Success!", "success")
 * ```
 */
export function useToastContext() {
  const context = useContext(ToastContext)
  if (!context) {
    throw new Error("useToastContext must be used within ToastProvider")
  }
  return context
}

/**
 * ToastContextProvider Component
 *
 * Provides toast context to child components.
 * This is used internally by ToastProvider.
 */
export function ToastContextProvider({ children }: { children: ReactNode }) {
  const { show } = useToast()

  const showToast: ToastContextType["showToast"] = (
    message,
    type = "info",
    options
  ) => {
    show(message, type, options)
  }

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
    </ToastContext.Provider>
  )
}
