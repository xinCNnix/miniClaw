"use client"

import { useState, useCallback } from "react"
import { apiClient } from "@/lib/api"
import type { FileContent, File } from "@/types/api"

interface UseEditorOptions {
  apiUrl?: string
  onError?: (error: Error) => void
}

interface UseEditorReturn {
  files: FileContent[]
  directories: File[]
  currentFile: FileContent | null
  currentDirectory: string
  isLoading: boolean
  loadFile: (path: string) => Promise<void>
  saveFile: (path: string, content: string) => Promise<void>
  closeFile: () => void
  refreshFiles: (path?: string) => Promise<void>
  changeDirectory: (path: string) => Promise<void>
  goUpDirectory: () => Promise<void>
}

export function useEditor(options: UseEditorOptions = {}): UseEditorReturn {
  const { apiUrl, onError } = options

  const [files, setFiles] = useState<FileContent[]>([])
  const [directories, setDirectories] = useState<File[]>([])
  const [currentFile, setCurrentFile] = useState<FileContent | null>(null)
  const [currentDirectory, setCurrentDirectory] = useState<string>(".")
  const [isLoading, setIsLoading] = useState(false)

  const refreshFiles = useCallback(async (path: string = currentDirectory) => {
    setIsLoading(true)
    try {
      const fileList = await apiClient.listFiles(path)
      const fileItems = fileList.files || []

      // Separate files and directories
      const dirs = fileItems.filter(f => f.type === "directory")
      const regularFiles = fileItems.filter(f => f.type === "file")

      setDirectories(dirs)
      setFiles(regularFiles)
      setCurrentDirectory(fileList.current_path || path)
    } catch (error) {
      if (onError) {
        onError(error as Error)
      } else {
        console.error("Failed to load files:", error)
      }
    } finally {
      setIsLoading(false)
    }
  }, [apiUrl, onError, currentDirectory])

  const changeDirectory = useCallback(async (path: string) => {
    await refreshFiles(path)
  }, [refreshFiles])

  const goUpDirectory = useCallback(async () => {
    const pathParts = currentDirectory.split('/')
    if (pathParts.length <= 1) {
      // Already at root, go to root
      await refreshFiles('.')
      return
    }

    const parentPath = pathParts.slice(0, -1).join('/')
    await refreshFiles(parentPath || '.')
  }, [currentDirectory, refreshFiles])

  const loadFile = useCallback(async (path: string) => {
    setIsLoading(true)
    try {
      const result = await apiClient.readFile(path)
      setCurrentFile({
        path,
        name: path.split('/').pop() || path,
        type: 'file',
        content: result.content,
      })
    } catch (error) {
      if (onError) {
        onError(error as Error)
      } else {
        console.error("Failed to load file:", error)
      }
    } finally {
      setIsLoading(false)
    }
  }, [apiUrl, onError])

  const saveFile = useCallback(async (path: string, content: string) => {
    setIsLoading(true)
    try {
      await apiClient.writeFile(path, content)
      setCurrentFile({
        path,
        name: path.split('/').pop() || path,
        type: 'file',
        content,
      })

      // Refresh file list
      await refreshFiles()
    } catch (error) {
      if (onError) {
        onError(error as Error)
      } else {
        console.error("Failed to save file:", error)
      }
    } finally {
      setIsLoading(false)
    }
  }, [apiUrl, onError, refreshFiles])

  const closeFile = useCallback(() => {
    setCurrentFile(null)
  }, [])

  return {
    files,
    directories,
    currentFile,
    currentDirectory,
    isLoading,
    loadFile,
    saveFile,
    closeFile,
    refreshFiles,
    changeDirectory,
    goUpDirectory,
  }
}
