import Link from 'next/link'
import { notFound } from 'next/navigation'
import { cookies } from 'next/headers'
import { isValidLocale, type Locale, defaultLocale } from '@/lib/i18n'
import { getNoticeDetail, type NoticeCardDto } from '@/lib/notices'
import type { CardType } from '@/types/database'
import NoticeCardSwiper, { type NoticeCard } from './NoticeCardSwiper'
import NoticeProcessingView from './NoticeProcessingView'
import NoticeErrorView from './NoticeErrorView'

interface Props {
  params: Promise<{ id: string }>
}

function asObject(content: unknown): Record<string, unknown> | null {
  if (content && typeof content === 'object' && !Array.isArray(content)) {
    return content as Record<string, unknown>
  }
  return null
}

function asText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function mapCommonCard(type: CardType, content: unknown, deadlineAt: string | null): NoticeCard | null {
  const obj = asObject(content)
  if (!obj) return null
  const rawItems = Array.isArray(obj.items) ? obj.items : []
  const items = rawItems
    .map(item => {
      const itemObj = asObject(item)
      if (!itemObj) return null
      const text = asText(itemObj.text)
      if (!text) return null
      const hint = asText(itemObj.hint)
      return hint ? { text, hint } : { text }
    })
    .filter((item): item is { text: string; hint?: string } => Boolean(item))
  if (items.length === 0) return null
  return {
    type,
    items,
    deadlineAt: type === 'action' ? deadlineAt : undefined,
    deadlineDaysLeft: type === 'action' ? daysLeftFromDeadline(deadlineAt) : undefined,
  }
}

function mapLegacySuppliesCard(content: unknown): NoticeCard | null {
  const obj = asObject(content)
  if (!obj) return null
  const items = Array.isArray(obj.items) ? obj.items.map(asText).filter(Boolean) : []
  if (items.length === 0) return null
  return {
    type: 'supplies',
    items: items.map(text => ({ text })),
  }
}

function mapLegacyActionCard(content: unknown, deadlineAt: string | null): NoticeCard | null {
  const obj = asObject(content)
  if (!obj) return null
  const values = Array.isArray(obj.items) ? obj.items.map(asText).filter(Boolean) : []
  const title = asText(obj.title)
  const deadline = asText(obj.deadline)
  const items = (values.length > 0 ? values : [title]).filter(Boolean)
  if (items.length === 0) return null
  return {
    type: 'action',
    items: items.map(text => (deadline ? { text, hint: deadline } : { text })),
    deadlineAt,
    deadlineDaysLeft: daysLeftFromDeadline(deadlineAt),
  }
}

function mapLegacyScheduleCard(content: unknown): NoticeCard | null {
  const obj = asObject(content)
  if (!obj) return null
  const date = asText(obj.date)
  const title = asText(obj.title)
  const location = asText(obj.location)
  const description = asText(obj.description)
  const text = date || title || description
  const hint = [location, description && description !== text ? description : ''].filter(Boolean).join(' · ')
  if (!text) return null
  return {
    type: 'schedule',
    items: [hint ? { text, hint } : { text }],
  }
}

function pickLocalized(content: unknown, locale: Locale): unknown {
  if (!content || typeof content !== 'object' || Array.isArray(content)) return content
  const c = content as Record<string, unknown>
  // jsonb { ko, zh, vi, en, ru, ar, fr, ... } 형태면 사용자 locale → ko fallback
  if (c.ko !== undefined || c[locale] !== undefined) {
    return c[locale] ?? c.ko ?? content
  }
  return content
}

function daysLeftFromDeadline(deadlineAt: string | null): number | null {
  if (!deadlineAt) return null
  return Math.ceil((new Date(deadlineAt).getTime() - Date.now()) / 86400000)
}

function mapCards(rows: NoticeCardDto[], locale: Locale, deadlineAt: string | null): NoticeCard[] {
  const mapped: NoticeCard[] = []
  for (const r of rows) {
    const localized = pickLocalized(r.content, locale)
    let card = mapCommonCard(r.type, localized, deadlineAt)
    if (!card && r.type === 'supplies') card = mapLegacySuppliesCard(localized)
    else if (!card && r.type === 'action') card = mapLegacyActionCard(localized, deadlineAt)
    else if (!card && r.type === 'schedule') card = mapLegacyScheduleCard(localized)
    if (card) mapped.push(card)
  }
  return mapped
}

export default async function NoticePage({ params }: Props) {
  const { id } = await params
  const cookieStore = await cookies()
  const cookieLocale = cookieStore.get('locale')?.value
  const locale: Locale = isValidLocale(cookieLocale) ? cookieLocale : defaultLocale
  const messages = (await import(`@/messages/${locale}.json`)).default

  const detail = await getNoticeDetail(id, locale)
  if (!detail) {
    notFound()
  }

  const backLabel = messages.notice_detail.back_to_list

  const Header = (
    <header className="sticky top-0 bg-surface border-b border-border px-4 py-3 flex items-center justify-between z-10">
      <Link href="/" className="flex items-center gap-2 text-text-secondary text-sm" aria-label={backLabel}>
        <span aria-hidden="true">←</span>
        <span>{backLabel}</span>
      </Link>
      <span className="text-sm text-text-secondary" aria-live="polite" />
    </header>
  )

  if (detail.status === 'pending' || detail.status === 'processing') {
    return (
      <main className="flex flex-col min-h-screen">
        {Header}
        <NoticeProcessingView
          title={messages.notice_detail.processing_title}
          description={messages.notice_detail.processing_desc}
        />
      </main>
    )
  }

  if (detail.status === 'error') {
    return (
      <main className="flex flex-col min-h-screen">
        {Header}
        <NoticeErrorView
          noticeId={id}
          title={messages.notice_detail.error_title}
          description={messages.notice_detail.error_desc}
          errorMessage={detail.errorMessage}
          retryLabel={messages.notice_detail.retry}
          retryingLabel={messages.notice_detail.retrying}
        />
      </main>
    )
  }

  const summary = detail.summary
  const cardRows = detail.cards

  const dataCards = mapCards(cardRows, locale, detail.deadlineAt)
  const intro: NoticeCard = {
    type: 'intro',
    emoji: messages.notice_detail.intro_emoji,
    title: messages.notice_detail.intro_title,
    summary: summary ?? '',
    hint: dataCards.length > 0 ? messages.notice_detail.swipe_hint : undefined,
  }
  const cards: NoticeCard[] = [intro, ...dataCards]

  return (
    <main className="flex flex-col min-h-screen">
      {Header}
      <NoticeCardSwiper
        noticeId={id}
        cards={cards}
        labels={{
          supplies: messages.notice_detail.supplies_badge,
          summary: messages.notice_detail.summary_badge,
          action: messages.notice_detail.action_badge,
          schedule: messages.notice_detail.schedule_badge,
          info: messages.notice_detail.info_badge,
          deadlineRemaining: messages.notice_detail.deadline_remaining,
          deadlineToday: messages.notice_detail.deadline_today,
        }}
      />
    </main>
  )
}
