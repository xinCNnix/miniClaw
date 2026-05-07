/**
 * Tests for useToast hook
 */

import { renderHook, act } from "@testing-library/react"
import { useToast } from "../useToast"

describe("useToast", () => {
  it("should start with empty toasts array", () => {
    const { result } = renderHook(() => useToast())

    expect(result.current.toasts).toEqual([])
  })

  it("should add toast when show is called", () => {
    const { result } = renderHook(() => useToast())

    act(() => {
      result.current.show("Test message", "info")
    })

    expect(result.current.toasts).toHaveLength(1)
    expect(result.current.toasts[0].message).toBe("Test message")
    expect(result.current.toasts[0].type).toBe("info")
  })

  it("should add multiple toasts", () => {
    const { result } = renderHook(() => useToast())

    act(() => {
      result.current.show("Message 1", "success")
      result.current.show("Message 2", "error")
      result.current.show("Message 3", "warning")
    })

    expect(result.current.toasts).toHaveLength(3)
  })

  it("should auto-dismiss toast after duration", () => {
    const { result } = renderHook(() => useToast())

    act(() => {
      result.current.show("Test message", "info", { duration: 3000 })
    })

    expect(result.current.toasts).toHaveLength(1)

    // Fast-forward time
    act(() => {
      jest.advanceTimersByTime(3000)
    })

    expect(result.current.toasts).toHaveLength(0)
  })

  it("should dismiss toast when dismiss is called", () => {
    const { result } = renderHook(() => useToast())

    act(() => {
      result.current.show("Test message", "info")
    })

    const toastId = result.current.toasts[0].id

    act(() => {
      result.current.dismiss(toastId)
    })

    expect(result.current.toasts).toHaveLength(0)
  })

  it("should clear all toasts when clear is called", () => {
    const { result } = renderHook(() => useToast())

    act(() => {
      result.current.show("Message 1", "info")
      result.current.show("Message 2", "info")
      result.current.show("Message 3", "info")
    })

    expect(result.current.toasts).toHaveLength(3)

    act(() => {
      result.current.clear()
    })

    expect(result.current.toasts).toHaveLength(0)
  })

  it("should use default duration of 3000ms", () => {
    const { result } = renderHook(() => useToast())

    act(() => {
      result.current.show("Test message", "info")
    })

    expect(result.current.toasts[0].duration).toBe(3000)
  })

  it("should use custom duration when provided", () => {
    const { result } = renderHook(() => useToast())

    act(() => {
      result.current.show("Test message", "info", { duration: 5000 })
    })

    expect(result.current.toasts[0].duration).toBe(5000)
  })
})
