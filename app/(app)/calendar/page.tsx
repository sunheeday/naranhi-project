import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import { isValidLocale, type Locale, defaultLocale } from '@/lib/i18n'
import { createSupabaseServerClient } from '@/lib/supabase/server'
import { isUiPreviewEnabled } from '@/lib/ui-preview'
import {
  fetchTimetableRangeFromNeis,
  UnsupportedTimetableError,
  type TimetablePeriod,
} from '@/lib/neis'
import CalendarTabs from './CalendarTabs'
import { type ScheduleEvent } from './CalendarView'
import { type TimetableDayEntry } from './TimetableWeekView'

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

  if (isUiPreviewEnabled()) {
    events = previewEvents(year, month)
    timetableDays = previewTimetableEntries(monday)
    childLabel = '나란히초등학교 3-2'
  } else {
    const supabase = await createSupabaseServerClient()
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) redirect('/login')

    try {
      const { data: children } = await supabase
        .from('children')
        .select('id, school_name, grade, class_no, neis_office_code, neis_school_code')
        .eq('user_id', user.id)
        .order('created_at', { ascending: false })

      const childIds = (children ?? []).map(child => child.id)
      const child = children?.[0] ?? null
      if (child) {
        childLabel = `${child.school_name} ${child.grade}-${child.class_no ?? ''}`
      }

      if (childIds.length > 0) {
        const { data: rows, error } = await supabase
          .from('schedules')
          .select('id, notice_id, title, event_date, location')
          .in('child_id', childIds)
          .gte('event_date', from)
          .lt('event_date', to)
          .order('event_date', { ascending: true })

        if (error) throw error

        events = (rows ?? []).map(row => ({
          id: row.id,
          noticeId: row.notice_id,
          title: row.title,
          eventDate: row.event_date,
          location: row.location,
          cardType: 'schedule',
        }))
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
          timetableDays = buildTimetableDays(monday, periods)
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
      <header className="sticky top-0 bg-surface border-b border-border px-6 py-4 z-10">
        <h1 className="text-lg font-bold text-text-primary">{messages.calendar.title}</h1>
        {childLabel && (
          <p className="text-xs text-muted truncate mt-0.5">{childLabel}</p>
        )}
      </header>

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
      location: '각 반 교실',
      cardType: 'action',
    },
    {
      id: 'preview-calendar-2',
      noticeId: 'preview-schedule',
      title: '학부모 상담주간',
      eventDate: `${base}-14`,
      location: '상담실',
      cardType: 'schedule',
    },
    {
      id: 'preview-calendar-3',
      noticeId: 'preview-supplies',
      title: '봄 소풍',
      eventDate: `${base}-21`,
      location: '서울숲',
      cardType: 'supplies',
    },
  ]
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
