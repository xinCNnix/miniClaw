import { AppProvider } from "@/contexts/AppContext"

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8002"
  return <AppProvider apiUrl={apiUrl}>{children}</AppProvider>
}
