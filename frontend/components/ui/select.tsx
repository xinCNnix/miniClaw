"use client"

import * as React from "react"
import { cn } from "@/lib/utils"
import { ChevronDown } from "lucide-react"

interface SelectContextType {
  value: string
  open: boolean
  onValueChange: (value: string) => void
  setOpen: React.Dispatch<React.SetStateAction<boolean>>
}

const SelectContext = React.createContext<SelectContextType | null>(null)

interface SelectProps {
  value: string
  onValueChange: (value: string) => void
  children: React.ReactNode
}

export function Select({ value, onValueChange, children }: SelectProps) {
  const [open, setOpen] = React.useState(false)
  const ref = React.useRef<HTMLDivElement>(null)

  React.useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener("mousedown", handleClick)
    return () => document.removeEventListener("mousedown", handleClick)
  }, [])

  return (
    <SelectContext.Provider value={{ value, open, onValueChange, setOpen }}>
      <div ref={ref} className="relative">
        {children}
      </div>
    </SelectContext.Provider>
  )
}

interface SelectTriggerProps {
  className?: string
  children: React.ReactNode
}

export function SelectTrigger({ className, children }: SelectTriggerProps) {
  const ctx = React.useContext(SelectContext)
  return (
    <button
      type="button"
      onClick={() => ctx?.setOpen?.((prev) => !prev)}
      className={cn(
        "flex h-9 w-full items-center justify-between rounded-md border border-gray-200 bg-white px-3 py-2 text-sm",
        "focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-1",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
    >
      {children}
      <ChevronDown className={cn("h-4 w-4 opacity-50 transition-transform", ctx?.open && "rotate-180")} />
    </button>
  )
}

export function SelectValue({ placeholder }: { placeholder?: string }) {
  const ctx = React.useContext(SelectContext)
  return <span>{ctx?.value || placeholder}</span>
}

interface SelectContentProps {
  children: React.ReactNode
  className?: string
}

export function SelectContent({ children, className }: SelectContentProps) {
  const ctx = React.useContext(SelectContext)
  if (!ctx?.open) return null

  return (
    <div className={cn(
      "absolute z-50 mt-1 max-h-60 w-full overflow-auto rounded-md border border-gray-200 bg-white py-1 shadow-md",
      className
    )}>
      {children}
    </div>
  )
}

interface SelectItemProps {
  value: string
  children: React.ReactNode
}

export function SelectItem({ value, children }: SelectItemProps) {
  const ctx = React.useContext(SelectContext)
  const isSelected = ctx?.value === value
  return (
    <div
      onClick={() => {
        ctx?.onValueChange?.(value)
        ctx?.setOpen?.(false)
      }}
      className={cn(
        "relative flex w-full cursor-pointer select-none items-center rounded-sm py-1.5 px-2 text-sm outline-none",
        "hover:bg-emerald-50 hover:text-emerald-700",
        isSelected && "bg-emerald-50 text-emerald-700 font-medium"
      )}
    >
      {children}
    </div>
  )
}
