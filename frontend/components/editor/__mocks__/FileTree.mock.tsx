/**
 * FileTree Component Mock
 *
 * Mock implementation of FileTree component for testing.
 */

import { ReactElement } from "react"
import type { File } from "@/types/api"

interface MockFileTreeProps {
  files: File[]
  currentPath?: string | null
  onSelectFile: (path: string) => Promise<void>
  className?: string
}

/**
 * Mock FileTree component
 *
 * Provides a simple mock that renders the file count and basic structure
 * without the complex tree-building logic.
 */
export function MockFileTree({
  files,
  currentPath,
  onSelectFile,
  className = "",
}: MockFileTreeProps): ReactElement {
  return (
    <div className={className} data-testid="file-tree">
      <div data-testid="file-count">{files.length} files</div>
      {currentPath && (
        <div data-testid="current-path">{currentPath}</div>
      )}
      <ul data-testid="file-list">
        {files.map((file) => (
          <li key={file.path} data-testid={`file-${file.path}`}>
            {file.path}
          </li>
        ))}
      </ul>
    </div>
  )
}
