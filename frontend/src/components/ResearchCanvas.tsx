import React from 'react';
import { ChevronDown, X, Sparkles } from 'lucide-react';
import type { Citation, ThoughtStep, WebSourceChip } from '../types/research';
import { CanvasThoughtStream } from './CanvasThoughtStream';
import { CanvasReportViewer } from './CanvasReportViewer';

interface ResearchCanvasProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  mode: 'progress' | 'report';
  report?: string;
  citations?: Record<number, Citation>;
  thoughtSteps: ThoughtStep[];
  webSources: WebSourceChip[];
  isStreaming: boolean;
}

export const ResearchCanvas: React.FC<ResearchCanvasProps> = ({
  isOpen,
  onClose,
  title,
  mode,
  report = '',
  citations = {},
  thoughtSteps,
  webSources,
  isStreaming,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-30 flex h-full w-full flex-col p-3 transition-all duration-300 sm:p-4 md:static md:h-full md:w-[min(56vw,52rem)] md:shrink-0">
      {/* Floating Canvas Card Container */}
      <div className="flex h-full w-full flex-col overflow-hidden rounded-3xl border border-[#1f1f1f] bg-[#171717]">
        {mode === 'progress' ? (
          <div className="flex flex-col h-full">
            {/* Header */}
            <div className="flex shrink-0 items-center justify-between border-b border-[#1f1f1f] bg-[#171717] px-5 py-4 sm:px-6">
              <div className="flex items-center gap-2 max-w-[65%]">
                <Sparkles className="h-4 w-4 shrink-0 text-[#e6e6e6]" />
                <h2 className="truncate text-sm font-semibold text-[var(--text-display)]" title={title}>
                  {title || 'Đang tiến hành nghiên cứu'}
                </h2>
              </div>

              <div className="flex items-center gap-2">
                <div className="hidden items-center gap-1.5 rounded-xl bg-[#1f1f1f] px-3 py-1.5 text-xs font-medium text-[#e6e6e6]/65 sm:flex">
                  <span>Tiến trình trực tiếp</span>
                  <ChevronDown className="h-3.5 w-3.5 text-[var(--text-tertiary)]" />
                </div>

                <button
                  type="button"
                  onClick={onClose}
                  className="rounded-xl bg-[#1f1f1f] p-1.5 text-white/45 transition-colors hover:text-[#e6e6e6]"
                  title="Đóng thẻ Canvas"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Body: Thought Stream & Compact Web Sources */}
            <div className="flex-1 overflow-y-auto px-5 py-6 sm:px-8">
              <CanvasThoughtStream
                thoughtSteps={thoughtSteps}
                webSources={webSources}
                isStreaming={isStreaming}
              />
            </div>
          </div>
        ) : (
          /* Report View */
          <CanvasReportViewer
            title={title}
            report={report}
            citations={citations}
            thoughtSteps={thoughtSteps}
            webSources={webSources}
            onClose={onClose}
          />
        )}
      </div>
    </div>
  );
};
