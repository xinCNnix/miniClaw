"use client"

import React, { ReactNode } from "react"
import { useToast, ToastContainer } from "@/hooks/useToast"
import { ToastContextProvider } from "./ToastContext"

/**
 * ToastProvider Component
 *
 * Provides toast notification context to the application.
 * Should be placed near the root of the component tree.
 *
 * Usage:
 * ```tsx
 * <ToastProvider>
 *   <YourApp />
 * </ToastProvider>
 * ```
 */
export function ToastProvider({ children }: { children: ReactNode }) {
  const { toasts, dismiss } = useToast()

  return (
    <ToastContextProvider>
      {children}
      <ToastContainer toasts={toasts} onDismiss={dismiss} />
    </ToastContextProvider>
  )
}
