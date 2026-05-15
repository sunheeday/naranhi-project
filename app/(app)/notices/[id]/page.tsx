import Link from 'next/link'
import { notFound } from 'next/navigation'
import { cookies } from 'next/headers'
import { isValidLocale, type Locale, defaultLocale } from '@/lib/i18n'
import { getNoticeDetail, type NoticeCardDto } from '@/lib/notices'
import NoticeCardSwiper, { type NoticeCard } from './NoticeCardSwiper'
import NoticeProcessingView from './NoticeProcessingView'
import NoticeErrorView from './NoticeErrorView'

interface Props {
  params: Promise<{ id: string }>
}

interface GeminiSupplies {
  title?: string
  items?: string[]
  deadline?: string | null
}
interface GeminiActions {
  title?: string
  items?: string[]
  deadline?: string | null
}
interface GeminiSchedule {
  title?: string
  date?: string
  location?: string | null
  description?: string | null
}

function asObject(content: unknown): Record<string, unknown> | null {
  if (content && typeof content === 'object' && !Array.isArray(content)) {
    return content as Record<string, unknown>
  }
  return null
}

function mapSuppliesCard(content: unknown): NoticeCard | null {
  const obj = asObject(content) as GeminiSupplies | null
  if (!obj) return null
  const items = Array.isArray(obj.items) ? obj.items : []
  return {
    type: 'supplies',
    supplies: items.map(name => ({ icon: '📦', name, amount: '' })),
  }
}

function mapActionCard(content: unknown): NoticeCard | null {
  const obj = asObject(content) as GeminiActions | null
  if (!obj) return null
  const items = Array.isArray(obj.items) ? obj.items : []
  const first = items[0] ?? obj.title ?? '제출 필요'
  const deadline = obj.deadline ?? ''
  const daysLeft = deadline ? Math.max(0, Math.ceil((new Date(deadline).getTime() - Date.now()) / 86400000)) : 0
  const reason = items.slice(1).join(' · ') || (obj.title ?? '')
  return {
    type: 'action',
    action: {
      action: first,
      deadline: deadline || '-',
      daysLeft,
      reason,
    },
  }
}

function mapScheduleCard(content: unknown): NoticeCard | null {
  const obj = asObject(content) as GeminiSchedule | null
  if (!obj) return null
  return {
    type: 'schedule',
    schedules: [
      {
        date: obj.date ?? '',
        location: obj.location ?? undefined,
        description: obj.description ?? obj.title ?? '',
      },
    ],
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

function mapCards(rows: NoticeCardDto[], locale: Locale): NoticeCard[] {
  const mapped: NoticeCard[] = []
  for (const r of rows) {
    const localized = pickLocalized(r.content, locale)
    let card: NoticeCard | null = null
    if (r.type === 'supplies') card = mapSuppliesCard(localized)
    else if (r.type === 'action') card = mapActionCard(localized)
    else if (r.type === 'schedule') card = mapScheduleCard(localized)
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

  const dataCards = mapCards(cardRows, locale)
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
          action: messages.notice_detail.action_badge,
          schedule: messages.notice_detail.schedule_badge,
          deadlineRemaining: messages.notice_detail.deadline_remaining,
          deadlineToday: messages.notice_detail.deadline_today,
        }}
      />
    </main>
  )
}
