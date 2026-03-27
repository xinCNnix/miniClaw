import type { Metadata } from "next"
import "./globals.css"
import { Providers } from "@/components/common/Providers"
import { AppProvider } from "@/contexts/AppContext"

export const metadata: Metadata = {
  title: "MiNiCLAW - AI Agent System",
  description: "Lightweight, transparent AI Agent system with file-first memory and skills as plugins",
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className="antialiased font-sans">
        <Providers>
          <AppProvider apiUrl={process.env.NEXT_PUBLIC_API_URL || "http://localhost:8002"}>
            {children}
          </AppProvider>
        </Providers>
      </body>
    </html>
  )
}
