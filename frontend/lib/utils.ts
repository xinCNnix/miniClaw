/**
 * Utility functions
 */

import { clsx, type ClassValue } from 'clsx'

/**
 * Merge Tailwind CSS classes
 */
export function cn(...inputs: ClassValue[]) {
  return clsx(inputs)
}

/**
 * Format timestamp for display
 */
export function formatTimestamp(timestamp: string): string {
  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();

  if (diffMs < 60000) {
    // Less than a minute ago
    return 'Just now';
  } else if (diffMs < 3600000) {
    // Less than an hour ago
    const minutes = Math.floor(diffMs / 60000);
    return `${minutes}m ago`;
  } else if (diffMs < 86400000) {
    // Less than a day ago
    const hours = Math.floor(diffMs / 3600000);
    return `${hours}h ago`;
  } else {
    // Days ago
    const days = Math.floor(diffMs / 86400000);
    return `${days}d ago`;
  }
}

/**
 * Format file size
 */
export function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 Bytes';

  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));

  return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
}

/**
 * Truncate text to max length
 */
export function truncateText(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return text.substring(0, maxLength) + '...[truncated]';
}

/**
 * Escape HTML to prevent XSS
 */
export function escapeHtml(unsafe: string): string {
  return unsafe
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

/**
 * Get file icon based on extension
 */
export function getFileIcon(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase() || '';

  const icons: Record<string, string> = {
    // Code files
    'py': '🐍',
    'js': '📜',
    'ts': '📘',
    'tsx': '⚛️',
    'jsx': '⚛️',
    'html': '🌐',
    'css': '🎨',
    'json': '📋',
    'md': '📝',

    // Data files
    'txt': '📄',
    'csv': '📊',
    'pdf': '📕',

    // Config files
    'yaml': '⚙️',
    'yml': '⚙️',
    'toml': '⚙️',
    'ini': '⚙️',

    // Archives
    'zip': '📦',
    'tar': '📦',
    'gz': '📦',
  };

  return icons[ext] || '📄';
}

/**
 * Check if path is a code file
 */
export function isCodeFile(filename: string): boolean {
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  return [
    'py', 'js', 'ts', 'tsx', 'jsx', 'html', 'css', 'json', 'md',
    'yaml', 'yml', 'toml', 'txt',
  ].includes(ext);
}

/**
 * Get language for Monaco Editor based on filename
 */
export function getLanguageForFile(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase() || '';

  const languages: Record<string, string> = {
    'py': 'python',
    'js': 'javascript',
    'ts': 'typescript',
    'tsx': 'typescript',
    'jsx': 'javascript',
    'html': 'html',
    'css': 'css',
    'json': 'json',
    'md': 'markdown',
    'yaml': 'yaml',
    'yml': 'yaml',
    'toml': 'toml',
    'txt': 'plaintext',
  };

  return languages[ext] || 'plaintext';
}

/**
 * CNPJ colors for code syntax highlighting
 */
export function getSyntaxColor(content: string): string {
  const ext = content.split('.').pop()?.toLowerCase() || '';

  const colors: Record<string, string> = {
    'py': '#3776ab',
    'js': '#f7df1e',
    'ts': '#3178c6',
    'json': '#cbcb41',
    'md': '#083fa1',
  };

  return colors[ext] || '#666';
}
