import type { File } from "@/types/api"

interface CacheEntry {
  files: File[]
  directories: File[]
  timestamp: number
}

class FileListCache {
  private cache: Map<string, CacheEntry> = new Map()
  private readonly TTL = 30000 // 30 seconds

  set(path: string, files: File[], directories: File[]): void {
    this.cache.set(path, { files, directories, timestamp: Date.now() })
  }

  get(path: string): { files: File[]; directories: File[] } | null {
    const entry = this.cache.get(path)
    if (!entry) return null
    if (Date.now() - entry.timestamp > this.TTL) {
      this.cache.delete(path)
      return null
    }
    return { files: entry.files, directories: entry.directories }
  }

  clear(): void {
    this.cache.clear()
  }

  delete(path: string): void {
    this.cache.delete(path)
  }
}

export const fileListCache = new FileListCache()
