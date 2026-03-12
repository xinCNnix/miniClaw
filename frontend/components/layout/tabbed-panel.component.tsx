/**
 * Tabbed Panel Component
 *
 * Manages tab switching between Editor and Knowledge Base panels.
 */

'use client';

import { useState } from 'react';
import { KnowledgeBasePanel } from '@/components/knowledge-base/knowledge-base-panel.component';
import { EditorPanel } from '@/components/layout/EditorPanel';
import { useTranslation } from '@/hooks/use-translation.hook';

export type TabType = 'editor' | 'knowledge-base';

interface TabbedPanelProps {
  // Editor props
  files: any[];
  directories?: any[];
  currentDirectory?: string;
  currentFile: any;
  onLoadFile: (path: string) => Promise<void>;
  onSaveFile?: (path: string, content: string) => Promise<void>;
  onCloseFile?: () => void;
  onChangeDirectory?: (path: string) => Promise<void>;
  onGoUpDirectory?: () => Promise<void>;
}

export function TabbedPanel({
  files,
  directories = [],
  currentDirectory = '.',
  currentFile,
  onLoadFile,
  onSaveFile,
  onCloseFile,
  onChangeDirectory,
  onGoUpDirectory,
}: TabbedPanelProps) {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<TabType>('editor');

  return (
    <div className="w-1/4 min-w-64 max-w-96 glass border-l border-gray-200 flex flex-col h-full">
      {/* Tab Headers */}
      <div className="flex border-b border-gray-200">
        <button
          onClick={() => setActiveTab('editor')}
          className={`flex-1 px-4 py-3 text-sm font-medium transition-colors ${
            activeTab === 'editor'
              ? 'text-emerald-700 bg-emerald-50 border-b-2 border-emerald-700'
              : 'text-gray-600 hover:text-gray-800 hover:bg-gray-50'
          }`}
        >
          {t('tabbed_panel.editor')}
        </button>
        <button
          onClick={() => setActiveTab('knowledge-base')}
          className={`flex-1 px-4 py-3 text-sm font-medium transition-colors ${
            activeTab === 'knowledge-base'
              ? 'text-emerald-700 bg-emerald-50 border-b-2 border-emerald-700'
              : 'text-gray-600 hover:text-gray-800 hover:bg-gray-50'
          }`}
        >
          {t('tabbed_panel.knowledge_base')}
        </button>
      </div>

      {/* Tab Content */}
      <div className="flex-1 overflow-hidden">
        {activeTab === 'editor' && (
          <EditorPanel
            files={files}
            directories={directories}
            currentDirectory={currentDirectory}
            currentFile={currentFile}
            onLoadFile={onLoadFile}
            onSaveFile={onSaveFile}
            onCloseFile={onCloseFile}
            onChangeDirectory={onChangeDirectory}
            onGoUpDirectory={onGoUpDirectory}
          />
        )}
        {activeTab === 'knowledge-base' && <KnowledgeBasePanel />}
      </div>
    </div>
  );
}
