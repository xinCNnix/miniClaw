"use client"

import { useEffect, useRef, useState } from "react"
import mermaid from "mermaid"

mermaid.initialize({
  startOnLoad: false,
  theme: "default",
  securityLevel: "strict",
  fontFamily: "inherit",
})

interface MermaidRendererProps {
  code: string
}

export default function MermaidRenderer({ code }: MermaidRendererProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [svg, setSvg] = useState<string>("")
  const [error, setError] = useState<string>("")
  const idRef = useRef(`mermaid-${Math.random().toString(36).slice(2, 10)}`)

  useEffect(() => {
    let cancelled = false

    async function render() {
      try {
        const { svg: rendered } = await mermaid.render(idRef.current, code)
        if (!cancelled) {
          setSvg(rendered)
          setError("")
        }
      } catch (err) {
        if (!cancelled) {
          setError(String(err))
          setSvg("")
        }
      }
    }

    render()
    return () => { cancelled = true }
  }, [code])

  if (error) {
    return (
      <div className="my-2 rounded border border-gray-200 bg-gray-50 p-3 text-sm">
        <pre className="whitespace-pre-wrap text-gray-700 text-xs font-mono">{code}</pre>
      </div>
    )
  }

  if (!svg) {
    return (
      <div className="my-2 flex items-center justify-center p-4 text-gray-400 text-sm">
        Rendering diagram...
      </div>
    )
  }

  return (
    <div
      ref={containerRef}
      className="my-2 flex justify-center overflow-x-auto rounded border border-gray-200 bg-white p-4"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  )
}
