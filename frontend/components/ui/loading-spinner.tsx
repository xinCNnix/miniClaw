import * as React from "react"
import { cn } from "@/lib/utils"

interface LoadingSpinnerProps {
  size?: "sm" | "md" | "lg"
  className?: string
}

export function LoadingSpinner({ size = "md", className }: LoadingSpinnerProps) {
  const sizes = {
    sm: "w-4 h-4 border-2",
    md: "w-6 h-6 border-2",
    lg: "w-8 h-8 border-2",
  }

  return (
    <div
      className={cn(
        "animate-spin rounded-full border-gray-300 border-t-[var(--ink-green)]",
        sizes[size],
        className
      )}
      role="status"
      aria-label="Loading"
    />
  )
}
