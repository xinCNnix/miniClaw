"use client"

import { apiClient } from "@/lib/api"
import { useEffect, useState } from "react"
import type { ExternalService } from "@/types/config"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Key, Check, X } from "lucide-react"

export function ExternalServicesSection() {
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

  return (
    <div className="space-y-4">
      {services.map((svc) => (
        <div key={svc.key} className="flex items-center gap-3 py-2">
          <Key className="h-4 w-4 text-muted-foreground shrink-0" />
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium">{svc.name_zh}</div>
            <div className="text-xs text-muted-foreground">{svc.description_zh}</div>
          </div>
          {editingKey === svc.key ? (
            <div className="flex items-center gap-2">
              <Input
                type="password"
                value={keyValue}
                onChange={(e) => setKeyValue(e.target.value)}
                placeholder="输入 API Key"
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
                  <Check className="h-3 w-3" /> 已配置
                </span>
              ) : (
                <span className="text-xs text-muted-foreground">未配置</span>
              )}
              <Button size="sm" variant="outline" onClick={() => setEditingKey(svc.key)}>
                {svc.has_key ? "更换" : "配置"}
              </Button>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
