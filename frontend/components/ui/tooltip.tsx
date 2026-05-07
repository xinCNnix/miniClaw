"use client"

import * as React from "react"
import { cn } from "@/lib/utils"

interface TooltipProps {
  children: React.ReactNode
}

export function Tooltip({ children }: TooltipProps) {
  return <>{children}</>
}

interface TooltipTriggerProps {
  asChild?: boolean
  children: React.ReactNode
}

export function TooltipTrigger({ asChild, children }: TooltipTriggerProps) {
  const ctx = React.useContext(TooltipContext)
  return (
    <span
      onMouseEnter={() => ctx?.setOpen(true)}
      onMouseLeave={() => ctx?.setOpen(false)}
      className="inline-flex"
    >
      {children}
    </span>
  )
}

interface TooltipContentProps {
  side?: "top" | "bottom" | "left" | "right"
  className?: string
  children: React.ReactNode
}

export function TooltipContent({ side = "top", className, children }: TooltipContentProps) {
  const ctx = React.useContext(TooltipContext)
  if (!ctx?.open) return null

  const posClasses: Record<string, string> = {
    top: "bottom-full left-1/2 -translate-x-1/2 mb-2",
    bottom: "top-full left-1/2 -translate-x-1/2 mt-2",
    left: "right-full top-1/2 -translate-y-1/2 mr-2",
    right: "left-full top-1/2 -translate-y-1/2 ml-2",
  }

  return (
    <div
      className={cn(
        "absolute z-50 rounded-xl px-4 py-2.5 text-xs text-white shadow-md whitespace-normal break-words border border-white/10",
        posClasses[side],
        className
      )}
      style={{ width: "max-content", maxWidth: "240px", backgroundColor: "#6B8E6B" }}
    >
      {children}
    </div>
  )
}

interface TooltipProviderProps {
  children: React.ReactNode
  delayDuration?: number
}

export function TooltipProvider({ children }: TooltipProviderProps) {
  const [open, setOpen] = React.useState(false)
  return (
    <TooltipContext.Provider value={{ open, setOpen }}>
      <div className="relative" style={{ display: "inline-flex" }}>
        {children}
      </div>
    </TooltipContext.Provider>
  )
}

const TooltipContext = React.createContext<{
  open: boolean
  setOpen: (open: boolean) => void
} | null>(null)
