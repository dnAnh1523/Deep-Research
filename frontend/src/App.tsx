import { useState, useEffect, useCallback } from 'react';
import type {
  ChatMessage,
  ResearchPlan,
  ResearchSession,
  ThoughtStep,
  WebSourceChip,
  Citation,
} from './types/research';
import { Sidebar } from './components/Sidebar';
import { ChatFeed } from './components/ChatFeed';
import { ResearchCanvas } from './components/ResearchCanvas';
import { useResearchApi } from './hooks/useResearchApi';

const SESSION_STORAGE_KEY = 'deep_research_sessions';

function readStoredSessions(): ResearchSession[] {
  try {
    const saved = localStorage.getItem(SESSION_STORAGE_KEY);
    const parsed: ResearchSession[] = saved ? JSON.parse(saved) : [];

    // A planning request cannot be resumed after a full page reload. Keep the
    // saved conversation usable instead of restoring a spinner forever.
    return parsed.map((session) => ({
      ...session,
      status: session.status === 'planning' ? 'idle' : session.status,
    }));
  } catch {
    return [];
  }
}

export function App() {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [sessions, setSessions] = useState<ResearchSession[]>(readStoredSessions);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(() => {
    const list = readStoredSessions();
    return list.length > 0 ? list[0].id : null;
  });

  // Current session state
  const currentSession = sessions.find((s) => s.id === currentSessionId);

  // Active working state
  const [messages, setMessages] = useState<ChatMessage[]>(currentSession?.messages || []);
  const [currentPlan, setCurrentPlan] = useState<ResearchPlan | null>(currentSession?.plan || null);
  const [status, setStatus] = useState<
    'idle' | 'planning' | 'editing_plan' | 'researching' | 'completed' | 'error'
  >(currentSession?.status || 'idle');
  const [thoughtSteps, setThoughtSteps] = useState<ThoughtStep[]>(
    currentSession?.thoughtSteps || []
  );
  const [webSources, setWebSources] = useState<WebSourceChip[]>(
    currentSession?.webSources || []
  );
  const [report, setReport] = useState<string>(currentSession?.report || '');
  const [citations, setCitations] = useState<Record<number, Citation>>(
    currentSession?.citations || {}
  );
  const [isCanvasOpen, setIsCanvasOpen] = useState<boolean>(
    Boolean(currentSession?.report || currentSession?.status === 'researching')
  );
  const [canvasMode, setCanvasMode] = useState<'progress' | 'report'>(
    currentSession?.report ? 'report' : 'progress'
  );
  const [clarificationHistory, setClarificationHistory] = useState<string[]>([]);

  const { isStreaming, fetchPlan, executeResearch } = useResearchApi();

  // Save sessions to localStorage
  useEffect(() => {
    try {
      localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(sessions));
    } catch {
      // storage quota or disabled
    }
  }, [sessions]);

  // Sync state when switching sessions
  const handleSelectSession = (id: string) => {
    const target = sessions.find((s) => s.id === id);
    if (!target) return;
    setCurrentSessionId(id);
    setMessages(target.messages || []);
    setCurrentPlan(target.plan || null);
    setStatus(target.status || 'idle');
    setThoughtSteps(target.thoughtSteps || []);
    setWebSources(target.webSources || []);
    setReport(target.report || '');
    setCitations(target.citations || {});
    setIsCanvasOpen(Boolean(target.report || target.status === 'researching'));
    setCanvasMode(target.report ? 'report' : 'progress');
    setClarificationHistory([]);
    setIsSidebarOpen(false);
  };

  // Start a fresh, clean session
  const handleNewSession = () => {
    const newId = `session_${Date.now()}`;
    const newSession: ResearchSession = {
      id: newId,
      title: '',
      date: new Date().toLocaleDateString('vi-VN'),
      messages: [],
      thoughtSteps: [],
      webSources: [],
      status: 'idle',
    };
    setSessions((prev) => [newSession, ...prev]);
    setCurrentSessionId(newId);
    setMessages([]);
    setCurrentPlan(null);
    setStatus('idle');
    setThoughtSteps([]);
    setWebSources([]);
    setReport('');
    setCitations({});
    setIsCanvasOpen(false);
    setCanvasMode('progress');
    setClarificationHistory([]);
    setIsSidebarOpen(false);
  };

  // Remove a saved research session from the sidebar and local storage.
  const handleDeleteSession = (sessionId: string) => {
    const target = sessions.find((session) => session.id === sessionId);
    if (!target || (sessionId === currentSessionId && isStreaming)) return;

    const title = target.title || 'Chủ đề nghiên cứu';
    if (!window.confirm(`Xóa nghiên cứu "${title}" khỏi danh sách?`)) return;

    const remainingSessions = sessions.filter((session) => session.id !== sessionId);
    setSessions(remainingSessions);

    if (sessionId !== currentSessionId) return;

    const nextSession = remainingSessions[0];
    setCurrentSessionId(nextSession?.id || null);
    setMessages(nextSession?.messages || []);
    setCurrentPlan(nextSession?.plan || null);
    setStatus(nextSession?.status || 'idle');
    setThoughtSteps(nextSession?.thoughtSteps || []);
    setWebSources(nextSession?.webSources || []);
    setReport(nextSession?.report || '');
    setCitations(nextSession?.citations || {});
    setClarificationHistory([]);
    setIsCanvasOpen(Boolean(nextSession?.report || nextSession?.status === 'researching'));
    setCanvasMode(nextSession?.report ? 'report' : 'progress');
    setIsSidebarOpen(false);
  };

  // Update session in store
  const updateSessionRecord = useCallback(
    (updates: Partial<ResearchSession>) => {
      if (!currentSessionId) return;
      setSessions((prev) =>
        prev.map((s) => (s.id === currentSessionId ? { ...s, ...updates } : s))
      );
    },
    [currentSessionId]
  );

  const updateSessionRecordById = useCallback(
    (sessionId: string, updates: Partial<ResearchSession>) => {
      setSessions((prev) =>
        prev.map((session) => (session.id === sessionId ? { ...session, ...updates } : session))
      );
    },
    []
  );

  // Send message handler (either starting query or clarification)
  const handleSendMessage = async (text: string) => {
    const userMsg: ChatMessage = {
      id: `msg_${Date.now()}`,
      sender: 'user',
      text,
      timestamp: new Date().toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' }),
    };

    const nextMessages = [...messages, userMsg];
    setMessages(nextMessages);

    // If we're editing plan
    if (status === 'editing_plan') {
      const updatedHistory = [...clarificationHistory, text];
      setClarificationHistory(updatedHistory);
      setStatus('planning');

      const originalQuery = nextMessages.find((m) => m.sender === 'user')?.text || text;
      const newPlan = await fetchPlan(originalQuery, updatedHistory);
      setCurrentPlan(newPlan);

      const botMsg: ChatMessage = {
        id: `bot_${Date.now()}`,
        sender: 'assistant',
        text: 'Đây là kế hoạch tôi đã chuẩn bị lại theo yêu cầu của bạn. Nếu bạn cần chỉnh sửa gì, hãy cho tôi biết trước khi tôi bắt đầu nghiên cứu.',
        type: 'plan',
        plan: newPlan,
      };

      const finalMessages = [...nextMessages, botMsg];
      setMessages(finalMessages);
      setStatus('idle');
      updateSessionRecord({ messages: finalMessages, plan: newPlan });
      return;
    }

    // New inquiry
    setStatus('planning');
    let sessionTitle = text.slice(0, 40);
    if (text.length > 40) sessionTitle += '...';

    // Create session if none active
    let activeId = currentSessionId;
    if (!activeId) {
      activeId = `session_${Date.now()}`;
      setCurrentSessionId(activeId);
      const newSession: ResearchSession = {
        id: activeId,
        title: sessionTitle,
        date: new Date().toLocaleDateString('vi-VN'),
        messages: nextMessages,
        status: 'planning',
      };
      setSessions((prev) => [newSession, ...prev]);
    } else {
      updateSessionRecord({ title: sessionTitle, messages: nextMessages });
    }

    // Generate initial research plan
    const generatedPlan = await fetchPlan(text, []);
    setCurrentPlan(generatedPlan);

    const botPlanMsg: ChatMessage = {
      id: `bot_${Date.now()}`,
      sender: 'assistant',
      text: 'Đây là kế hoạch nghiên cứu cho chủ đề đó. Nếu bạn cần thay đổi, hãy cho tôi biết nhé!',
      type: 'plan',
      plan: generatedPlan,
    };

    const updatedMessagesWithPlan = [...nextMessages, botPlanMsg];
    setMessages(updatedMessagesWithPlan);
    setStatus('idle');
    updateSessionRecordById(activeId, {
      title: generatedPlan.title || sessionTitle,
      messages: updatedMessagesWithPlan,
      plan: generatedPlan,
      status: 'idle',
    });
  };

  // User clicks "Chỉnh sửa kế hoạch"
  const handleEditPlan = () => {
    setStatus('editing_plan');
    if (!currentPlan) return;

    const botMsg: ChatMessage = {
      id: `bot_${Date.now()}`,
      sender: 'assistant',
      text: 'Đây là kế hoạch hiện tại. Bạn muốn chỉnh sửa gì?',
      type: 'plan_edit_request',
      plan: currentPlan,
    };

    const next = [...messages, botMsg];
    setMessages(next);
    updateSessionRecord({ messages: next, status: 'editing_plan' });
  };

  // User clicks "Bắt đầu nghiên cứu"
  const handleStartResearch = async () => {
    if (!currentPlan) return;

    const query = currentPlan.title || messages[0]?.text || 'Nghiên cứu chủ đề';

    // Chat feedback messages
    const userConfirmMsg: ChatMessage = {
      id: `user_${Date.now()}`,
      sender: 'user',
      text: 'Bắt đầu nghiên cứu',
    };

    const botWaitMsg: ChatMessage = {
      id: `bot_${Date.now()}`,
      sender: 'assistant',
      text: 'Tuyệt! Trong khi tôi nghiên cứu, bạn cứ thoải mái rời cuộc trò chuyện này. Tôi sẽ báo ngay khi xong.',
      type: 'start_confirmation',
    };

    const nextMessages = [...messages, userConfirmMsg, botWaitMsg];
    setMessages(nextMessages);
    setStatus('researching');

    // Open side canvas in progress mode
    setIsCanvasOpen(true);
    setCanvasMode('progress');

    // Clear previous thoughts & sources
    setThoughtSteps([]);
    setWebSources([]);

    updateSessionRecord({
      messages: nextMessages,
      status: 'researching',
    });

    // Execute real stream
    await executeResearch(query, clarificationHistory, {
      onThought: (thought) => {
        setThoughtSteps((prev) => {
          if (prev.some((p) => p.id === thought.id)) return prev;
          return [...prev, thought];
        });
      },
      onWebSource: (source) => {
        setWebSources((prev) => {
          if (prev.some((p) => p.url === source.url)) return prev;
          return [...prev, source];
        });
      },
      onComplete: (finalReport, finalCitations) => {
        setReport(finalReport);
        setCitations(finalCitations);
        setStatus('completed');
        setCanvasMode('report');

        const botCompletedMsg: ChatMessage = {
          id: `bot_${Date.now()}`,
          sender: 'assistant',
          text: 'Tôi đã hoàn thành nghiên cứu cho bạn. Bạn có thể xem toàn bộ báo cáo chi tiết ở bảng bên cạnh hoặc tiếp tục đặt câu hỏi.',
          type: 'completed_notice',
        };

        setMessages((prev) => {
          const finished = [...prev, botCompletedMsg];
          updateSessionRecord({
            messages: finished,
            report: finalReport,
            citations: finalCitations,
            status: 'completed',
          });
          return finished;
        });
      },
      onError: (err) => {
        setStatus('error');
        const botErrorMsg: ChatMessage = {
          id: `bot_${Date.now()}`,
          sender: 'assistant',
          text: `Đã có lỗi xảy ra trong quá trình nghiên cứu: ${err}. Vui lòng thử lại.`,
        };
        setMessages((prev) => {
          const failedMessages = [...prev, botErrorMsg];
          updateSessionRecord({ messages: failedMessages, status: 'error' });
          return failedMessages;
        });
      },
    });
  };

  return (
    <div className="app-shell h-screen w-screen overflow-hidden flex bg-[var(--surface-ground)] text-[var(--text-primary)] font-sans">
      {/* Left Collapsible Sidebar */}
      <Sidebar
        isOpen={isSidebarOpen}
        onToggle={() => setIsSidebarOpen((prev) => !prev)}
        sessions={sessions}
        currentSessionId={currentSessionId}
        isCurrentSessionStreaming={isStreaming}
        onSelectSession={handleSelectSession}
        onDeleteSession={handleDeleteSession}
        onNewSession={handleNewSession}
      />

      {/* Main Chat Feed */}
      <ChatFeed
        messages={messages}
        currentPlan={currentPlan}
        onSendMessage={handleSendMessage}
        onEditPlan={handleEditPlan}
        onStartResearch={handleStartResearch}
        onOpenCanvas={() => setIsCanvasOpen(true)}
        isCanvasOpen={isCanvasOpen}
        status={status}
        isSidebarOpen={isSidebarOpen}
        onToggleSidebar={() => setIsSidebarOpen((prev) => !prev)}
        webSourcesCount={webSources.length}
      />

      {/* Right Canvas Panel (Fixed size, transitions from progress to report) */}
      <ResearchCanvas
        isOpen={isCanvasOpen}
        onClose={() => setIsCanvasOpen(false)}
        title={currentPlan?.title || currentSession?.title || 'Báo cáo nghiên cứu'}
        mode={canvasMode}
        report={report}
        citations={citations}
        thoughtSteps={thoughtSteps}
        webSources={webSources}
        isStreaming={isStreaming}
      />
    </div>
  );
}

export default App;
