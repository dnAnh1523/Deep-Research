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

      let finalReport = '';
      let citations: Record<number, Citation> = {};
      let thoughtCounter = 1;
      let pendingLine = '';
      const seenThoughtTitles = new Set<string>();
      const seenSourceUrls = new Set<string>();

      const emitUniqueThought = (title: string, detail: string) => {
        const trimmedTitle = title.trim();
        if (seenThoughtTitles.has(trimmedTitle)) return;
        seenThoughtTitles.add(trimmedTitle);
        callbacks.onThought({
          id: `thought-${thoughtCounter++}`,
          title: trimmedTitle,
          detail: detail.trim(),
        });
      };

      const emitWebSource = (url: string, title?: string) => {
        if (!url || seenSourceUrls.has(url)) return;
        try {
          const urlObj = new URL(url);
          const domain = urlObj.hostname.replace(/^www\./, '');
          seenSourceUrls.add(url);

          let cleanTitle = (title || '').trim();
          if (!cleanTitle || cleanTitle === url) {
            const pathParts = urlObj.pathname.split('/').filter(Boolean);
            cleanTitle = pathParts.length > 0
              ? pathParts[pathParts.length - 1].replace(/[-_]/g, ' ')
              : domain;
          }

          callbacks.onWebSource({
            url,
            title: cleanTitle,
            domain,
          });
        } catch {
          // Ignore malformed URLs from upstream payloads.
        }
      };

      // Initial thought step
      emitUniqueThought(
        'Bắt đầu phân tích nghiên cứu',
        `Tôi đang bắt đầu hệ thống hóa dữ liệu và phân tích câu hỏi "${query}"...`
      );

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

        const processLine = (line: string) => {
          if (!line.startsWith('data: ')) return;

          try {
            const eventData = JSON.parse(line.slice(6));

            if (eventData.intent_arbitrator) {
              emitUniqueThought(
                'Xác thực yêu cầu nghiên cứu',
                'Hệ thống đã phân loại mục tiêu và chuẩn bị kế hoạch nghiên cứu chuyên biệt.'
              );
            }

            if (eventData.research_brief) {
              const brief =
                eventData.research_brief.supervisor?.brief ||
                eventData.research_brief.brief;
              if (brief) {
                if (Array.isArray(brief.sub_questions) && brief.sub_questions.length > 0) {
                  const questionsText = brief.sub_questions
                    .map((q: string, idx: number) => `${idx + 1}. ${q}`)
                    .join('\n');
                  emitUniqueThought(
                    'Xác định các trọng tâm nghiên cứu',
                    `Tôi đã phân rã chủ đề thành các câu hỏi khảo sát độc lập để đảm bảo bao quát toàn diện:\n${questionsText}`
                  );
                } else if (brief.objective) {
                  emitUniqueThought(
                    'Xác định trọng tâm nghiên cứu',
                    `Mục tiêu nghiên cứu: ${brief.objective}`
                  );
                }
              }
            }

            if (eventData.supervisor) {
              const sup =
                eventData.supervisor.supervisor || eventData.supervisor;
              const currentRound = sup?.current_round || 1;
              const status = sup?.status;
              const guidance = sup?.research_guidance;

              if (status === 'writing_report') {
                emitUniqueThought(
                  'Tổng hợp và chuẩn bị báo cáo',
                  'Đã thu thập đầy đủ tài liệu từ các nguồn khảo sát. Bắt đầu tổng hợp luận điểm và kiểm chứng trích dẫn.'
                );
              } else if (currentRound > 1) {
                const guidanceDetail = guidance
                  ? `Phát hiện khoảng trống thông tin: ${guidance}`
                  : 'Tiếp tục mở rộng điều tra các khía cạnh cần thêm số liệu và tài liệu thực tế.';
                emitUniqueThought(
                  `Mở rộng điều tra (Vòng ${currentRound})`,
                  guidanceDetail
                );
              } else {
                emitUniqueThought(
                  'Triển khai các tác tử tìm kiếm song song',
                  'Đang phân bổ các truy vấn tìm kiếm chuyên biệt tới các tác tử để rà soát dữ liệu trên internet.'
                );
              }
            }

            if (eventData.researcher) {
              const researcherData = eventData.researcher;
              // Stream web sources in real-time as researcher nodes complete
              if (Array.isArray(researcherData.sources) && researcherData.sources.length > 0) {
                researcherData.sources.forEach((s: { url?: string; title?: string }) => {
                  if (s && s.url) emitWebSource(s.url, s.title);
                });
              } else if (Array.isArray(researcherData.visited_urls)) {
                researcherData.visited_urls.forEach((u: string) => {
                  if (u) emitWebSource(u);
                });
              }

              emitUniqueThought(
                'Khai thác dữ liệu từ các nguồn web',
                'Các tác tử đang truy cập vào các website uy tín, báo cáo khoa học và trích xuất số liệu liên quan.'
              );
            }

            if (eventData.compression) {
              emitUniqueThought(
                'Cô đọng và chắt lọc luận điểm',
                'Hệ thống đang hệ thống hóa các phát hiện quan trọng, loại bỏ trùng lặp và làm nổi bật các luận điểm cốt lõi.'
              );
            }

            if (eventData.verification) {
              emitUniqueThought(
                'Kiểm chứng trích dẫn & Thẩm định nguồn',
                'Đang thẩm định chéo các khẳng định với nguồn tài liệu gốc để đảm bảo độ chính xác và tính khách quan.'
              );
            }

            if (eventData.reporting) {
              const rep = eventData.reporting;
              if (rep.final_report) finalReport = rep.final_report;
              if (rep.citations && Object.keys(rep.citations).length > 0) {
                citations = { ...citations, ...rep.citations };
                Object.values(rep.citations).forEach((c: any) => {
                  if (c?.url) emitWebSource(c.url, c.title);
                });
              }
            }

            if (eventData.final_report) {
              finalReport = eventData.final_report;
            }

            if (eventData.citations && Object.keys(eventData.citations).length > 0) {
              citations = { ...citations, ...eventData.citations };
              Object.values(eventData.citations).forEach((c: any) => {
                if (c?.url) emitWebSource(c.url, c.title);
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
