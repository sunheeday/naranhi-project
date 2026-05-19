import Link from 'next/link'
import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import { isValidLocale, type Locale, defaultLocale } from '@/lib/i18n'
import { createSupabaseServerClient } from '@/lib/supabase/server'
import { isUiPreviewEnabled, previewChildInfo } from '@/lib/ui-preview'
import type { Json, NoticeSource, NoticeStatus } from '@/types/database'
import { schoolNeedsInitialCrawl, type SchoolCrawlerState } from '@/lib/school-crawler-trigger'
import HomePoller from './HomePoller'
import NoticeCardItem from './NoticeCardItem'
import SchoolCrawlerKickoff from './SchoolCrawlerKickoff'

interface NoticeRow {
  id: string
  status: NoticeStatus
  source: NoticeSource
  title: string | null
  summary_translations: { [locale: string]: string }
  crawl_result: Json
  created_at: string
  notice_cards: { type: string }[]
}

interface DisplayNotice {
  id: string
  cardType: 'supplies' | 'action' | 'schedule' | null
  title: string
  status: NoticeStatus
  source: NoticeSource
  arrivedAt: string
}

type CategoryLabels = Record<Locale, string>
const BADGE: Record<'supplies' | 'action' | 'schedule' | 'null', { bar: string; bg: string; text: string; label: CategoryLabels }> = {
  supplies: { bar: 'bg-cat-supply',   bg: 'bg-cat-supply-bg',   text: 'text-cat-supply',
    label: { ko: '준비물', en: 'Supplies', zh: '准备物品', vi: 'Đồ dùng', ru: 'Принадлежности', ar: 'المستلزمات', fr: 'Fournitures', id: 'Perlengkapan', th: 'อุปกรณ์' } },
  action:   { bar: 'bg-cat-action',   bg: 'bg-cat-action-bg',   text: 'text-cat-action',
    label: { ko: '해야 할 일', en: 'To-do', zh: '待办事项', vi: 'Việc cần làm', ru: 'Дела', ar: 'المهام', fr: 'À faire', id: 'Tugas', th: 'งานที่ต้องทำ' } },
  schedule: { bar: 'bg-cat-schedule', bg: 'bg-cat-schedule-bg', text: 'text-cat-schedule',
    label: { ko: '일정', en: 'Schedule', zh: '日程', vi: 'Lịch', ru: 'Расписание', ar: 'الجدول', fr: 'Planning', id: 'Jadwal', th: 'ตารางเวลา' } },
  null:     { bar: 'bg-ink',          bg: 'bg-surface-card',    text: 'text-ink',
    label: { ko: '공지', en: 'Notice', zh: '通知', vi: 'Thông báo', ru: 'Объявление', ar: 'إشعار', fr: 'Annonce', id: 'Pemberitahuan', th: 'ประกาศ' } },
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

function jsonObject(value: Json | null | undefined): Record<string, Json> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : {}
}

function jsonNumber(value: Json | undefined): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function jsonString(value: Json | undefined): string | null {
  return typeof value === 'string' && value.trim() ? value : null
}

function noticeSortTime(row: NoticeRow): number {
  if (row.source === 'crawl') {
    const crawl = jsonObject(row.crawl_result)
    const checkedAt = jsonString(crawl.crawl_checked_at)
    if (checkedAt) {
      return new Date(checkedAt).getTime()
    }
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

  if (a.source === 'crawl' && b.source === 'crawl') {
    const rankDiff = crawlPostRank(a) - crawlPostRank(b)
    if (rankDiff !== 0) return rankDiff
  }

  return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
}

function pickTitle(row: NoticeRow, locale: Locale, m: HomeMessages): string {
  // 1순위: 사용자 locale로 lazy 번역돼 캐시된 summary의 첫 줄
  //        (사용자가 한 번이라도 그 공지에 진입했으면 캐시 적중)
  const t = row.summary_translations ?? {}
  const localized = t[locale]?.trim()
  if (localized) return localized.split('\n')[0].slice(0, 40)

  // 2순위: 한국어 title (Gemini가 만든 짧은 제목, 한국어)
  if (row.title && row.title.trim()) return row.title.trim().slice(0, 60)

  // 3순위: ko summary 첫 줄
  const ko = (t.ko ?? '').trim()
  return ko.split('\n')[0].slice(0, 40) || m.fallback_title
}

function dominantCardType(cards: { type: string }[]): 'supplies' | 'action' | 'schedule' | null {
  // 홈 badge는 행동 힌트용 3가지 type만 사용한다. summary는 상세 화면에서만 표시한다.
  const order: Array<'action' | 'schedule' | 'supplies'> = ['action', 'schedule', 'supplies']
  for (const t of order) {
    if (cards.some(c => c.type === t)) return t
  }
  return null
}

function previewNotices(): DisplayNotice[] {
  return [
    {
      id: 'preview-action',
      cardType: 'action',
      title: '현장체험학습 참가 동의서 제출',
      status: 'done',
      source: 'manual',
      arrivedAt: '12분 전',
    },
    {
      id: 'preview-supplies',
      cardType: 'supplies',
      title: '봄 소풍 준비물 안내',
      status: 'done',
      source: 'manual',
      arrivedAt: '2시간 전',
    },
    {
      id: 'preview-schedule',
      cardType: 'schedule',
      title: '학부모 상담주간 일정 안내',
      status: 'processing',
      source: 'manual',
      arrivedAt: '어제',
    },
  ]
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

  if (isUiPreviewEnabled()) {
    childInfo = previewChildInfo()
    notices = previewNotices()
  } else {
    const supabase = await createSupabaseServerClient()
    const { data: { user } } = await supabase.auth.getUser()

    if (!user) {
      redirect('/login')
    }

    const { data: child } = await supabase
      .from('children')
      .select('id, school_id, name, school_name, grade, class_no')
      .eq('user_id', user.id)
      .order('created_at', { ascending: false })
      .limit(1)
      .maybeSingle()

    if (!child) {
      redirect('/onboarding')
    }

    childInfo = `${child.name} · ${child.school_name} ${child.grade}-${child.class_no ?? ''}`

    if (child.school_id) {
      const { data: school } = await supabase
        .from('schools')
        .select('id,crawl_status,crawl_board_url,crawl_last_checked_at')
        .eq('id', child.school_id)
        .maybeSingle()
      schoolCrawlerState = school
    }

    const { data: hiddenRows } = await supabase
      .from('notice_hides')
      .select('notice_id')
      .eq('user_id', user.id)
    const hiddenIds = new Set((hiddenRows ?? []).map(row => row.notice_id))

    const { data: personalRows } = await supabase
      .from('notices')
      .select('id, source, status, title, summary_translations, crawl_result, created_at')
      .eq('child_id', child.id)
      .eq('status', 'done')
      .order('created_at', { ascending: false })
      .limit(50)

    const { data: schoolRows } = child.school_id
      ? await supabase
          .from('notices')
          .select('id, source, status, title, summary_translations, crawl_result, created_at')
          .eq('school_id', child.school_id)
          .eq('source', 'crawl')
          .eq('status', 'done')
          .order('created_at', { ascending: false })
          .limit(50)
      : { data: [] }

    const { count: personalProcessingCount } = await supabase
      .from('notices')
      .select('id', { count: 'exact', head: true })
      .eq('child_id', child.id)
      .in('status', ['pending', 'processing'])

    const { count: schoolProcessingCount } = child.school_id
      ? await supabase
          .from('notices')
          .select('id', { count: 'exact', head: true })
          .eq('school_id', child.school_id)
          .eq('source', 'crawl')
          .in('status', ['pending', 'processing'])
      : { count: 0 }

    hasProcessingNotices = Boolean((personalProcessingCount ?? 0) + (schoolProcessingCount ?? 0))

    const rowMap = new Map<string, NoticeRow>()
    for (const row of [...(personalRows ?? []), ...(schoolRows ?? [])]) {
      if (!hiddenIds.has(row.id)) {
        rowMap.set(row.id, row as NoticeRow)
      }
    }
    const rows = Array.from(rowMap.values()).sort(compareNoticeRows)

    if (rows && rows.length > 0) {
      const noticeIds = rows.map(r => r.id)
      const { data: cards } = await supabase
        .from('notice_cards')
        .select('notice_id, type')
        .in('notice_id', noticeIds)

      const cardsByNotice: Record<string, { type: string }[]> = {}
      for (const c of cards ?? []) {
        ;(cardsByNotice[c.notice_id] ??= []).push({ type: c.type })
      }

      notices = rows.map(row => ({
        id: row.id,
        cardType: dominantCardType(cardsByNotice[row.id] ?? []),
        title: pickTitle(row as NoticeRow, locale, homeMsg),
        status: row.status,
        source: row.source,
        arrivedAt: relativeTime(row.created_at, homeMsg),
      }))
    }
  }

  const shouldCollectSchoolNotices = schoolCrawlerState ? schoolNeedsInitialCrawl(schoolCrawlerState) : false
  const isPreparingSchoolNotices = shouldCollectSchoolNotices || hasProcessingNotices

  return (
    <main className="flex flex-col min-h-screen pb-24">
      <HomePoller hasPending={hasProcessingNotices} />
      <header className="sticky top-0 bg-canvas border-b border-hairline-soft px-6 py-4 flex items-center justify-between z-10">
        <div className="min-w-0">
          <span className="block text-base font-bold text-ink truncate" style={{ letterSpacing: '-0.01em' }}>{messages.common.app_name}</span>
          <p className="text-xs text-muted truncate mt-0.5">{childInfo}</p>
        </div>
        <Link
          href="/settings"
          aria-label={messages.nav.settings}
          className="w-10 h-10 flex items-center justify-center rounded-full active:bg-surface-card"
        >
          <SettingsIcon />
        </Link>
      </header>

      <section className="px-6 pt-6">
        <p className="text-xs font-medium text-muted-soft uppercase tracking-wide mb-3">{messages.home.notices_title}</p>

        {notices.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 gap-3">
            <span className="text-3xl" aria-hidden="true">📭</span>
            <p className="text-sm text-muted-soft text-center">
              {isPreparingSchoolNotices
                ? messages.home.crawl_collecting ?? '학교 공지를 가져오는 중이에요.'
                : messages.home.no_notices}
            </p>
            {isPreparingSchoolNotices && schoolCrawlerState ? (
              <SchoolCrawlerKickoff schoolId={schoolCrawlerState.id} />
            ) : null}
          </div>
        ) : (
          <>
            {isPreparingSchoolNotices && schoolCrawlerState ? (
              <SchoolCrawlerKickoff schoolId={schoolCrawlerState.id} showFailure={false} />
            ) : null}
            <ul className="flex flex-col gap-3">
              {notices.map(notice => {
                const badge = BADGE[notice.cardType ?? 'null']
                const badgeLabel = badge.label[locale] ?? badge.label.ko
                return (
                  <li key={notice.id}>
                    <NoticeCardItem
                      noticeId={notice.id}
                      title={notice.title}
                      statusLabel={notice.status !== 'done' ? statusLabel(notice.status, homeMsg) : ''}
                      arrivedAt={notice.arrivedAt}
                      arrivedSuffix={homeMsg.relative.arrived_suffix}
                      accentBar={badge.bar}
                      badgeBg={badge.bg}
                      badgeText={badge.text}
                      badgeLabel={badgeLabel}
                      deleteLabel={messages.home.delete ?? '삭제'}
                      confirmTitle={
                        notice.source === 'crawl'
                          ? messages.home.hide_confirm_title ?? messages.home.delete_confirm_title ?? '이 공지를 숨길까요?'
                          : messages.home.delete_confirm_title ?? '이 공지를 삭제할까요?'
                      }
                      confirmBody={
                        notice.source === 'crawl'
                          ? messages.home.hide_confirm_body
                          : messages.home.delete_confirm_body ?? '삭제하면 복구할 수 없어요.'
                      }
                      confirmCancel={messages.common.cancel ?? '취소'}
                      confirmDelete={messages.home.delete ?? '삭제'}
                      deletingLabel={messages.home.deleting ?? '삭제 중...'}
                    />
                  </li>
                )
              })}
            </ul>
          </>
        )}
      </section>
    </main>
  )
}

function SettingsIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="#111111" aria-hidden="true">
      <path d="M19.14 12.94c.04-.3.06-.61.06-.94s-.02-.64-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.49.49 0 0 0-.59-.22l-2.39.96a7.02 7.02 0 0 0-1.62-.94l-.36-2.54A.484.484 0 0 0 14 4h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96a.48.48 0 0 0-.59.22L2.74 8.87a.48.48 0 0 0 .12.61l2.03 1.58c-.05.3-.07.62-.07.94s.02.64.07.94l-2.03 1.58a.49.49 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.37 1.04.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.57 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32a.49.49 0 0 0-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/>
    </svg>
  )
}
