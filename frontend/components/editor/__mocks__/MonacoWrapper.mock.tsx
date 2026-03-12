/**
 * MonacoWrapper Component Mock
 *
 * Mock implementation of MonacoWrapper component for testing.
 */

import { ReactElement } from "react"

interface MockMonacoWrapperProps {
  content: string
  language?: string
  readOnly?: boolean
  onChange?: (value: string | undefined) => void
  className?: string
}

/**
 * Mock MonacoWrapper component
 *
 * Provides a simple mock that renders a textarea instead of the Monaco Editor,
 * allowing tests to verify content and changes without loading the heavy editor.
 */
export function MockMonacoWrapper({
  content,
  language = "plaintext",
  readOnly = false,
  onChange,
  className = "",
}: MockMonacoWrapperProps): ReactElement {
  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    if (onChange) {
      onChange(e.target.value)
    }
  }

  return (
    <div
      className={className}
      data-testid="monaco-editor"
      data-language={language}
      data-readonly={readOnly}
    >
      <textarea
        data-testid="monaco-textarea"
        value={content}
        onChange={handleChange}
        readOnly={readOnly}
        className="w-full h-full p-2 font-mono text-sm border rounded"
      />
    </div>
  )
}
