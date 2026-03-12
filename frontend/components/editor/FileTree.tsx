"use client"

import { useState } from "react"
import { clsx } from "clsx"
import { File as FileIcon, Folder, FolderOpen } from "lucide-react"
import type { File } from "@/types/api"

interface FileNode {
  name: string
  path: string
  type: "file" | "directory"
  children?: FileNode[]
}

interface FileTreeProps {
  files: File[]
  directories?: File[]
  currentPath?: string | null
  onSelectFile: (path: string) => Promise<void>
  onSelectDirectory?: (path: string) => Promise<void>
  className?: string
}

export function FileTree({
  files,
  directories = [],
  currentPath,
  onSelectFile,
  onSelectDirectory,
  className,
}: FileTreeProps) {
  // Build tree structure from flat file list
  const buildTree = (files: File[]): FileNode[] => {
    const root: FileNode[] = []
    const map = new Map<string, FileNode>()

    // Create nodes for all files
    files.forEach((file) => {
      const parts = file.path.split("/")
      let currentPath = ""

      parts.forEach((part, index) => {
        const isLast = index === parts.length - 1
        currentPath = currentPath ? `${currentPath}/${part}` : part

        if (!map.has(currentPath)) {
          const nodeType: "file" | "directory" = isLast && file.type === "file" ? "file" : "directory"
          const node: FileNode = {
            name: part,
            path: currentPath,
            type: nodeType,
            children: nodeType === "directory" ? [] : undefined,
          }
          map.set(currentPath, node)

          // Add to parent or root
          if (index === 0) {
            root.push(node)
          } else {
            const parentPath = parts.slice(0, index).join("/")
            const parent = map.get(parentPath)
            if (parent && parent.children) {
              parent.children.push(node)
            } else if (parent) {
              // Parent exists but has no children array yet
              parent.children = [node]
            }
          }
        }
      })
    })

    return root
  }

  const tree = buildTree(files)

  // Combine directories and files for display
  const allItems = [...directories, ...files]

  return (
    <div className={clsx("p-2", className)}>
      {allItems.length === 0 ? (
        <p className="text-sm text-gray-400">No files available</p>
      ) : (
        <>
          {/* Simple list view for directory navigation */}
          <div className="space-y-1">
            {directories.map((dir) => (
              <div
                key={dir.path}
                className={clsx(
                  "flex items-center gap-2 py-1 px-2 rounded cursor-pointer hover:bg-gray-100",
                  "text-sm"
                )}
                onClick={() => onSelectDirectory?.(dir.path)}
              >
                <Folder className="w-4 h-4 text-yellow-600" />
                <span className="font-medium">{dir.name}</span>
              </div>
            ))}
            {files.map((file) => (
              <div
                key={file.path}
                className={clsx(
                  "flex items-center gap-2 py-1 px-2 rounded cursor-pointer hover:bg-gray-100",
                  "text-sm",
                  currentPath === file.path && "bg-emerald-50"
                )}
                onClick={() => onSelectFile(file.path)}
              >
                <FileIcon className="w-4 h-4 text-gray-500" />
                <span>{file.name}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

interface FileTreeNodeProps {
  nodes: FileNode[]
  currentPath?: string | null
  onSelectFile: (path: string) => Promise<void>
  level: number
}

function FileTreeNode({
  nodes,
  currentPath,
  onSelectFile,
  level,
}: FileTreeNodeProps) {
  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(new Set())

  const toggleDir = (path: string) => {
    setExpandedDirs((prev) => {
      const next = new Set(prev)
      if (next.has(path)) {
        next.delete(path)
      } else {
        next.add(path)
      }
      return next
    })
  }

  return (
    <div>
      {nodes.map((node) => (
        <div key={node.path}>
          <div
            className={clsx(
              "flex items-center gap-1 py-1 px-2 rounded cursor-pointer hover:bg-gray-100",
              "text-sm",
              currentPath === node.path && "bg-emerald-50"
            )}
            style={{ paddingLeft: `${level * 12 + 8}px` }}
            onClick={() => {
              if (node.type === "directory") {
                toggleDir(node.path)
              } else {
                onSelectFile(node.path)
              }
            }}
          >
            {node.type === "directory" ? (
              expandedDirs.has(node.path) ? (
                <FolderOpen className="w-4 h-4 text-yellow-600" />
              ) : (
                <Folder className="w-4 h-4 text-yellow-600" />
              )
            ) : (
              <FileIcon className="w-4 h-4 text-gray-500" />
            )}
            <span
              className={clsx(
                "truncate",
                node.type === "directory" && "font-medium"
              )}
            >
              {node.name}
            </span>
          </div>
          {node.type === "directory" &&
            expandedDirs.has(node.path) &&
            node.children && (
              <FileTreeNode
                nodes={node.children}
                currentPath={currentPath}
                onSelectFile={onSelectFile}
                level={level + 1}
              />
            )}
        </div>
      ))}
    </div>
  )
}
