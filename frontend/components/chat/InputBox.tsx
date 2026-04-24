"use client"

import { useState, KeyboardEvent, useRef, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Send, Loader2, X, FileText, Music, Video } from "lucide-react"
import { cn } from "@/lib/utils"
import { useTranslation } from "@/hooks/use-translation.hook"
import type { FileCategory } from "@/types/chat"

export interface PendingAttachment {
  file: File
  preview: string
  base64?: string
  category: FileCategory
  filename: string
}

interface InputBoxProps {
  className?: string
  onSend: (content: string, attachments?: PendingAttachment[]) => void
  disabled?: boolean
  placeholder?: string
  onFileSizeWarning?: (file: File, pendingIndex: number) => void
}

function classifyFile(file: File): FileCategory {
  const mime = file.type || ''
  if (mime.startsWith('image/')) return 'image'
  if (mime.startsWith('video/')) return 'video'
  if (mime.startsWith('audio/')) return 'audio'
  return 'document'
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`
}

const SIZE_WARNING = 20 * 1024 * 1024 // 20MB
const MAX_ATTACHMENTS = 10

export function InputBox({
  className,
  onSend,
  disabled,
  placeholder,
  onFileSizeWarning,
}: InputBoxProps) {
  const { t } = useTranslation()
  const [content, setContent] = useState("")
  const [attachments, setAttachments] = useState<PendingAttachment[]>([])
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto"
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`
    }
  }, [content])

  const handleSend = () => {
    const trimmed = content.trim()
    if ((trimmed || attachments.length > 0) && !disabled) {
      onSend(trimmed, attachments)
      setContent("")
      setAttachments([])
    }
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files || files.length === 0) return

    const slotLeft = MAX_ATTACHMENTS - attachments.length
    const toProcess = Array.from(files).slice(0, slotLeft)

    let loadedCount = 0
    const newAttachments: PendingAttachment[] = []

    for (const file of toProcess) {
      const category = classifyFile(file)
      const preview = category === 'image' ? URL.createObjectURL(file) : ''
      const pendingIndex = attachments.length + newAttachments.length

      if (file.size > SIZE_WARNING && onFileSizeWarning) {
        onFileSizeWarning(file, pendingIndex)
      }

      const reader = new FileReader()
      reader.onload = () => {
        newAttachments.push({
          file,
          preview,
          base64: reader.result as string,
          category,
          filename: file.name,
        })
        loadedCount++
        if (loadedCount === toProcess.length) {
          setAttachments(prev => [...prev, ...newAttachments])
        }
      }
      reader.readAsDataURL(file)
    }

    if (fileInputRef.current) {
      fileInputRef.current.value = ""
    }
  }

  const handleRemove = (index: number) => {
    setAttachments(prev => {
      const next = [...prev]
      if (next[index].preview) URL.revokeObjectURL(next[index].preview)
      next.splice(index, 1)
      return next
    })
  }

  const renderPreview = (att: PendingAttachment, index: number) => {
    if (att.category === 'image' && att.preview) {
      return (
        <img
          src={att.preview}
          alt={att.filename}
          className="h-20 w-20 object-cover"
        />
      )
    }
    const icons: Record<FileCategory, typeof FileText> = {
      image: FileText,
      video: Video,
      audio: Music,
      document: FileText,
    }
    const Icon = icons[att.category]
    return (
      <div className="h-20 w-20 flex flex-col items-center justify-center bg-gray-50 gap-1 px-1">
        <Icon className="w-6 h-6 text-gray-400" />
        <span className="text-[10px] text-gray-500 text-center truncate w-full">
          {att.filename}
        </span>
        <span className="text-[9px] text-gray-400">
          {formatSize(att.file.size)}
        </span>
      </div>
    )
  }

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      {attachments.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {attachments.map((att, index) => (
            <div
              key={index}
              className="relative group rounded-md overflow-hidden border border-gray-200"
            >
              {renderPreview(att, index)}
              <button
                onClick={() => handleRemove(index)}
                className="absolute top-1 right-1 bg-red-500 text-white rounded-full p-1 opacity-0 group-hover:opacity-100 transition-opacity"
              >
                <X className="w-3 h-3" />
              </button>
            </div>
          ))}
        </div>
      )}

      <div className={cn("flex gap-2 items-end", className)}>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          onChange={handleFileUpload}
        />
        <Button
          variant="primary"
          size="md"
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled}
          title={t('chat.upload_file_title')}
          data-testid="file-upload-button"
          className="bg-white hover:bg-gray-50 border border-gray-200"
        >
          <span className="text-5xl leading-none font-bold -mt-1.5 text-[var(--ink-green)]">+</span>
        </Button>

        <textarea
          ref={textareaRef}
          value={content}
          onChange={(e) => setContent(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder || t('chat.type_message')}
          disabled={disabled}
          rows={1}
          data-testid="chat-input"
          className={cn(
            "flex-1 resize-none rounded-md border border-gray-300 px-3 py-2",
            "focus:outline-none focus:ring-2 focus:ring-[var(--ink-green)] focus:border-transparent",
            "disabled:cursor-not-allowed disabled:opacity-50",
            "max-h-32 overflow-y-auto"
          )}
        />
        <Button
          variant="primary"
          onClick={handleSend}
          disabled={disabled || (!content.trim() && attachments.length === 0)}
          data-testid="send-button"
        >
          {disabled ? (
            <Loader2 className="w-5 h-5 animate-spin" />
          ) : (
            <Send className="w-5 h-5" />
          )}
        </Button>
      </div>
    </div>
  )
}
