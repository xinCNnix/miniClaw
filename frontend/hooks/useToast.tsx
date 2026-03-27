"use client"

import { useState, useCallback, useEffect, ReactNode } from "react"

export type ToastType = "success" | "error" | "info" | "warning"

export interface Toast {
  id: number
  message: string
  type: ToastType
  duration?: number
}

/**
 * useToast Hook
 *
 * Provides a simple toast notification system for displaying
 * temporary messages to the user.
 *
 * Features:
 * - Auto-dismiss after duration
 * - Multiple toast types (success, error, info, warning)
 * - Multiple toasts can be displayed simultaneously
 * - Customizable duration per toast
 * - Manual dismiss capability
 *
 * Usage:
 * ```tsx
 * const { show, toasts, dismiss } = useToast()
 *
 * show("Success!", "success")
 * show("Error occurred", "error", { duration: 5000 })
 * dismiss(toastId)
 * ```
 */
export function useToast() {
  const [toasts, setToasts] = useState<Toast[]>([])

  const show = useCallback(
    (
      message: string,
      type: ToastType = "info",
      options?: { duration?: number }
    ) => {
      const id = Date.now()
      const duration = options?.duration ?? 3000

      setToasts((prev) => [...prev, { id, message, type, duration }])

      // Auto-dismiss after duration
      if (duration > 0) {
        setTimeout(() => {
          setToasts((prev) => prev.filter((t) => t.id !== id))
        }, duration)
      }
    },
    []
  )

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const clear = useCallback(() => {
    setToasts([])
  }, [])

  return {
    toasts,
    show,
    dismiss,
    clear,
  }
}

/**
 * Toast Props Component
 *
 * Renders individual toast notifications.
 */
export interface ToastProps {
  toast: Toast
  onDismiss: (id: number) => void
}

export function ToastComponent({ toast, onDismiss }: ToastProps) {
  useEffect(() => {
    // Auto-dismiss on mount if duration is set
    if (toast.duration && toast.duration > 0) {
      const timer = setTimeout(() => {
        onDismiss(toast.id)
      }, toast.duration)

      return () => clearTimeout(timer)
    }
  }, [toast.id, toast.duration, onDismiss])

  const bgColor = {
    success: "bg-green-500",
    error: "bg-red-500",
    info: "bg-blue-500",
    warning: "bg-yellow-500",
  }[toast.type]

  const icon = {
    success: (
      <svg
        className="w-5 h-5"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M5 13l4 4L19 7"
        />
      </svg>
    ),
    error: (
      <svg
        className="w-5 h-5"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M6 18L18 6M6 6l12 12"
        />
      </svg>
    ),
    info: (
      <svg
        className="w-5 h-5"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
        />
      </svg>
    ),
    warning: (
      <svg
        className="w-5 h-5"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
        />
      </svg>
    ),
  }[toast.type]

  return (
    <div
      className={`${bgColor} text-white px-4 py-3 rounded-lg shadow-lg flex items-center gap-3 animate-slide-in-right`}
      role="alert"
      aria-live="polite"
    >
      <div className="flex-shrink-0">{icon}</div>
      <div className="flex-1 text-sm font-medium">{toast.message}</div>
      <button
        onClick={() => onDismiss(toast.id)}
        className="flex-shrink-0 hover:opacity-80 transition-opacity"
        aria-label="Dismiss notification"
      >
        <svg
          className="w-4 h-4"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M6 18L18 6M6 6l12 12"
          />
        </svg>
      </button>
    </div>
  )
}

/**
 * Toast Container Component
 *
 * Displays all active toast notifications.
 */
export function ToastContainer({ toasts, onDismiss }: { toasts: Toast[]; onDismiss: (id: number) => void }) {
  if (toasts.length === 0) {
    return null
  }

  return (
    <div className="fixed top-4 right-4 z-50 flex flex-col gap-2 max-w-md">
      {toasts.map((toast) => (
        <ToastComponent key={toast.id} toast={toast} onDismiss={onDismiss} />
      ))}
    </div>
  )
}
