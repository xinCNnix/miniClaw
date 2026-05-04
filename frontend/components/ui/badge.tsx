"use client"

import * as React from "react"
import { cn } from "@/lib/utils"

interface BadgeProps {
  variant?: "default" | "secondary" | "outline"
  className?: string
  children: React.ReactNode
}

export function Badge({ variant = "default", className, children }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium transition-colors",
        variant === "default" && "bg-emerald-100 text-emerald-700",
        variant === "secondary" && "bg-gray-100 text-gray-700",
        variant === "outline" && "border border-gray-200 text-gray-700",
        className
      )}
    >
      {children}
    </span>
  )
}
