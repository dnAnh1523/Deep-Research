import React, { useState, useMemo } from 'react';
import {
  ChevronDown,
  Share2,
  Copy,
  Download,
  Check,
  Globe,
  Brain,
  List,
  ExternalLink,
  BookOpen,
  X,
} from 'lucide-react';
import type { Citation, SectionNode, ThoughtStep, WebSourceChip } from '../types/research';
import { ReadingCanvas } from './ReadingCanvas';
import { CanvasThoughtStream } from './CanvasThoughtStream';

interface CanvasReportViewerProps {
  title: string;
  report: string;
  citations: Record<number, Citation>;
  thoughtSteps?: ThoughtStep[];
  webSources?: WebSourceChip[];
  onClose: () => void;
}

export const CanvasReportViewer: React.FC<CanvasReportViewerProps> = ({
  title,
  report,
  citations,
  thoughtSteps = [],
  webSources = [],
  onClose,
}) => {
  const [isTocOpen, setIsTocOpen] = useState(false);
  const [isExportOpen, setIsExportOpen] = useState(false);
  const [hasCopied, setHasCopied] = useState(false);

  // Accordion states at the bottom
  const [openUsedSources, setOpenUsedSources] = useState(false);
  const [openUnusedSources, setOpenUnusedSources] = useState(false);
  const [openThoughts, setOpenThoughts] = useState(false);

  // Extract sections (H2, H3) for TOC dropdown
  const sections: SectionNode[] = useMemo(() => {
    const lines = report.split('\n');
    const list: SectionNode[] = [];
    lines.forEach((line) => {
      const trimmed = line.trim();
      if (trimmed.startsWith('## ')) {
        const hTitle = trimmed.replace('## ', '');
        const id = hTitle.toLowerCase().replace(/[^a-z0-9]/g, '-').replace(/-+/g, '-');
        list.push({ id, title: hTitle, level: 2 });
      } else if (trimmed.startsWith('### ')) {
        const hTitle = trimmed.replace('### ', '');
        const id = hTitle.toLowerCase().replace(/[^a-z0-9]/g, '-').replace(/-+/g, '-');
        list.push({ id, title: hTitle, level: 3 });
      }
    });
    return list;
  }, [report]);

  // Handle jump to section
  const handleJumpToSection = (id: string) => {
    setIsTocOpen(false);
    const element = document.getElementById(id);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  // Copy report
  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(report);
    } catch {
      // Clipboard access can be unavailable in a restricted browser context.
      return;
    }
    setHasCopied(true);
    setTimeout(() => {
      setHasCopied(false);
      setIsExportOpen(false);
    }, 2000);
  };

  // Export .md
  const handleDownload = () => {
    const blob = new Blob([report], { type: 'text/markdown;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `${title.slice(0, 30).replace(/[^a-z0-9]/gi, '_')}.md`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setIsExportOpen(false);
  };

  // Distinguish used vs unused sources
  const usedCitationList = Object.values(citations).sort((a, b) => a.number - b.number);
  const usedUrls = new Set(usedCitationList.map((c) => c.url.toLowerCase()));
  const unusedWebSources = webSources.filter(
    (w) => w.url && !usedUrls.has(w.url.toLowerCase())
  );

  return (
    <div className="relative flex h-full flex-col bg-[var(--surface-card)] text-[var(--text-primary)]">
      {/* Top Header Bar */}
      <div className="sticky top-0 z-30 flex items-center justify-between border-b border-[var(--surface-border)] bg-[var(--surface-card)]/90 px-4 py-3.5 backdrop-blur-xl sm:px-6">
        <div className="flex max-w-[50%] items-center gap-2">
          <BookOpen className="h-4 w-4 shrink-0 text-[var(--accent-emerald)]" />
          <h2 className="truncate text-sm font-medium text-[var(--text-display)]" title={title}>
            {title}
          </h2>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2">
          {/* TOC Dropdown */}
          <div className="relative">
            <button
              onClick={() => {
                setIsTocOpen((prev) => !prev);
                setIsExportOpen(false);
              }}
              className="flex items-center gap-1.5 rounded-xl border border-[var(--surface-border)] bg-white/[0.04] px-3 py-1.5 text-xs font-medium text-[var(--text-secondary)] transition-colors hover:bg-white/[0.08] hover:text-[var(--text-display)]"
              aria-expanded={isTocOpen}
              aria-label="Mở mục lục báo cáo"
            >
              <List className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Mục lục</span>
              <ChevronDown className="h-3.5 w-3.5 text-[var(--text-tertiary)]" />
            </button>

            {isTocOpen && (
              <div className="absolute right-0 z-50 mt-2 max-h-80 w-64 space-y-1 overflow-y-auto rounded-2xl border border-[var(--surface-border-strong)] bg-[var(--surface-overlay)] p-2 shadow-2xl">
                <div className="px-3 py-1 text-[11px] font-semibold uppercase tracking-wider text-[var(--text-tertiary)]">
                  Các mục trong bài
                </div>
                {sections.length === 0 ? (
                  <div className="px-3 py-2 text-xs text-[var(--text-tertiary)]">Không có đề mục</div>
                ) : (
                  sections.map((sec) => (
                    <button
                      key={sec.id}
                      onClick={() => handleJumpToSection(sec.id)}
                      className={`block w-full truncate rounded-lg px-3 py-1.5 text-left text-xs transition-colors hover:bg-white/[0.08] ${
                        sec.level === 3 ? 'pl-6 text-[var(--text-secondary)]' : 'font-medium text-[var(--text-display)]'
                      }`}
                    >
                      {sec.title}
                    </button>
                  ))
                )}
              </div>
            )}
          </div>

          {/* Export / Share Dropdown */}
          <div className="relative">
            <button
              onClick={() => {
                setIsExportOpen((prev) => !prev);
                setIsTocOpen(false);
              }}
              className="flex items-center gap-1.5 rounded-xl border border-[var(--surface-border)] bg-white/[0.04] px-3 py-1.5 text-xs font-medium text-[var(--text-secondary)] transition-colors hover:bg-white/[0.08] hover:text-[var(--text-display)]"
              aria-expanded={isExportOpen}
              aria-label="Mở menu chia sẻ và xuất báo cáo"
            >
              <Share2 className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Chia sẻ & xuất</span>
              <ChevronDown className="h-3.5 w-3.5 text-[var(--text-tertiary)]" />
            </button>

            {isExportOpen && (
              <div className="absolute right-0 z-50 mt-2 w-48 space-y-1 rounded-2xl border border-[var(--surface-border-strong)] bg-[var(--surface-overlay)] p-1.5 shadow-2xl">
                <button
                  onClick={handleCopy}
                  className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-xs text-[var(--text-primary)] transition-colors hover:bg-white/[0.08]"
                >
                  {hasCopied ? (
                    <Check className="h-3.5 w-3.5 text-[var(--accent-emerald)]" />
                  ) : (
                    <Copy className="h-3.5 w-3.5 text-[var(--text-tertiary)]" />
                  )}
                  <span>{hasCopied ? 'Đã sao chép!' : 'Sao chép Markdown'}</span>
                </button>

                <button
                  onClick={handleDownload}
                  className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-xs text-[var(--text-primary)] transition-colors hover:bg-white/[0.08]"
                >
                  <Download className="h-3.5 w-3.5 text-[var(--text-tertiary)]" />
                  <span>Tải file .md</span>
                </button>
              </div>
            )}
          </div>

          {/* Close Button */}
          <button
            onClick={onClose}
            className="rounded-xl bg-white/[0.04] p-1.5 text-[var(--text-tertiary)] transition-colors hover:bg-white/[0.08] hover:text-[var(--text-display)]"
            title="Đóng bảng"
            aria-label="Đóng bảng báo cáo"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Main Report Body Container */}
      <div className="flex-1 space-y-12 overflow-y-auto px-4 py-8 sm:px-10">
        {/* Render Formatted Markdown */}
        <div className="max-w-3xl mx-auto">
          <ReadingCanvas content={report} citations={citations} />
        </div>

        {/* Bottom Accordions (Exact match to User Screenshot 2) */}
        <div className="mx-auto max-w-3xl space-y-3 border-t border-[var(--surface-border)] pt-8 pb-16">
          {/* Accordion 1: Nguồn được dùng trong báo cáo */}
          <div className="overflow-hidden rounded-2xl border border-[var(--surface-border)] bg-[var(--surface-elevated)]/55">
            <button
              onClick={() => setOpenUsedSources((prev) => !prev)}
              className="flex w-full items-center justify-between px-5 py-4 text-left text-sm font-medium text-[var(--text-primary)] transition-colors hover:bg-white/[0.05]"
            >
              <div className="flex items-center gap-2.5">
                <Globe className="h-4 w-4 text-[var(--accent-emerald)]" />
                <span>Nguồn được dùng trong báo cáo ({usedCitationList.length})</span>
              </div>
              <ChevronDown
                className={`h-4 w-4 text-[var(--text-tertiary)] transition-transform duration-200 ${
                  openUsedSources ? 'rotate-180' : ''
                }`}
              />
            </button>

            {openUsedSources && (
              <div className="space-y-3 border-t border-[var(--surface-border)] px-5 pt-1 pb-5 text-xs">
                {usedCitationList.length === 0 ? (
                  <p className="text-[var(--text-tertiary)]">Chưa có trích dẫn nào trong báo cáo.</p>
                ) : (
                  usedCitationList.map((cite) => (
                    <div
                      key={cite.number}
                      className="flex flex-col gap-1.5 rounded-xl border border-[var(--surface-border)] bg-white/[0.04] p-3"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-semibold text-[var(--text-primary)]">
                          [{cite.number}] {cite.title}
                        </span>
                        {cite.url && (
                          <a
                            href={cite.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex shrink-0 items-center gap-1 text-[var(--accent-blue)] hover:text-[var(--text-display)]"
                          >
                            <span>Mở nguồn</span>
                            <ExternalLink className="h-3 w-3" />
                          </a>
                        )}
                      </div>
                      <p className="leading-relaxed text-[var(--text-secondary)] italic">
                        "{cite.snippet}"
                      </p>
                      <div className="text-[11px] text-[var(--text-tertiary)]">
                        {cite.publisher || cite.url} {cite.year ? `• ${cite.year}` : ''}
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}
          </div>

          {/* Accordion 2: Nguồn tham khảo nhưng không được dùng */}
          <div className="overflow-hidden rounded-2xl border border-[var(--surface-border)] bg-[var(--surface-elevated)]/55">
            <button
              onClick={() => setOpenUnusedSources((prev) => !prev)}
              className="w-full px-5 py-4 flex items-center justify-between text-left text-sm font-medium text-white/90 hover:bg-white/5 transition-colors"
            >
              <div className="flex items-center gap-2.5">
                <Globe className="w-4 h-4 text-white/40" />
                <span>Nguồn tham khảo nhưng không được dùng trong báo cáo ({unusedWebSources.length})</span>
              </div>
              <ChevronDown
                className={`w-4 h-4 text-white/40 transition-transform duration-200 ${
                  openUnusedSources ? 'rotate-180' : ''
                }`}
              />
            </button>

            {openUnusedSources && (
              <div className="px-5 pb-5 pt-1 space-y-2 border-t border-white/5 text-xs">
                {unusedWebSources.length === 0 ? (
                  <p className="text-white/40">Tất cả các nguồn tìm kiếm đều đã được chọn lọc đưa vào bài.</p>
                ) : (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {unusedWebSources.map((source, idx) => (
                      <a
                        key={idx}
                        href={source.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="p-2.5 rounded-xl bg-white/5 hover:bg-white/10 border border-white/5 transition-colors flex items-center justify-between group"
                      >
                        <div className="truncate mr-2">
                          <div className="font-medium text-white/80 truncate">
                            {source.title || source.domain}
                          </div>
                          <div className="text-[10px] text-white/40 truncate">
                            {source.domain}
                          </div>
                        </div>
                        <ExternalLink className="w-3.5 h-3.5 text-white/30 group-hover:text-white/70 shrink-0" />
                      </a>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Accordion 3: Quá trình suy nghĩ */}
          <div className="overflow-hidden rounded-2xl border border-[var(--surface-border)] bg-[var(--surface-elevated)]/55">
            <button
              onClick={() => setOpenThoughts((prev) => !prev)}
              className="w-full px-5 py-4 flex items-center justify-between text-left text-sm font-medium text-white/90 hover:bg-white/5 transition-colors"
            >
              <div className="flex items-center gap-2.5">
                <Brain className="h-4 w-4 text-[var(--accent-blue)]" />
                <span>Quá trình suy nghĩ</span>
              </div>
              <ChevronDown
                className={`w-4 h-4 text-white/40 transition-transform duration-200 ${
                  openThoughts ? 'rotate-180' : ''
                }`}
              />
            </button>

            {openThoughts && (
              <div className="px-5 pb-5 pt-3 border-t border-white/5">
                <CanvasThoughtStream
                  thoughtSteps={thoughtSteps}
                  webSources={webSources}
                  isStreaming={false}
                />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
