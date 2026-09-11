import React from 'react';
import { Globe, Sparkles, ExternalLink } from 'lucide-react';
import type { ThoughtStep, WebSourceChip } from '../types/research';

interface CanvasThoughtStreamProps {
  thoughtSteps: ThoughtStep[];
  webSources: WebSourceChip[];
  isStreaming: boolean;
}

export const CanvasThoughtStream: React.FC<CanvasThoughtStreamProps> = ({
  thoughtSteps,
  webSources,
  isStreaming,
}) => {
  return (
    <div className="space-y-6 text-[var(--text-primary)]">
      {/* Stream of Thoughts with Diamond Star */}
      <div className="space-y-5">
        {thoughtSteps.map((step) => (
          <div key={step.id} className="animate-in space-y-1.5 fade-in duration-300">
            <div className="flex items-center gap-2 text-[13px] font-semibold text-[var(--text-display)]">
              <Sparkles className="h-3.5 w-3.5 shrink-0 text-[var(--accent-blue)]" />
              <span>{step.title}</span>
            </div>
            <p className="pl-5 text-xs font-normal leading-relaxed text-[var(--text-secondary)] sm:text-[13px]">
              {step.detail}
            </p>
          </div>
        ))}
      </div>

      {/* Discovered Web Sources - Compact Capsule Pills matching Gemini */}
      {webSources.length > 0 && (
        <div className="pt-2 space-y-2.5">
          <div className="flex flex-wrap items-center gap-2">
            {webSources.map((source, index) => {
              const cleanDomain = source.domain.replace(/^www\./, '');
              const faviconUrl = `https://www.google.com/s2/favicons?domain=${cleanDomain}&sz=32`;

              return (
                <a
                  key={index}
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="group inline-flex max-w-[240px] items-center gap-2 truncate rounded-full bg-[#1f1f1f] px-3 py-1.5 text-xs text-[#e6e6e6]/80 transition-colors hover:text-[#e6e6e6]"
                  title={source.title || source.domain}
                >
                  <span className="relative flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[#e6e6e6]/70">
                    <Globe className="h-2.5 w-2.5" />
                    <img
                      src={faviconUrl}
                      alt=""
                      className="absolute inset-0 h-4 w-4 rounded-full bg-[var(--surface-elevated)] object-contain"
                      onError={(event) => event.currentTarget.remove()}
                    />
                  </span>
                  <span className="truncate text-[11px] font-medium text-[var(--text-secondary)] group-hover:text-[var(--text-display)]">
                    {source.title ? `${cleanDomain}... ${source.title.slice(0, 16)}` : cleanDomain}
                  </span>
                  <ExternalLink className="h-2.5 w-2.5 shrink-0 text-[#e6e6e6]/45 opacity-0 transition-opacity group-hover:text-[#e6e6e6] group-hover:opacity-100" />
                </a>
              );
            })}
          </div>
        </div>
      )}

      {/* Skeleton Loading Bars while actively streaming */}
      {isStreaming && (
        <div className="animate-pulse space-y-3 border-t border-[var(--surface-border)] pt-4">
          <div className="h-2.5 w-4/5 rounded-full bg-white/[0.07]" />
          <div className="h-2.5 w-full rounded-full bg-white/[0.07]" />
          <div className="h-2.5 w-3/4 rounded-full bg-white/[0.07]" />
          <div className="h-2.5 w-5/6 rounded-full bg-white/[0.07]" />
        </div>
      )}
    </div>
  );
};
