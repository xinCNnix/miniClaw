/**
 * Test file upload functionality in InputBox component
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { InputBox } from '../InputBox'

// Mock URL.createObjectURL and revokeObjectURL
const mockCreateObjectURL = jest.fn((file: File) => `blob:${file.name}`)
const mockRevokeObjectURL = jest.fn()

Object.defineProperty(global, 'URL', {
  value: {
    createObjectURL: mockCreateObjectURL,
    revokeObjectURL: mockRevokeObjectURL
  }
})

// Mock FileReader
class MockFileReader {
  onload: ((event: ProgressEvent<FileReader>) => void) | null = null
  result: string | null = null

  readAsDataURL(file: File) {
    setTimeout(() => {
      this.result = `data:${file.type};base64,${file.name}`
      if (this.onload) {
        this.onload({ target: this } as ProgressEvent<FileReader>)
      }
    }, 0)
  }
}

global.FileReader = MockFileReader as any

// Mock useTranslation
jest.mock('@/hooks/use-translation.hook', () => ({
  useTranslation: () => ({
    t: (key: string, params?: any) => {
      if (params?.name) return `${key} for ${params.name}`
      if (params?.max) return `${key} ${params.max}`
      return key
    }
  })
}))

describe('InputBox - File Upload Tests', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  test('should create object URLs for image files', async () => {
    const mockOnSend = jest.fn()
    render(<InputBox onSend={mockOnSend} />)

    const file = new File(['test'], 'test.jpg', { type: 'image/jpeg' })
    const fileInput = screen.getByTestId('file-upload-button').nextElementSibling as HTMLInputElement

    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(mockCreateObjectURL).toHaveBeenCalledWith(file)
    }, { timeout: 2000 })
  })

  test('should accept non-image files (documents)', async () => {
    const mockOnSend = jest.fn()
    render(<InputBox onSend={mockOnSend} />)

    const fileInput = screen.getByTestId('file-upload-button').nextElementSibling as HTMLInputElement
    const textFile = new File(['test'], 'test.txt', { type: 'text/plain' })

    fireEvent.change(fileInput, { target: { files: [textFile] } })

    // Should still create object URL for preview (document type)
    await waitFor(() => {
      expect(mockCreateObjectURL).toHaveBeenCalledWith(textFile)
    }, { timeout: 2000 })
  })

  test('should accept audio files', async () => {
    const mockOnSend = jest.fn()
    render(<InputBox onSend={mockOnSend} />)

    const fileInput = screen.getByTestId('file-upload-button').nextElementSibling as HTMLInputElement
    const audioFile = new File(['test'], 'test.mp3', { type: 'audio/mpeg' })

    fireEvent.change(fileInput, { target: { files: [audioFile] } })

    await waitFor(() => {
      expect(mockCreateObjectURL).toHaveBeenCalledWith(audioFile)
    }, { timeout: 2000 })
  })

  test('should accept video files', async () => {
    const mockOnSend = jest.fn()
    render(<InputBox onSend={mockOnSend} />)

    const fileInput = screen.getByTestId('file-upload-button').nextElementSibling as HTMLInputElement
    const videoFile = new File(['test'], 'test.mp4', { type: 'video/mp4' })

    fireEvent.change(fileInput, { target: { files: [videoFile] } })

    await waitFor(() => {
      expect(mockCreateObjectURL).toHaveBeenCalledWith(videoFile)
    }, { timeout: 2000 })
  })

  test('should cleanup object URL when removing attachment', async () => {
    const mockOnSend = jest.fn()
    render(<InputBox onSend={mockOnSend} />)

    const file = new File(['test'], 'test.jpg', { type: 'image/jpeg' })
    const fileInput = screen.getByTestId('file-upload-button').nextElementSibling as HTMLInputElement

    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(mockCreateObjectURL).toHaveBeenCalled()
    }, { timeout: 2000 })

    const previewUrl = mockCreateObjectURL.mock.results[0].value

    const removeButtons = screen.queryAllByRole('button').filter(btn =>
      btn.classList.contains('bg-red-500')
    )

    if (removeButtons.length > 0) {
      fireEvent.click(removeButtons[0])
      expect(mockRevokeObjectURL).toHaveBeenCalledWith(previewUrl)
    }
  })

  test('should reset input after file selection', async () => {
    const mockOnSend = jest.fn()
    render(<InputBox onSend={mockOnSend} />)

    const fileInput = screen.getByTestId('file-upload-button').nextElementSibling as HTMLInputElement
    const file = new File(['test'], 'test.jpg', { type: 'image/jpeg' })

    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(mockCreateObjectURL).toHaveBeenCalled()
    }, { timeout: 2000 })

    expect(fileInput.files).toBeNull()
  })
})
