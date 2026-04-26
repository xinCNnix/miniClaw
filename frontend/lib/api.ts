/**
 * API client for backend communication
 */

import type {
  FileListResponse,
  Session,
  SessionListResponse
} from '@/types/api';
import type {
  KBDocument,
  KBDocumentListResponse,
  KBStats,
  KBUploadResponse,
  KBDeleteResponse,
  KBLargeFileUploadRequest,
  KBLargeFileUploadResponse,
  KBBatchUploadRequest,
  KBBatchUploadResponse,
  KBBatchUploadComplete
} from '@/types/knowledge-base';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8002';

export interface ChatRequest {
  message: string;
  session_id?: string;
  stream?: boolean;
  context?: Record<string, any>;
}

export interface ChatResponse {
  role: string;
  content: string;
  tool_calls?: any[];
}

export class APIClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  /**
   * Send a chat message and get response (non-streaming)
   */
  async chat(request: ChatRequest): Promise<ChatResponse> {
    const response = await fetch(`${this.baseUrl}/api/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        ...request,
        stream: false,
      }),
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Chat request failed: ${error}`);
    }

    return response.json();
  }

  /**
   * Get files in a directory
   */
  async listFiles(path: string = '.'): Promise<FileListResponse> {
    const response = await fetch(
      `${this.baseUrl}/api/files?path=${encodeURIComponent(path)}`,
    );

    if (!response.ok) {
      throw new Error(`Failed to list files: ${await response.text()}`);
    }

    return response.json();
  }

  /**
   * Read a file
   */
  async readFile(path: string): Promise<{ content: string; encoding: string }> {
    const response = await fetch(
      `${this.baseUrl}/api/files/read?path=${encodeURIComponent(path)}`,
    );

    if (!response.ok) {
      throw new Error(`Failed to read file: ${await response.text()}`);
    }

    return response.json();
  }

  /**
   * Write a file
   */
  async writeFile(path: string, content: string): Promise<{ success: boolean; message: string }> {
    const response = await fetch(`${this.baseUrl}/api/files`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        path,
        content,
      }),
    });

    if (!response.ok) {
      throw new Error(`Failed to write file: ${await response.text()}`);
    }

    return response.json();
  }

  /**
   * List all sessions
   */
  async listSessions(): Promise<SessionListResponse> {
    const response = await fetch(`${this.baseUrl}/api/sessions`);

    if (!response.ok) {
      throw new Error(`Failed to list sessions: ${await response.text()}`);
    }

    return response.json();
  }

  /**
   * Create a new session
   */
  async createSession(
    sessionId?: string,
    metadata?: Record<string, any>
  ): Promise<Session> {
    const response = await fetch(`${this.baseUrl}/api/sessions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        session_id: sessionId,
        metadata,
      }),
    });

    if (!response.ok) {
      throw new Error(`Failed to create session: ${await response.text()}`);
    }

    return response.json();
  }

  /**
   * Get session details
   */
  async getSession(sessionId: string): Promise<any> {
    const response = await fetch(`${this.baseUrl}/api/sessions/${sessionId}`);

    if (!response.ok) {
      throw new Error(`Failed to get session: ${await response.text()}`);
    }

    return response.json();
  }

  /**
   * Delete a session
   */
  async deleteSession(sessionId: string): Promise<{ success: boolean; message: string }> {
    const response = await fetch(`${this.baseUrl}/api/sessions/${sessionId}`, {
      method: 'DELETE',
    });

    if (!response.ok) {
      throw new Error(`Failed to delete session: ${await response.text()}`);
    }

    return response.json();
  }

  /**
   * Get API health status
   */
  async getHealth(): Promise<any> {
    const response = await fetch(`${this.baseUrl}/health`);

    if (!response.ok) {
      throw new Error(`Health check failed: ${await response.text()}`);
    }

    return response.json();
  }

  /**
   * Save LLM configuration with obfuscated API key
   */
  async saveLLMConfig(config: {
    provider: string;
    api_key: string;
    model?: string;
    base_url?: string;
    user_confirmed?: boolean;
  }): Promise<{
    success: boolean;
    message: string;
    requires_confirmation?: boolean;
    domain?: string;
  }> {
    const response = await fetch(`${this.baseUrl}/api/config/save`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(config),
    });

    if (!response.ok) {
      throw new Error(`Failed to save config: ${await response.text()}`);
    }

    return response.json();
  }

  /**
   * Get configuration status
   */
  async getConfigStatus(): Promise<{
    has_credentials: boolean;
    providers: string[];
  }> {
    const response = await fetch(`${this.baseUrl}/api/config/status`);

    if (!response.ok) {
      throw new Error(`Failed to get config status: ${await response.text()}`);
    }

    return response.json();
  }

  /**
   * Delete provider configuration
   */
  async deleteProviderConfig(provider: string): Promise<{
    success: boolean;
    message: string;
  }> {
    const response = await fetch(`${this.baseUrl}/api/config/${provider}`, {
      method: 'DELETE',
    });

    if (!response.ok) {
      throw new Error(`Failed to delete config: ${await response.text()}`);
    }

    return response.json();
  }

  /**
   * Check if domain is trusted
   */
  async checkDomain(domain: string): Promise<{
    trusted: boolean;
    domain: string;
  }> {
    const response = await fetch(`${this.baseUrl}/api/config/check-domain`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ domain }),
    });

    if (!response.ok) {
      throw new Error(`Failed to check domain: ${await response.text()}`);
    }

    return response.json();
  }

  /**
   * Upload document to knowledge base
   */
  async uploadKBDocument(
    file: File,
    uploadToken?: string,
    onProgress?: (progress: number) => void
  ): Promise<KBUploadResponse> {
    const formData = new FormData();
    formData.append('file', file);

    let url = `${this.baseUrl}/api/kb/upload`;
    if (uploadToken) {
      url += `?upload_token=${encodeURIComponent(uploadToken)}`;
    }

    const response = await fetch(url, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Failed to upload document: ${error}`);
    }

    return response.json();
  }

  /**
   * Check if file requires authorization for upload
   */
  async checkLargeFile(
    filename: string,
    fileSize: number,
    confirm: boolean
  ): Promise<KBLargeFileUploadResponse> {
    const response = await fetch(`${this.baseUrl}/api/kb/upload/check-large-file`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        filename,
        file_size: fileSize,
        confirm,
      }),
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Failed to check large file: ${error}`);
    }

    return response.json();
  }

  /**
   * List all documents in knowledge base
   */
  async listKBDocuments(): Promise<KBDocumentListResponse> {
    const response = await fetch(`${this.baseUrl}/api/kb/documents`);

    if (!response.ok) {
      throw new Error(`Failed to list documents: ${await response.text()}`);
    }

    return response.json();
  }

  /**
   * Delete document from knowledge base
   */
  async deleteKBDocument(docId: string): Promise<KBDeleteResponse> {
    const response = await fetch(`${this.baseUrl}/api/kb/documents/${docId}`, {
      method: 'DELETE',
    });

    if (!response.ok) {
      throw new Error(`Failed to delete document: ${await response.text()}`);
    }

    return response.json();
  }

  /**
   * Get knowledge base statistics
   */
  async getKBStats(): Promise<KBStats> {
    const response = await fetch(`${this.baseUrl}/api/kb/stats`);

    if (!response.ok) {
      throw new Error(`Failed to get KB stats: ${await response.text()}`);
    }

    return response.json();
  }

  /**
   * List all skills
   */
  async listSkills(): Promise<{ skills: SkillMetadata[] }> {
    const response = await fetch(`${this.baseUrl}/api/skills/list`);

    if (!response.ok) {
      throw new Error(`Failed to list skills: ${await response.text()}`);
    }

    return response.json();
  }

  /**
   * Install a skill
   */
  async installSkill(skillName: string): Promise<{
    success: boolean;
    message: string;
    skill: SkillMetadata;
  }> {
    const response = await fetch(`${this.baseUrl}/api/skills/install`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ name: skillName }),
    });

    if (!response.ok) {
      throw new Error(`Failed to install skill: ${await response.text()}`);
    }

    return response.json();
  }

  /**
   * Delete a skill
   */
  async deleteSkill(skillName: string): Promise<{
    success: boolean;
    message: string;
  }> {
    const response = await fetch(`${this.baseUrl}/api/skills/${skillName}`, {
      method: 'DELETE',
    });

    if (!response.ok) {
      throw new Error(`Failed to delete skill: ${await response.text()}`);
    }

    return response.json();
  }

  /**
   * Toggle skill enabled state
   */
  async toggleSkill(skillName: string, enabled: boolean): Promise<SkillMetadata> {
    const response = await fetch(`${this.baseUrl}/api/skills/${skillName}/toggle`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ enabled }),
    });

    if (!response.ok) {
      throw new Error(`Failed to toggle skill: ${await response.text()}`);
    }

    return response.json();
  }

  /**
   * Refresh skills from filesystem
   */
  async refreshSkills(): Promise<{
    success: boolean;
    message: string;
    removed: string[];
    added: string[];
  }> {
    const response = await fetch(`${this.baseUrl}/api/skills/refresh`, {
      method: 'POST',
    });

    if (!response.ok) {
      throw new Error(`Failed to refresh skills: ${await response.text()}`);
    }

    return response.json();
  }

  /**
   * Create a new skill
   */
  async createSkill(data: {
    name: string;
    description: string;
    author?: string;
    tags?: string[];
    version?: string;
  }): Promise<{
    success: boolean;
    message: string;
    skill: SkillMetadata;
  }> {
    const response = await fetch(`${this.baseUrl}/api/skills/create`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data),
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Failed to create skill: ${error}`);
    }

    return response.json();
  }

  /**
   * Check if batch upload requires authorization
   */
  async checkBatchUpload(
    fileCount: number,
    totalSize: number,
    confirm: boolean
  ): Promise<KBBatchUploadResponse> {
    const response = await fetch(`${this.baseUrl}/api/kb/upload/batch/check`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        confirm,
        file_count: fileCount,
        total_size: totalSize,
      }),
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Failed to check batch upload: ${error}`);
    }

    return response.json();
  }

  /**
   * Upload multiple files as a batch
   */
  async uploadBatch(
    files: File[],
    uploadToken?: string,
    onProgress?: (progress: number, currentFile: string) => void
  ): Promise<KBBatchUploadComplete> {
    const formData = new FormData();
    files.forEach((file) => {
      formData.append('files', file);
    });

    let url = `${this.baseUrl}/api/kb/upload/batch`;
    if (uploadToken) {
      url += `?upload_token=${encodeURIComponent(uploadToken)}`;
    }

    const response = await fetch(url, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Failed to upload batch: ${error}`);
    }

    return response.json();
  }

  /**
   * Upload folder as ZIP archive
   */
  async uploadFolder(
    zipFile: File,
    onProgress?: (progress: number, currentFile: string) => void
  ): Promise<KBBatchUploadComplete> {
    const formData = new FormData();
    formData.append('folder', zipFile);

    const response = await fetch(`${this.baseUrl}/api/kb/upload/folder`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Failed to upload folder: ${error}`);
    }

    return response.json();
  }

  /**
   * Get current LLM provider information
   */
  async getCurrentProvider(): Promise<{
    current_provider: string;
    current_model: string;
    available_providers: Array<{
      id: string;
      name: string;
      default_model: string;
      requires_api_key: boolean;
      description: string;
    }>;
    configured_providers: string[];
  }> {
    const response = await fetch(`${this.baseUrl}/api/config/provider`);

    if (!response.ok) {
      throw new Error(`Failed to get provider info: ${await response.text()}`);
    }

    return response.json();
  }

  /**
   * Switch to a different LLM provider (hot-switch) - Legacy
   */
  async switchProvider(provider: string): Promise<{
    success: boolean;
    provider: string;
    model: string;
    message: string;
  }> {
    const response = await fetch(`${this.baseUrl}/api/config/switch-provider`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ provider }),
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Failed to switch provider: ${error}`);
    }

    return response.json();
  }

  /**
   * Get all configured LLMs (without API keys)
   */
  async listLLMs(): Promise<{
    current_llm_id: string;
    llms: Array<{
      id: string;
      provider: string;
      name: string;
      model: string;
      base_url: string;
      has_api_key: boolean;
      api_key_preview: string;
      is_current: boolean;
    }>;
  }> {
    const response = await fetch(`${this.baseUrl}/api/config/llms`);

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Failed to list LLMs: ${error}`);
    }

    return response.json();
  }

  /**
   * Save or update LLM configuration
   *
   * api_key 是可选的：
   * - 新增时：必须提供 api_key
   * - 编辑时：如果不修改 api_key 则不传此字段
   */
  async saveLLM(request: {
    id?: string;
    provider: string;
    name: string;
    model: string;
    base_url: string;
    api_key?: string;
    user_confirmed?: boolean;
  }): Promise<{
    success: boolean;
    llm_id: string;
    requires_confirmation?: boolean;
    message?: string;
    domain?: string;
  }> {
    const response = await fetch(`${this.baseUrl}/api/config/llms`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Failed to save LLM: ${error}`);
    }

    return response.json();
  }

  /**
   * Switch to a different LLM (hot-switch)
   */
  async switchLLM(llmId: string): Promise<{
    success: boolean;
    current_llm_id: string;
  }> {
    const response = await fetch(`${this.baseUrl}/api/config/llms/switch`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ llm_id: llmId }),
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Failed to switch LLM: ${error}`);
    }

    return response.json();
  }

  /**
   * Delete LLM configuration
   */
  async deleteLLM(llmId: string): Promise<{
    success: boolean;
  }> {
    const response = await fetch(`${this.baseUrl}/api/config/llms/${llmId}`, {
      method: 'DELETE',
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Failed to delete LLM: ${error}`);
    }

    return response.json();
  }

  async cancelRun(runId: string): Promise<{ success: boolean; message: string }> {
    const response = await fetch(`${this.baseUrl}/api/chat/cancel`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ run_id: runId }),
    });
    if (!response.ok) {
      throw new Error(`Failed to cancel run: ${await response.text()}`);
    }
    return response.json();
  }

  async getRunStatus(runId: string): Promise<Record<string, unknown>> {
    const response = await fetch(`${this.baseUrl}/api/chat/runs/${runId}`);
    if (!response.ok) {
      throw new Error(`Failed to get run status: ${await response.text()}`);
    }
    return response.json();
  }
}

// Export singleton instance
export const apiClient = new APIClient();

/**
 * Skill metadata type
 */
export interface SkillMetadata {
  name: string;
  description: string;
  description_en: string;
  enabled: boolean;
  version: string;
  author: string;
  tags: string[];
  installed_at?: string;
}
