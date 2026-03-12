"use client"

import { useState, useEffect } from "react"
import Editor from "@monaco-editor/react"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { cn } from "@/lib/utils"

interface MonacoWrapperProps {
  content: string
  language?: string
  readOnly?: boolean
  onChange?: (value: string | undefined) => void
  className?: string
}

export function MonacoWrapper({
  content,
  language = "plaintext",
  readOnly = false,
  onChange,
  className,
}: MonacoWrapperProps) {
  const [isEditorReady, setIsEditorReady] = useState(false)

  // Light theme configuration
  const handleEditorDidMount = () => {
    setIsEditorReady(true)
  }

  const handleEditorChange = (value: string | undefined) => {
    if (onChange) {
      onChange(value)
    }
  }

  return (
    <div className={cn("h-full w-full", className)} data-testid="monaco-editor">
      {!isEditorReady && (
        <div className="h-full flex items-center justify-center">
          <LoadingSpinner size="lg" />
        </div>
      )}
      <Editor
        height="100%"
        language={language}
        value={content}
        onChange={handleEditorChange}
        onMount={handleEditorDidMount}
        theme="vs"
        options={{
          readOnly,
          minimap: { enabled: false },
          fontSize: 13,
          lineNumbers: "on",
          scrollBeyondLastLine: false,
          wordWrap: "on",
          automaticLayout: true,
          tabSize: 2,
          formatOnPaste: true,
          formatOnType: true,
        }}
        loading={<LoadingSpinner size="md" />}
      />
    </div>
  )
}
