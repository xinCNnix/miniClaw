/**
 * Unit tests for useEditor hook
 */

import { renderHook, act, waitFor } from '@testing-library/react'
import { useEditor } from './useEditor'
import { apiClient } from '@/lib/api'

// Mock the API client
jest.mock('@/lib/api', () => ({
  apiClient: {
    listFiles: jest.fn(),
    readFile: jest.fn(),
    writeFile: jest.fn(),
  },
}))

describe('useEditor Hook', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Initial State', () => {
    it('should initialize with default values', () => {
      const { result } = renderHook(() => useEditor())

      expect(result.current.files).toEqual([])
      expect(result.current.directories).toEqual([])
      expect(result.current.currentFile).toBeNull()
      expect(result.current.currentDirectory).toBe('.')
      expect(result.current.isLoading).toBe(false)
    })
  })

  describe('refreshFiles', () => {
    it('should load files from root directory by default', async () => {
      const mockFiles = [
        { name: 'test.py', path: 'test.py', type: 'file' },
        { name: 'README.md', path: 'README.md', type: 'file' },
      ]
      const mockDirectories = [
        { name: 'data', path: 'data', type: 'directory' },
        { name: 'src', path: 'src', type: 'directory' },
      ]

      ;(apiClient.listFiles as jest.Mock).mockResolvedValue({
        files: [...mockDirectories, ...mockFiles],
        current_path: '.',
      })

      const { result } = renderHook(() => useEditor())

      await act(async () => {
        await result.current.refreshFiles()
      })

      expect(apiClient.listFiles).toHaveBeenCalledWith('.')
      expect(result.current.files).toEqual(mockFiles)
      expect(result.current.directories).toEqual(mockDirectories)
      expect(result.current.currentDirectory).toBe('.')
      expect(result.current.isLoading).toBe(false)
    })

    it('should load files from specified directory', async () => {
      const mockFiles = [
        { name: 'file.txt', path: 'data/file.txt', type: 'file' },
      ]
      const mockDirectories = [
        { name: 'subdir', path: 'data/subdir', type: 'directory' },
      ]

      ;(apiClient.listFiles as jest.Mock).mockResolvedValue({
        files: [...mockDirectories, ...mockFiles],
        current_path: 'data',
      })

      const { result } = renderHook(() => useEditor())

      await act(async () => {
        await result.current.refreshFiles('data')
      })

      expect(apiClient.listFiles).toHaveBeenCalledWith('data')
      expect(result.current.files).toEqual(mockFiles)
      expect(result.current.directories).toEqual(mockDirectories)
      expect(result.current.currentDirectory).toBe('data')
    })

    it('should handle API errors gracefully', async () => {
      const onError = jest.fn()
      const mockError = new Error('Failed to fetch')

      ;(apiClient.listFiles as jest.Mock).mockRejectedValue(mockError)

      const { result } = renderHook(() => useEditor({ onError }))

      await act(async () => {
        await result.current.refreshFiles()
      })

      expect(onError).toHaveBeenCalledWith(mockError)
      expect(result.current.files).toEqual([])
      expect(result.current.isLoading).toBe(false)
    })
  })

  describe('changeDirectory', () => {
    it('should change to specified directory and load its contents', async () => {
      const rootFiles = [
        { name: 'root.txt', path: 'root.txt', type: 'file' },
      ]
      const rootDirs = [
        { name: 'data', path: 'data', type: 'directory' },
      ]

      const dataFiles = [
        { name: 'data.txt', path: 'data/data.txt', type: 'file' },
      ]
      const dataDirs = [
        { name: 'subdir', path: 'data/subdir', type: 'directory' },
      ]

      ;(apiClient.listFiles as jest.Mock)
        .mockResolvedValueOnce({
          files: [...rootDirs, ...rootFiles],
          current_path: '.',
        })
        .mockResolvedValueOnce({
          files: [...dataDirs, ...dataFiles],
          current_path: 'data',
        })

      const { result } = renderHook(() => useEditor())

      // Load root directory
      await act(async () => {
        await result.current.refreshFiles()
      })

      expect(result.current.files).toEqual(rootFiles)
      expect(result.current.currentDirectory).toBe('.')

      // Change to data directory
      await act(async () => {
        await result.current.changeDirectory('data')
      })

      expect(apiClient.listFiles).toHaveBeenLastCalledWith('data')
      expect(result.current.files).toEqual(dataFiles)
      expect(result.current.directories).toEqual(dataDirs)
      expect(result.current.currentDirectory).toBe('data')
    })
  })

  describe('goUpDirectory', () => {
    it('should navigate to parent directory', async () => {
      const parentFiles = [
        { name: 'parent.txt', path: 'parent.txt', type: 'file' },
      ]
      const parentDirs = [
        { name: 'child', path: 'child', type: 'directory' },
      ]

      const childFiles = [
        { name: 'child.txt', path: 'child/child.txt', type: 'file' },
      ]

      ;(apiClient.listFiles as jest.Mock)
        .mockResolvedValueOnce({
          files: [...parentDirs, ...parentFiles],
          current_path: '.',
        })
        .mockResolvedValueOnce({
          files: childFiles,
          current_path: 'child',
        })
        .mockResolvedValueOnce({
          files: [...parentDirs, ...parentFiles],
          current_path: '.',
        })

      const { result } = renderHook(() => useEditor())

      // Start at root
      await act(async () => {
        await result.current.refreshFiles('.')
      })
      expect(result.current.currentDirectory).toBe('.')

      // Go to child directory
      await act(async () => {
        await result.current.changeDirectory('child')
      })
      expect(result.current.currentDirectory).toBe('child')

      // Go up to parent
      await act(async () => {
        await result.current.goUpDirectory()
      })

      expect(apiClient.listFiles).toHaveBeenLastCalledWith('.')
      expect(result.current.currentDirectory).toBe('.')
    })

    it('should stay at root when already at root', async () => {
      const rootFiles = [
        { name: 'root.txt', path: 'root.txt', type: 'file' },
      ]

      ;(apiClient.listFiles as jest.Mock).mockResolvedValue({
        files: rootFiles,
        current_path: '.',
      })

      const { result } = renderHook(() => useEditor())

      await act(async () => {
        await result.current.refreshFiles('.')
      })

      const callCount = (apiClient.listFiles as jest.Mock).mock.calls.length

      // Try to go up from root
      await act(async () => {
        await result.current.goUpDirectory()
      })

      // Should still call listFiles to ensure root state
      expect(result.current.currentDirectory).toBe('.')
    })
  })

  describe('loadFile', () => {
    it('should load file content successfully', async () => {
      const mockContent = '# Test File\n\nContent here'

      ;(apiClient.readFile as jest.Mock).mockResolvedValue({
        content: mockContent,
        encoding: 'utf-8',
      })

      const { result } = renderHook(() => useEditor())

      await act(async () => {
        await result.current.loadFile('test.md')
      })

      expect(apiClient.readFile).toHaveBeenCalledWith('test.md')
      expect(result.current.currentFile).toEqual({
        path: 'test.md',
        name: 'test.md',
        type: 'file',
        content: mockContent,
      })
    })

    it('should handle file loading errors', async () => {
      const onError = jest.fn()
      const mockError = new Error('File not found')

      ;(apiClient.readFile as jest.Mock).mockRejectedValue(mockError)

      const { result } = renderHook(() => useEditor({ onError }))

      await act(async () => {
        await result.current.loadFile('nonexistent.md')
      })

      expect(onError).toHaveBeenCalledWith(mockError)
      expect(result.current.currentFile).toBeNull()
    })
  })

  describe('saveFile', () => {
    it('should save file content and refresh file list', async () => {
      const mockContent = 'Updated content'

      ;(apiClient.writeFile as jest.Mock).mockResolvedValue({
        success: true,
        message: 'File saved',
      })

      ;(apiClient.listFiles as jest.Mock).mockResolvedValue({
        files: [],
        current_path: '.',
      })

      const { result } = renderHook(() => useEditor())

      // Set current file
      act(() => {
        result.current.currentFile = {
          path: 'test.md',
          name: 'test.md',
          type: 'file',
          content: 'Old content',
        }
      })

      await act(async () => {
        await result.current.saveFile('test.md', mockContent)
      })

      expect(apiClient.writeFile).toHaveBeenCalledWith('test.md', mockContent)
      expect(result.current.currentFile?.content).toBe(mockContent)
      expect(apiClient.listFiles).toHaveBeenCalled()
    })
  })

  describe('closeFile', () => {
    it('should clear current file', async () => {
      const mockContent = '# Test Content'

      ;(apiClient.readFile as jest.Mock).mockResolvedValue({
        content: mockContent,
        encoding: 'utf-8',
      })

      const { result } = renderHook(() => useEditor())

      // First load a file
      await act(async () => {
        await result.current.loadFile('test.md')
      })

      expect(result.current.currentFile).not.toBeNull()

      // Then close it
      act(() => {
        result.current.closeFile()
      })

      expect(result.current.currentFile).toBeNull()
    })
  })
})
