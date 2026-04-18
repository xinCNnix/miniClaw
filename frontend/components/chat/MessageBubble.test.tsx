/**
 * Unit tests for MessageBubble component
 */

import React from 'react'
import { render, screen } from '@testing-library/react'
import { MessageBubble } from './MessageBubble'
import type { Message } from '@/types/chat'

// Mock react-markdown and dependencies
jest.mock('react-markdown', () => {
  return function MockReactMarkdown({ children, components }: any) {
    // Simple mock that handles basic markdown
    let content = String(children)

    // Handle code blocks
    if (content.includes('```')) {
      content = content.replace(/```(\w+)?\n([\s\S]*?)```/g, (_, lang, code) => {
        return `<pre><code class="language-${lang || 'text'}">${code.trim()}</code></pre>`
      })
    }

    // Handle inline code
    content = content.replace(/`([^`]+)`/g, '<code>$1</code>')

    // Handle bold
    content = content.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')

    // Handle links
    content = content.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>')

    return <div dangerouslySetInnerHTML={{ __html: content }} />
  }
})

jest.mock('remark-gfm', () => ({}))

jest.mock('react-syntax-highlighter', () => ({
  Prism: {
    __esModule: true,
    default: ({ children, className }: any) => (
      <div className={`mock-syntax-highlighter ${className || ''}`} data-testid="syntax-highlighter">
        {children}
      </div>
    ),
  },
}))

jest.mock('react-syntax-highlighter/dist/esm/styles/prism', () => ({
  oneDark: {},
}))

describe('MessageBubble Component', () => {
  const userMessage: Message = {
    role: 'user',
    content: 'Hello, how are you?',
    timestamp: '2024-03-12T10:00:00Z',
  }

  const botMessage: Message = {
    role: 'assistant',
    content: 'I am doing well, thank you!',
    timestamp: '2024-03-12T10:00:01Z',
  }

  describe('Rendering', () => {
    it('should render user message correctly', () => {
      render(<MessageBubble message={userMessage} />)

      expect(screen.getByText('Hello, how are you?')).toBeInTheDocument()
    })

    it('should render bot message correctly', () => {
      render(<MessageBubble message={botMessage} />)

      expect(screen.getByText('I am doing well, thank you!')).toBeInTheDocument()
    })

    it('should show timestamp', () => {
      render(<MessageBubble message={userMessage} />)

      expect(screen.getByText(/\d{2}:\d{2}:\d{2}/)).toBeInTheDocument()
    })
  })

  describe('Markdown Rendering', () => {
    it('should render inline code correctly', () => {
      const message: Message = {
        role: 'assistant',
        content: 'Use `const` for constants.',
        timestamp: '2024-03-12T10:00:00Z',
      }

      render(<MessageBubble message={message} />)

      expect(screen.getByText('const')).toBeInTheDocument()
    })

    it('should render code blocks correctly', () => {
      const message: Message = {
        role: 'assistant',
        content: '```javascript\nconst x = 1;\n```',
        timestamp: '2024-03-12T10:00:00Z',
      }

      render(<MessageBubble message={message} />)

      expect(screen.getByText('const x = 1;')).toBeInTheDocument()
    })

    it('should render bold text', () => {
      const message: Message = {
        role: 'assistant',
        content: 'This is **bold** text.',
        timestamp: '2024-03-12T10:00:00Z',
      }

      const { container } = render(<MessageBubble message={message} />)

      expect(container.querySelector('strong')).toBeInTheDocument()
    })

    it('should render links', () => {
      const message: Message = {
        role: 'assistant',
        content: '[Example](https://example.com)',
        timestamp: '2024-03-12T10:00:00Z',
      }

      const { container } = render(<MessageBubble message={message} />)

      const link = container.querySelector('a')
      expect(link).toBeInTheDocument()
      expect(link).toHaveAttribute('href', 'https://example.com')
    })
  })

  describe('Styling', () => {
    it('should apply user message styling', () => {
      const { container } = render(<MessageBubble message={userMessage} />)

      const messageDiv = container.querySelector('.bg-\\[var\\(--ink-green\\)\\]')
      expect(messageDiv).toBeInTheDocument()
    })

    it('should apply bot message styling', () => {
      const { container } = render(<MessageBubble message={botMessage} />)

      const messageDiv = container.querySelector('.bg-white.border')
      expect(messageDiv).toBeInTheDocument()
    })
  })
})
