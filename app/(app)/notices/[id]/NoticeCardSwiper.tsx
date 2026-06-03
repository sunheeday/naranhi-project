'use client'

import { useCallback, useEffect, useState } from 'react'
import useEmblaCarousel from 'embla-carousel-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Components } from 'react-markdown'
import type { PluggableList } from 'unified'
import CharacterImage from '@/components/brand/CharacterImage'
import type { CharacterKey } from '@/components/brand/characters'
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

/**
 * 카드 종류별 브랜드 테마: 배경 그라데이션 · 강조색 · 배지 · 나리·누리 캐릭터.
 * 색은 globals의 카테고리 토큰(학부모 인식 컬러)을 그대로 쓴다.
 */
interface CardTheme {
  /** 슬라이드 전체 배경 그라데이션 (위 카테고리 톤 → 아래 캔버스) */
  bg: string
  /** 배지/포인트 배경색 */
  badge: string
  /** 항목 아이콘 동그라미 배경 */
  bullet: string
  icon: string
  character: CharacterKey
}

const THEME: Record<NoticeCard['type'], CardTheme> = {
  intro: {
    bg: 'from-primary-soft via-surface to-canvas',
    badge: 'bg-primary text-on-primary',
    bullet: 'bg-primary-soft text-primary',
    icon: '📄',
    character: 'wave',
  },
  action: {
    bg: 'from-cat-action-bg via-surface to-canvas',
    badge: 'bg-cat-action text-white',
    bullet: 'bg-cat-action-bg text-cat-action',
    icon: '✅',
    character: 'pointYellow',
  },
  schedule: {
    bg: 'from-cat-schedule-bg via-surface to-canvas',
    badge: 'bg-cat-schedule text-white',
    bullet: 'bg-cat-schedule-bg text-cat-schedule',
    icon: '📅',
    character: 'walk',
  },
  supplies: {
    bg: 'from-cat-supply-bg via-surface to-canvas',
    badge: 'bg-cat-supply text-white',
    bullet: 'bg-cat-supply-bg text-cat-supply',
    icon: '🎒',
    character: 'thumbBlue',
  },
  // 본문/첨부 정제본(원본 읽기): 중립 톤 + '종이 읽기' 캐릭터.
  source: {
    bg: 'from-surface via-surface to-canvas',
    badge: 'bg-ink text-canvas',
    bullet: 'bg-primary-soft text-primary',
    icon: '📄',
    character: 'readingPaper',
  },
  // 원본 파일(미리보기/다운로드): 중립 톤 + '서서 종이' 캐릭터.
  file: {
    bg: 'from-surface via-surface to-canvas',
    badge: 'bg-ink text-canvas',
    bullet: 'bg-primary-soft text-primary',
    icon: '📎',
    character: 'standingPaper',
  },
}

export default function NoticeCardSwiper({ noticeId, cards, labels }: Props) {
  const [emblaRef, emblaApi] = useEmblaCarousel({ loop: false, align: 'center' })
  const [selectedIndex, setSelectedIndex] = useState(0)

  // 카드 순서는 호출부(page.tsx)가 요약 → 구조화 → 본문/첨부 → 원본파일 순으로 정한다(여기선 재정렬 안 함).
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

  const total = orderedCards.length

  return (
    <div className="flex flex-col flex-1">
      {/* 인스타 스토리식 진행 바: 지나온 카드는 채워지고 현재까지 강조 */}
      {total > 1 && (
        <div
          className="flex gap-1.5 px-5 pt-3 pb-2"
          role="status"
          aria-label={`${selectedIndex + 1} / ${total}`}
        >
          {orderedCards.map((_, i) => (
            <button
              key={i}
              onClick={() => emblaApi?.scrollTo(i)}
              aria-label={`${i + 1}번 카드로 이동`}
              className="flex-1 h-1.5 rounded-full overflow-hidden bg-hairline"
            >
              <span
                className={`block h-full rounded-full transition-all duration-300 ${
                  i <= selectedIndex ? 'w-full bg-primary' : 'w-0'
                }`}
              />
            </button>
          ))}
        </div>
      )}

      <div className="overflow-hidden flex-1" ref={emblaRef}>
        <div className="flex">
          {orderedCards.map((card, i) => {
            const theme = THEME[card.type]
            return (
              <div
                key={`${noticeId}-${card.type}-${i}`}
                className={`flex-[0_0_100%] min-w-0 bg-gradient-to-b ${theme.bg}`}
              >
                <div className="min-h-[calc(100dvh-150px)] flex flex-col items-center justify-center px-7 py-8 gap-5">
                  <CardContent
                    card={card}
                    theme={theme}
                    labels={labels}
                    isLast={i === total - 1}
                  />
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

/** 정제된 markdown 본문(#, |표|, - 목록)을 실제 제목·표·목록으로 렌더한다.
 *  react-markdown 은 기본적으로 raw HTML 을 무시하므로 추출/LLM 내용이라도 XSS 안전. */
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

// singleTilde:false — 범위 기호 '~'(p78~93)를 취소선으로 오인하지 않게(취소선은 '~~'만).
const REMARK_PLUGINS: PluggableList = [[remarkGfm, { singleTilde: false }]]

function MarkdownBody({ source }: { source: string }) {
  return (
    <div className="break-words text-start">
      <ReactMarkdown remarkPlugins={REMARK_PLUGINS} components={markdownComponents}>
        {source}
      </ReactMarkdown>
    </div>
  )
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

function CardContent({
  card,
  theme,
  labels,
  isLast,
}: {
  card: NoticeCard
  theme: CardTheme
  labels: CardLabels
  isLast: boolean
}) {
  const isIntro = card.type === 'intro'
  const isStructured =
    card.type === 'action' || card.type === 'schedule' || card.type === 'supplies'
  const badgeLabel = isStructured
    ? labelFor(card.type as CardType, labels)
    : card.title ?? '가정통신문'

  return (
    <>
      {/* 캐릭터: 카드 종류에 맞는 나리·누리 */}
      <CharacterImage character={theme.character} size={104} disc priority className="shrink-0" />

      {/* 배지 */}
      <span
        className={`inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-pill text-sm font-bold shadow-soft ${theme.badge}`}
      >
        <span aria-hidden="true">{theme.icon}</span>
        {badgeLabel}
      </span>

      {isIntro && <IntroBody card={card} />}
      {isStructured && <CategoryBody card={card} theme={theme} />}
      {card.type === 'source' && <SourceBody card={card} />}
      {card.type === 'file' && <FileBody card={card} />}

      {/* 넘기기 안내 (마지막 카드 제외) */}
      {!isLast && (
        <p className="mt-1 text-xs text-muted-soft flex items-center gap-1">
          <span>옆으로 넘겨 보세요</span>
          <span aria-hidden="true" className="rtl-flip">→</span>
        </p>
      )}
    </>
  )
}

function IntroBody({ card }: { card: NoticeCard }) {
  const blocks = splitParagraphs(card.summary)
  // 항목이 여러 줄이면 가운데 정렬보다 왼쪽 정렬이 읽기 좋다.
  const align = blocks.length > 2 ? 'text-start' : 'text-center'
  return (
    <div className={`w-full max-w-[20rem] flex flex-col gap-2.5 ${align}`}>
      {card.dateRange && (
        <p className="text-base font-bold text-ink text-readable">{card.dateRange}</p>
      )}
      {blocks.length > 0 ? (
        blocks.map((block, i) => {
          const bullet = /^[-•]\s+/.test(block)
          const text = block.replace(/^[-•]\s+/, '')
          if (bullet) {
            return (
              <p key={i} className="flex gap-2 text-[15px] leading-[1.7] text-body text-readable">
                <span aria-hidden="true" className="text-primary shrink-0">•</span>
                <span>{text}</span>
              </p>
            )
          }
          return (
            <p
              key={i}
              className={`text-readable ${i === 0 ? 'text-lg font-bold text-ink leading-snug' : 'text-[15px] leading-[1.7] text-body'}`}
            >
              {text}
            </p>
          )
        })
      ) : (
        <p className="text-sm text-muted-soft">요약 정보가 없어요.</p>
      )}
    </div>
  )
}

function CategoryBody({ card, theme }: { card: NoticeCard; theme: CardTheme }) {
  const items = card.items ?? []
  if (items.length === 0) {
    return <p className="text-sm text-muted-soft">표시할 항목이 없어요.</p>
  }
  return (
    <ul className="w-full max-w-[22rem] flex flex-col gap-3">
      {items.map((item, i) => (
        <li
          key={i}
          className="flex items-start gap-3 bg-surface rounded-card shadow-card px-4 py-3.5 text-start"
        >
          <span
            className={`shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-sm font-bold ${theme.bullet}`}
            aria-hidden="true"
          >
            {i + 1}
          </span>
          <div className="flex-1 min-w-0">
            <p className="text-base font-bold text-ink leading-snug text-readable">{item.text}</p>
            {item.hint ? (
              <p className="text-sm text-muted mt-1 leading-relaxed text-readable">{item.hint}</p>
            ) : null}
          </div>
        </li>
      ))}
    </ul>
  )
}

/** 본문/첨부 정제본 카드: 정제 markdown(표·제목·목록)을 그대로 렌더. 복잡하면 원본 파일 안내. */
function SourceBody({ card }: { card: NoticeCard }) {
  if (card.needsFile || !card.content?.trim()) {
    return <p className="w-full max-w-[22rem] text-[15px] leading-[1.7] text-body text-start">{card.complexNotice}</p>
  }
  return (
    <div className="w-full max-w-[22rem] bg-canvas rounded-card shadow-card px-4 py-4 border border-hairline-soft">
      <MarkdownBody source={card.content} />
    </div>
  )
}

/** 원본 파일 카드: 우리 Storage 사본을 미리보기(새 창)·다운로드. */
function FileBody({ card }: { card: NoticeCard }) {
  const files = card.files ?? []
  const previewLabel = card.fileLabels?.preview ?? 'Preview'
  const downloadLabel = card.fileLabels?.download ?? 'Download'
  if (files.length === 0) {
    return <p className="text-sm text-muted-soft">첨부된 원본 파일이 없어요.</p>
  }
  return (
    <ul className="w-full max-w-[22rem] flex flex-col gap-3">
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
  )
}

function labelFor(type: CardType, labels: CardLabels): string {
  return labels[type]
}

function splitParagraphs(value: string | undefined): string[] {
  return (value ?? '')
    .split(/\n+/)
    .map(s => s.trim())
    .filter(Boolean)
}
