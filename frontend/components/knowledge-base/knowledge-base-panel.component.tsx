/**
 * Knowledge Base Panel Component
 *
 * Displays document list, handles file uploads, and provides document management.
 */

'use client';

import { useState, useEffect } from 'react';
import { apiClient } from '@/lib/api';
import type { KBDocument, KBUploadStatus, KBLargeFileUploadResponse, KBBatchUploadResponse, KBBatchUploadComplete } from '@/types/knowledge-base';
import { Upload, File, Trash2, AlertCircle, FileText, AlertTriangle, FolderOpen } from 'lucide-react';
import { useTranslation } from '@/hooks/use-translation.hook';
import { useToastContext } from '@/components/common/ToastContext';

export function KnowledgeBasePanel() {
  const { t } = useTranslation()
  const { showToast } = useToastContext()
  const [documents, setDocuments] = useState<KBDocument[]>([]);
  const [uploadStatus, setUploadStatus] = useState<KBUploadStatus>({
    isUploading: false,
    progress: 0,
    currentFile: null,
    error: null,
  });

  // Large file upload state
  const [largeFileCheck, setLargeFileCheck] = useState<{
    file: File | null
    checkResult: KBLargeFileUploadResponse | null
  }>({
    file: null,
    checkResult: null,
  });

  // Batch upload state
  const [batchCheck, setBatchCheck] = useState<{
    files: File[] | null
    checkResult: KBBatchUploadResponse | null
  }>({
    files: null,
    checkResult: null,
  });

  // Upload mode: 'single' | 'batch' | 'folder'
  const [uploadMode, setUploadMode] = useState<'single' | 'batch' | 'folder'>('single');

  // Allowed file types - matches backend config
  const ALLOWED_FILE_TYPES = [
    // Text & Documentation
    '.txt', '.md', '.rst', '.log',
    // Web
    '.html', '.htm', '.xml',
    // Documents
    '.pdf', '.docx', '.doc',
    // Spreadsheets
    '.xlsx', '.xls', '.csv', '.json', '.jsonl',
    // Configuration
    '.yaml', '.yml', '.toml', '.ini', '.conf', '.cfg',
    // Code files
    '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.c', '.h', '.go', '.rs', '.php', '.rb', '.cs', '.swift', '.kt', '.scala', '.sh', '.bash',
    // Data
    '.sql', '.graphql', '.proto',
    // Special files (no extension)
    'README', 'CHANGELOG', 'LICENSE', 'AUTHORS', 'CONTRIBUTING',
  ];

  const MAX_FILE_SIZE = 1024 * 1024 * 1024; // 1GB
  const LARGE_FILE_THRESHOLD = 100 * 1024 * 1024; // 100MB
  const MAX_BATCH_FILES = 20;

  // Fetch documents on mount
  useEffect(() => {
    fetchDocuments();
  }, []);

  const fetchDocuments = async () => {
    try {
      const response = await apiClient.listKBDocuments();
      setDocuments(response.documents);
    } catch (error) {
      console.error('Failed to fetch documents:', error);
      setUploadStatus(prev => ({
        ...prev,
        error: t('knowledge_base.error_load_failed'),
      }));
    }
  };

  const handleFileSelect = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files || files.length === 0) return;

    if (uploadMode === 'batch') {
      // Batch upload - handle multiple files
      await handleBatchUpload(Array.from(files));
    } else {
      // Single file upload
      const file = files[0];
      await handleSingleFileUpload(file);
    }
  };

  const handleSingleFileUpload = async (file: File) => {
    // Validate file type
    const fileExt = '.' + file.name.split('.').pop()?.toLowerCase();
    if (!ALLOWED_FILE_TYPES.includes(fileExt)) {
      setUploadStatus({
        isUploading: false,
        progress: 0,
        currentFile: null,
        error: t('knowledge_base.error_unsupported_type', { ext: fileExt }),
      });
      return;
    }

    if (file.size > MAX_FILE_SIZE) {
      setUploadStatus({
        isUploading: false,
        progress: 0,
        currentFile: null,
        error: `File too large: ${(file.size / (1024 * 1024)).toFixed(1)}MB exceeds maximum 1024MB`,
      });
      return;
    }

    // For large files (> 100MB), check authorization first
    if (file.size > LARGE_FILE_THRESHOLD) {
      try {
        const checkResult = await apiClient.checkLargeFile(file.name, file.size, false);

        if (checkResult.requires_authorization) {
          setLargeFileCheck({
            file,
            checkResult,
          });
          return;
        }
      } catch (error) {
        console.error('Failed to check large file:', error);
        setUploadStatus({
          isUploading: false,
          progress: 0,
          currentFile: null,
          error: 'Failed to check file authorization requirements',
        });
        return;
      }
    }

    await uploadFile(file);
  };

  const handleBatchUpload = async (files: File[]) => {
    if (files.length === 0) return;

    if (files.length > MAX_BATCH_FILES) {
      setUploadStatus({
        isUploading: false,
        progress: 0,
        currentFile: null,
        error: `Too many files: ${files.length} exceeds maximum ${MAX_BATCH_FILES}`,
      });
      return;
    }

    // Calculate total size
    const totalSize = files.reduce((sum, file) => sum + file.size, 0);

    // Check if authorization is needed
    if (totalSize > LARGE_FILE_THRESHOLD) {
      try {
        const checkResult = await apiClient.checkBatchUpload(files.length, totalSize, false);

        if (checkResult.requires_authorization) {
          setBatchCheck({
            files,
            checkResult,
          });
          return;
        }
      } catch (error) {
        console.error('Failed to check batch upload:', error);
        setUploadStatus({
          isUploading: false,
          progress: 0,
          currentFile: null,
          error: 'Failed to check batch authorization requirements',
        });
        return;
      }
    }

    await uploadBatch(files);
  };

  const handleFolderSelect = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    // Validate it's a ZIP file
    if (!file.name.toLowerCase().endsWith('.zip')) {
      setUploadStatus({
        isUploading: false,
        progress: 0,
        currentFile: null,
        error: 'Folder must be uploaded as a ZIP file',
      });
      return;
    }

    await uploadFolder(file);
  };

  const uploadBatch = async (files: File[], uploadToken?: string) => {
    setUploadStatus({
      isUploading: true,
      progress: 0,
      currentFile: `Uploading ${files.length} files...`,
      error: null,
    });

    try {
      const response = await apiClient.uploadBatch(files, uploadToken);

      // Refresh document list if upload was successful
      if (response.successful > 0) {
        await fetchDocuments();
      }

      setUploadStatus({
        isUploading: false,
        progress: 100,
        currentFile: null,
        error: null,
      });

      // Show result message from server
      showToast(response.message, 'success');
    } catch (error: unknown) {
      console.error('Batch upload failed:', error);
      const errorMessage = error instanceof Error ? error.message : 'Unknown error'
      setUploadStatus({
        isUploading: false,
        progress: 0,
        currentFile: null,
        error: errorMessage || 'Batch upload failed',
      });
    }
  };

  const uploadFolder = async (zipFile: File) => {
    setUploadStatus({
      isUploading: true,
      progress: 0,
      currentFile: `Uploading folder: ${zipFile.name}...`,
      error: null,
    });

    try {
      const response = await apiClient.uploadFolder(zipFile);

      // Refresh document list if upload was successful
      if (response.successful > 0) {
        await fetchDocuments();
      }

      setUploadStatus({
        isUploading: false,
        progress: 100,
        currentFile: null,
        error: null,
      });

      // Show result message from server
      showToast(response.message, 'success');
    } catch (error: unknown) {
      console.error('Folder upload failed:', error);
      const errorMessage = error instanceof Error ? error.message : 'Unknown error'
      setUploadStatus({
        isUploading: false,
        progress: 0,
        currentFile: null,
        error: errorMessage || 'Folder upload failed',
      });
    }
  };

  const uploadFile = async (file: File, uploadToken?: string) => {
    // Upload file
    setUploadStatus({
      isUploading: true,
      progress: 0,
      currentFile: file.name,
      error: null,
    });

    try {
      const response = await apiClient.uploadKBDocument(file, uploadToken);

      if (response.success) {
        await fetchDocuments();
        setUploadStatus({
          isUploading: false,
          progress: 100,
          currentFile: null,
          error: null,
        });
      }
    } catch (error: unknown) {
      const err = error as { message?: string }
      console.error('Upload failed:', error);
      setUploadStatus({
        isUploading: false,
        progress: 0,
        currentFile: null,
        error: err.message || t('knowledge_base.error_upload_failed'),
      });
    }
  };

  const handleLargeFileConfirm = async () => {
    const { file, checkResult } = largeFileCheck;
    if (!file || !checkResult) return;

    try {
      // Confirm and get upload token
      const confirmedResult = await apiClient.checkLargeFile(file.name, file.size, true);

      if (confirmedResult.upload_token) {
        // Upload with token
        await uploadFile(file, confirmedResult.upload_token);

        // Clear large file state
        setLargeFileCheck({
          file: null,
          checkResult: null,
        });
      }
    } catch (error) {
      console.error('Failed to authorize large file:', error);
      setUploadStatus({
        isUploading: false,
        progress: 0,
        currentFile: null,
        error: 'Failed to authorize large file upload',
      });
    }
  };

  const handleLargeFileCancel = () => {
    setLargeFileCheck({
      file: null,
      checkResult: null,
    });
  };

  const handleBatchConfirm = async () => {
    const { files, checkResult } = batchCheck;
    if (!files || !checkResult) return;

    try {
      const confirmedResult = await apiClient.checkBatchUpload(files.length, files.reduce((sum, f) => sum + f.size, 0), true);

      if (confirmedResult.upload_token) {
        await uploadBatch(files, confirmedResult.upload_token);

        setBatchCheck({
          files: null,
          checkResult: null,
        });
      }
    } catch (error) {
      console.error('Failed to authorize batch upload:', error);
      setUploadStatus({
        isUploading: false,
        progress: 0,
        currentFile: null,
        error: 'Failed to authorize batch upload',
      });
    }
  };

  const handleBatchCancel = () => {
    setBatchCheck({
      files: null,
      checkResult: null,
    });
  };

  const handleDelete = async (docId: string, filename: string) => {
    // TODO: Replace with proper confirmation dialog
    // For now, just show a warning toast and proceed
    showToast(t('knowledge_base.delete_confirm', { filename }), 'warning');

    try {
      await apiClient.deleteKBDocument(docId);
      await fetchDocuments();
    } catch (error) {
      console.error('Delete failed:', error);
      showToast(t('knowledge_base.error_delete_failed'), 'error');
    }
  };

  const handleDragOver = (event: React.DragEvent) => {
    event.preventDefault();
  };

  const handleDrop = async (event: React.DragEvent) => {
    event.preventDefault();

    const files = Array.from(event.dataTransfer.files);
    if (files.length === 0) return;

    // Check if first file is ZIP (folder upload)
    if (files.length === 1 && files[0].name.toLowerCase().endsWith('.zip')) {
      await uploadFolder(files[0]);
      return;
    }

    // Handle as batch upload if multiple files
    if (files.length > 1 || uploadMode === 'batch') {
      await handleBatchUpload(files);
    } else {
      await handleSingleFileUpload(files[0]);
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  };

  const getFileIcon = (fileType: string) => {
    return <FileText className="w-4 h-4" />;
  };

  const getDocumentCountText = () => {
    if (documents.length === 1) {
      return t('knowledge_base.document_count_singular', { count: 1 })
    }
    return t('knowledge_base.document_count', { count: documents.length, plural: documents.length !== 1 ? 's' : '' })
  };

  return (
    <div className="w-full h-full flex flex-col">
      {/* Header */}
      <div className="p-4 border-b border-gray-200">
        <h2 className="text-lg font-semibold text-gray-800">{t('knowledge_base.title')}</h2>
        <p className="text-sm text-gray-500 mt-1">
          {getDocumentCountText()}
        </p>
      </div>

      {/* Upload Area */}
      <div className="p-4 border-b border-gray-200">
        {/* Upload Mode Toggle */}
        <div className="flex gap-2 mb-3">
          <button
            onClick={() => setUploadMode('single')}
            className={`flex-1 px-3 py-2 text-xs font-medium rounded transition-colors ${
              uploadMode === 'single'
                ? 'bg-emerald-600 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            {t('knowledge_base.single_file')}
          </button>
          <button
            onClick={() => setUploadMode('batch')}
            className={`flex-1 px-3 py-2 text-xs font-medium rounded transition-colors ${
              uploadMode === 'batch'
                ? 'bg-emerald-600 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            {t('knowledge_base.batch_upload')}
          </button>
          <button
            onClick={() => setUploadMode('folder')}
            className={`flex-1 px-3 py-2 text-xs font-medium rounded transition-colors ${
              uploadMode === 'folder'
                ? 'bg-emerald-600 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            {t('knowledge_base.folder_upload')}
          </button>
        </div>

        <div
          className="border-2 border-dashed border-gray-300 rounded-lg p-6 text-center hover:border-gray-400 transition-colors cursor-pointer"
          onDragOver={handleDragOver}
          onDrop={handleDrop}
          onClick={() => {
            if (!uploadStatus.isUploading && !largeFileCheck.file && !batchCheck.files) {
              if (uploadMode === 'folder') {
                document.getElementById('folder-upload')?.click()
              } else {
                document.getElementById('file-upload')?.click()
              }
            }
          }}
        >
          <input
            id="file-upload"
            type="file"
            className="hidden"
            accept={ALLOWED_FILE_TYPES.join(',')}
            onChange={handleFileSelect}
            disabled={uploadStatus.isUploading || largeFileCheck.file !== null || batchCheck.files !== null}
            multiple={uploadMode === 'batch'}
          />
          <input
            id="folder-upload"
            type="file"
            className="hidden"
            accept=".zip"
            onChange={handleFolderSelect}
            disabled={uploadStatus.isUploading || largeFileCheck.file !== null || batchCheck.files !== null}
          />
          {uploadMode === 'folder' ? (
            <FolderOpen className="w-8 h-8 mx-auto mb-2 text-gray-400" />
          ) : (
            <Upload className="w-8 h-8 mx-auto mb-2 text-gray-400" />
          )}
          <p className="text-sm text-gray-600 mb-1">
            {uploadStatus.isUploading
              ? t('knowledge_base.uploading', { filename: uploadStatus.currentFile || '' })
              : largeFileCheck.file
              ? t('knowledge_base.large_file_pending')
              : batchCheck.files
              ? t('knowledge_base.batch_upload_pending', { count: batchCheck.files.length })
              : uploadMode === 'single'
              ? t('knowledge_base.upload_area_title')
              : uploadMode === 'batch'
              ? t('knowledge_base.batch_upload_title')
              : t('knowledge_base.folder_upload_title')}
          </p>
          <p className="text-xs text-gray-400">
            {uploadMode === 'folder'
              ? t('knowledge_base.folder_upload_hint', { max: MAX_BATCH_FILES })
              : uploadMode === 'batch'
              ? t('knowledge_base.batch_upload_hint', { max: MAX_BATCH_FILES })
              : t('knowledge_base.supported_formats_hint', { count: ALLOWED_FILE_TYPES.length })}
          </p>
        </div>

        {/* Error Message */}
        {uploadStatus.error && (
          <div className="mt-3 p-2 bg-red-50 border border-red-200 rounded flex items-start gap-2">
            <AlertCircle className="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" />
            <p className="text-sm text-red-600">{uploadStatus.error}</p>
          </div>
        )}

        {/* Large File Confirmation Dialog */}
        {largeFileCheck.file && largeFileCheck.checkResult && (
          <div className="mt-3 p-3 bg-amber-50 border border-amber-200 rounded">
            <div className="flex items-start gap-2">
              <AlertTriangle className="w-5 h-5 text-amber-500 mt-0.5 flex-shrink-0" />
              <div className="flex-1">
                <p className="text-sm font-medium text-amber-800 mb-1">
                  Large file upload requires confirmation
                </p>
                <p className="text-xs text-amber-700 mb-2">
                  File size: {largeFileCheck.checkResult.file_size_mb.toFixed(1)}MB
                  {' '}exceeds {largeFileCheck.checkResult.threshold_mb.toFixed(0)}MB threshold
                </p>
                <p className="text-xs text-amber-600 mb-3">
                  {largeFileCheck.checkResult.message}
                </p>
                <div className="flex gap-2">
                  <button
                    onClick={handleLargeFileConfirm}
                    className="px-3 py-1 bg-amber-600 text-white text-xs rounded hover:bg-amber-700 transition-colors"
                  >
                    Confirm Upload
                  </button>
                  <button
                    onClick={handleLargeFileCancel}
                    className="px-3 py-1 bg-gray-200 text-gray-700 text-xs rounded hover:bg-gray-300 transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Batch Upload Confirmation Dialog */}
        {batchCheck.files && batchCheck.checkResult && (
          <div className="mt-3 p-3 bg-amber-50 border border-amber-200 rounded">
            <div className="flex items-start gap-2">
              <AlertTriangle className="w-5 h-5 text-amber-500 mt-0.5 flex-shrink-0" />
              <div className="flex-1">
                <p className="text-sm font-medium text-amber-800 mb-1">
                  Batch upload requires confirmation
                </p>
                <p className="text-xs text-amber-700 mb-2">
                  {batchCheck.files.length} files, total size: {batchCheck.checkResult.total_size_mb.toFixed(1)}MB
                  {' '}exceeds {batchCheck.checkResult.threshold_mb.toFixed(0)}MB threshold
                </p>
                <p className="text-xs text-amber-600 mb-3">
                  {batchCheck.checkResult.message}
                </p>
                <div className="flex gap-2">
                  <button
                    onClick={handleBatchConfirm}
                    className="px-3 py-1 bg-amber-600 text-white text-xs rounded hover:bg-amber-700 transition-colors"
                  >
                    Confirm Upload
                  </button>
                  <button
                    onClick={handleBatchCancel}
                    className="px-3 py-1 bg-gray-200 text-gray-700 text-xs rounded hover:bg-gray-300 transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Document List */}
      <div className="flex-1 overflow-y-auto">
        {documents.length === 0 ? (
          <div className="p-8 text-center">
            <File className="w-12 h-12 mx-auto mb-3 text-gray-300" />
            <p className="text-sm text-gray-500">{t('knowledge_base.no_documents_title')}</p>
            <p className="text-xs text-gray-400 mt-1">
              {t('knowledge_base.no_documents_hint')}
            </p>
          </div>
        ) : (
          <ul className="divide-y divide-gray-100">
            {documents.map((doc) => (
              <li
                key={doc.id}
                className="p-4 hover:bg-gray-50 transition-colors flex items-start justify-between gap-3"
              >
                <div className="flex items-start gap-3 flex-1 min-w-0">
                  <div className="text-emerald-600 mt-0.5 flex-shrink-0">
                    {getFileIcon(doc.file_type)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-800 truncate">
                      {doc.filename}
                    </p>
                    <p className="text-xs text-gray-500 mt-0.5">
                      {formatFileSize(doc.size)} • {doc.chunk_count} {t('knowledge_base.chunks')}
                    </p>
                    <p className="text-xs text-gray-400 mt-0.5">
                      {new Date(doc.upload_date).toLocaleString()}
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => handleDelete(doc.id, doc.filename)}
                  className="flex-shrink-0 p-1 text-gray-400 hover:text-red-500 transition-colors"
                  title={t('knowledge_base.delete_document')}
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Footer */}
      <div className="p-3 border-t border-gray-200 text-xs text-gray-400 text-center">
        {t('knowledge_base.indexed_hint')}
      </div>
    </div>
  );
}
