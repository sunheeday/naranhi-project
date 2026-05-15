import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import { isValidLocale, type Locale, defaultLocale } from '@/lib/i18n'
import { createSupabaseServerClient } from '@/lib/supabase/server'
import { isUiPreviewEnabled } from '@/lib/ui-preview'
import CalendarView, { type ScheduleEvent } from './CalendarView'

export default async function CalendarPage() {
  const cookieStore = await cookies()
  const cookieLocale = cookieStore.get('locale')?.value
  const locale: Locale = isValidLocale(cookieLocale) ? cookieLocale : defaultLocale
  const messages = (await import(`@/messages/${locale}.json`)).default

  const now = new Date()
  const year = now.getFullYear()
  const month = now.getMonth() + 1

  // 현재 월 ±2달 범위 (총 5개월) 조회
  const fromYear = month <= 2 ? year - 1 : year
  const fromMonth = ((month - 3 + 12) % 12) + 1
  const toYear = month >= 11 ? year + 1 : year
  const toMonth = ((month + 2) % 12) + 1
  const from = `${fromYear}-${String(fromMonth).padStart(2, '0')}-01`
  const to = `${toYear}-${String(toMonth).padStart(2, '0')}-01`

  let events: ScheduleEvent[] = []
  let errorMessage: string | null = null

  if (isUiPreviewEnabled()) {
    events = previewEvents(year, month)
  } else {
    const supabase = await createSupabaseServerClient()
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) redirect('/login')

    try {
      const { data: children } = await supabase
        .from('children')
        .select('id')
        .eq('user_id', user.id)

      const childIds = (children ?? []).map(child => child.id)
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
    } catch (e) {
      console.error('[calendar] schedule fetch failed:', e instanceof Error ? e.message : e)
      errorMessage = messages.calendar.gcal_error ?? '일정을 불러오지 못했어요.'
    }
  }

  return (
    <main className="flex flex-col min-h-screen pb-20">
      <header className="sticky top-0 bg-surface border-b border-border px-6 py-4 z-10">
        <h1 className="text-lg font-bold text-text-primary">{messages.calendar.title}</h1>
      </header>

      {errorMessage && (
        <div role="alert" className="mx-6 mt-4 rounded-card border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          {errorMessage}
        </div>
      )}

      <CalendarView
        events={events}
        initialYear={year}
        initialMonth={month}
        noEventsLabel={messages.calendar.no_events}
        monthYearLabel={messages.calendar.month_year}
        weekdays={messages.calendar.weekdays}
        prevMonthLabel={messages.calendar.prev_month}
        nextMonthLabel={messages.calendar.next_month}
        monthEventsTitle={messages.calendar.month_events_title}
        daySheetTitle={messages.calendar.day_sheet_title}
        closeLabel={messages.common.close}
      />
    </main>
  )
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
