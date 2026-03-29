"use client"

import React, { Component, ErrorInfo, ReactNode } from "react"
import { Button } from "@/components/ui/button"

interface Props {
  children: ReactNode
  fallback?: ReactNode
  onError?: (error: Error, errorInfo: ErrorInfo) => void
}

interface State {
  hasError: boolean
  error: Error | null
  errorInfo: ErrorInfo | null
}

/**
 * ErrorBoundary Component
 *
 * Catches JavaScript errors anywhere in the child component tree,
 * logs those errors, and displays a fallback UI instead of the
 * component tree that crashed.
 *
 * Features:
 * - Catches runtime errors in component tree
 * - Logs errors to console and optional error handler
 * - Displays user-friendly error message
 * - Provides retry mechanism
 * - Preserves component stack for debugging
 *
 * Usage:
 * ```tsx
 * <ErrorBoundary onError={(error, info) => logError(error)}>
 *   <YourComponent />
 * </ErrorBoundary>
 * ```
 */
export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
    }
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    // Update state so the next render will show the fallback UI
    return { hasError: true }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    // Log the error to console
    console.error("ErrorBoundary caught an error:", error)
    console.error("Component stack:", errorInfo.componentStack)

    // Update state with error details
    this.setState({
      error,
      errorInfo,
    })

    // Call optional error handler prop
    if (this.props.onError) {
      this.props.onError(error, errorInfo)
    }

    // TODO: Send to error reporting service (e.g., Sentry)
    // logErrorToService(error, errorInfo)
  }

  handleReset = (): void => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
    })
  }

  handleReload = (): void => {
    window.location.reload()
  }

  render(): ReactNode {
    if (this.state.hasError) {
      // Use custom fallback if provided
      if (this.props.fallback) {
        return this.props.fallback
      }

      // Default error UI
      return (
        <div className="flex items-center justify-center min-h-screen p-4 bg-gray-50">
          <div className="w-full max-w-md bg-white rounded-lg shadow-lg p-6">
            <div className="mb-4">
              <h1 className="text-xl font-semibold text-red-600 flex items-center gap-2">
                <svg
                  className="w-6 h-6"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                  />
                </svg>
                Something went wrong
              </h1>
              <p className="text-sm text-gray-600 mt-2">
                An unexpected error occurred. This has been logged and we'll
                look into it.
              </p>
            </div>

            {this.state.error && (
              <div className="space-y-2 mb-4">
                <p className="text-sm font-medium text-gray-700">
                  Error: {this.state.error.message}
                </p>
                {process.env.NODE_ENV === "development" &&
                  this.state.errorInfo && (
                    <details className="mt-4">
                      <summary className="cursor-pointer text-sm text-gray-600 hover:text-gray-800">
                        Component Stack
                      </summary>
                      <pre className="mt-2 text-xs bg-gray-100 p-2 rounded overflow-auto max-h-40">
                        {this.state.errorInfo.componentStack}
                      </pre>
                    </details>
                  )}
                {process.env.NODE_ENV === "development" &&
                  this.state.error && (
                    <details className="mt-4">
                      <summary className="cursor-pointer text-sm text-gray-600 hover:text-gray-800">
                        Error Stack
                      </summary>
                      <pre className="mt-2 text-xs bg-gray-100 p-2 rounded overflow-auto max-h-40">
                        {this.state.error.stack}
                      </pre>
                    </details>
                  )}
              </div>
            )}

            <div className="flex gap-2">
              <Button onClick={this.handleReset} variant="outline">
                Try Again
              </Button>
              <Button onClick={this.handleReload}>Reload Page</Button>
            </div>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}

/**
 * Error Fallback Component
 *
 * A simple error fallback component that can be used
 * as a fallback UI for ErrorBoundary.
 */
export function ErrorFallback({
  error,
  reset,
}: {
  error: Error
  reset: () => void
}): ReactNode {
  return (
    <div className="flex items-center justify-center min-h-screen p-4 bg-gray-50">
      <div className="w-full max-w-md bg-white rounded-lg shadow-lg p-6">
        <h1 className="text-xl font-semibold text-red-600 mb-2">
          Something went wrong
        </h1>
        <p className="text-sm text-gray-600 mb-4">{error.message}</p>
        <Button onClick={reset}>Try Again</Button>
      </div>
    </div>
  )
}
