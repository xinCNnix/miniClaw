"use client"

import { clsx } from "clsx"
import { User, Bot } from "lucide-react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import remarkMath from "remark-math"
import rehypeKatex from "rehype-katex"
import "katex/dist/katex.min.css"
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter"
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism"
import type { Message, GeneratedImage } from "@/types/chat"
import MermaidRenderer from "./MermaidRenderer"

const _BOX_DRAWING_RE = /[\u2500-\u257F\u2580-\u259F\u2190-\u21FF\u2B00-\u2BFF▶►]/

function _isBoxDrawingText(text: string): boolean {
  if (!text) return false
  const lines = text.split('\n')
  const boxLines = lines.filter((l) => _BOX_DRAWING_RE.test(l))
  return boxLines.length >= 2
}

interface MessageBubbleProps {
  message: Message
  thinkingEvents?: unknown[]
  className?: string
}

export function MessageBubble({ message, className }: MessageBubbleProps) {
  const isUser = message.role === "user"

  return (
    <div
      className={clsx(
        "flex gap-3",
        isUser ? "justify-end" : "justify-start",
        className
      )}
    >
      {/* Avatar */}
      {!isUser && (
        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-[var(--ink-green)] flex items-center justify-center">
          <Bot className="w-5 h-5 text-white" />
        </div>
      )}

      {/* Content */}
      <div
        className={clsx(
          "max-w-[80%] rounded-lg px-4 py-2",
          isUser
            ? "bg-[var(--ink-green)] text-white"
            : "bg-white border border-gray-200 text-gray-900"
        )}
      >
        {/* User-attached images */}
        {message.images && message.images.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-2">
            {message.images
              .filter((img) => img.content && img.mime_type)
              .map((img, idx) => (
                <img
                  key={idx}
                  src={`data:${img.mime_type};base64,${img.content}`}
                  alt={`Attachment ${idx + 1}`}
                  className="max-w-[200px] rounded-md border border-gray-300 dark:border-gray-600"
                />
              ))}
          </div>
        )}

        {/* User-attached files (attachments) */}
        {message.attachments && message.attachments.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-2">
            {message.attachments.map((att, idx) => {
              if (att.type === 'image' && att.content && att.mime_type) {
                return (
                  <img
                    key={`att-${idx}`}
                    src={`data:${att.mime_type};base64,${att.content}`}
                    alt={att.filename || `Attachment ${idx + 1}`}
                    className="max-w-[200px] rounded-md border border-gray-300 dark:border-gray-600"
                  />
                );
              }
              if (att.type === 'audio' && att.content && att.mime_type) {
                return (
                  <audio
                    key={`att-${idx}`}
                    controls
                    src={`data:${att.mime_type};base64,${att.content}`}
                    className="max-w-[300px]"
                  />
                );
              }
              if (att.type === 'video' && att.content && att.mime_type) {
                return (
                  <video
                    key={`att-${idx}`}
                    controls
                    src={`data:${att.mime_type};base64,${att.content}`}
                    className="max-w-[300px] rounded-md"
                  />
                );
              }
              // document or fallback: show filename chip
              return (
                <span
                  key={`att-${idx}`}
                  className="inline-flex items-center gap-1 px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded text-xs"
                >
                  {att.filename || `File ${idx + 1}`}
                </span>
              );
            })}
          </div>
        )}

        {isUser ? (
          <p className="whitespace-pre-wrap">{message.content}</p>
        ) : (
          <div className="prose prose-sm max-w-none dark:prose-invert">
            <ReactMarkdown
              remarkPlugins={[remarkGfm, remarkMath]}
              rehypePlugins={[rehypeKatex]}
              components={{
                img({ src, alt, ...props }: any) {
                  if (!src || src.trim() === '') return null;
                  return (
                    <img
                      src={src}
                      alt={alt || 'Image'}
                      className="max-w-full rounded-md border border-gray-200 my-2"
                      loading="lazy"
                      onError={(e) => {
                        (e.target as HTMLImageElement).style.display = 'none';
                      }}
                    />
                  );
                },
                code({ className, children, inline, ...props }: any) {
                  const match = /language-(\w+)/.exec(className || '')
                  const language = match ? match[1] : null

                  if (language === 'mermaid') {
                    const code = String(children).replace(/\n$/, '')
                    return <MermaidRenderer code={code} />
                  }

                  return !inline && match ? (
                    <SyntaxHighlighter
                      style={oneDark}
                      language={match[1]}
                      PreTag="div"
                      customStyle={{
                        borderRadius: '0.375rem',
                        fontSize: '0.875rem',
                      }}
                    >
                      {String(children).replace(/\n$/, '')}
                    </SyntaxHighlighter>
                  ) : (
                    <code
                      className={clsx(
                        "px-1.5 py-0.5 rounded text-sm",
                        "bg-gray-100 dark:bg-gray-800",
                        "text-pink-600 dark:text-pink-400",
                        className
                      )}
                      {...props}
                    >
                      {children}
                    </code>
                  )
                },
                p({ children }) {
                  return <p className="mb-2 last:mb-0">{children}</p>
                },
                ul({ children }) {
                  return <ul className="list-disc list-inside mb-2">{children}</ul>
                },
                ol({ children }) {
                  return <ol className="list-decimal list-inside mb-2">{children}</ol>
                },
                li({ children }) {
                  return <li className="mb-1">{children}</li>
                },
                h1({ children }) {
                  return <h1 className="text-xl font-bold mb-2 mt-4">{children}</h1>
                },
                h2({ children }) {
                  return <h2 className="text-lg font-bold mb-2 mt-3">{children}</h2>
                },
                h3({ children }) {
                  return <h3 className="text-base font-bold mb-2 mt-2">{children}</h3>
                },
                strong({ children }) {
                  return <strong className="font-bold">{children}</strong>
                },
                a({ children, href }) {
                  return (
                    <a
                      href={href}
                      className="text-blue-600 dark:text-blue-400 hover:underline"
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {children}
                    </a>
                  )
                },
                blockquote({ children }) {
                  return (
                    <blockquote className="border-l-4 border-gray-300 pl-4 italic my-2">
                      {children}
                    </blockquote>
                  )
                },
                table({ children }) {
                  return (
                    <div className="overflow-x-auto my-2">
                      <table className="min-w-full border-collapse border border-gray-300 text-sm">
                        {children}
                      </table>
                    </div>
                  )
                },
                thead({ children }) {
                  return <thead className="bg-gray-50 dark:bg-gray-800">{children}</thead>
                },
                th({ children }) {
                  return (
                    <th className="border border-gray-300 px-3 py-1.5 text-left font-semibold">
                      {children}
                    </th>
                  )
                },
                td({ children }) {
                  return (
                    <td className="border border-gray-300 px-3 py-1.5">{children}</td>
                  )
                },
                pre({ children }) {
                  const text = String(children)
                  if (_isBoxDrawingText(text)) {
                    return (
                      <pre
                        className="my-2 p-3 rounded-md bg-gray-50 dark:bg-gray-900 border border-gray-200 overflow-x-auto text-sm leading-tight"
                        style={{ fontFamily: 'var(--font-mono)' }}
                      >
                        {children}
                      </pre>
                    )
                  }
                  return <pre className="my-2">{children}</pre>
                },
              }}
            >
              {message.content}
            </ReactMarkdown>
          </div>
        )}

        {/* [IMAGE_UNIFY] Commented out: images now render inline via ReactMarkdown
            using API URL markdown refs (![name](/api/media/media_id)).
            generated_images data structure preserved in useChat.ts for debug/session.
            To restore, uncomment this block:
        {!isUser && message.generated_images && message.generated_images.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-2">
            {message.generated_images.map((img: GeneratedImage, idx: number) => (
              <img
                key={img.media_id || idx}
                src={img.api_url}
                alt={img.name || `Generated ${idx + 1}`}
                className="max-w-full rounded-md border border-gray-200 my-2"
                loading="lazy"
                onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
              />
            ))}
          </div>
        )}
        */}

        {/* Timestamp */}
        {message.timestamp && (
          <p
            className={clsx(
              "text-xs mt-1",
              isUser ? "text-emerald-100" : "text-gray-400"
            )}
          >
            {new Date(message.timestamp).toLocaleTimeString()}
          </p>
        )}
      </div>

      {isUser && (
        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-gray-500 flex items-center justify-center">
          <User className="w-5 h-5 text-white" />
        </div>
      )}
    </div>
  )
}
