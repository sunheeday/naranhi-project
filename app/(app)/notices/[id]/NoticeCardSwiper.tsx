'use client'

import { useCallback, useEffect, useState } from 'react'
import useEmblaCarousel from 'embla-carousel-react'
import CharacterImage from '@/components/brand/CharacterImage'
import type { CharacterKey } from '@/components/brand/characters'
import type { CardType } from '@/types/database'

export interface NoticeCardItem {
  text: string
  hint?: string
}

export interface NoticeCard {
  type: 'intro' | CardType
  emoji?: string
  title?: string
  dateRange?: string
  summary?: string
  hint?: string
  items?: NoticeCardItem[]
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

const THEME: Record<'intro' | CardType, CardTheme> = {
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
}

const CARD_ORDER: CardType[] = ['action', 'schedule', 'supplies']

export default function NoticeCardSwiper({ noticeId, cards, labels }: Props) {
  const [emblaRef, emblaApi] = useEmblaCarousel({ loop: false, align: 'center' })
  const [selectedIndex, setSelectedIndex] = useState(0)

  const orderedCards = [...cards].sort((a, b) => cardSortIndex(a.type) - cardSortIndex(b.type))

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

  return (
    <>
      {/* 캐릭터: 카드 종류에 맞는 나리·누리 */}
      <CharacterImage character={theme.character} size={104} disc priority className="shrink-0" />

      {/* 배지 */}
      <span
        className={`inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-pill text-sm font-bold shadow-soft ${theme.badge}`}
      >
        <span aria-hidden="true">{theme.icon}</span>
        {isIntro ? (card.title ?? '가정통신문') : labelFor(card.type as CardType, labels)}
      </span>

      {isIntro ? (
        <IntroBody card={card} />
      ) : (
        <CategoryBody card={card} theme={theme} />
      )}

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

function labelFor(type: CardType, labels: CardLabels): string {
  return labels[type]
}

function cardSortIndex(type: 'intro' | CardType): number {
  if (type === 'intro') return -1
  const index = CARD_ORDER.indexOf(type)
  return index >= 0 ? index : CARD_ORDER.length
}

function splitParagraphs(value: string | undefined): string[] {
  return (value ?? '')
    .split(/\n+/)
    .map(s => s.trim())
    .filter(Boolean)
}
