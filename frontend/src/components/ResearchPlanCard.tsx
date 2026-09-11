import React, { useState } from 'react';
import { Files, BarChart3, FileText, Clock, ChevronDown, ChevronUp } from 'lucide-react';
import type { ResearchPlan } from '../types/research';

interface ResearchPlanCardProps {
  plan: ResearchPlan;
  onEditPlan: () => void;
  onStartResearch: () => void;
  disabled?: boolean;
}

export const ResearchPlanCard: React.FC<ResearchPlanCardProps> = ({
  plan,
  onEditPlan,
  onStartResearch,
  disabled = false,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);

  // Show first 2-3 steps if collapsed, all if expanded
  const displaySteps = isExpanded ? plan.steps : plan.steps.slice(0, 3);
  const hasMore = plan.steps.length > 3;

  return (
    <div className="apple-card my-3 w-full max-w-2xl space-y-5 rounded-3xl p-6 text-[var(--text-primary)]">
      {/* Report title */}
      <div className="min-w-0">
        <h3 className="break-words text-lg font-semibold leading-snug tracking-tight text-[var(--text-display)]">
          {plan.title}
        </h3>
      </div>

      {/* Steps List */}
      <div className="space-y-4 text-xs text-[var(--text-secondary)]">
        {/* Step 1: Research plan */}
        <div className="relative space-y-2 pl-9">
          <div className="absolute bottom-1 left-3 top-8 w-px bg-[#e6e6e6]/20" aria-hidden="true" />
          <div className="absolute left-0 top-0 flex h-6 w-6 items-center justify-center text-[#e6e6e6]">
            <Files className="h-5 w-5" />
          </div>
          <div className="font-medium text-[var(--text-display)]">Kế hoạch nghiên cứu</div>

          <div className="space-y-2 leading-relaxed text-[var(--text-secondary)]">
            {displaySteps.map((step, idx) => (
              <div key={idx} className="flex items-start gap-1.5">
                <span className="shrink-0 font-mono text-[var(--text-tertiary)]">{String(idx + 1).padStart(2, '0')}</span>
                <span>{step}</span>
              </div>
            ))}

            {hasMore && (
              <button
                type="button"
                onClick={() => setIsExpanded((prev) => !prev)}
                className="flex items-center gap-1 pt-1 text-xs font-medium text-[#e6e6e6]/65 transition-colors hover:text-[#e6e6e6]"
              >
                {isExpanded ? (
                  <>
                    <span>Thu gọn</span>
                    <ChevronUp className="w-3.5 h-3.5" />
                  </>
                ) : (
                  <>
                    <span>Hiện thêm</span>
                    <ChevronDown className="w-3.5 h-3.5" />
                  </>
                )}
              </button>
            )}
          </div>
        </div>

        {/* Step 2: Analyze Results */}
        <div className="flex items-center gap-2 font-medium text-[var(--text-display)]">
          <BarChart3 className="h-5 w-5 shrink-0 text-[#e6e6e6]" />
          <span>Phân tích kết quả</span>
        </div>

        {/* Step 3: Generate Report */}
        <div className="flex items-center gap-2 font-medium text-[var(--text-display)]">
          <FileText className="h-5 w-5 shrink-0 text-[#e6e6e6]" />
          <span>Tạo báo cáo</span>
        </div>
      </div>

      {/* Footer: ETA + Action Buttons */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--surface-border)] pt-4 text-xs">
        <div className="flex items-center gap-1.5 text-[#e6e6e6]/75">
          <Clock className="h-4 w-4" />
          <span>{plan.time_estimate || 'Sẵn sàng sau vài phút'}</span>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onEditPlan}
            disabled={disabled}
            className="flex h-9 min-w-40 items-center justify-center gap-1.5 rounded-full px-5 py-2 text-sm font-medium text-[#e6e6e6]/85 transition-colors hover:bg-[#1f1f1f] hover:text-[#e6e6e6] disabled:opacity-50"
          >
            <span>Chỉnh sửa kế hoạch</span>
          </button>

          <button
            type="button"
            onClick={onStartResearch}
            disabled={disabled}
            className="group flex h-9 min-w-40 items-center justify-center gap-1.5 rounded-full bg-[#1f3b9b] px-5 py-2 text-sm font-medium text-[#e6e6e6] transition-colors hover:bg-[#1f3b9b] disabled:opacity-50"
          >
            <span>Bắt đầu nghiên cứu</span>
          </button>
        </div>
      </div>
    </div>
  );
};
