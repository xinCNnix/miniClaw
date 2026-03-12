"use client"

import { useState, useEffect } from "react"
import { X, Save, RefreshCw, Trash2, Plus, FileText, Power, PowerOff, AlertTriangle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { apiClient, type SkillMetadata } from "@/lib/api"
import { useTranslation } from "@/hooks/use-translation.hook"
import { LanguageSwitcher } from "@/components/ui/language-switcher"
import { AddSkillDialog } from "./AddSkillDialog"

interface SettingsDialogProps {
  open: boolean
  onClose: () => void
}

interface LLMConfig {
  provider: string
  apiKey?: string
  baseUrl?: string
  model?: string
}

interface SavedConfig {
  has_credentials: boolean
  providers: string[]
}

interface CurrentProviderInfo {
  current_provider: string
  current_model: string
  available_providers: Array<{
    id: string
    name: string
    default_model: string
    requires_api_key: boolean
    description: string
  }>
  configured_providers: string[]
}

interface Skill {
  name: string
  description: string
  description_en: string
  enabled: boolean
  version: string
  author: string
  tags: string[]
  installed_at?: string
}

export function SettingsDialog({ open, onClose }: SettingsDialogProps) {
  const { t } = useTranslation()
  const [activeTab, setActiveTab] = useState<"llm" | "skills" | "language">("llm")
  const [llmConfig, setLlmConfig] = useState<LLMConfig>({
    provider: "qwen",
  })
  const [savedConfig, setSavedConfig] = useState<SavedConfig>({
    has_credentials: false,
    providers: [],
  })
  const [currentProviderInfo, setCurrentProviderInfo] = useState<CurrentProviderInfo | null>(null)
  const [isSwitching, setIsSwitching] = useState(false)
  const [switchMessage, setSwitchMessage] = useState("")
  const [skills, setSkills] = useState<Skill[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [saveMessage, setSaveMessage] = useState("")
  const [showDomainConfirm, setShowDomainConfirm] = useState(false)
  const [pendingDomain, setPendingDomain] = useState("")
  const [showAddSkillDialog, setShowAddSkillDialog] = useState(false)

  // Load configuration when dialog opens
  useEffect(() => {
    if (open) {
      loadConfigStatus()
      loadSkills()
    }
  }, [open])

  const loadConfigStatus = async () => {
    try {
      const status = await apiClient.getConfigStatus()
      setSavedConfig(status)

      // Also get current provider info
      const providerInfo = await apiClient.getCurrentProvider()
      setCurrentProviderInfo(providerInfo)
    } catch (error) {
      console.error("Failed to load config status:", error)
    }
  }

  const handleSwitchProvider = async (provider: string) => {
    if (provider === currentProviderInfo?.current_provider) return

    setIsSwitching(true)
    setSwitchMessage("")

    try {
      const result = await apiClient.switchProvider(provider)

      if (result.success) {
        setSwitchMessage(`已切换到 ${result.provider} (${result.model})`)
        // Reload provider info
        await loadConfigStatus()
        setTimeout(() => setSwitchMessage(""), 3000)
      }
    } catch (error: any) {
      setSwitchMessage(`切换失败: ${error.message || '未知错误'}`)
      console.error("Failed to switch provider:", error)
      setTimeout(() => setSwitchMessage(""), 3000)
    } finally {
      setIsSwitching(false)
    }
  }

  const loadSkills = async () => {
    try {
      const response = await apiClient.listSkills()
      setSkills(response.skills)
    } catch (error) {
      console.error("Failed to load skills:", error)
    }
  }

  const handleSave = async (userConfirmed: boolean = false) => {
    if (!llmConfig.apiKey) {
      setSaveMessage(t('settings.enter_api_key'))
      setTimeout(() => setSaveMessage(""), 2000)
      return
    }

    setIsLoading(true)
    setSaveMessage("")

    try {
      const response = await apiClient.saveLLMConfig({
        provider: llmConfig.provider,
        api_key: llmConfig.apiKey,
        model: llmConfig.model || "",
        base_url: llmConfig.baseUrl || "",
        user_confirmed: userConfirmed,
      })

      if (response.requires_confirmation) {
        // Need user confirmation for domain
        setPendingDomain(response.domain || "")
        setShowDomainConfirm(true)
        setIsLoading(false)
        return
      }

      if (response.success) {
        setSaveMessage(t('settings.config_saved'))
        setLlmConfig({ ...llmConfig, apiKey: "", model: "", baseUrl: "" })
        loadConfigStatus()
        setTimeout(() => setSaveMessage(""), 3000)
      }
    } catch (error: any) {
      setSaveMessage(t('settings.save_failed', { error: error.message || t('common.error') }))
      console.error("Failed to save config:", error)
    } finally {
      setIsLoading(false)
    }
  }

  const handleDeleteProvider = async (provider: string) => {
    const displayName = getProviderDisplayName(provider)
    if (!confirm(t('settings.config_deleted', { provider: displayName }))) return

    try {
      await apiClient.deleteProviderConfig(provider)
      loadConfigStatus()
      setSaveMessage(t('settings.config_deleted', { provider: displayName }))
      setTimeout(() => setSaveMessage(""), 2000)
    } catch (error) {
      setSaveMessage(t('settings.delete_failed'))
      console.error("Failed to delete config:", error)
    }
  }

  const handleDeleteSkill = async (skillName: string) => {
    if (!confirm(t('settings.confirm_delete_skill', { name: skillName }))) return

    try {
      await apiClient.deleteSkill(skillName)
      await loadSkills()
    } catch (error) {
      console.error("Failed to delete skill:", error)
    }
  }

  const handleToggleSkill = async (skillName: string, enabled: boolean) => {
    try {
      await apiClient.toggleSkill(skillName, enabled)

      // Update local state
      setSkills(prev =>
        prev.map(skill =>
          skill.name === skillName ? { ...skill, enabled } : skill
        )
      )
    } catch (error) {
      console.error("Failed to toggle skill:", error)
    }
  }

  const getProviderDisplayName = (provider: string) => {
    const key = `settings.providers.${provider}` as const
    const translated = t(key)
    return translated !== key ? translated : provider
  }

  return (
    <>
      {/* Domain confirmation dialog */}
      {showDomainConfirm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[60]">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
            <div className="flex items-start gap-3">
              <AlertTriangle className="w-6 h-6 text-yellow-500 mt-0.5" />
              <div className="flex-1">
                <h3 className="text-lg font-semibold mb-2">{t('settings.security_warning')}</h3>
                <p className="text-sm text-gray-600 mb-4">
                  {t('settings.domain_warning', { domain: pendingDomain })}
                </p>
                <div className="flex gap-2 justify-end">
                  <Button
                    variant="secondary"
                    onClick={() => {
                      setShowDomainConfirm(false)
                      setPendingDomain("")
                    }}
                  >
                    {t('settings.cancel')}
                  </Button>
                  <Button
                    onClick={() => {
                      setShowDomainConfirm(false)
                      handleSave(true)
                    }}
                  >
                    {t('settings.allow_and_save')}
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {showAddSkillDialog && (
        <AddSkillDialog
          open={showAddSkillDialog}
          onClose={() => setShowAddSkillDialog(false)}
          onSkillAdded={() => {
            loadSkills()
            setShowAddSkillDialog(false)
          }}
        />
      )}

      {open && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[80vh] overflow-hidden flex flex-col">
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b">
              <h2 className="text-lg font-semibold">{t('settings.title')}</h2>
              <Button variant="ghost" size="sm" onClick={onClose}>
                <X className="w-4 h-4" />
              </Button>
            </div>

            {/* Tabs */}
            <div className="flex border-b">
              <button
                className={`flex-1 px-4 py-2 text-sm font-medium transition-colors ${
                  activeTab === "llm"
                    ? "bg-emerald-50 text-emerald-700 border-b-2 border-emerald-700"
                    : "text-gray-600 hover:bg-gray-50"
                }`}
                onClick={() => setActiveTab("llm")}
              >
                {t('settings.llm_config')}
              </button>
              <button
                className={`flex-1 px-4 py-2 text-sm font-medium transition-colors ${
                  activeTab === "skills"
                    ? "bg-emerald-50 text-emerald-700 border-b-2 border-emerald-700"
                    : "text-gray-600 hover:bg-gray-50"
                }`}
                onClick={() => setActiveTab("skills")}
              >
                {t('settings.skills_management')}
              </button>
              <button
                className={`flex-1 px-4 py-2 text-sm font-medium transition-colors ${
                  activeTab === "language"
                    ? "bg-emerald-50 text-emerald-700 border-b-2 border-emerald-700"
                    : "text-gray-600 hover:bg-gray-50"
                }`}
                onClick={() => setActiveTab("language")}
              >
                {t('language.title')}
              </button>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-6">
              {activeTab === "llm" ? (
                <div className="space-y-6">
                  {/* Current Provider Display */}
                  {currentProviderInfo && (
                    <div className="p-4 bg-blue-50 border border-blue-200 rounded-md">
                      <h3 className="text-sm font-medium mb-3 text-blue-900">
                        🤖 当前使用的 LLM
                      </h3>
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="text-lg font-semibold text-blue-800">
                            {currentProviderInfo.available_providers.find(p => p.id === currentProviderInfo.current_provider)?.name || currentProviderInfo.current_provider}
                          </div>
                          <div className="text-sm text-blue-600 mt-1">
                            模型: {currentProviderInfo.current_model || '未配置'}
                          </div>
                        </div>
                        <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse"></div>
                      </div>
                    </div>
                  )}

                  {/* Configured providers list */}
                  {savedConfig.has_credentials && savedConfig.providers.length > 0 && (
                    <div>
                      <h3 className="text-sm font-medium mb-3 text-gray-700">{t('settings.configured_providers')}</h3>
                      <div className="space-y-2">
                        {savedConfig.providers.map((provider) => {
                          const isCurrent = provider === currentProviderInfo?.current_provider
                          const providerInfo = currentProviderInfo?.available_providers.find(p => p.id === provider)

                          return (
                            <div
                              key={provider}
                              className={`flex items-center justify-between p-3 rounded-md border transition-colors ${
                                isCurrent
                                  ? "bg-blue-50 border-blue-300"
                                  : "bg-green-50 border-green-200"
                              }`}
                            >
                              <div className="flex items-center gap-2">
                                <div className={`w-2 h-2 rounded-full ${
                                  isCurrent ? "bg-blue-500" : "bg-green-500"
                                }`}></div>
                                <span className={`font-medium ${
                                  isCurrent ? "text-blue-800" : "text-green-800"
                                }`}>
                                  {getProviderDisplayName(provider)}
                                </span>
                                <span className={`text-xs ${
                                  isCurrent ? "text-blue-600" : "text-green-600"
                                }`}>({provider})</span>
                                {isCurrent && (
                                  <span className="ml-2 text-xs bg-blue-200 text-blue-800 px-2 py-0.5 rounded">
                                    当前使用
                                  </span>
                                )}
                              </div>
                              <div className="flex items-center gap-2">
                                {!isCurrent && (
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => handleSwitchProvider(provider)}
                                    disabled={isSwitching}
                                    className="text-blue-600 hover:text-blue-800 disabled:opacity-50"
                                    title="切换到此 LLM"
                                  >
                                    <RefreshCw className={`w-4 h-4 ${isSwitching ? "animate-spin" : ""}`} />
                                  </Button>
                                )}
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleDeleteProvider(provider)}
                                  className="text-red-500 hover:text-red-700"
                                  title="删除此配置"
                                >
                                  <Trash2 className="w-4 h-4" />
                                </Button>
                              </div>
                            </div>
                          )
                        })}
                      </div>
                      <p className="text-xs text-gray-500 mt-2">
                        {t('settings.encrypted_storage')}
                      </p>
                    </div>
                  )}

                  {/* Switch status message */}
                  {switchMessage && (
                    <div className={`p-3 rounded-md text-sm ${
                      switchMessage.includes('切换失败')
                        ? 'bg-red-50 text-red-700 border border-red-200'
                        : 'bg-green-50 text-green-700 border border-green-200'
                    }`}>
                      {switchMessage}
                    </div>
                  )}

                  {/* Add new configuration */}
                  <div className={savedConfig.has_credentials ? "border-t pt-4" : ""}>
                    <h3 className="text-sm font-medium mb-4 text-gray-700">
                      {savedConfig.has_credentials ? t('settings.add_or_update_config') : t('settings.configure_api_key')}
                    </h3>

                    {/* LLM Provider */}
                    <div className="mb-4">
                      <label className="block text-sm font-medium mb-2">{t('settings.llm_provider')}</label>
                      <select
                        className="w-full px-3 py-2 border rounded-md"
                        value={llmConfig.provider}
                        onChange={(e) => setLlmConfig({ ...llmConfig, provider: e.target.value })}
                      >
                        <optgroup label={t('settings.provider_groups.domestic')}>
                          <option value="qwen">{t('settings.providers.qwen')}</option>
                          <option value="deepseek">{t('settings.providers.deepseek')}</option>
                        </optgroup>
                        <optgroup label={t('settings.provider_groups.openai_compatible')}>
                          <option value="openai">{t('settings.providers.openai')}</option>
                          <option value="claude">{t('settings.providers.claude')}</option>
                          <option value="custom">{t('settings.providers.custom')}</option>
                        </optgroup>
                        <optgroup label={t('settings.provider_groups.other')}>
                          <option value="gemini">{t('settings.providers.gemini')}</option>
                        </optgroup>
                        <optgroup label={t('settings.provider_groups.local')}>
                          <option value="ollama">{t('settings.providers.ollama')}</option>
                        </optgroup>
                      </select>
                    </div>

                    {/* API Base URL */}
                    {(llmConfig.provider === 'custom' || llmConfig.provider === 'claude') && (
                      <div className="mb-4">
                        <label className="block text-sm font-medium mb-2">{t('settings.api_base_url')}</label>
                        <input
                          type="text"
                          className="w-full px-3 py-2 border rounded-md"
                          placeholder={
                            llmConfig.provider === 'claude'
                              ? 'https://api.anthropic.com'
                              : 'https://api.example.com/v1'
                          }
                          value={llmConfig.baseUrl || ""}
                          onChange={(e) => setLlmConfig({ ...llmConfig, baseUrl: e.target.value })}
                        />
                        <p className="text-xs text-gray-500 mt-1">
                          {llmConfig.provider === 'claude'
                            ? t('settings.claude_openai_mode')
                            : t('settings.custom_api_url')}
                        </p>
                      </div>
                    )}

                    {/* API Key */}
                    <div className="mb-4">
                      <label className="block text-sm font-medium mb-2">{t('settings.api_key')}</label>
                      <input
                        type="password"
                        className="w-full px-3 py-2 border rounded-md"
                        placeholder={
                          llmConfig.provider === 'gemini'
                            ? 'AIza...'
                            : llmConfig.provider === 'claude'
                            ? 'sk-ant-...'
                            : 'sk-...'
                        }
                        value={llmConfig.apiKey || ""}
                        onChange={(e) => setLlmConfig({ ...llmConfig, apiKey: e.target.value })}
                      />
                      <p className="text-xs text-gray-500 mt-1">
                        {llmConfig.provider === 'gemini' ? t('settings.gemini_format') : t('settings.encrypted_storage')}
                      </p>
                    </div>

                    {/* Model */}
                    <div className="mb-4">
                      <label className="block text-sm font-medium mb-2">{t('settings.model_name')}</label>
                      <input
                        type="text"
                        className="w-full px-3 py-2 border rounded-md"
                        placeholder={t('settings.model_name_placeholder')}
                        value={llmConfig.model || ""}
                        onChange={(e) => setLlmConfig({ ...llmConfig, model: e.target.value })}
                      />
                      <p className="text-xs text-gray-500 mt-1">
                        {t('settings.model_name_hint')}
                      </p>
                    </div>

                    {/* Security Info */}
                    <div className="p-3 bg-green-50 border border-green-200 rounded-md text-sm text-green-800">
                      <p className="font-medium mb-1">{t('settings.security_protection')}</p>
                      <ul className="space-y-1 text-xs">
                        <li>{t('settings.security_info_1')}</li>
                        <li>{t('settings.security_info_2')}</li>
                        <li>{t('settings.security_info_3')}</li>
                      </ul>
                    </div>
                  </div>
                </div>
              ) : activeTab === "skills" ? (
                <div className="space-y-4">
                  {/* Skills Header */}
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="font-medium">{t('settings.skills_installed')}</h3>
                      <p className="text-sm text-gray-500">{t('settings.skills_installed_desc')}</p>
                    </div>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => setShowAddSkillDialog(true)}
                    >
                      <Plus className="w-4 h-4 mr-1" />
                      {t('settings.add_skill')}
                    </Button>
                  </div>

                  {/* Skills List */}
                  <div className="space-y-2">
                    {skills.map((skill) => (
                      <div
                        key={skill.name}
                        className="flex items-center justify-between p-3 border rounded-md"
                      >
                        <div className="flex items-center gap-3 flex-1">
                          <FileText className="w-5 h-5 text-gray-400" />
                          <div className="flex-1" title={skill.description}>
                            <p className="font-medium">{skill.name}</p>
                            <p className="text-sm text-gray-500 truncate">{skill.description}</p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <button
                            className={`p-2 rounded-md transition-colors ${
                              skill.enabled
                                ? "bg-green-100 text-green-600 hover:bg-green-200"
                                : "bg-gray-100 text-gray-400 hover:bg-gray-200"
                            }`}
                            onClick={() => handleToggleSkill(skill.name, !skill.enabled)}
                            title={skill.enabled ? t('settings.disable') : t('settings.enable')}
                          >
                            {skill.enabled ? <Power className="w-4 h-4" /> : <PowerOff className="w-4 h-4" />}
                          </button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleDeleteSkill(skill.name)}
                          >
                            <Trash2 className="w-4 h-4 text-red-500" />
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>

                  {skills.length === 0 && (
                    <div className="text-center py-8 text-gray-500">
                      <FileText className="w-12 h-12 mx-auto mb-2 opacity-50" />
                      <p>{t('settings.no_skills')}</p>
                      <p className="text-sm">{t('settings.no_skills_desc')}</p>
                    </div>
                  )}

                  {/* Skills Info */}
                  <div className="mt-4 p-3 bg-emerald-50 rounded-md">
                    <p className="text-sm text-emerald-800">
                      <strong>{t('settings.skills_hint')}</strong>
                    </p>
                  </div>
                </div>
              ) : (
                <div className="space-y-6">
                  {/* Language Settings */}
                  <div>
                    <h3 className="text-sm font-medium mb-4 text-gray-700">{t('language.current')}</h3>
                    <LanguageSwitcher className="w-full" />
                    <p className="text-xs text-gray-500 mt-2">
                      {t('language.title')}
                    </p>
                  </div>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="flex items-center justify-between p-4 border-t bg-gray-50">
              <span className={`text-sm ${
                saveMessage.includes(t('settings.config_saved')) ? "text-green-600" :
                saveMessage.includes(t('settings.save_failed')) || saveMessage.includes(t('settings.delete_failed')) ? "text-red-600" :
                "text-gray-500"
              }`}>
                {saveMessage}
              </span>
              <div className="flex gap-2">
                <Button variant="secondary" onClick={onClose}>
                  {t('settings.cancel')}
                </Button>
                <Button onClick={() => handleSave()} disabled={isLoading}>
                  {isLoading ? (
                    <>
                      <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                      {t('settings.saving')}
                    </>
                  ) : (
                    <>
                      <Save className="w-4 h-4 mr-2" />
                      {t('settings.save')}
                    </>
                  )}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
