import { Compass, MessageSquare, PanelLeftClose, PanelLeftOpen, Trash2 } from 'lucide-react';
import type { ResearchSession } from '../types/research';

interface SidebarProps {
  isOpen: boolean;
  onToggle: () => void;
  sessions: ResearchSession[];
  currentSessionId: string | null;
  isCurrentSessionStreaming: boolean;
  onSelectSession: (id: string) => void;
  onDeleteSession: (id: string) => void;
  onNewSession: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  isOpen,
  onToggle,
  sessions,
  currentSessionId,
  isCurrentSessionStreaming,
  onSelectSession,
  onDeleteSession,
  onNewSession,
}) => {
  return (
    <>
      {isOpen && (
        <button
          type="button"
          aria-label="Đóng thanh bên"
          className="fixed inset-0 z-30 bg-[#0f0f0f]/75 md:hidden"
          onClick={onToggle}
        />
      )}

      {isOpen ? (
        <aside
          aria-label="Thanh bên phiên nghiên cứu"
          className="fixed inset-y-0 left-0 z-40 flex w-[min(86vw,18rem)] shrink-0 flex-col border-r border-[#1f1f1f] bg-[#171717] md:static"
        >
          <div className="flex items-center gap-3 border-b border-[#1f1f1f] px-3.5 py-3">
            <img src="/ai-logo.svg" alt="" className="h-7 w-7 shrink-0 object-contain" />
            <p className="min-w-0 flex-1 truncate text-sm font-semibold text-[#e6e6e6]">Deep Research</p>
            <button
              type="button"
              onClick={onToggle}
              className="rounded-lg p-2 text-white/40 transition-colors hover:text-[#e6e6e6]"
              title="Thu gọn thanh bên"
              aria-label="Thu gọn thanh bên"
            >
              <PanelLeftClose className="h-4 w-4" />
            </button>
          </div>

          <div className="p-3">
            <button
              type="button"
              onClick={onNewSession}
              className="group flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-left text-sm font-medium text-[#e6e6e6] transition-colors hover:bg-[#1f1f1f] hover:text-white"
            >
              <img src="/new-chat.svg" alt="" className="h-4 w-4 shrink-0 object-contain" />
              <span>Nghiên cứu mới</span>
            </button>
          </div>

          <div className="flex-1 space-y-2 overflow-y-auto px-2.5 pb-3">
            <div className="px-2.5 py-2">
              <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-white/40">Gần đây</span>
            </div>

            {sessions.length === 0 ? (
              <div className="px-3 py-7 text-center text-xs text-white/40">
                <Compass className="mx-auto mb-2 h-5 w-5 text-white/45" />
                <p>Chưa có phiên nghiên cứu nào</p>
                <p className="mt-1 text-[11px] text-white/30">Nhập câu hỏi để bắt đầu</p>
              </div>
            ) : (
              sessions.map((session) => {
                const isActive = session.id === currentSessionId;
                const isBusy = isActive && isCurrentSessionStreaming;
                return (
                  <div
                    key={session.id}
                    className={`group flex w-full items-center rounded-lg text-xs transition-colors ${
                      isActive ? 'bg-[#1f1f1f] font-medium text-[#e6e6e6]' : 'text-white/55'
                    }`}
                  >
                    <button
                      type="button"
                      aria-current={isActive ? 'page' : undefined}
                      onClick={() => onSelectSession(session.id)}
                      className="flex min-w-0 flex-1 items-center gap-2.5 px-3 py-2.5 text-left transition-colors hover:text-[#e6e6e6]"
                    >
                      <MessageSquare className="h-3.5 w-3.5 shrink-0 text-current" />
                      <span className="min-w-0 flex-1 truncate">{session.title || 'Chủ đề nghiên cứu'}</span>
                      {isBusy && (
                        <span className="h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-[#1f3b9b]" />
                      )}
                    </button>
                    <button
                      type="button"
                      onClick={() => onDeleteSession(session.id)}
                      disabled={isBusy}
                      title={isBusy ? 'Nghiên cứu đang chạy' : 'Xóa nghiên cứu'}
                      aria-label={isBusy ? 'Nghiên cứu đang chạy' : `Xóa ${session.title || 'nghiên cứu'}`}
                      className="mr-1.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-white/30 opacity-0 transition-[opacity,color] hover:text-[#e6e6e6] focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-white/30 group-hover:opacity-100 disabled:cursor-not-allowed disabled:opacity-25"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                );
              })
            )}
          </div>
        </aside>
      ) : (
        <div className="hidden w-[72px] shrink-0 flex-col items-center border-r border-[#1f1f1f] bg-[#171717] py-3 md:flex">
          <div className="flex flex-col items-center gap-3">
            <img src="/ai-logo.svg" alt="Deep Research" className="h-7 w-7 object-contain" />
            <button
              type="button"
              onClick={onToggle}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-white/40 transition-colors hover:text-[#e6e6e6]"
              title="Mở thanh bên"
              aria-label="Mở thanh bên"
            >
              <PanelLeftOpen className="h-4 w-4" />
            </button>
          </div>

          <div className="my-4 h-px w-8 bg-[#1f1f1f]" />
          <button
            type="button"
            onClick={onNewSession}
            className="flex h-10 w-10 items-center justify-center rounded-xl text-[#e6e6e6] transition-colors hover:bg-[#1f1f1f] hover:text-white"
            title="Nghiên cứu mới"
            aria-label="Nghiên cứu mới"
          >
            <img src="/new-chat.svg" alt="" className="h-5 w-5 object-contain" />
          </button>

          <div className="mt-5 flex flex-col items-center gap-2">
            {sessions.slice(0, 5).map((session) => {
              const isActive = session.id === currentSessionId;
              return (
                <button
                  key={session.id}
                  type="button"
                  onClick={() => onSelectSession(session.id)}
                  className={`flex h-9 w-9 items-center justify-center rounded-lg transition-colors ${
                    isActive ? 'bg-[#1f1f1f] text-[#e6e6e6]' : 'text-white/35 hover:text-[#e6e6e6]'
                  }`}
                  title={session.title || 'Chủ đề nghiên cứu'}
                  aria-label={session.title || 'Chủ đề nghiên cứu'}
                >
                  <MessageSquare className="h-4 w-4" />
                </button>
              );
            })}
          </div>
        </div>
      )}
    </>
  );
};
