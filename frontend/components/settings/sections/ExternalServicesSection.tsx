"use client"

import { apiClient } from "@/lib/api"
import { useEffect, useState } from "react"
import type { ExternalService } from "@/types/config"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Key, Check, X } from "lucide-react"
import { useApp } from "@/contexts/AppContext"

export function ExternalServicesSection() {
  const { locale } = useApp()
  const [services, setServices] = useState<ExternalService[]>([])
  const [editingKey, setEditingKey] = useState<string | null>(null)
  const [keyValue, setKeyValue] = useState("")

  useEffect(() => {
    apiClient.getExternalKeys().then((res) => setServices(res.services))
  }, [])

  const handleSave = async (serviceKey: string) => {
    await apiClient.saveExternalKey(serviceKey, keyValue)
    setEditingKey(null)
    setKeyValue("")
    const res = await apiClient.getExternalKeys()
    setServices(res.services)
  }

  const isZh = locale === "zh"

  return (
    <div className="space-y-4">
      {services.map((svc) => (
        <div key={svc.key} className="flex items-center gap-3 py-2">
          <Key className="h-4 w-4 text-gray-400 shrink-0" />
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium">
              {isZh ? svc.name_zh : svc.name_en}
            </div>
            <div className="text-xs text-gray-400">
              {isZh ? svc.description_zh : svc.description_en}
            </div>
          </div>
          {editingKey === svc.key ? (
            <div className="flex items-center gap-2">
              <Input
                type="password"
                value={keyValue}
                onChange={(e) => setKeyValue(e.target.value)}
                placeholder={isZh ? "输入 API Key" : "Enter API Key"}
                className="w-48"
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleSave(svc.key)
                  if (e.key === "Escape") { setEditingKey(null); setKeyValue("") }
                }}
              />
              <Button size="sm" variant="ghost" onClick={() => handleSave(svc.key)}>
                <Check className="h-4 w-4" />
              </Button>
              <Button size="sm" variant="ghost" onClick={() => { setEditingKey(null); setKeyValue("") }}>
                <X className="h-4 w-4" />
              </Button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              {svc.has_key ? (
                <span className="text-xs text-green-600 flex items-center gap-1">
                  <Check className="h-3 w-3" /> {isZh ? "已配置" : "Configured"}
                </span>
              ) : (
                <span className="text-xs text-gray-400">{isZh ? "未配置" : "Not configured"}</span>
              )}
              <Button size="sm" variant="secondary" onClick={() => setEditingKey(svc.key)}>
                {svc.has_key
                  ? (isZh ? "更换" : "Update")
                  : (isZh ? "配置" : "Configure")}
              </Button>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
