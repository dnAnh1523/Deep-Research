import React, { useState, useRef, useEffect } from 'react';
import { marked, type Token } from 'marked';
import type { Citation, SectionNode } from '../types/research';
import { CitationPopover } from './CitationPopover';

interface ReadingCanvasProps {
  content: string;
  citations: Record<number, Citation>;
  onSectionsParsed?: (sections: SectionNode[]) => void;
}

interface ActiveCitationState {
  key: string;
  rect: DOMRect;
  citation: Citation;
}

export const ReadingCanvas: React.FC<ReadingCanvasProps> = ({
  content,
  citations,
}) => {
  const [activeCitation, setActiveCitation] = useState<ActiveCitationState | null>(null);
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Clear timers on unmount
  useEffect(() => {
    return () => {
      if (closeTimerRef.current) {
        clearTimeout(closeTimerRef.current);
      }
    };
  }, []);

  const handleCitationMouseEnter = (
    instanceKey: string,
    element: HTMLElement,
    citationData: Citation
  ) => {
    if (closeTimerRef.current) {
      clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
    const rect = element.getBoundingClientRect();
    setActiveCitation({
      key: instanceKey,
      rect,
      citation: citationData,
    });
  };

  const handleCitationMouseLeave = () => {
    if (closeTimerRef.current) {
      clearTimeout(closeTimerRef.current);
    }
    closeTimerRef.current = setTimeout(() => {
      setActiveCitation(null);
    }, 350);
  };

  const handlePopoverMouseEnter = () => {
    if (closeTimerRef.current) {
      clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
  };

  const handlePopoverMouseLeave = () => {
    if (closeTimerRef.current) {
      clearTimeout(closeTimerRef.current);
    }
    closeTimerRef.current = setTimeout(() => {
      setActiveCitation(null);
    }, 350);
  };

  // Parse text string and extract interactive superscript citations and HTML line breaks
  const renderTextWithCitations = (text: string, keyPrefix: string): React.ReactNode => {
    // If text contains HTML line break tags (<br>, <br/>, <br />), split by them first
    if (/<br\s*\/?>/i.test(text)) {
      const segments = text.split(/(<br\s*\/?>)/gi);
      return segments.map((seg, sIdx) => {
        if (/^<br\s*\/?>$/i.test(seg)) {
          return <br key={`${keyPrefix}-br-${sIdx}`} className="my-1 block" />;
        }
        return (
          <React.Fragment key={`${keyPrefix}-seg-${sIdx}`}>
            {renderTextWithCitations(seg, `${keyPrefix}-sub-${sIdx}`)}
          </React.Fragment>
        );
      });
    }

    const citationRegex = /(\[([\d\s,]+)\]|【([\d\s,]+)】)/g;
    const parts: React.ReactNode[] = [];
    let lastIndex = 0;
    let match: RegExpExecArray | null;

    while ((match = citationRegex.exec(text)) !== null) {
      const matchIndex = match.index;
      const fullMatch = match[0];
      const numbersStr = match[2] || match[3] || '';
      const numbers = numbersStr
        .split(',')
        .map((s) => parseInt(s.trim(), 10))
        .filter((n) => !isNaN(n));

      if (matchIndex > lastIndex) {
        parts.push(text.substring(lastIndex, matchIndex));
      }

      if (numbers.length > 0) {
        parts.push(
          <span
            key={`cite-group-${keyPrefix}-${matchIndex}`}
            className="relative inline-block align-baseline whitespace-nowrap mx-[1px]"
          >
            <sup className="align-baseline relative -top-[0.55em] font-mono text-[11px] font-bold select-none leading-none inline-flex items-center">
              {numbers.map((citeNum, idx) => {
                const citationData = citations[citeNum];
                const instanceKey = `${keyPrefix}-${matchIndex}-${citeNum}`;
                const isActive = activeCitation?.key === instanceKey;

                return (
                  <span key={`cite-${instanceKey}`} className="relative inline-flex items-center">
                    {idx > 0 && (
                      <span className="mx-[1px] select-none font-normal text-[9px] text-[var(--accent-gold)]/40">
                        ,
                      </span>
                    )}
                    <button
                      type="button"
                      onMouseEnter={(e) => {
                        if (citationData) {
                          handleCitationMouseEnter(instanceKey, e.currentTarget, citationData);
                        }
                      }}
                      onMouseLeave={handleCitationMouseLeave}
                      onClick={(e) => {
                        e.stopPropagation();
                        if (citationData) {
                          if (activeCitation?.key === instanceKey) {
                            setActiveCitation(null);
                          } else {
                            handleCitationMouseEnter(instanceKey, e.currentTarget, citationData);
                          }
                        }
                      }}
                      className={`cursor-pointer transition-all duration-150 inline-block px-[1.5px] py-0 leading-none ${
                        isActive
                          ? 'scale-110 font-extrabold text-[var(--accent-gold)] underline decoration-[var(--accent-gold)] decoration-2'
                          : 'text-[var(--accent-gold)] hover:text-[var(--text-display)] hover:underline'
                      }`}
                      title={
                        citationData
                          ? `[${citeNum}] ${citationData.title} (${citationData.publisher})`
                          : `Trích dẫn số ${citeNum}`
                      }
                      aria-label={`Trích dẫn số ${citeNum}`}
                    >
                      {citeNum}
                    </button>
                  </span>
                );
              })}
            </sup>
          </span>
        );
      } else {
        parts.push(fullMatch);
      }

      lastIndex = matchIndex + fullMatch.length;
    }

    if (lastIndex < text.length) {
      parts.push(text.substring(lastIndex));
    }

    return parts;
  };

  // Render inline tokens (bold, italic, code, links, text)
  const renderInlineTokens = (tokens: Token[] | undefined, prefix: string): React.ReactNode => {
    if (!tokens || tokens.length === 0) return null;

    return tokens.map((token, idx) => {
      const key = `${prefix}-tok-${idx}`;

      switch (token.type) {
        case 'strong':
          return (
            <strong key={key} className="font-semibold text-white">
              {renderInlineTokens(token.tokens, key)}
            </strong>
          );

        case 'em':
          return (
            <em key={key} className="italic text-white/90">
              {renderInlineTokens(token.tokens, key)}
            </em>
          );

        case 'codespan':
          return (
            <code
              key={key}
              className="rounded border border-white/5 bg-white/10 px-1.5 py-0.5 font-mono text-xs text-[var(--accent-gold)]"
            >
              {token.text}
            </code>
          );

        case 'link':
          return (
            <a
              key={key}
              href={token.href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[var(--accent-gold)] underline decoration-1 underline-offset-2 transition-colors hover:text-[var(--text-display)]"
            >
              {renderInlineTokens(token.tokens, key)}
            </a>
          );

        case 'del':
          return (
            <del key={key} className="line-through text-white/50">
              {renderInlineTokens(token.tokens, key)}
            </del>
          );

        case 'br':
          return <br key={key} className="my-1 block" />;

        case 'html': {
          const rawHtml = ((token as any).raw || (token as any).text || '').trim();
          if (/^<br\s*\/?>$/i.test(rawHtml)) {
            return <br key={key} className="my-1 block" />;
          }
          if (/<br\s*\/?>/i.test(rawHtml)) {
            const splitParts: string[] = rawHtml.split(/(<br\s*\/?>)/i);
            return (
              <React.Fragment key={key}>
                {splitParts.map((sp: string, sIdx: number) =>
                  /^<br\s*\/?>$/i.test(sp) ? (
                    <br key={`${key}-br-${sIdx}`} className="my-1 block" />
                  ) : (
                    <span key={`${key}-sp-${sIdx}`}>{sp}</span>
                  )
                )}
              </React.Fragment>
            );
          }
          return null;
        }

        case 'escape':
          return <span key={key}>{token.text}</span>;

        case 'text':
        default: {
          const anyToken = token as any;
          if (anyToken.tokens && anyToken.tokens.length > 0) {
            return (
              <span key={key}>
                {renderInlineTokens(anyToken.tokens, key)}
              </span>
            );
          }
          const textVal = anyToken.text || anyToken.raw || '';
          return (
            <React.Fragment key={key}>
              {renderTextWithCitations(textVal, key)}
            </React.Fragment>
          );
        }
      }
    });
  };

  // Render a single block token
  const renderBlockToken = (token: Token, key: string): React.ReactNode => {
    switch (token.type) {
      case 'heading': {
        const title = token.text;
        const id = title.toLowerCase().replace(/[^a-z0-9]/g, '-').replace(/-+/g, '-');

        if (token.depth === 1) {
          return (
            <h1
              key={key}
              id={id}
              className="text-3xl font-bold tracking-tight text-white mt-10 mb-6 pb-2 border-b border-white/10"
            >
              {renderInlineTokens(token.tokens, `${key}-h1`)}
            </h1>
          );
        }

        if (token.depth === 2) {
          return (
            <h2
              key={key}
              id={id}
              className="text-2xl font-semibold tracking-tight text-white mt-12 mb-5 pb-2.5 border-b border-white/10 flex items-center justify-between"
            >
              <span>{renderInlineTokens(token.tokens, `${key}-h2`)}</span>
            </h2>
          );
        }

        if (token.depth === 3) {
          return (
            <h3
              key={key}
              id={id}
              className="text-lg font-medium tracking-tight text-white/90 mt-8 mb-3"
            >
              {renderInlineTokens(token.tokens, `${key}-h3`)}
            </h3>
          );
        }

        return (
          <h4
            key={key}
            id={id}
            className="text-base font-medium text-white/80 mt-6 mb-2"
          >
            {renderInlineTokens(token.tokens, `${key}-h4`)}
          </h4>
        );
      }

      case 'paragraph':
        return (
          <p
            key={key}
            className="text-[15px] text-white/80 leading-[1.75] my-4 font-normal"
          >
            {renderInlineTokens(token.tokens, `${key}-p`)}
          </p>
        );

      case 'blockquote':
        return (
          <blockquote
            key={key}
            className="my-5 rounded-r-lg border-l-2 border-[var(--accent-gold)] bg-white/[0.02] py-2 pl-4 text-sm text-[var(--text-secondary)] italic"
          >
            {token.tokens
              ? token.tokens.map((t: Token, idx: number) => renderBlockToken(t, `${key}-bq-${idx}`))
              : renderTextWithCitations(token.text, `${key}-bq-txt`)}
          </blockquote>
        );

      case 'list': {
        const anyList = token as any;
        const ListTag = anyList.ordered ? 'ol' : 'ul';
        const listClass = anyList.ordered
          ? 'list-decimal list-outside ml-6 my-4 space-y-2 text-[15px] text-white/80 leading-relaxed'
          : 'list-disc list-outside ml-6 my-4 space-y-2 text-[15px] text-white/80 leading-relaxed';

        return (
          <ListTag key={key} start={anyList.start ? Number(anyList.start) : undefined} className={listClass}>
            {anyList.items.map((item: any, itemIdx: number) => {
              const itemKey = `${key}-item-${itemIdx}`;
              return (
                <li key={itemKey}>
                  {item.tokens && item.tokens.length > 0
                    ? item.tokens.map((t: any, tIdx: number) => {
                        if (t.type === 'text') {
                          return (
                            <span key={`${itemKey}-txt-${tIdx}`}>
                              {t.tokens
                                ? renderInlineTokens(t.tokens, `${itemKey}-txt-${tIdx}`)
                                : renderTextWithCitations(t.text, `${itemKey}-txt-${tIdx}`)}
                            </span>
                          );
                        }
                        return renderBlockToken(t, `${itemKey}-b-${tIdx}`);
                      })
                    : renderTextWithCitations(item.text, `${itemKey}-raw`)}
                </li>
              );
            })}
          </ListTag>
        );
      }

      case 'table': {
        const anyTable = token as any;
        return (
          <div key={key} className="my-6 overflow-x-auto rounded-xl border border-white/10 glass-chrome">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="bg-white/5 border-b border-white/10 text-white/70 font-mono text-[11px] uppercase tracking-wider">
                  {anyTable.header.map((cell: any, hIdx: number) => (
                    <th key={`th-${hIdx}`} className="py-3 px-4 font-medium">
                      {cell.tokens
                        ? renderInlineTokens(cell.tokens, `${key}-th-${hIdx}`)
                        : renderTextWithCitations(cell.text, `${key}-th-${hIdx}`)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {anyTable.rows.map((row: any[], rIdx: number) => (
                  <tr key={`tr-${rIdx}`} className="hover:bg-white/[0.02] transition-colors">
                    {row.map((cell: any, cIdx: number) => (
                      <td key={`td-${cIdx}`} className="py-3 px-4 text-white/80 leading-relaxed">
                        {cell.tokens
                          ? renderInlineTokens(cell.tokens, `${key}-td-${rIdx}-${cIdx}`)
                          : renderTextWithCitations(cell.text, `${key}-td-${rIdx}-${cIdx}`)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      }

      case 'code':
        return (
          <div key={key} className="my-5 rounded-xl bg-black/60 border border-white/10 overflow-hidden">
            {token.lang && (
              <div className="px-4 py-1.5 bg-white/5 border-b border-white/10 text-[10px] font-mono text-white/40 uppercase">
                {token.lang}
              </div>
            )}
            <pre className="overflow-x-auto p-4 font-mono text-xs leading-relaxed text-[var(--accent-emerald)]">
              <code>{token.text}</code>
            </pre>
          </div>
        );

      case 'hr':
        return <hr key={key} className="border-t border-white/10 my-8" />;

      case 'space':
        return null;

      default:
        if ('tokens' in token && token.tokens && token.tokens.length > 0) {
          return (
            <div key={key}>
              {token.tokens.map((t: Token, idx: number) => renderBlockToken(t, `${key}-def-${idx}`))}
            </div>
          );
        }
        return (
          <p key={key} className="text-[15px] text-white/80 my-4">
            {renderTextWithCitations((token as any).text || (token as any).raw || '', key)}
          </p>
        );
    }
  };

  // Main content parsing using marked AST
  const renderFormattedContent = () => {
    try {
      const tokens = marked.lexer(content);
      return tokens.map((token, idx) => renderBlockToken(token, `block-${idx}`));
    } catch (err) {
      console.error('Markdown lexing error:', err);
      return <div className="text-red-400 p-4">Lỗi hiển thị nội dung báo cáo</div>;
    }
  };

  return (
    <article
      onClick={() => setActiveCitation(null)}
      className="w-full max-w-4xl 2xl:max-w-5xl mx-auto px-4 sm:px-6 py-6 font-sans"
    >
      {renderFormattedContent()}

      {/* Portal-rendered Popover: completely unclipped by tables or overflow containers */}
      {activeCitation && (
        <CitationPopover
          citation={activeCitation.citation}
          anchorRect={activeCitation.rect}
          onClose={() => setActiveCitation(null)}
          onMouseEnter={handlePopoverMouseEnter}
          onMouseLeave={handlePopoverMouseLeave}
        />
      )}
    </article>
  );
};
