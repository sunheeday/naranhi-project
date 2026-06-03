'use client'

import { useCallback, useEffect, useState } from 'react'
import useEmblaCarousel from 'embla-carousel-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Components } from 'react-markdown'
import type { PluggableList } from 'unified'
import type { CardType } from '@/types/database'

export interface NoticeCardItem {
  text: string
  hint?: string
}

export interface NoticeFileEntry {
  filename: string
  publicUrl: string
  previewable: boolean
}

export interface NoticeCard {
  type: 'intro' | 'file' | 'source' | CardType
  emoji?: string
  title?: string
  dateRange?: string
  summary?: string
  /** 'source' 카드의 정제 markdown 본문 */
  content?: string
  /** 'source' 카드: 형식이 복잡해 원본 파일 안내로 대체할지 */
  needsFile?: boolean
  /** needsFile 일 때 보여줄 안내 문구 */
  complexNotice?: string
  hint?: string
  items?: NoticeCardItem[]
  /** 'file' 카드: 우리 Storage 첨부 파일들(미리보기/다운로드) */
  files?: NoticeFileEntry[]
  fileLabels?: { preview: string; download: string }
}

export interface CardLabels {
  supplies: string
  action: string
  schedule: string
}

interface Props {
  noticeId: string
  cards: NoticeCard[]
  labels: CardLabels
}

const CARD_STYLE: Record<CardType, { icon: string; color: string; bg: string }> = {
  action:   { icon: '✅', color: 'text-cat-action',   bg: 'bg-cat-action-bg' },
  schedule: { icon: '📅', color: 'text-cat-schedule', bg: 'bg-cat-schedule-bg' },
  supplies: { icon: '🎒', color: 'text-cat-supply',   bg: 'bg-cat-supply-bg' },
}

export default function NoticeCardSwiper({ noticeId, cards, labels }: Props) {
  const [emblaRef, emblaApi] = useEmblaCarousel({ loop: false, align: 'center' })
  const [selectedIndex, setSelectedIndex] = useState(0)

  // 카드 순서는 호출부(page.tsx)가 본문 → 첨부 → 원본파일 순으로 정한다(여기선 재정렬 안 함).
  const orderedCards = cards

  const onSelect = useCallback(() => {
    if (!emblaApi) return
    setSelectedIndex(emblaApi.selectedScrollSnap())
  }, [emblaApi])

  useEffect(() => {
    if (!emblaApi) return
    emblaApi.on('select', onSelect)
    return () => { emblaApi.off('select', onSelect) }
  }, [emblaApi, onSelect])

  return (
    <div className="flex flex-col min-h-screen">
      <div className="overflow-hidden flex-1" ref={emblaRef}>
        <div className="flex h-full">
          {orderedCards.map((card, i) => (
            <div
              key={`${noticeId}-${card.type}-${i}`}
              className="flex-[0_0_100%] min-w-0 px-6 pt-6 pb-24"
            >
              <CardContent card={card} labels={labels} />
            </div>
          ))}
        </div>
      </div>

      <div className="flex justify-center gap-2 py-4 pb-20" aria-label={`${selectedIndex + 1} / ${orderedCards.length}`} role="status">
        {orderedCards.map((_, i) => (
          <button
            key={i}
            onClick={() => emblaApi?.scrollTo(i)}
            aria-label={`${i + 1}번 카드`}
            className={`w-2 h-2 rounded-full transition-colors ${
              i === selectedIndex ? 'bg-ink' : 'bg-hairline'
            }`}
          />
        ))}
      </div>
    </div>
  )
}

const markdownComponents: Components = {
  h1: ({ children }) => <h1 className="text-lg font-bold text-ink mt-1 mb-1">{children}</h1>,
  h2: ({ children }) => <h2 className="text-base font-bold text-ink mt-4 mb-1">{children}</h2>,
  h3: ({ children }) => <h3 className="text-sm font-semibold text-ink mt-3 mb-1">{children}</h3>,
  p: ({ children }) => <p className="text-[16px] leading-[1.7] text-body my-2">{children}</p>,
  ul: ({ children }) => <ul className="list-disc pl-5 my-2 flex flex-col gap-1">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal pl-5 my-2 flex flex-col gap-1">{children}</ol>,
  li: ({ children }) => <li className="text-[15px] leading-[1.6] text-body">{children}</li>,
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer" className="text-cat-action underline break-all">
      {children}
    </a>
  ),
  strong: ({ children }) => <strong className="font-semibold text-ink">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  hr: () => <hr className="my-3 border-hairline-soft" />,
  blockquote: ({ children }) => (
    <blockquote className="border-l-2 border-hairline-soft pl-3 text-muted my-2">{children}</blockquote>
  ),
  table: ({ children }) => (
    <div className="my-3 overflow-x-auto">
      <table className="w-full border-collapse text-[13px]">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-surface">{children}</thead>,
  th: ({ children }) => (
    <th className="border border-border px-2.5 py-1.5 text-left font-semibold text-ink align-top">{children}</th>
  ),
  td: ({ children }) => (
    <td className="border border-border px-2.5 py-1.5 text-body align-top">{children}</td>
  ),
}

/** 보편적인 미리보기(눈)·다운로드 아이콘 (Feather 스타일 인라인 SVG, currentColor 로 테마 적용). */
function PreviewIcon() {
  return (
    <svg
      width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"
    >
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  )
}

function DownloadIcon() {
  return (
    <svg
      width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"
    >
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  )
}

/** 정제된 markdown 본문(#, |표|, - 목록)을 실제 제목·표·목록으로 렌더한다.
 *  react-markdown 은 기본적으로 raw HTML 을 무시하므로 추출/LLM 내용이라도 XSS 안전. */
// singleTilde:false — 범위 기호 '~'(p78~93)를 취소선으로 오인하지 않게(취소선은 '~~'만).
const REMARK_PLUGINS: PluggableList = [[remarkGfm, { singleTilde: false }]]

function MarkdownBody({ source }: { source: string }) {
  return (
    <div className="break-words">
      <ReactMarkdown remarkPlugins={REMARK_PLUGINS} components={markdownComponents}>
        {source}
      </ReactMarkdown>
    </div>
  )
}

function CardContent({ card, labels }: { card: NoticeCard; labels: CardLabels }) {
  if (card.type === 'intro') {
    return (
      <div className="bg-canvas rounded-card shadow-soft p-6 flex flex-col gap-5 min-h-[360px] border border-hairline-soft">
        <div className="flex items-center gap-2">
          <span className="text-xl" aria-hidden="true">{card.emoji ?? '📄'}</span>
          <span className="text-xs font-semibold tracking-wide text-muted uppercase">
            {card.title ?? '가정통신문'}
          </span>
        </div>

        {card.dateRange && (
          <p className="text-base text-ink font-semibold">{card.dateRange}</p>
        )}

        <div className="flex flex-col">
          {card.summary?.trim() ? (
            <MarkdownBody source={card.summary} />
          ) : (
            <p className="text-sm text-muted-soft">요약 정보가 없어요.</p>
          )}
        </div>

        {card.hint && (
          <p className="mt-auto pt-4 text-xs text-muted-soft text-center border-t border-hairline-soft">
            {card.hint}
          </p>
        )}
      </div>
    )
  }

  if (card.type === 'source') {
    return (
      <div className="bg-canvas rounded-card shadow-soft p-6 flex flex-col gap-4 min-h-[360px] border border-hairline-soft">
        <div className="flex items-center gap-2">
          <span className="text-xl" aria-hidden="true">{card.emoji ?? '📄'}</span>
          <span className="text-xs font-semibold tracking-wide text-muted uppercase">
            {card.title}
          </span>
        </div>

        {card.needsFile ? (
          <p className="text-[15px] leading-[1.7] text-body">{card.complexNotice}</p>
        ) : card.content?.trim() ? (
          <MarkdownBody source={card.content} />
        ) : (
          <p className="text-[15px] leading-[1.7] text-body">{card.complexNotice}</p>
        )}

        {card.hint && (
          <p className="mt-auto pt-4 text-xs text-muted-soft text-center border-t border-hairline-soft">
            {card.hint}
          </p>
        )}
      </div>
    )
  }

  if (card.type === 'file') {
    const files = card.files ?? []
    const previewLabel = card.fileLabels?.preview ?? 'Preview'
    const downloadLabel = card.fileLabels?.download ?? 'Download'

    return (
      <div className="bg-canvas rounded-card shadow-soft p-6 flex flex-col gap-5 min-h-[360px] border border-hairline-soft">
        <div className="flex items-center gap-2">
          <span className="text-xl" aria-hidden="true">{card.emoji ?? '📎'}</span>
          <span className="text-xs font-semibold tracking-wide text-muted uppercase">
            {card.title ?? '원본 파일'}
          </span>
        </div>

        {files.length > 0 ? (
          <ul className="flex flex-col gap-3">
            {files.map((file, i) => (
              <li
                key={i}
                className="flex items-center gap-2 px-4 py-3 rounded-card border border-hairline-soft bg-surface"
              >
                <span aria-hidden="true">📄</span>
                <span className="flex-1 truncate text-ink font-medium">{file.filename}</span>
                {file.previewable && (
                  <a
                    href={file.publicUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    aria-label={previewLabel}
                    title={previewLabel}
                    className="shrink-0 w-9 h-9 inline-flex items-center justify-center rounded-card text-text-secondary hover:bg-canvas hover:text-ink transition-colors"
                  >
                    <PreviewIcon />
                  </a>
                )}
                <a
                  href={`${file.publicUrl}?download=${encodeURIComponent(file.filename)}`}
                  aria-label={downloadLabel}
                  title={downloadLabel}
                  className="shrink-0 w-9 h-9 inline-flex items-center justify-center rounded-card text-text-secondary hover:bg-canvas hover:text-ink transition-colors"
                >
                  <DownloadIcon />
                </a>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-soft">첨부된 원본 파일이 없어요.</p>
        )}

        {card.hint && (
          <p className="mt-auto pt-4 text-xs text-muted-soft text-center border-t border-hairline-soft">
            {card.hint}
          </p>
        )}
      </div>
    )
  }

  const style = CARD_STYLE[card.type]
  const items = card.items ?? []

  return (
    <div className="bg-canvas rounded-card shadow-soft p-5 flex flex-col gap-4 border border-hairline-soft">
      <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-pill text-xs font-semibold w-fit ${style.bg} ${style.color}`}>
        <span aria-hidden="true">{style.icon}</span>
        {labelFor(card.type, labels)}
      </span>

      {items.length > 0 ? (
        <ul className="flex flex-col gap-3">
          {items.map((item, i) => (
            <li key={i} className="py-3 border-b border-hairline-soft last:border-0">
              <p className="text-base font-semibold text-ink leading-snug">{item.text}</p>
              {item.hint ? <p className="text-sm text-muted mt-1.5 leading-relaxed">{item.hint}</p> : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-soft">표시할 항목이 없어요.</p>
      )}
    </div>
  )
}

function labelFor(type: CardType, labels: CardLabels): string {
  return labels[type]
}

