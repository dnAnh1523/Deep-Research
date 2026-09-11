import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { ExternalLink, CheckCircle2, X } from 'lucide-react';
import type { Citation } from '../types/research';

interface CitationPopoverProps {
  citation: Citation;
  anchorRect?: DOMRect | null;
  onClose: () => void;
  onMouseEnter?: () => void;
  onMouseLeave?: () => void;
}

export const CitationPopover: React.FC<CitationPopoverProps> = ({
  citation,
  anchorRect,
  onClose,
  onMouseEnter,
  onMouseLeave,
}) => {
  const [coords, setCoords] = useState<{
    top: number;
    left: number;
    placeAbove: boolean;
    width: number;
  } | null>(null);

  useEffect(() => {
    if (!anchorRect) return;

    const computePosition = () => {
      const cardWidth = Math.min(384, window.innerWidth - 32);
      const triggerCenter = anchorRect.left + anchorRect.width / 2;

      let left = triggerCenter - cardWidth / 2;
      if (left < 16) left = 16;
      if (left + cardWidth > window.innerWidth - 16) {
        left = window.innerWidth - 16 - cardWidth;
      }

      // Check if there is enough space above the trigger in viewport (~240px)
      const placeAbove = anchorRect.top >= 240;
      const top = placeAbove
        ? anchorRect.top - 8
        : anchorRect.bottom + 8;

      setCoords({ top, left, placeAbove, width: cardWidth });
    };

    computePosition();
    window.addEventListener('resize', computePosition);
    window.addEventListener('scroll', computePosition, true);

    return () => {
      window.removeEventListener('resize', computePosition);
      window.removeEventListener('scroll', computePosition, true);
    };
  }, [anchorRect]);

  if (!anchorRect || !coords) return null;

  const content = (
    <div
      style={{
        position: 'fixed',
        top: `${coords.top}px`,
        left: `${coords.left}px`,
        width: `${coords.width}px`,
        transform: coords.placeAbove ? 'translateY(-100%)' : 'none',
      }}
      className="p-4 rounded-xl glass-chrome shadow-2xl z-[9999] animate-in fade-in zoom-in-95 duration-150 border border-white/10 whitespace-normal font-sans font-normal text-left select-text leading-normal break-words pointer-events-auto"
      onClick={(e) => e.stopPropagation()}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      {/* Invisible hover bridge to prevent premature closing when moving mouse */}
      <div
        className="absolute left-0 right-0 h-4 pointer-events-auto"
        style={{
          [coords.placeAbove ? 'bottom' : 'top']: '-16px',
        }}
      />
      <div className="flex items-start justify-between gap-2 mb-2 pb-2 border-b border-white/10">
        <div className="flex items-center gap-1.5 shrink-0">
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-[var(--accent-gold-soft)] font-mono text-xs font-semibold text-[var(--accent-gold)]">
            {citation.number}
          </span>
          <span className="text-xs text-white/50 font-mono uppercase tracking-wider">
            {citation.type}
          </span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="inline-flex items-center gap-1 rounded-full border border-[var(--accent-emerald)]/25 bg-[var(--accent-emerald-soft)] px-2 py-0.5 text-[11px] font-medium text-[var(--accent-emerald)]">
            <CheckCircle2 className="w-3 h-3" />
            Đã đối chiếu
          </span>
          <button
            onClick={onClose}
            className="text-white/40 hover:text-white/80 transition-colors p-0.5 rounded-md hover:bg-white/5 cursor-pointer"
            aria-label="Đóng trích dẫn"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      <h4 className="text-xs font-semibold text-white/90 leading-snug mb-1 break-words">
        {citation.title}
      </h4>

      <p className="text-[11px] text-white/60 mb-2 break-words">
        {citation.authors ? `${citation.authors} • ` : ''}
        <span className="text-white/80">{citation.publisher}</span> ({citation.year})
      </p>

      <div className="p-2.5 rounded-lg bg-black/40 border border-white/5 mb-3 text-[11px] text-white/80 leading-relaxed italic break-words whitespace-normal max-h-44 overflow-y-auto">
        "{citation.snippet}"
      </div>

      <div className="flex items-center justify-between pt-1 text-[11px] gap-2">
        <span className="text-white/40 font-mono text-[10px] truncate max-w-[120px]">
          DOI / URL Độc quyền
        </span>
        <a
          href={citation.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex shrink-0 items-center gap-1 font-medium text-[var(--accent-gold)] transition-colors hover:text-[var(--text-display)] hover:underline"
        >
          Xem tài liệu gốc
          <ExternalLink className="w-3 h-3" />
        </a>
      </div>
    </div>
  );

  return createPortal(content, document.body);
};
