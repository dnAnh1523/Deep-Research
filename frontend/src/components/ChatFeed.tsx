import React, { useState, useRef, useEffect } from 'react';
import {
  ArrowUp,
  Sparkles,
  PanelLeft,
  FileText,
  Globe,
  Loader2,
  CheckCircle2,
  Square,
} from 'lucide-react';
import type { ChatMessage, ResearchPlan } from '../types/research';
import { ResearchPlanCard } from './ResearchPlanCard';

interface ChatFeedProps {
  messages: ChatMessage[];
  currentPlan?: ResearchPlan | null;
  onSendMessage: (text: string) => void;
  onEditPlan: () => void;
  onStartResearch: () => void;
  onOpenCanvas: () => void;
  isCanvasOpen: boolean;
  status: 'idle' | 'planning' | 'editing_plan' | 'researching' | 'completed' | 'error';
  isSidebarOpen: boolean;
  onToggleSidebar: () => void;
  webSourcesCount: number;
}

export const ChatFeed: React.FC<ChatFeedProps> = ({
  messages,
  currentPlan,
  onSendMessage,
  onEditPlan,
  onStartResearch,
  onOpenCanvas,
  isCanvasOpen,
  status,
  isSidebarOpen,
  onToggleSidebar,
  webSourcesCount,
}) => {
  const [inputText, setInputText] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const isBusy = status === 'planning' || status === 'researching';

  const isPlanEditMessage = (msg: ChatMessage) =>
    msg.type === 'plan_edit_request' ||
    msg.text?.startsWith('Đây là kế hoạch hiện tại. Bạn muốn chỉnh sửa gì?');

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, status]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputText.trim() || isBusy) return;
    onSendMessage(inputText.trim());
    setInputText('');
  };

  return (
    <main className="relative flex h-full min-w-0 flex-1 flex-col overflow-hidden bg-[var(--surface-ground)] text-[var(--text-primary)]">
      {/* Mobile-only access point. Desktop uses the persistent collapsed rail. */}
      {!isSidebarOpen && (
        <button
          type="button"
          onClick={onToggleSidebar}
          className="absolute left-4 top-4 z-20 rounded-xl p-2 text-[var(--text-secondary)] transition-colors hover:text-[var(--text-display)] md:hidden"
          title="Mở thanh bên"
          aria-label="Mở thanh bên"
        >
          <PanelLeft className="h-4 w-4" />
        </button>
      )}

      {/* Canvas toggle stays available without bringing back the redundant header. */}
      <div className="pointer-events-none absolute inset-x-0 top-0 z-20 flex justify-end p-4 sm:p-5">
        {(status === 'researching' || status === 'completed') && (
          <button
            type="button"
            onClick={onOpenCanvas}
            className={`pointer-events-auto flex items-center gap-1.5 rounded-xl bg-[#1f1f1f] px-3 py-1.5 text-xs font-medium text-[#e6e6e6] transition-colors hover:text-white ${
            isCanvasOpen ? '' : 'text-[#e6e6e6]'
            }`}
          >
            <FileText className="h-3.5 w-3.5" />
            <span>{status === 'researching' ? 'Tiến trình' : 'Báo cáo'}</span>
          </button>
        )}
      </div>

      {/* Main Messages Scroll Area */}
      <div className="relative flex-1 space-y-6 overflow-y-auto px-4 py-6 sm:px-6">
        <div className="surface-grid pointer-events-none absolute inset-x-0 top-0 h-80 opacity-60" />
        {/* Zero State / Welcome (Clean, NO pre-baked topics) */}
        {messages.length === 0 && (
          <div className="relative mx-auto max-w-xl space-y-4 pt-28 text-center animate-in fade-in duration-500 sm:pt-36">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl text-[#e6e6e6]">
              <Sparkles className="h-5 w-5" />
            </div>
            <h1 className="text-2xl font-medium tracking-tight text-[var(--text-display)] sm:text-3xl">
              Bạn muốn nghiên cứu về nội dung gì?
            </h1>
            <p className="mx-auto max-w-md text-xs leading-relaxed text-[var(--text-secondary)] sm:text-sm">
              Hệ thống sẽ lập kế hoạch, tìm kiếm tài liệu trên web, đối chiếu đa nguồn và tổng hợp thành báo cáo hoàn chỉnh.
            </p>
          </div>
        )}

        {/* Messages Feed */}
        <div className="relative mx-auto max-w-2xl space-y-6">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex flex-col ${
                msg.sender === 'user' ? 'items-end' : 'items-start'
              } space-y-1.5`}
            >
              {/* User message */}
              {msg.sender === 'user' && (
                <div className="max-w-xl rounded-2xl border border-[var(--surface-border)] bg-[var(--surface-card)] px-4 py-2.5 text-sm font-normal text-[var(--text-display)] shadow-lg shadow-black/10">
                  {msg.text}
                </div>
              )}

              {/* Assistant message */}
              {msg.sender === 'assistant' && (
                <div className="w-full max-w-2xl space-y-3">
                  {msg.text && !isPlanEditMessage(msg) && (
                    <div className="text-sm leading-relaxed text-[var(--text-primary)]">
                      {msg.text}
                    </div>
                  )}

                  {/* Structured plan shown when the user asks to edit it. */}
                  {isPlanEditMessage(msg) && (msg.plan || currentPlan) && (
                    <div className="space-y-3 text-sm leading-relaxed text-[var(--text-primary)]">
                      <p>Đây là kế hoạch hiện tại. Bạn muốn chỉnh sửa gì?</p>
                      <ol className="space-y-2.5 pl-0">
                        {(msg.plan || currentPlan)!.steps.map((step, idx) => (
                          <li key={`${msg.id}-step-${idx}`} className="flex items-start gap-2.5">
                            <span className="shrink-0 font-mono text-xs text-[var(--text-tertiary)]">
                              {String(idx + 1).padStart(2, '0')}
                            </span>
                            <span>{step}</span>
                          </li>
                        ))}
                      </ol>
                    </div>
                  )}

                  {/* Plan Card */}
                  {msg.type === 'plan' && msg.plan && (
                    <ResearchPlanCard
                      plan={msg.plan}
                      onEditPlan={onEditPlan}
                      onStartResearch={onStartResearch}
                      disabled={status === 'researching'}
                    />
                  )}

                  {/* Live Researching Status Pill */}
                  {msg.type === 'start_confirmation' && (
                    <button
                      type="button"
                      onClick={onOpenCanvas}
                      className="group flex w-full max-w-md items-center justify-between rounded-2xl bg-[#1f1f1f] p-4 text-left transition-colors hover:text-white"
                    >
                      <div className="flex items-center gap-3">
                        <div className="flex h-8 w-8 items-center justify-center rounded-xl text-[#e6e6e6]">
                          <Globe className="w-4 h-4 animate-spin" />
                        </div>
                        <div>
                          <div className="text-xs font-semibold text-[var(--text-display)]">
                            {currentPlan?.title || 'Đang nghiên cứu trang web'}
                          </div>
                            <div className="text-[11px] text-[#e6e6e6]/60">
                            {status === 'researching'
                              ? `Đang nghiên cứu ${webSourcesCount > 0 ? webSourcesCount : 10}+ trang web...`
                              : 'Bấm để mở thẻ Canvas'}
                          </div>
                        </div>
                      </div>
                    </button>
                  )}

                  {/* Completed Report Notice Card */}
                  {msg.type === 'completed_notice' && (
                    <button
                      type="button"
                      onClick={onOpenCanvas}
                      className="group flex w-full max-w-md items-center justify-between rounded-2xl bg-[#1f1f1f] p-4 text-left transition-colors hover:text-white"
                    >
                      <div className="flex items-center gap-3">
                        <div className="flex h-8 w-8 items-center justify-center rounded-xl text-[#e6e6e6]">
                          <CheckCircle2 className="w-4 h-4" />
                        </div>
                        <div>
                          <div className="text-xs font-semibold text-[var(--text-display)]">
                            {currentPlan?.title || 'Báo cáo hoàn tất'}
                          </div>
                            <div className="text-[11px] text-[#e6e6e6]/60">
                            Bấm để xem báo cáo trong thẻ Canvas
                          </div>
                        </div>
                      </div>
                    </button>
                  )}
                </div>
              )}
            </div>
          ))}

          {/* Planning Spinner Indicator */}
          {status === 'planning' && (
            <div className="flex items-center gap-2 pl-2 text-xs text-[var(--text-secondary)]">
              <Loader2 className="h-3.5 w-3.5 animate-spin text-[var(--accent-blue)]" />
              <span>Đang thiết lập kế hoạch nghiên cứu...</span>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Floating Bottom Input Bar - Matching Gemini Reference */}
      <div className="shrink-0 p-4 sm:p-6">
        <form
          onSubmit={handleSubmit}
          className="mx-auto flex max-w-2xl items-center gap-2 rounded-3xl border border-[#1f1f1f] bg-[#171717] p-2 pl-4 transition-colors focus-within:border-[#1f1f1f]"
        >
          <input
            type="text"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            placeholder={
              status === 'editing_plan'
                ? 'Nhập nội dung bạn muốn sửa đổi trong kế hoạch...'
                : 'Bạn muốn nghiên cứu về nội dung gì?'
            }
            disabled={isBusy}
            aria-label="Câu hỏi nghiên cứu"
            className="min-w-0 flex-1 border-none bg-transparent px-2 py-1.5 text-sm text-[var(--text-display)] outline-hidden placeholder:text-[var(--text-tertiary)] disabled:opacity-50"
          />

          <button
            type="submit"
            disabled={!inputText.trim() || isBusy}
            className={`relative flex h-9 w-9 shrink-0 items-center justify-center rounded-full shadow-lg transition-all ${
              isBusy
                ? 'bg-[#1f3b9b] text-[#e6e6e6]'
                : 'bg-[#e6e6e6] text-[#0f0f0f] hover:bg-white disabled:bg-[#1f1f1f] disabled:text-[#e6e6e6] disabled:opacity-35 disabled:hover:bg-[#1f1f1f]'
            }`}
            title={isBusy ? 'Đang xử lý' : 'Gửi câu hỏi'}
            aria-label={isBusy ? 'Đang xử lý' : 'Gửi câu hỏi'}
          >
            {isBusy ? (
              <>
                <span className="absolute inset-0 animate-ping rounded-full bg-[#1f3b9b]/30" />
                <Square className="relative h-3.5 w-3.5 fill-current" />
              </>
            ) : (
              <ArrowUp className="h-4 w-4" />
            )}
          </button>
        </form>
      </div>
    </main>
  );
};
