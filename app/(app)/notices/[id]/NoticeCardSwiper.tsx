'use client'

import { useCallback, useEffect, useState } from 'react'
import useEmblaCarousel from 'embla-carousel-react'
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

const CARD_STYLE: Record<CardType, { icon: string; color: string; bg: string }> = {
  action:   { icon: '✅', color: 'text-cat-action',   bg: 'bg-cat-action-bg' },
  schedule: { icon: '📅', color: 'text-cat-schedule', bg: 'bg-cat-schedule-bg' },
  supplies: { icon: '🎒', color: 'text-cat-supply',   bg: 'bg-cat-supply-bg' },
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

function CardContent({ card, labels }: { card: NoticeCard; labels: CardLabels }) {
  if (card.type === 'intro') {
    const paragraphs = splitParagraphs(card.summary)

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

        <div className="flex flex-col gap-3">
          {paragraphs.length > 0 ? (
            paragraphs.map((p, i) => (
              <p key={i} className="text-[16px] leading-[1.7] text-body">
                {p}
              </p>
            ))
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
