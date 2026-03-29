"use client"

import React, { ReactNode } from "react"
import { ErrorBoundary } from "./ErrorBoundary"
import { ToastProvider } from "./ToastProvider"

interface ProvidersProps {
  children: ReactNode
}

/**
 * Providers Component
 *
 * Wraps the application with all necessary providers:
 * - ErrorBoundary: Catches React errors
 * - ToastProvider: Provides toast notifications
 *
 * This should be used in the root layout to wrap the entire app.
 */
export function Providers({ children }: ProvidersProps) {
  return (
    <ErrorBoundary>
      <ToastProvider>{children}</ToastProvider>
    </ErrorBoundary>
  )
}
