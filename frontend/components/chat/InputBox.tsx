"use client"

import { useState, KeyboardEvent, useRef, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Send, Loader2, Image as ImageIcon, X } from "lucide-react"
import { cn } from "@/lib/utils"
import { useTranslation } from "@/hooks/use-translation.hook"
import { useToastContext } from "@/components/common/ToastContext"

interface ImageAttachment {
  file: File
  preview: string
  base64?: string
}

interface InputBoxProps {
  className?: string
  onSend: (content: string, images?: ImageAttachment[]) => Promise<void>
  disabled?: boolean
  placeholder?: string
}

export function InputBox({
  className,
  onSend,
  disabled,
  placeholder,
}: InputBoxProps) {
  const { t } = useTranslation()
  const { showToast } = useToastContext()
  const [content, setContent] = useState("")
  const [images, setImages] = useState<ImageAttachment[]>([])
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto"
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`
    }
  }, [content])

  // Cleanup object URLs on unmount
  useEffect(() => {
    return () => {
      images.forEach(img => {
        if (img.preview) {
          URL.revokeObjectURL(img.preview)
        }
      })
    }
  }, [images])

  const handleSend = async () => {
    const trimmed = content.trim()
    if ((trimmed || images.length > 0) && !disabled) {
      await onSend(trimmed, images)
      setContent("")
      setImages([])
    }
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files || files.length === 0) return

    const newImages: ImageAttachment[] = []

    for (let i = 0; i < files.length; i++) {
      const file = files[i]
      if (!file.type.startsWith("image/")) {
        showToast(t('chat.upload_only_images'), 'error')
        continue
      }

      // Limit size to 10MB
      if (file.size > 10 * 1024 * 1024) {
        showToast(t('chat.upload_too_large', { name: file.name }), 'error')
        continue
      }

      // 创建预览
      const preview = URL.createObjectURL(file)

      // 转换为 base64
      const reader = new FileReader()
      reader.onload = () => {
        const base64 = reader.result as string
        newImages.push({
          file,
          preview,
          base64,
        })

        // 所有图片处理完成后更新状态
        if (newImages.length === images.length + i) {
          setImages(prev => [...prev, ...newImages])
        }
      }
      reader.readAsDataURL(file)
    }

    // 重置 input
    if (fileInputRef.current) {
      fileInputRef.current.value = ""
    }
  }

  const handleRemoveImage = (index: number) => {
    setImages(prev => {
      const newImages = [...prev]
      URL.revokeObjectURL(newImages[index].preview)
      newImages.splice(index, 1)
      return newImages
    })
  }

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      {/* Images Preview */}
      {images.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {images.map((image, index) => (
            <div
              key={index}
              className="relative group rounded-md overflow-hidden border border-gray-200"
            >
              <img
                src={image.preview}
                alt={`Upload ${index + 1}`}
                className="h-20 w-20 object-cover"
              />
              <button
                onClick={() => handleRemoveImage(index)}
                className="absolute top-1 right-1 bg-red-500 text-white rounded-full p-1 opacity-0 group-hover:opacity-100 transition-opacity"
              >
                <X className="w-3 h-3" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Input Area */}
      <div className={cn("flex gap-2 items-end", className)}>
        {/* Image Upload Button */}
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          multiple
          className="hidden"
          onChange={handleImageUpload}
        />
        <Button
          variant="secondary"
          size="md"
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled}
          title={t('chat.upload_image_title')}
          data-testid="image-upload-button"
        >
          <ImageIcon className="w-5 h-5" />
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
          disabled={disabled || (!content.trim() && images.length === 0)}
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
