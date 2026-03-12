"use client"

import { ReactNode } from "react"
import { cn } from "@/lib/utils"

interface IDELayoutProps {
  children: ReactNode
  className?: string
}

export function IDELayout({ children, className }: IDELayoutProps) {
  return (
    <div
      className={cn(
        "h-screen w-screen flex overflow-hidden bg-[var(--background)]",
        className
      )}
    >
      {children}
    </div>
  )
}
