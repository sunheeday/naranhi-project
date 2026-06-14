import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import { isValidLocale, type Locale, defaultLocale } from '@/lib/i18n'
import { createSupabaseServerClient, createSupabaseServiceClient } from '@/lib/supabase/server'
import { getChildrenForUser } from '@/lib/server-cache'
import { ensureTestBypassChildren, isTestEntryBypassEnabled } from '@/lib/test-entry-bypass'
import { backfillSchoolEventsForSchools } from '@/lib/schedule-backfill'
import { isUiPreviewEnabled } from '@/lib/ui-preview'
import {
  fetchTimetableRangeFromNeis,
  UnsupportedTimetableError,
  type TimetablePeriod,
} from '@/lib/neis'
import { pickNoticeDisplayTitle } from '@/lib/notice-title'
import BrandHeader from '@/components/brand/BrandHeader'
import NoticeTranslationKickoff from '../NoticeTranslationKickoff'
import CalendarTabs from './CalendarTabs'
import { type ScheduleEvent } from './CalendarView'
import { type TimetableDayEntry } from './TimetableWeekView'
import { translateTimetableDays } from '@/lib/subject-translation'

interface Props {
  searchParams: Promise<{ week?: string; tab?: string }>
}

function isoParts(iso: string): { weekday: number; ms: number } {
  const [y, m, d] = iso.split('-').map(Number)
  const ms = Date.UTC(y, m - 1, d)
  return { weekday: new Date(ms).getUTCDay(), ms }
}

function msToIso(ms: number): string {
  const dt = new Date(ms)
  const yy = dt.getUTCFullYear()
  const mm = String(dt.getUTCMonth() + 1).padStart(2, '0')
  const dd = String(dt.getUTCDate()).padStart(2, '0')
  return `${yy}-${mm}-${dd}`
}

function startOfWeekMonday(iso: string): string {
  const { weekday, ms } = isoParts(iso)
  const diff = weekday === 0 ? -6 : 1 - weekday
  return msToIso(ms + diff * 86400000)
}

function addDaysIso(iso: string, days: number): string {
  const { ms } = isoParts(iso)
  return msToIso(ms + days * 86400000)
}

function todayKstIso(): string {
  const fmt = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })
  return fmt.format(new Date())
}

export default async function CalendarPage({ searchParams }: Props) {
  const cookieStore = await cookies()
  const cookieLocale = cookieStore.get('locale')?.value
  const locale: Locale = isValidLocale(cookieLocale) ? cookieLocale : defaultLocale
  const messages = (await import(`@/messages/${locale}.json`)).default
  const params = await searchParams

  const now = new Date()
  const year = now.getFullYear()
  const month = now.getMonth() + 1
  const todayIso = todayKstIso()
  const baseIso = params.week && /^\d{4}-\d{2}-\d{2}$/.test(params.week) ? params.week : todayIso
  const monday = startOfWeekMonday(baseIso)
  const friday = addDaysIso(monday, 4)

  // 현재 월 ±2달 범위 (총 5개월) 조회
  const fromYear = month <= 2 ? year - 1 : year
  const fromMonth = ((month - 3 + 12) % 12) + 1
  const toYear = month >= 11 ? year + 1 : year
  const toMonth = ((month + 2) % 12) + 1
  const from = `${fromYear}-${String(fromMonth).padStart(2, '0')}-01`
  const to = `${toYear}-${String(toMonth).padStart(2, '0')}-01`

  let events: ScheduleEvent[] = []
  let errorMessage: string | null = null
  let timetableDays: TimetableDayEntry[] = buildTimetableDays(monday, [])
  let timetableUnsupported = false
  let timetableErrorMessage: string | null = null
  let childLabel = ''
  let pendingTranslationNoticeIds: string[] = []

  if (await isUiPreviewEnabled()) {
    events = previewEvents(year, month)
    timetableDays = await translateTimetableDays(previewTimetableEntries(monday), locale)
    childLabel = '나란히초등학교 3-2'
  } else {
    const testEntryBypass = isTestEntryBypassEnabled()
    const supabase = testEntryBypass
      ? createSupabaseServiceClient()
      : await createSupabaseServerClient()
    const { data: { user } } = testEntryBypass
      ? { data: { user: null } }
      : await supabase.auth.getUser()
    if (!user && !testEntryBypass) redirect('/login')

    try {
      const children = testEntryBypass
        ? await ensureTestBypassChildren()
        : await getChildrenForUser(user!.id)

      const schoolIds = Array.from(new Set((children ?? []).map(child => child.school_id).filter(Boolean))) as string[]
      const child = children?.[0] ?? null
      if (child) {
        childLabel = `${child.school_name} ${child.grade}-${child.class_no ?? ''}`
      }

      if (schoolIds.length > 0) {
        let { data: rows, error } = await supabase
          .from('school_events')
          .select('id, notice_id, title, event_date, event_kinds, location, description')
          .in('school_id', schoolIds)
          .gte('event_date', from)
          .lt('event_date', to)
          .order('event_date', { ascending: true })

        if (error) throw error

        if ((rows ?? []).length === 0) {
          const serviceClient = createSupabaseServiceClient()
          await backfillSchoolEventsForSchools({
            serviceClient,
            schoolIds,
            preferredLocale: locale,
          })

          const retry = await supabase
            .from('school_events')
            .select('id, notice_id, title, event_date, event_kinds, location, description')
            .in('school_id', schoolIds)
            .gte('event_date', from)
            .lt('event_date', to)
            .order('event_date', { ascending: true })

          if (retry.error) throw retry.error
          rows = retry.data
        }

        const noticeIds = Array.from(new Set(
          (rows ?? [])
            .map(row => row.notice_id)
            .filter((value): value is string => typeof value === 'string' && value.length > 0),
        ))
        const fallbackTitle = messages.home?.fallback_title ?? messages.notice_detail?.intro_title ?? '공지'
        const noticeRows = noticeIds.length > 0
          ? await supabase
              .from('notices')
              .select('id, title, extracted_content')
              .in('id', noticeIds)
          : { data: [], error: null }
        if (noticeRows.error) throw noticeRows.error

        const translationRows = noticeIds.length > 0
          ? await supabase
              .from('notice_ai_translations')
              .select('notice_id, target_language, translated_title, translated_location, translated_text')
              .in('notice_id', noticeIds)
              .in('target_language', locale === 'ko' ? ['ko'] : [locale, 'ko'])
          : { data: [], error: null }
        if (translationRows.error) throw translationRows.error

        const noticesById = new Map(
          (noticeRows.data ?? []).map(row => [row.id, row] as const),
        )
        const translationsByNotice: Record<string, Record<string, string>> = {}
        const translatedTitlesByNotice: Record<string, Record<string, string>> = {}
        const translatedLocationsByNotice: Record<string, Record<string, string>> = {}
        for (const row of translationRows.data ?? []) {
          if (row.notice_id && row.target_language && row.translated_text) {
            ;(translationsByNotice[row.notice_id] ??= {})[row.target_language] = row.translated_text
          }
          if (row.notice_id && row.target_language && row.translated_title) {
            ;(translatedTitlesByNotice[row.notice_id] ??= {})[row.target_language] = row.translated_title
          }
          if (row.notice_id && row.target_language && row.translated_location) {
            ;(translatedLocationsByNotice[row.notice_id] ??= {})[row.target_language] = row.translated_location
          }
        }

        pendingTranslationNoticeIds = locale === 'ko'
          ? []
          : noticeIds.filter(noticeId => !translationsByNotice[noticeId]?.[locale])

        events = (rows ?? []).map(row => {
          const sourceTitle = noticesById.get(row.notice_id)?.title ?? row.title
          return {
            id: row.id,
            noticeId: row.notice_id,
            title: pickNoticeDisplayTitle(
              {
                title: sourceTitle,
                extracted_content: noticesById.get(row.notice_id)?.extracted_content ?? null,
                translated_titles: translatedTitlesByNotice[row.notice_id] ?? {},
              },
              locale,
              fallbackTitle,
            ),
            sourceTitle,
            eventDate: row.event_date,
            eventKinds: parseEventKinds(row.event_kinds),
            location: translatedLocationsByNotice[row.notice_id]?.[locale] ?? row.location,
            description: row.description,
          }
        })
      }

      if (!child?.neis_office_code || !child.neis_school_code || !child.class_no) {
        timetableUnsupported = true
      } else {
        try {
          const periods = await fetchTimetableRangeFromNeis(
            child.neis_office_code,
            child.neis_school_code,
            child.school_name,
            child.grade,
            child.class_no,
            monday.replace(/-/g, ''),
            friday.replace(/-/g, ''),
          )
          timetableDays = await translateTimetableDays(
            buildTimetableDays(monday, periods),
            locale,
            createSupabaseServiceClient(),
          )
        } catch (e) {
          if (e instanceof UnsupportedTimetableError) {
            timetableUnsupported = true
          } else {
            console.error('[calendar] timetable fetch failed:', e instanceof Error ? e.message : e)
            timetableErrorMessage = messages.calendar.timetable_error ?? messages.meals?.timetable_error ?? '수업 정보를 불러오지 못했어요.'
          }
        }
      }
    } catch (e) {
      console.error('[calendar] schedule fetch failed:', e instanceof Error ? e.message : e)
      errorMessage = messages.calendar.gcal_error ?? '일정을 불러오지 못했어요.'
    }
  }

  return (
    <main className="flex flex-col min-h-screen pb-20">
      <NoticeTranslationKickoff locale={locale} noticeIds={pendingTranslationNoticeIds} />
      <BrandHeader title={messages.calendar.title} subtitle={childLabel || undefined} character="walk" />

      {errorMessage && (
        <div role="alert" className="mx-6 mt-4 rounded-card border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          {errorMessage}
        </div>
      )}

      {timetableErrorMessage && (
        <div role="alert" className="mx-6 mt-4 rounded-card border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          {timetableErrorMessage}
        </div>
      )}

      <CalendarTabs
        activeTab={params.tab === 'classes' ? 'classes' : 'events'}
        eventTabLabel={messages.calendar.event_tab ?? messages.calendar.title}
        timetableTabLabel={messages.calendar.timetable_tab ?? messages.meals?.timetable_tab ?? '수업'}
        events={events}
        initialYear={year}
        initialMonth={month}
        calendarLabels={{
          noEventsLabel: messages.calendar.no_events,
          monthYearLabel: messages.calendar.month_year,
          weekdays: messages.calendar.weekdays,
          prevMonthLabel: messages.calendar.prev_month,
          nextMonthLabel: messages.calendar.next_month,
          monthEventsTitle: messages.calendar.month_events_title,
          daySheetTitle: messages.calendar.day_sheet_title,
          closeLabel: messages.common.close,
          eventKindLabels: {
            event: messages.notice_detail.schedule_badge,
            deadline: messages.notice_detail.action_badge,
          },
        }}
        weekStartIso={monday}
        timetableDays={timetableDays}
        timetableUnsupported={timetableUnsupported}
        timetableLabels={{
          weekdays: messages.calendar.weekdays,
          prevWeek: messages.calendar.prev_week ?? messages.meals?.prev_week ?? '이전 주',
          nextWeek: messages.calendar.next_week ?? messages.meals?.next_week ?? '다음 주',
          range: messages.calendar.week_range ?? messages.meals?.range ?? '{startMonth}/{startDay} – {endMonth}/{endDay}',
          today: messages.calendar.today,
          noTimetable: messages.calendar.no_timetable ?? messages.meals?.no_timetable ?? '수업 정보 없음',
          periodSuffix: messages.calendar.period_suffix ?? messages.meals?.period_suffix ?? '{period}교시',
          unsupported: messages.calendar.timetable_unsupported ?? messages.meals?.timetable_unsupported ?? '학년/반 또는 학교 종류가 맞지 않아 수업 정보를 표시할 수 없어요.',
        }}
      />
    </main>
  )
}

function buildTimetableDays(monday: string, periods: TimetablePeriod[]): TimetableDayEntry[] {
  const byDate = new Map<string, TimetablePeriod[]>()
  for (const period of periods) {
    const list = byDate.get(period.date) ?? []
    list.push(period)
    byDate.set(period.date, list)
  }

  const days: TimetableDayEntry[] = []
  for (let i = 0; i < 5; i++) {
    const iso = addDaysIso(monday, i)
    days.push({
      isoDate: iso,
      periods: (byDate.get(iso) ?? []).sort((a, b) => a.period - b.period),
    })
  }
  return days
}

function previewEvents(year: number, month: number): ScheduleEvent[] {
  const base = `${year}-${String(month).padStart(2, '0')}`

  return [
    {
      id: 'preview-calendar-1',
      noticeId: 'preview-action',
      title: '체험학습 동의서 제출',
      eventDate: `${base}-08`,
      eventKinds: ['deadline'],
      location: '각 반 교실',
      description: '체험학습 동의서 제출 마감일',
    },
    {
      id: 'preview-calendar-2',
      noticeId: 'preview-schedule',
      title: '학부모 상담주간',
      eventDate: `${base}-14`,
      eventKinds: ['event'],
      location: '상담실',
      description: '학부모 상담 일정',
    },
    {
      id: 'preview-calendar-3',
      noticeId: 'preview-supplies',
      title: '봄 소풍',
      eventDate: `${base}-21`,
      eventKinds: ['event'],
      location: '서울숲',
      description: '봄 소풍 행사일',
    },
  ]
}

function parseEventKinds(value: unknown): ('event' | 'deadline')[] {
  if (!Array.isArray(value)) return ['event']
  const kinds = value.filter((item): item is 'event' | 'deadline' => item === 'event' || item === 'deadline')
  return kinds.length > 0 ? kinds : ['event']
}

function previewTimetableEntries(monday: string): TimetableDayEntry[] {
  const subjects = [
    ['국어', '수학', '과학', '체육', '음악'],
    ['영어', '국어', '미술', '수학', '창체'],
    ['사회', '과학', '영어', '도덕'],
    ['수학', '국어', '체육', '사회', '미술'],
    ['과학', '음악', '영어', '국어'],
  ]

  return subjects.map((daySubjects, dayIndex) => ({
    isoDate: addDaysIso(monday, dayIndex),
    periods: daySubjects.map((subject, index) => ({
      date: addDaysIso(monday, dayIndex),
      period: index + 1,
      subject,
      grade: 3,
      className: '2',
      classroom: null,
    })),
  }))
}
