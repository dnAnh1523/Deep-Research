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
            <div className="flex items-center gap-2 text-[13px] sm:text-sm font-semibold text-[#e8eaed]">
              <Sparkles className="h-3.5 w-3.5 shrink-0 text-[#8ab4f8]" />
              <span>{step.title}</span>
            </div>
            <p className="pl-5 text-xs sm:text-[13px] font-normal leading-relaxed text-[#bdc1c6] whitespace-pre-line">
              {step.detail}
            </p>
          </div>
        ))}
      </div>

      {/* Discovered Web Sources - Compact Capsule Pills matching Gemini */}
      {webSources.length > 0 && (
        <div className="pt-2 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            {/* Google Search Indicator */}
            <div
              className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-white/[0.06] text-white/80"
              title="Tìm kiếm thông tin trên web"
            >
              <svg className="h-3.5 w-3.5" viewBox="0 0 24 24">
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"/>
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"/>
              </svg>
            </div>

            {webSources.map((source, index) => {
              const cleanDomain = source.domain.replace(/^www\./, '');
              const faviconUrl = `https://www.google.com/s2/favicons?domain=${cleanDomain}&sz=32`;
              const domainSnippet = cleanDomain.length > 8 ? `${cleanDomain.slice(0, 6)}...` : cleanDomain;
              const titleSnippet = source.title && source.title !== source.domain
                ? (source.title.length > 18 ? `${source.title.slice(0, 16)}...` : source.title)
                : '';

              return (
                <a
                  key={`${source.url}-${index}`}
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="group inline-flex max-w-[230px] items-center gap-1.5 truncate rounded-full border border-white/[0.08] bg-[#1e1f20] px-2.5 py-1 text-xs transition-all duration-200 hover:border-white/20 hover:bg-[#282a2c]"
                  title={`${source.title || source.domain}\n${source.url}`}
                >
                  <span className="relative flex h-3.5 w-3.5 shrink-0 items-center justify-center overflow-hidden rounded-full bg-white/10">
                    <Globe className="h-2 w-2 text-white/50" />
                    <img
                      src={faviconUrl}
                      alt=""
                      className="absolute inset-0 h-3.5 w-3.5 rounded-full object-contain"
                      onError={(event) => {
                        event.currentTarget.style.display = 'none';
                      }}
                    />
                  </span>
                  <span className="shrink-0 text-[11px] font-medium text-[#9aa0a6]">
                    {domainSnippet}
                  </span>
                  {titleSnippet && (
                    <span className="truncate text-[11px] text-[#e8eaed] group-hover:text-white">
                      {titleSnippet}
                    </span>
                  )}
                  <ExternalLink className="h-2 w-2 shrink-0 text-[#9aa0a6] opacity-0 transition-opacity group-hover:opacity-100" />
                </a>
              );
            })}
          </div>
        </div>
      )}

      {/* Skeleton Loading Bars while actively streaming */}
      {isStreaming && (
        <div className="space-y-3 pt-4 border-t border-[var(--surface-border)]">
          <div className="h-2 w-3/5 rounded-full bg-white/[0.07] animate-pulse" />
          <div className="h-2 w-full rounded-full bg-white/[0.07] animate-pulse" />
          <div className="h-2 w-4/5 rounded-full bg-white/[0.07] animate-pulse" />
          <div className="h-2 w-5/6 rounded-full bg-white/[0.07] animate-pulse" />
        </div>
      )}
    </div>
  );
};
