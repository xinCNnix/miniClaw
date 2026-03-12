"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"
import { useTranslation } from "@/hooks/use-translation.hook"

export default function HomePage() {
  const router = useRouter()
  const { t } = useTranslation()

  useEffect(() => {
    // Redirect to chat page
    router.push("/chat")
  }, [router])

  return (
    <div className="h-screen w-screen flex items-center justify-center bg-gray-50">
      <div className="text-center">
        <h1 className="text-2xl font-bold text-[var(--ink-green)] mb-2">
          miniClaw
        </h1>
        <p className="text-gray-600">{t('common.loading')}</p>
      </div>
    </div>
  )
}
