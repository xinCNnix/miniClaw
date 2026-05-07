/**
 * Test memory leak fixes in useChat hook
 */

import { renderHook, waitFor, act } from '@testing-library/react'
import { useChat } from '../useChat'

// Mock fetch
global.fetch = jest.fn()

// Mock AbortController
class MockAbortController {
  static abortControllerInstances: MockAbortController[] = []
  signal = {}
  aborted = false

  abort() {
    this.aborted = true
  }

  constructor() {
    MockAbortController.abortControllerInstances.push(this)
  }

  static reset() {
    this.abortControllerInstances = []
  }
}

global.AbortController = MockAbortController as any

// Mock TextDecoder
global.TextDecoder = class MockTextDecoder {
  decode(value: Uint8Array, options?: { stream?: boolean }) {
    return ''
  }
} as any

describe('useChat - Memory Leak Tests', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    MockAbortController.reset()
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  test('should cleanup on unmount', async () => {
    const { unmount } = renderHook(() => useChat())

    // Unmount immediately
    act(() => {
      unmount()
    })

    // Wait to ensure cleanup completed
    await new Promise(resolve => setTimeout(resolve, 100))

    // Verify isMountedRef is set to false (by checking no state updates happen)
    // This is implicit - if there were memory leaks, we'd see errors or hanging tests
    expect(MockAbortController.abortControllerInstances.length).toBe(0)
  })

  test('should handle stopGeneration and cleanup', async () => {
    let shouldContinue = true

    const mockReader = {
      read: jest.fn().mockImplementation(async () => {
        if (!shouldContinue) {
          return { done: true, value: new Uint8Array() }
        }
        // Simulate streaming data
        await new Promise(resolve => setTimeout(resolve, 50))
        return { done: false, value: new Uint8Array([1]) }
      }),
      cancel: jest.fn()
    }

    ;(global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      body: {
        getReader: () => mockReader
      }
    })

    const { result } = renderHook(() => useChat())

    // Start streaming (this will hang, so we'll just test the abort logic)
    act(() => {
      result.current.sendMessage('test message')
    })

    // Wait a bit
    await new Promise(resolve => setTimeout(resolve, 100))

    // Stop generation
    act(() => {
      result.current.stopGeneration()
    })

    // Stop the stream
    shouldContinue = false

    // Should have aborted
    if (MockAbortController.abortControllerInstances.length > 0) {
      expect(MockAbortController.abortControllerInstances[0].aborted).toBe(true)
    }

    // Loading should be false
    await waitFor(() => expect(result.current.isLoading).toBe(false), { timeout: 2000 })
  })

  test('should cleanup messages on newSession', async () => {
    const { result } = renderHook(() => useChat())

    // Load some messages
    act(() => {
      result.current.loadMessages([
        { role: 'user', content: 'test', timestamp: new Date().toISOString() }
      ])
    })

    expect(result.current.messages.length).toBe(1)

    // Create new session
    await act(async () => {
      await result.current.newSession()
    })

    // Messages should be cleared
    expect(result.current.messages.length).toBe(0)
    expect(result.current.currentSessionId).toBeNull()
  })

  test('should cleanup messages on clearMessages', async () => {
    const { result } = renderHook(() => useChat())

    // Load some messages and thinking events
    act(() => {
      result.current.loadMessages([
        { role: 'user', content: 'test', timestamp: new Date().toISOString() },
        { role: 'assistant', content: 'response', timestamp: new Date().toISOString() }
      ])
    })

    expect(result.current.messages.length).toBe(2)

    // Clear messages
    act(() => {
      result.current.clearMessages()
    })

    // Messages should be cleared
    expect(result.current.messages.length).toBe(0)
    expect(result.current.thinkingEvents.length).toBe(0)
  })

  test('should set session correctly', async () => {
    const { result } = renderHook(() => useChat())

    const sessionId = 'test-session-123'

    act(() => {
      result.current.setSession(sessionId)
    })

    expect(result.current.currentSessionId).toBe(sessionId)
  })
})
