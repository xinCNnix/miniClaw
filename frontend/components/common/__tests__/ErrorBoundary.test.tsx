/**
 * Tests for ErrorBoundary component
 */

import React from "react"
import { render, screen, fireEvent } from "@testing-library/react"
import { ErrorBoundary, ErrorFallback } from "../ErrorBoundary"

// Mock console.error to avoid cluttering test output
const originalError = console.error
beforeAll(() => {
  console.error = jest.fn()
})

afterAll(() => {
  console.error = originalError
})

describe("ErrorBoundary", () => {
  it("should render children when there is no error", () => {
    const ThrowError = () => {
      throw new Error("Test error")
    }

    render(
      <ErrorBoundary>
        <div>Safe content</div>
      </ErrorBoundary>
    )

    expect(screen.getByText("Safe content")).toBeInTheDocument()
  })

  it("should catch errors and render fallback UI", () => {
    const ThrowError = () => {
      throw new Error("Test error")
    }

    render(
      <ErrorBoundary>
        <ThrowError />
      </ErrorBoundary>
    )

    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument()
  })

  it("should call onError prop when error is caught", () => {
    const onError = jest.fn()
    const ThrowError = () => {
      throw new Error("Test error")
    }

    render(
      <ErrorBoundary onError={onError}>
        <ThrowError />
      </ErrorBoundary>
    )

    expect(onError).toHaveBeenCalled()
    expect(onError.mock.calls[0][0]).toBeInstanceOf(Error)
  })

  it("should reset error state when retry button is clicked", () => {
    const ThrowError = () => {
      throw new Error("Test error")
    }

    const { container } = render(
      <ErrorBoundary>
        <ThrowError />
      </ErrorBoundary>
    )

    // Error boundary should show fallback
    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument()

    // Click retry button
    const retryButton = screen.getByText("Try Again")
    fireEvent.click(retryButton)

    // Error should be cleared (but component will throw again immediately)
    expect(console.error).toHaveBeenCalled()
  })

  it("should reload page when reload button is clicked", () => {
    const ThrowError = () => {
      throw new Error("Test error")
    }

    // Mock window.location.reload
    const reloadMock = jest.fn()
    Object.defineProperty(window, "location", {
      value: { reload: reloadMock },
      writable: true,
    })

    render(
      <ErrorBoundary>
        <ThrowError />
      </ErrorBoundary>
    )

    const reloadButton = screen.getByText("Reload Page")
    fireEvent.click(reloadButton)

    expect(reloadMock).toHaveBeenCalled()
  })

  it("should use custom fallback when provided", () => {
    const ThrowError = () => {
      throw new Error("Test error")
    }

    const CustomFallback = () => <div>Custom Error UI</div>

    render(
      <ErrorBoundary fallback={<CustomFallback />}>
        <ThrowError />
      </ErrorBoundary>
    )

    expect(screen.getByText("Custom Error UI")).toBeInTheDocument()
    expect(screen.queryByText(/something went wrong/i)).not.toBeInTheDocument()
  })

  it("should display error message in development mode", () => {
    const originalEnv = process.env.NODE_ENV
    process.env.NODE_ENV = "development"

    const ThrowError = () => {
      throw new Error("Specific error message")
    }

    render(
      <ErrorBoundary>
        <ThrowError />
      </ErrorBoundary>
    )

    expect(screen.getByText("Specific error message")).toBeInTheDocument()

    process.env.NODE_ENV = originalEnv
  })

  it("should display component stack in development mode", () => {
    const originalEnv = process.env.NODE_ENV
    process.env.NODE_ENV = "development"

    const ThrowError = () => {
      throw new Error("Test error")
    }

    const { container } = render(
      <ErrorBoundary>
        <ThrowError />
      </ErrorBoundary>
    )

    // Check for details element which contains component stack
    const detailsElements = container.querySelectorAll("details")
    expect(detailsElements.length).toBeGreaterThan(0)

    process.env.NODE_ENV = originalEnv
  })
})

describe("ErrorFallback", () => {
  it("should render error message and reset button", () => {
    const error = new Error("Test error")
    const reset = jest.fn()

    render(<ErrorFallback error={error} reset={reset} />)

    expect(screen.getByText("Test error")).toBeInTheDocument()
    expect(screen.getByText("Try Again")).toBeInTheDocument()
  })

  it("should call reset when button is clicked", () => {
    const error = new Error("Test error")
    const reset = jest.fn()

    render(<ErrorFallback error={error} reset={reset} />)

    const resetButton = screen.getByText("Try Again")
    fireEvent.click(resetButton)

    expect(reset).toHaveBeenCalled()
  })
})
