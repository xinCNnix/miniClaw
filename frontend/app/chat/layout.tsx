"use client"

import { AppProvider } from "@/contexts/AppContext"

export default function ChatLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <AppProvider apiUrl={process.env.NEXT_PUBLIC_API_URL || "http://localhost:8002"}>
      {children}
    </AppProvider>
  )
}
