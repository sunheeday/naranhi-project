'use client'

import { useCallback, useEffect, useState } from 'react'
import useEmblaCarousel from 'embla-carousel-react'

export type CardType = 'supplies' | 'action' | 'schedule'

export interface SupplyItem {
  icon: string
  name: string
  amount: string
  warning?: boolean
}

export interface ActionItem {
  action: string
  deadline: string
  daysLeft: number
  reason: string
}

export interface ScheduleItem {
  date: string
  time?: string
  location?: string
  description: string
}

export interface NoticeCard {
  type: 'intro' | CardType
  title?: string
  subtitle?: string
  emoji?: string
  dateRange?: string
  summary?: string
  hint?: string
  supplies?: SupplyItem[]
  warningNote?: string
  action?: ActionItem
  schedules?: ScheduleItem[]
}

export interface CardLabels {
  supplies: string
  action: string
  schedule: string
  deadlineRemaining: string  // "D-{days}일 남음" 형식 (값은 로케일별 템플릿)
  deadlineToday: string
}

interface Props {
  noticeId: string
  cards: NoticeCard[]
  labels: CardLabels
}

const BADGE_STYLE = {
  supplies: { color: 'text-cat-supply',   bg: 'bg-cat-supply-bg' },
  action:   { color: 'text-cat-action',   bg: 'bg-cat-action-bg' },
  schedule: { color: 'text-cat-schedule', bg: 'bg-cat-schedule-bg' },
} as const

export default function NoticeCardSwiper({ noticeId, cards, labels }: Props) {
  const [emblaRef, emblaApi] = useEmblaCarousel({ loop: false, align: 'center' })
  const [selectedIndex, setSelectedIndex] = useState(0)

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
          {cards.map((card, i) => (
            <div
              key={i}
              className="flex-[0_0_100%] min-w-0 px-6 pt-6 pb-24"
            >
              <CardContent card={card} noticeId={noticeId} labels={labels} />
            </div>
          ))}
        </div>
      </div>

      {/* 도트 인디케이터 */}
      <div className="flex justify-center gap-2 py-4 pb-20" aria-label={`${selectedIndex + 1} / ${cards.length}`} role="status">
        {cards.map((_, i) => (
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

function CardContent({ card, noticeId, labels }: { card: NoticeCard; noticeId: string; labels: CardLabels }) {
  if (card.type === 'intro') {
    const paragraphs = (card.summary ?? '')
      .split(/\n+/)
      .map(s => s.trim())
      .filter(Boolean)

    return (
      <div className="bg-canvas rounded-card shadow-soft p-6 flex flex-col gap-5 min-h-[360px] border border-hairline-soft">
        <div className="flex items-center gap-2">
          <span className="text-xl" aria-hidden="true">{card.emoji ?? '📄'}</span>
          <span className="text-xs font-semibold tracking-wide text-muted uppercase">
            {card.title ?? '가정통신문'}
          </span>
        </div>

        {card.dateRange && (
          <p className="text-base text-ink font-semibold" style={{ letterSpacing: '-0.01em' }}>{card.dateRange}</p>
        )}

        <div className="flex flex-col gap-3">
          {paragraphs.length > 0 ? (
            paragraphs.map((p, i) => {
              const isWarning = /^⚠️?|^주의/.test(p)
              if (isWarning) {
                return (
                  <div
                    key={i}
                    className="bg-cat-action-bg border-s-4 border-cat-action rounded-btn px-4 py-3"
                  >
                    <p className="text-[15px] leading-[1.65] text-cat-action font-semibold">
                      {p}
                    </p>
                  </div>
                )
              }
              return (
                <p key={i} className="text-[16px] leading-[1.7] text-body">
                  {p}
                </p>
              )
            })
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

  const t = card.type as CardType
  const badge = BADGE_STYLE[t]
  const badgeLabel = t === 'supplies' ? labels.supplies : t === 'action' ? labels.action : labels.schedule

  return (
    <div className="bg-canvas rounded-card shadow-soft p-5 flex flex-col gap-4 border border-hairline-soft">
      <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-pill text-xs font-semibold w-fit ${badge.bg} ${badge.color}`}>
        {t === 'supplies' && '🎒'}
        {t === 'action' && '✅'}
        {t === 'schedule' && '📅'}
        {badgeLabel}
      </span>

      {t === 'supplies' && card.supplies && (
        <SuppliesContent items={card.supplies} warningNote={card.warningNote} />
      )}
      {t === 'action' && card.action && (
        <ActionContent item={card.action} labels={labels} />
      )}
      {t === 'schedule' && card.schedules && (
        <ScheduleContent items={card.schedules} />
      )}
    </div>
  )
}

function SuppliesContent({ items, warningNote }: { items: SupplyItem[]; warningNote?: string }) {
  return (
    <div className="flex flex-col gap-3">
      {items.map((item, i) => (
        <div key={i} className="flex items-center justify-between py-2 border-b border-hairline-soft last:border-0">
          <div className="flex items-center gap-3">
            <span className="text-2xl" aria-hidden="true">{item.icon}</span>
            <span className={`text-base ${item.warning ? 'text-cat-action font-semibold' : 'text-ink'}`}>
              {item.name}
            </span>
          </div>
          <span className="text-base font-bold text-ink">{item.amount}</span>
        </div>
      ))}
      {warningNote && (
        <div className="mt-2 bg-cat-action-bg rounded-btn px-4 py-3 flex items-start gap-2">
          <span aria-hidden="true">⚠️</span>
          <p className="text-sm text-cat-action font-semibold">{warningNote}</p>
        </div>
      )}
    </div>
  )
}

function ActionContent({ item, labels }: { item: ActionItem; labels: CardLabels }) {
  const dLabel =
    item.daysLeft <= 0
      ? labels.deadlineToday
      : labels.deadlineRemaining.replace('{days}', String(item.daysLeft))

  return (
    <div className="flex flex-col gap-4">
      <p className="text-lg font-semibold text-ink leading-snug" style={{ letterSpacing: '-0.01em' }}>{item.action}</p>
      <div className="flex flex-col gap-1.5">
        <p className="text-2xl font-bold text-ink" style={{ letterSpacing: '-0.02em' }}>{item.deadline}</p>
        <span className="inline-flex items-center px-3 py-1 rounded-pill bg-cat-action-bg text-cat-action text-xs font-semibold w-fit">
          {dLabel}
        </span>
      </div>
      <p className="text-sm text-muted">{item.reason}</p>
    </div>
  )
}

function ScheduleContent({ items }: { items: ScheduleItem[] }) {
  return (
    <div className="flex flex-col gap-3">
      {items.map((item, i) => (
        <div key={i} className="flex flex-col gap-1 py-3 border-b border-hairline-soft last:border-0">
          <p className="text-2xl font-bold text-ink" style={{ letterSpacing: '-0.02em' }}>{item.date}</p>
          {item.time && <p className="text-sm text-muted">{item.time}</p>}
          {item.location && <p className="text-sm text-muted">{item.location}</p>}
          <p className="text-sm text-body mt-1">{item.description}</p>
        </div>
      ))}
    </div>
  )
}
