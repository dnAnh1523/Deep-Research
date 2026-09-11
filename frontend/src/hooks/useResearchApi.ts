import { useState, useCallback } from 'react';
import type { Citation, ResearchPlan, ThoughtStep, WebSourceChip } from '../types/research';

function createFallbackTitle(query: string): string {
  const normalized = query.replace(/\s+/g, ' ').trim().replace(/[.!?]+$/, '');
  const semanticPrefix = normalized.split(/\s+(?:và|,|:|;)\s+/)[0]?.trim();
  if (semanticPrefix && semanticPrefix.split(' ').length >= 4 && semanticPrefix.length < normalized.length) {
    return semanticPrefix;
  }
  return normalized.split(' ').slice(0, 12).join(' ') || 'Kế hoạch nghiên cứu';
}

export function useResearchApi() {
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  const [apiError, setApiError] = useState<string | null>(null);

  // Generate research plan via /research/plan
  const fetchPlan = useCallback(
    async (query: string, clarificationHistory: string[] = []): Promise<ResearchPlan> => {
      try {
        setApiError(null);
        const res = await fetch('/research/plan', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query, clarification_history: clarificationHistory }),
        });

        if (res.ok) {
          const data = await res.json();
          return {
            title: data.title || query,
            steps: data.steps || [
              `Tìm kiếm thông tin tổng quan về ${query}`,
              `Xác định các yếu tố, bên liên quan và phạm vi của ${query}`,
              'Khảo sát các nguồn tin tức, nghiên cứu và bài viết phân tích uy tín',
              'Đối chiếu số liệu, quan điểm và các trường hợp thực tế',
              'Đánh giá các xu hướng, rủi ro và khoảng trống thông tin',
              'Tổng hợp các phát hiện chính thành kết luận có thể kiểm chứng',
            ],
            time_estimate: data.time_estimate || 'Sẵn sàng sau vài phút',
            full_explanation: data.full_explanation || `Kế hoạch nghiên cứu cho "${query}".`,
          };
        }
      } catch (err) {
        console.warn('Backend plan generation error, using fallback plan:', err);
      }

      // Fallback plan if backend is temporarily unreachable
      return {
        // Keep the complete user topic. The card owns responsive wrapping;
        // truncating here made every fallback plan look like a mock preview.
        title: createFallbackTitle(query),
        steps: [
          `Tìm hiểu tổng quan và định nghĩa cốt lõi về ${query}`,
          `Xác định phạm vi, các yếu tố chính và bối cảnh của ${query}`,
          'Khảo sát các nguồn tin tức, nghiên cứu và tài liệu phân tích uy tín',
          'Đối chiếu dữ liệu, quan điểm và các trường hợp thực tế',
          'Đánh giá xu hướng, rủi ro và những điểm còn thiếu bằng chứng',
          'Đúc kết các phát hiện chính thành bài viết hoàn chỉnh',
        ],
        time_estimate: 'Sẵn sàng sau vài phút',
        full_explanation: `Đây là kế hoạch nghiên cứu được chuẩn bị cho "${query}".`,
      };
    },
    []
  );

  // Stream research execution
  const executeResearch = useCallback(
    async (
      query: string,
      clarificationHistory: string[],
      callbacks: {
        onThought: (thought: ThoughtStep) => void;
        onWebSource: (source: WebSourceChip) => void;
        onComplete: (report: string, citations: Record<number, Citation>) => void;
        onError: (error: string) => void;
      }
    ) => {
      setIsStreaming(true);
      setApiError(null);

      // Initial thought step
      callbacks.onThought({
        id: 'step-1',
        title: 'Bắt đầu khởi tạo nghiên cứu',
        detail: `Tôi đang bắt đầu hệ thống hóa dữ liệu và phân tích câu hỏi "${query}"...`,
      });

      try {
        const response = await fetch('/research/stream', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            query,
            clarification_history: clarificationHistory,
          }),
        });

        if (!response.ok) {
          throw new Error(`Máy chủ phản hồi mã lỗi ${response.status}`);
        }

        if (!response.body) {
          throw new Error('ReadableStream không được hỗ trợ');
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');

        let finalReport = '';
        let citations: Record<number, Citation> = {};
        let thoughtCounter = 2;
        let pendingLine = '';

        const processLine = (line: string) => {
          if (!line.startsWith('data: ')) return;

          try {
            const eventData = JSON.parse(line.slice(6));

            if (eventData.intent_arbitrator) {
              callbacks.onThought({
                id: `step-${thoughtCounter++}`,
                title: 'Xác định mục tiêu tìm kiếm',
                detail: 'Hệ thống đã phân loại mục tiêu và chuẩn bị các truy vấn tìm kiếm chuyên biệt.',
              });
            }

            if (eventData.supervisor) {
              callbacks.onThought({
                id: `step-${thoughtCounter++}`,
                title: 'Điều phối các tác tử tìm kiếm',
                detail: 'Đang triển khai các tác tử tìm kiếm song song trên các trang web uy tín.',
              });
            }

            if (eventData.researcher) {
              callbacks.onThought({
                id: `step-${thoughtCounter++}`,
                title: 'Đang cào dữ liệu và tổng hợp',
                detail: 'Đã thu thập dữ liệu từ các trang web và đang chọn lọc các thông tin giá trị.',
              });
            }

            if (eventData.final_report) {
              finalReport = eventData.final_report;
            }

            if (eventData.citations && Object.keys(eventData.citations).length > 0) {
              citations = eventData.citations;
              Object.values(citations).forEach((citation) => {
                if (!citation.url) return;

                try {
                  const urlObj = new URL(citation.url);
                  callbacks.onWebSource({
                    url: citation.url,
                    title: citation.title || urlObj.hostname,
                    domain: urlObj.hostname,
                  });
                } catch {
                  // Ignore malformed URLs from an upstream citation payload.
                }
              });
            }
          } catch {
            // Ignore non-JSON SSE pings while preserving the stream.
          }
        };

        while (true) {
          const { done, value } = await reader.read();
          if (done) {
            pendingLine += decoder.decode();
            break;
          }

          pendingLine += decoder.decode(value, { stream: true });
          const lines = pendingLine.split('\n');
          pendingLine = lines.pop() || '';
          lines.forEach(processLine);
        }

        if (pendingLine) processLine(pendingLine);

        // If report finished
        if (finalReport) {
          callbacks.onComplete(finalReport, citations);
        } else {
          // Check disk latest report as fallback
          const latestRes = await fetch('/api/latest-report');
          if (latestRes.ok) {
            const data = await latestRes.json();
            if (data.report) {
              callbacks.onComplete(data.report, data.citations || {});
              return;
            }
          }
          throw new Error('Chưa nhận được bài báo cáo từ hệ thống');
        }
      } catch (err: unknown) {
        const errorMessage = err instanceof Error ? err.message : 'Lỗi kết nối tới Deep Research Backend';
        console.error('Lỗi khi nghiên cứu:', err);
        setApiError(errorMessage);
        callbacks.onError(errorMessage);
      } finally {
        setIsStreaming(false);
      }
    },
    []
  );

  return {
    isStreaming,
    apiError,
    fetchPlan,
    executeResearch,
  };
}
