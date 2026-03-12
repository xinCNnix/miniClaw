"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { FileTree } from "@/components/editor/FileTree"
import { MonacoWrapper } from "@/components/editor/MonacoWrapper"
import { X, Edit, Save, ArrowLeft, Home } from "lucide-react"
import { cn } from "@/lib/utils"
import type { FileContent, File } from "@/types/api"
import { useTranslation } from "@/hooks/use-translation.hook"

interface EditorPanelProps {
  className?: string
  files: FileContent[]
  directories?: File[]
  currentFile: FileContent | null
  currentDirectory?: string
  onLoadFile: (path: string) => Promise<void>
  onSaveFile?: (path: string, content: string) => Promise<void>
  onCloseFile?: () => void
  onChangeDirectory?: (path: string) => Promise<void>
  onGoUpDirectory?: () => Promise<void>
}

export function EditorPanel({
  className,
  files,
  directories = [],
  currentFile,
  currentDirectory = ".",
  onLoadFile,
  onSaveFile,
  onCloseFile,
  onChangeDirectory,
  onGoUpDirectory,
}: EditorPanelProps) {
  const { t } = useTranslation()
  const [isEditing, setIsEditing] = useState(false)
  const [editedContent, setEditedContent] = useState(currentFile?.content || "")

  const handleSave = async () => {
    if (onSaveFile && currentFile) {
      await onSaveFile(currentFile.path, editedContent)
      setIsEditing(false)
    }
  }

  const handleCancelEdit = () => {
    setEditedContent(currentFile?.content || "")
    setIsEditing(false)
  }

  return (
    <aside
      className={cn(
        "w-full h-full glass border-l border-gray-200 flex flex-col",
        className
      )}
    >
      {/* Header */}
      <div className="p-4 border-b border-gray-200 flex items-center justify-between">
        <div className="flex items-center gap-2">
          {currentDirectory !== '.' && onGoUpDirectory && (
            <Button
              variant="ghost"
              size="sm"
              onClick={onGoUpDirectory}
              title={t('editor_panel.go_up') || 'Go up'}
            >
              <ArrowLeft className="w-4 h-4" />
            </Button>
          )}
          {currentDirectory !== '.' && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onChangeDirectory?.('.')}
              title={t('editor_panel.go_home') || 'Go to root'}
            >
              <Home className="w-4 h-4" />
            </Button>
          )}
          <h2 className="text-sm font-semibold text-gray-700">
            {t('editor_panel.title')}
          </h2>
        </div>
        {currentFile && onCloseFile && (
          <Button variant="ghost" size="sm" onClick={onCloseFile}>
            <X className="w-4 h-4" />
          </Button>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* File Tree */}
        <div className="w-48 border-r border-gray-200 overflow-y-auto">
          <FileTree
            files={files}
            directories={directories}
            currentPath={currentFile?.path}
            onSelectFile={onLoadFile}
            onSelectDirectory={onChangeDirectory}
          />
        </div>

        {/* Editor */}
        <div className="flex-1 flex flex-col">
          {currentFile ? (
            <>
              {/* File Header */}
              <div className="p-2 border-b border-gray-200 bg-gray-50 flex items-center justify-between">
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium truncate">
                    {currentFile.path}
                  </p>
                  <p className="text-xs text-gray-500">
                    {currentFile.size ? `${currentFile.size} ${t('editor_panel.bytes')}` : ""}
                  </p>
                </div>
                {onSaveFile && (
                  <div className="flex gap-1">
                    {!isEditing ? (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setIsEditing(true)}
                      >
                        <Edit className="w-3 h-3" />
                      </Button>
                    ) : (
                      <>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={handleSave}
                        >
                          <Save className="w-3 h-3 text-green-600" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={handleCancelEdit}
                        >
                          <X className="w-3 h-3 text-red-600" />
                        </Button>
                      </>
                    )}
                  </div>
                )}
              </div>

              {/* Monaco Editor */}
              <div className="flex-1 min-h-0">
                <MonacoWrapper
                  content={editedContent}
                  language="plaintext"
                  readOnly={!isEditing}
                  onChange={(value) => setEditedContent(value || "")}
                />
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center text-gray-400">
              <p className="text-sm">{t('editor_panel.select_file_hint')}</p>
            </div>
          )}
        </div>
      </div>
    </aside>
  )
}
