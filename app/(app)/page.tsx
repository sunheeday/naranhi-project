import Link from 'next/link'
import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import { isValidLocale, type Locale, defaultLocale } from '@/lib/i18n'
import { getViewer } from '@/lib/viewer'
import { DEMO_NOTICE_LIMIT, readDemoHiddenNoticeIds } from '@/lib/test-entry-bypass'
import { getHiddenNoticeIds, getSchoolSummary } from '@/lib/server-cache'
import type { Json, NoticeStatus } from '@/types/database'
import { schoolNeedsInitialCrawl, type SchoolCrawlerState } from '@/lib/school-crawler-trigger'
import { pickNoticeDisplayTitle } from '@/lib/notice-title'
import BrandHeader from '@/components/brand/BrandHeader'
import CharacterEmptyState from '@/components/brand/CharacterEmptyState'
import HomePoller from './HomePoller'
import HomeNoticeSections from './HomeNoticeSections'
import NoticeTranslationKickoff from './NoticeTranslationKickoff'
import SchoolCrawlerKickoff from './SchoolCrawlerKickoff'

interface NoticeRow {
  id: string
  status: NoticeStatus
  title: string | null
  due_date: string | null
  extracted_content: Json | null
  ai_translations: { [locale: string]: string }
  crawl_result: Json
  created_at: string
  notice_cards: { type: string }[]
}

interface DisplayNotice {
  id: string
  cardType: 'action' | null
  title: string
  status: NoticeStatus
  arrivedAt: string
  needsTranslation: boolean
  /** 홈 분류 기준: action 카드가 있으면 '해야 할 일', 없으면 '공지' */
  actionRequired: boolean
  /** 연결된 일정이 있을 때의 마감/일정 칩 (예: 'D-3 · 4/18'), 없으면 null */
  dueLabel: string | null
  dueUrgent: boolean
}

type CategoryLabels = Record<Locale, string>
const BADGE: Record<'action' | 'null', { bar: string; bg: string; text: string; label: CategoryLabels }> = {
  action:   { bar: 'bg-cat-action',   bg: 'bg-cat-action-bg',   text: 'text-cat-action',
    label: { ko: '해야 할 일', en: 'To-do', zh: '待办事项', vi: 'Việc cần làm', ru: 'Дела', ar: 'المهام', fr: 'À faire', id: 'Tugas', th: 'งานที่ต้องทำ' } },
  null:     { bar: 'bg-ink',          bg: 'bg-surface-card',    text: 'text-ink',
    label: { ko: '공지', en: 'Notice', zh: '通知', vi: 'Thông báo', ru: 'Объявление', ar: 'إشعار', fr: 'Annonce', id: 'Pemberitahuan', th: 'ประกาศ' } },
}

// 홈 상단 섹션 라벨 (행동 필요 / 단순 안내)
const SECTION_LABELS: { todo: CategoryLabels; news: CategoryLabels } = {
  todo: { ko: '해야 할 일', en: 'To-do', zh: '待办事项', vi: 'Việc cần làm', ru: 'Нужно сделать', ar: 'مهام مطلوبة', fr: 'À faire', id: 'Perlu dilakukan', th: 'สิ่งที่ต้องทำ' },
  news: { ko: '공지', en: 'Notice', zh: '通知', vi: 'Thông báo', ru: 'Объявление', ar: 'إشعار', fr: 'Annonce', id: 'Pemberitahuan', th: 'ประกาศ' },
}

interface HomeMessages {
  status: { pending: string; processing: string; error: string }
  relative: {
    minutes_ago: string
    hours_ago: string
    days_ago: string
    arrived_suffix: string
  }
  fallback_title: string
}

function statusLabel(status: NoticeStatus, m: HomeMessages): string {
  if (status === 'done') return ''
  return m.status[status] ?? ''
}

function relativeTime(iso: string, m: HomeMessages): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return m.relative.minutes_ago.replace('{n}', String(mins))
  const hours = Math.floor(mins / 60)
  if (hours < 24) return m.relative.hours_ago.replace('{n}', String(hours))
  return m.relative.days_ago.replace('{n}', String(Math.floor(hours / 24)))
}

function jsonObject(value: Json | null | undefined): Record<string, Json | undefined> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : {}
}

function jsonNumber(value: Json | undefined): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function jsonString(value: Json | undefined): string | null {
  return typeof value === 'string' && value.trim() ? value : null
}

function noticeSortTime(row: NoticeRow): number {
  const crawl = jsonObject(row.crawl_result)
  const checkedAt = jsonString(crawl.crawl_checked_at)
  if (checkedAt) {
    return new Date(checkedAt).getTime()
  }
  return new Date(row.created_at).getTime()
}

function crawlPostRank(row: NoticeRow): number {
  const rank = jsonNumber(jsonObject(row.crawl_result).post_rank)
  return rank ?? Number.MAX_SAFE_INTEGER
}

function compareNoticeRows(a: NoticeRow, b: NoticeRow): number {
  const timeDiff = noticeSortTime(b) - noticeSortTime(a)
  if (timeDiff !== 0) return timeDiff

  const rankDiff = crawlPostRank(a) - crawlPostRank(b)
  if (rankDiff !== 0) return rankDiff

  return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
}

function dominantCardType(cards: { type: string }[]): 'action' | null {
  return cards.some(c => c.type === 'action') ? 'action' : null
}

// 홈 분류는 2가지만 유지한다: action 카드가 있으면 '해야 할 일', 없으면 '공지'.
function isActionRequired(cards: { type: string }[]): boolean {
  return cards.some(c => c.type === 'action')
}

function isoToUtcMs(iso: string): number {
  const [y, m, d] = iso.split('-').map(Number)
  return Date.UTC(y, (m ?? 1) - 1, d ?? 1)
}

function todayKstIso(): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date())
}

/**
 * 연결된 일정(event_date)으로 D-day 칩을 만든다.
 * 지난 날짜는 마감 정보로 부적절하므로 표시하지 않는다(null).
 * 주의: event_date는 '행사일'이며 정확한 '제출 마감일'과 다를 수 있다.
 */
function computeDue(eventDate: string | null | undefined, todayIso: string): { label: string; urgent: boolean } | null {
  if (!eventDate || !/^\d{4}-\d{2}-\d{2}$/.test(eventDate)) return null
  const days = Math.round((isoToUtcMs(eventDate) - isoToUtcMs(todayIso)) / 86400000)
  if (days < 0) return null
  const [, m, d] = eventDate.split('-')
  const md = `${Number(m)}/${Number(d)}`
  const dtag = days === 0 ? 'D-DAY' : `D-${days}`
  return { label: `${dtag} · ${md}`, urgent: days <= 3 }
}

export default async function HomePage() {
  const cookieStore = await cookies()
  const cookieLocale = cookieStore.get('locale')?.value
  const locale: Locale = isValidLocale(cookieLocale) ? cookieLocale : defaultLocale
  const messages = (await import(`@/messages/${locale}.json`)).default
  const homeMsg: HomeMessages = {
    status: {
      pending: messages.home.status_pending,
      processing: messages.home.status_processing,
      error: messages.home.status_error,
    },
    relative: {
      minutes_ago: messages.home.minutes_ago,
      hours_ago: messages.home.hours_ago,
      days_ago: messages.home.days_ago,
      arrived_suffix: messages.home.arrived_suffix,
    },
    fallback_title: messages.home.fallback_title,
  }

  let childInfo = ''
  let notices: DisplayNotice[] = []
  let schoolCrawlerState: SchoolCrawlerState | null = null
  let hasProcessingNotices = false

  const viewer = await getViewer()
  if (!viewer) {
    redirect('/login')
  }
  const supabase = viewer.supabase

  const child = await viewer.latestChild()

  if (!child) {
    redirect('/onboarding')
  }

  childInfo = `${child.name} · ${child.school_name} ${child.grade}-${child.class_no ?? ''}`

  // 시연 방문자는 자녀 행이 DB 에 없어 «내 자녀 학교» 조회가 성립하지 않는다 — 수집 상태 배너는 생략한다.
  const schoolPromise = child.school_id && viewer.userId
    ? getSchoolSummary(viewer.userId, child.school_id)
    : Promise.resolve(null)

  const hiddenRowsPromise = viewer.userId
    ? getHiddenNoticeIds(viewer.userId)
    : readDemoHiddenNoticeIds()

  const schoolRowsQuery = child.school_id
    ? supabase
        .from('notices')
        .select('id, status, title, due_date, extracted_content, crawl_result, created_at')
        .eq('school_id', child.school_id)
        .eq('status', 'done')
    : null
  const schoolRowsPromise = schoolRowsQuery
    ? schoolRowsQuery.order('created_at', { ascending: false }).limit(viewer.demo ? DEMO_NOTICE_LIMIT : 50)
    : Promise.resolve({ data: [] })

  const schoolProcessingCountQuery = child.school_id
    ? supabase
        .from('notices')
        .select('id', { count: 'exact', head: true })
        .eq('school_id', child.school_id)
        .in('status', ['pending', 'processing'])
    : null
  const schoolProcessingCountPromise = schoolProcessingCountQuery
    ? schoolProcessingCountQuery
    : Promise.resolve({ count: 0 })

  const [
    school,
    hiddenNoticeIds,
    { data: schoolRows },
    { count: schoolProcessingCount },
  ] = await Promise.all([
    schoolPromise,
    hiddenRowsPromise,
    schoolRowsPromise,
    schoolProcessingCountPromise,
  ])

  schoolCrawlerState = school
  const hiddenIds = new Set(hiddenNoticeIds)

  hasProcessingNotices = Boolean(schoolProcessingCount ?? 0)

  const rowMap = new Map<string, NoticeRow>()
  for (const row of schoolRows ?? []) {
    if (!hiddenIds.has(row.id)) {
      rowMap.set(row.id, row as NoticeRow)
    }
  }
  const rows = Array.from(rowMap.values()).sort(compareNoticeRows)

  if (rows && rows.length > 0) {
    const noticeIds = rows.map(r => r.id)
    const translationsPromise = supabase
      .from('notice_ai_translations')
      .select('notice_id, target_language, translated_title, translated_text')
      .in('notice_id', noticeIds)
      .in('target_language', [locale, 'ko'])

    const cardsPromise = supabase
      .from('notice_cards')
      .select('notice_id, type, id')
      .in('notice_id', noticeIds)

    // 공지별 D-day용 날짜: 연결된 학교 일정(school_events) 중 오늘 이후 가장 가까운 event_date.
    // event_date가 없으면 칩은 표시하지 않는다(안전).
    const todayIso = todayKstIso()
    const dueByNotice: Record<string, string> = {}
    for (const row of rows) {
      if (row.due_date && /^\d{4}-\d{2}-\d{2}$/.test(row.due_date)) {
        dueByNotice[row.id] = row.due_date
      }
    }
    const schoolEventsPromise = child.school_id
      ? supabase
          .from('school_events')
          .select('notice_id, event_date')
          .eq('school_id', child.school_id)
          .in('notice_id', noticeIds)
          .gte('event_date', todayIso)
          .order('event_date', { ascending: true })
      : Promise.resolve({ data: [] })

    const [
      { data: translations },
      { data: cards },
      { data: schoolEventRows },
    ] = await Promise.all([
      translationsPromise,
      cardsPromise,
      schoolEventsPromise,
    ])

    const translationsByNotice: Record<string, { [locale: string]: string }> = {}
    const translatedTitlesByNotice: Record<string, { [locale: string]: string }> = {}
    for (const t of translations ?? []) {
      if (t.notice_id && t.target_language && t.translated_text) {
        ;(translationsByNotice[t.notice_id] ??= {})[t.target_language] = t.translated_text
      }
      if (t.notice_id && t.target_language && t.translated_title) {
        ;(translatedTitlesByNotice[t.notice_id] ??= {})[t.target_language] = t.translated_title
      }
    }

    const cardsByNotice: Record<string, { type: string }[]> = {}
    const cardIdToNotice: Record<string, string> = {}
    for (const c of cards ?? []) {
      ;(cardsByNotice[c.notice_id] ??= []).push({ type: c.type })
      if (c.id) cardIdToNotice[c.id] = c.notice_id
    }

    // 홈 '번역 완료' 기준을 상세(lib/notices.ts hasLocaleTranslation)와 통일:
    // 본문뿐 아니라 카드까지 번역돼야 완료로 본다. 공지별 번역된 카드 수를 집계한다.
    const translatedCardCountByNotice: Record<string, number> = {}
    if (locale !== 'ko') {
      const allCardIds = Object.keys(cardIdToNotice)
      if (allCardIds.length > 0) {
        const { data: cardTranslationRows } = await supabase
          .from('notice_card_translations')
          .select('notice_card_id')
          .eq('target_language', locale)
          .in('notice_card_id', allCardIds)
        for (const ct of cardTranslationRows ?? []) {
          const nId = cardIdToNotice[ct.notice_card_id]
          if (nId) translatedCardCountByNotice[nId] = (translatedCardCountByNotice[nId] ?? 0) + 1
        }
      }
    }

    for (const s of schoolEventRows ?? []) {
      if (s.notice_id && s.event_date && !dueByNotice[s.notice_id]) {
        dueByNotice[s.notice_id] = s.event_date
      }
    }

    notices = rows.map(row => {
      const noticeCards = cardsByNotice[row.id] ?? []
      const due = computeDue(dueByNotice[row.id], todayIso)
      return {
        id: row.id,
        cardType: dominantCardType(noticeCards),
        title: pickNoticeDisplayTitle(
          { ...(row as NoticeRow), translated_titles: translatedTitlesByNotice[row.id] ?? {} },
          locale,
          homeMsg.fallback_title,
        ),
        status: row.status,
        arrivedAt: relativeTime(row.created_at, homeMsg),
        // 시연 방문자는 번역을 새로 시키지 않는다(로그인이 없어 서버가 요청을 거절하고,
        // 사람마다 번역 비용이 생긴다). 미리 만들어 둔 번역만 보여준다.
        needsTranslation: !viewer.demo && locale !== 'ko'
          && (
            !translationsByNotice[row.id]?.[locale]
            || (noticeCards.length > 0 && (translatedCardCountByNotice[row.id] ?? 0) < noticeCards.length)
          ),
        actionRequired: isActionRequired(noticeCards),
        dueLabel: due?.label ?? null,
        dueUrgent: due?.urgent ?? false,
      }
    })
  }

  const shouldCollectSchoolNotices = schoolCrawlerState ? schoolNeedsInitialCrawl(schoolCrawlerState) : false
  // 시연에서는 5초마다 화면을 새로 고치지 않는다 — 밀린 공지가 있는 학교(동인천중 2건)를 고른
  // 모든 방문자가 계속 새로 고치게 된다.
  const isPreparingSchoolNotices = !viewer.demo && (shouldCollectSchoolNotices || hasProcessingNotices)

  const actionNotices = notices.filter(n => n.actionRequired)
  const infoNotices = notices.filter(n => !n.actionRequired)
  const todoTitle = SECTION_LABELS.todo[locale] ?? SECTION_LABELS.todo.ko
  const newsTitle = SECTION_LABELS.news[locale] ?? SECTION_LABELS.news.ko

  const mapNoticeForClient = (notice: DisplayNotice) => {
    const badge = BADGE[notice.cardType ?? 'null']
    const badgeLabel = badge.label[locale] ?? badge.label.ko
    return {
      id: notice.id,
      accentBar: badge.bar,
      badgeBg: badge.bg,
      badgeText: badge.text,
      badgeLabel,
      title: notice.title,
      statusLabel: notice.status !== 'done' ? statusLabel(notice.status, homeMsg) : '',
      arrivedAt: notice.arrivedAt,
      arrivedSuffix: homeMsg.relative.arrived_suffix,
      dueLabel: notice.dueLabel,
      dueUrgent: notice.dueUrgent,
      deleteLabel: messages.home.delete ?? '삭제',
      confirmTitle: messages.home.hide_confirm_title ?? messages.home.delete_confirm_title ?? '이 공지를 숨길까요?',
      confirmBody: messages.home.hide_confirm_body,
      confirmCancel: messages.common.cancel ?? '취소',
      confirmDelete: messages.home.delete ?? '삭제',
      deletingLabel: messages.home.deleting ?? '삭제 중...',
      translationPending: notice.needsTranslation,
    }
  }

  return (
    <main className="flex flex-col min-h-screen pb-24">
      <HomePoller
        active={isPreparingSchoolNotices}
        loadingLabel={messages.common.loading ?? 'Loading...'}
      />
      <NoticeTranslationKickoff
        locale={locale}
        noticeIds={viewer.demo ? [] : notices.filter(notice => notice.needsTranslation).map(notice => notice.id)}
      />
      <BrandHeader
        title={messages.common.app_name}
        subtitle={childInfo}
        character="readingPaper"
        rightSlot={
          <Link
            href="/settings"
            aria-label={messages.nav.settings}
            className="w-10 h-10 flex items-center justify-center rounded-full bg-surface/70 active:bg-surface"
          >
            <SettingsIcon />
          </Link>
        }
      />

      <section className="px-6 pt-6 flex flex-col gap-7">
        {notices.length === 0 ? (
          isPreparingSchoolNotices ? (
            <CharacterEmptyState
              character="standingPaper"
              title={messages.home.crawl_collecting ?? '학교 공지를 가져오는 중이에요.'}
              action={
                schoolCrawlerState ? <SchoolCrawlerKickoff schoolId={schoolCrawlerState.id} /> : undefined
              }
            />
          ) : (
            <CharacterEmptyState
              character="readingBlue"
              title={messages.home.no_notices}
            />
          )
        ) : (
          <>
            {isPreparingSchoolNotices && schoolCrawlerState ? (
              <SchoolCrawlerKickoff schoolId={schoolCrawlerState.id} showFailure={false} />
            ) : null}

            <HomeNoticeSections
              todoTitle={todoTitle}
              newsTitle={newsTitle}
              translationProcessingLabel={messages.home.status_processing ?? '처리 중'}
              actionNotices={actionNotices.map(mapNoticeForClient)}
              infoNotices={infoNotices.map(mapNoticeForClient)}
            />
          </>
        )}
      </section>
    </main>
  )
}

function SettingsIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="#2B211C" aria-hidden="true">
      <path d="M19.14 12.94c.04-.3.06-.61.06-.94s-.02-.64-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.49.49 0 0 0-.59-.22l-2.39.96a7.02 7.02 0 0 0-1.62-.94l-.36-2.54A.484.484 0 0 0 14 4h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96a.48.48 0 0 0-.59.22L2.74 8.87a.48.48 0 0 0 .12.61l2.03 1.58c-.05.3-.07.62-.07.94s.02.64.07.94l-2.03 1.58a.49.49 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.37 1.04.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.57 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32a.49.49 0 0 0-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/>
    </svg>
  )
}
