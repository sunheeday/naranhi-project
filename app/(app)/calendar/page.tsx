import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import { isValidLocale, type Locale, defaultLocale } from '@/lib/i18n'
import { createSupabaseServiceClient } from '@/lib/supabase/server'
import { getViewer } from '@/lib/viewer'
import { DEMO_NOTICE_LIMIT, readDemoPersonalSchedules } from '@/lib/test-entry-bypass'
import { dedupeEventsByNoticeEnd } from '@/lib/calendar-events'
import { backfillSchoolEventsForSchools } from '@/lib/schedule-backfill'
import {
  fetchTimetableRangeFromNeis,
  UnsupportedTimetableError,
  type TimetablePeriod,
} from '@/lib/neis'
import { pickNoticeDisplayTitle } from '@/lib/notice-title'
import { applyBellOverrides, resolveDismissal, type BellPeriod } from '@/lib/bell-schedule'
import { ensureBellSchedule } from '@/lib/bell-schedule-store'
import {
  fetchPersonalSchedulesForChild,
  type PersonalScheduleItem,
} from '@/lib/child-personal-schedules'
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
  let childId: string | null = null
  let pendingTranslationNoticeIds: string[] = []

  const viewer = await getViewer()
  if (!viewer) redirect('/login')
  const supabase = viewer.supabase

  try {
    const children = await viewer.children()

    const schoolIds = Array.from(new Set((children ?? []).map(child => child.school_id).filter(Boolean))) as string[]
    const child = children?.[0] ?? null
    if (child) {
      childLabel = `${child.school_name} ${child.grade}-${child.class_no ?? ''}`
    }

    if (schoolIds.length > 0) {
      let { data: rows, error } = await supabase
        .from('school_events')
        .select('id, notice_id, title, event_date, end_date, event_kinds, location, description')
        .in('school_id', schoolIds)
        .gte('event_date', from)
        .lt('event_date', to)
        .order('event_date', { ascending: true })

      if (error) throw error

      // 시연 방문자에게는 홈과 같은 기준(학교별 최신 N건)의 공지에서 나온 일정만 보여준다.
      // 학교 학사일정처럼 공지에 묶이지 않은 행(notice_id 없음)은 그대로 둔다.
      if (viewer.demo && rows) {
        const { data: recent } = await supabase
          .from('notices')
          .select('id')
          .in('school_id', schoolIds)
          .eq('status', 'done')
          .order('created_at', { ascending: false })
          .limit(DEMO_NOTICE_LIMIT)
        const allowed = new Set((recent ?? []).map(r => r.id))
        rows = rows.filter(row => !row.notice_id || allowed.has(row.notice_id))
      }

      if ((rows ?? []).length === 0 && !viewer.demo) {
        const serviceClient = createSupabaseServiceClient()
        await backfillSchoolEventsForSchools({
          serviceClient,
          schoolIds,
          preferredLocale: locale,
        })

        const retry = await supabase
          .from('school_events')
          .select('id, notice_id, title, event_date, end_date, event_kinds, location, description')
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

      // 같은 공지에서 끝나는 날이 같은 일정은 한 번만 보여준다(AI 가 같은 일정을 여러 행으로 뽑는 경우).
      events = dedupeEventsByNoticeEnd((rows ?? []).map(row => {
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
          endDate: row.end_date,
          eventKinds: parseEventKinds(row.event_kinds),
          location: translatedLocationsByNotice[row.notice_id]?.[locale] ?? row.location,
          description: row.description,
        }
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
        const translated = await translateTimetableDays(
          buildTimetableDays(monday, periods),
          locale,
          createSupabaseServiceClient(),
        )

        // 교시 시각은 NEIS 에 없다(날짜·교시·과목만 준다). 학교별 시각표를 따로 붙인다.
        // 학교가 연결되지 않은 자녀는 시각 없이 기존 «N교시» 표시로 남는다.
        if (child.school_id) {
          const bell = applyBellOverrides(
            await ensureBellSchedule(
              createSupabaseServiceClient(),
              child.school_id,
              child.school_name,
            ),
            {
              offsetMinutes: child.bell_offset_minutes ?? 0,
              breakMinutes: child.bell_break_minutes,
              lunchMinutes: child.bell_lunch_minutes,
            },
          )
          timetableDays = attachBellTimes(translated, bell)
        } else {
          timetableDays = translated
        }
      } catch (e) {
        if (e instanceof UnsupportedTimetableError) {
          timetableUnsupported = true
        } else {
          console.error('[calendar] timetable fetch failed:', e instanceof Error ? e.message : e)
          timetableErrorMessage = messages.calendar.timetable_error ?? messages.meals?.timetable_error ?? '수업 정보를 불러오지 못했어요.'
        }
      }
    }

    // 개인 일정은 시간표 지원 여부와 무관하게 붙인다 — 미지원 학교에서도 학원은 보여야 한다.
    // 그리고 번역(translateTimetableDays) «뒤에» 붙인다: 제목은 부모가 직접 쓴 표현이라
    // 번역 경로를 타면 안 된다.
    if (child?.id) {
      childId = child.id
      // 시연 방문자의 방과후 일정은 DB 가 아니라 그 사람 쿠키에 있다.
      const personalItems = viewer.demo
        ? await readDemoPersonalSchedules()
        : await fetchPersonalSchedulesForChild(supabase, child.id)
      timetableDays = attachPersonalItems(timetableDays, personalItems)
    }
  } catch (e) {
    console.error('[calendar] schedule fetch failed:', e instanceof Error ? e.message : e)
    errorMessage = messages.calendar.gcal_error ?? '일정을 불러오지 못했어요.'
  }

  return (
    <main className="flex flex-col min-h-screen pb-20">
      <NoticeTranslationKickoff locale={locale} noticeIds={viewer?.demo ? [] : pendingTranslationNoticeIds} />
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
          dismissal: messages.calendar.dismissal ?? '하교 {time}쯤',
        }}
        childId={childId}
        personalLabels={{
          section: messages.calendar.personal_section ?? '개인 일정',
          add: messages.calendar.personal_add ?? '개인 일정 추가',
          edit: messages.calendar.personal_edit ?? '일정 수정',
          titleLabel: messages.calendar.personal_title_label ?? '제목',
          titlePlaceholder: messages.calendar.personal_title_placeholder ?? '예: 태권도',
          weekdayLabel: messages.calendar.personal_weekday_label ?? '요일',
          startLabel: messages.calendar.personal_start_label ?? '시작 시간',
          endLabel: messages.calendar.personal_end_label ?? '종료 시간',
          locationLabel: messages.calendar.personal_location_label ?? '장소',
          locationPlaceholder: messages.calendar.personal_location_placeholder ?? '예: ○○체육관',
          memoLabel: messages.calendar.personal_memo_label ?? '메모',
          colorLabel: messages.calendar.personal_color_label ?? '색상',
          save: messages.common.save,
          saving: messages.calendar.personal_saving ?? '저장 중...',
          cancel: messages.common.cancel,
          delete: messages.calendar.personal_delete ?? '삭제',
          deleteConfirmTitle: messages.calendar.personal_delete_confirm_title ?? '이 일정을 삭제할까요?',
          deleteConfirmBody: messages.calendar.personal_delete_confirm_body ?? '삭제하면 복구할 수 없어요.',
          errTimeOrder: messages.calendar.personal_err_time_order ?? '종료 시간이 시작 시간보다 빨라요.',
          weekdays: messages.calendar.weekdays,
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

/** 각 교시에 시각을 붙이고, 그날 마지막 교시로 하교 시각을 계산해 카드에 얹는다.
 *
 *  bell 은 이미 applyBellOverrides 를 거친 값이므로 resolveDismissal 에는 0 을 넘긴다 —
 *  여기서 다시 더하면 보정이 두 번 먹는다. */
function attachBellTimes(days: TimetableDayEntry[], bell: BellPeriod[]): TimetableDayEntry[] {
  const byPeriod = new Map(bell.map(p => [p.period, p]))
  return days.map(day => {
    const lastPeriod = day.periods.length
      ? Math.max(...day.periods.map(p => p.period))
      : 0
    return {
      ...day,
      periods: day.periods.map(p => ({
        ...p,
        startTime: byPeriod.get(p.period)?.startTime ?? null,
        endTime: byPeriod.get(p.period)?.endTime ?? null,
      })),
      dismissalTime: lastPeriod ? resolveDismissal(bell, lastPeriod, 0) : null,
    }
  })
}

/** 요일이 맞는 개인 일정을 각 날짜 카드에 붙인다. 시작 시각 순으로 정렬한다. */
function attachPersonalItems(
  days: TimetableDayEntry[],
  items: PersonalScheduleItem[],
): TimetableDayEntry[] {
  if (items.length === 0) return days
  return days.map(day => {
    const weekday = new Date(`${day.isoDate}T00:00:00Z`).getUTCDay()
    return {
      ...day,
      personalItems: items
        .filter(item => item.dayOfWeek === weekday)
        .sort((a, b) => a.startTime.localeCompare(b.startTime)),
    }
  })
}

function parseEventKinds(value: unknown): ('event' | 'deadline')[] {
  if (!Array.isArray(value)) return ['event']
  const kinds = value.filter((item): item is 'event' | 'deadline' => item === 'event' || item === 'deadline')
  return kinds.length > 0 ? kinds : ['event']
}
