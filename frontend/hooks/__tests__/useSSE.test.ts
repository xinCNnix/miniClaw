/**
 * Test memory leak fixes in useSSE hook
 */

import { renderHook, waitFor, act } from '@testing-library/react'
import { useSSE } from '../useSSE'

// Mock fetch
const mockFetch = jest.fn()
global.fetch = mockFetch

// Mock AbortController to track instances
let abortControllerInstances: any[] = []

class MockAbortController {
  signal = {}
  aborted = false

  abort() {
    this.aborted = true
  }

  constructor() {
    abortControllerInstances.push(this)
  }
}

global.AbortController = MockAbortController as any

describe('useSSE - Memory Leak Tests', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    abortControllerInstances = []
  })

  test('should create abort controller on mount', async () => {
    mockFetch.mockRejectedValue(new Error('Connection failed'))

    renderHook(() =>
      useSSE({
        url: '/api/test',
        request: { test: 'data' },
        enabled: true
      })
    )

    // Wait a bit for the hook to initialize
    await new Promise(resolve => setTimeout(resolve, 100))

    // Should have created an abort controller
    expect(abortControllerInstances.length).toBeGreaterThan(0)
  })

  test('should call abort on unmount', async () => {
    mockFetch.mockRejectedValue(new Error('Connection failed'))

    const { unmount } = renderHook(() =>
      useSSE({
        url: '/api/test',
        request: { test: 'data' },
        enabled: true
      })
    )

    // Wait for initialization
    await new Promise(resolve => setTimeout(resolve, 100))

    const controllerCount = abortControllerInstances.length

    // Unmount the hook
    act(() => {
      unmount()
    })

    // At least one controller should be aborted
    const abortedControllers = abortControllerInstances.filter((c: any) => c.aborted)
    expect(abortedControllers.length).toBeGreaterThan(0)
  })

  test('should handle disable gracefully', async () => {
    mockFetch.mockRejectedValue(new Error('Connection failed'))

    const { rerender } = renderHook(
      ({ enabled }) =>
        useSSE({
          url: '/api/test',
          request: { test: 'data' },
          enabled
        }),
      { initialProps: { enabled: true } }
    )

    // Wait for initialization
    await new Promise(resolve => setTimeout(resolve, 100))

    // Disable the connection
    act(() => {
      rerender({ enabled: false })
    })

    // Should have created at least one controller
    expect(abortControllerInstances.length).toBeGreaterThan(0)

    // Wait to ensure no errors
    await new Promise(resolve => setTimeout(resolve, 100))
  })

  test('should cleanup when URL changes', async () => {
    mockFetch.mockRejectedValue(new Error('Connection failed'))

    const { rerender } = renderHook(
      ({ url }) =>
        useSSE({
          url,
          request: { test: 'data' },
          enabled: true
        }),
      { initialProps: { url: '/api/test1' } }
    )

    // Wait for initialization
    await new Promise(resolve => setTimeout(resolve, 100))

    const initialCount = abortControllerInstances.length

    // Rerender with different URL
    act(() => {
      rerender({ url: '/api/test2' })
    })

    // Should have created more controllers
    await waitFor(() => {
      expect(abortControllerInstances.length).toBeGreaterThan(initialCount)
    }, { timeout: 2000 })

    // Previous controller should be aborted
    const abortedControllers = abortControllerInstances.filter((c: any) => c.aborted)
    expect(abortedControllers.length).toBeGreaterThan(0)
  })
})
