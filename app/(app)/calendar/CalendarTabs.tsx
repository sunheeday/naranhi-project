'use client'

import { useRouter, useSearchParams } from 'next/navigation'
import CalendarView, { type ScheduleEvent } from './CalendarView'
import TimetableWeekView, { type TimetableDayEntry } from './TimetableWeekView'

interface CalendarLabels {
  noEventsLabel: string
  monthYearLabel: string
  weekdays: string[]
  prevMonthLabel: string
  nextMonthLabel: string
  monthEventsTitle: string
  daySheetTitle: string
  closeLabel: string
  eventKindLabels: {
    event: string
    deadline: string
  }
}

interface TimetableLabels {
  weekdays: string[]
  prevWeek: string
  nextWeek: string
  range: string
  today: string
  noTimetable: string
  periodSuffix: string
  unsupported: string
}

interface Props {
  activeTab: 'events' | 'classes'
  eventTabLabel: string
  timetableTabLabel: string
  events: ScheduleEvent[]
  initialYear: number
  initialMonth: number
  calendarLabels: CalendarLabels
  weekStartIso: string
  timetableDays: TimetableDayEntry[]
  timetableUnsupported: boolean
  timetableLabels: TimetableLabels
}

export default function CalendarTabs({
  activeTab,
  eventTabLabel,
  timetableTabLabel,
  events,
  initialYear,
  initialMonth,
  calendarLabels,
  weekStartIso,
  timetableDays,
  timetableUnsupported,
  timetableLabels,
}: Props) {
  const router = useRouter()
  const searchParams = useSearchParams()

  function switchTab(tab: 'events' | 'classes') {
    const params = new URLSearchParams(searchParams.toString())
    if (tab === 'events') {
      params.delete('tab')
    } else {
      params.set('tab', 'classes')
    }
    router.push(params.toString() ? `?${params.toString()}` : '?')
  }

  return (
    <div className="flex flex-col">
      <div className="px-6 pt-4">
        <div className="grid grid-cols-2 gap-1 rounded-btn bg-surface-card p-1" role="tablist" aria-label="캘린더 보기">
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'events'}
            onClick={() => switchTab('events')}
            className={[
              'h-10 rounded-md text-sm font-bold transition-colors',
              activeTab === 'events' ? 'bg-surface text-ink shadow-soft' : 'text-muted',
            ].join(' ')}
          >
            {eventTabLabel}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'classes'}
            onClick={() => switchTab('classes')}
            className={[
              'h-10 rounded-md text-sm font-bold transition-colors',
              activeTab === 'classes' ? 'bg-surface text-ink shadow-soft' : 'text-muted',
            ].join(' ')}
          >
            {timetableTabLabel}
          </button>
        </div>
      </div>

      {activeTab === 'events' ? (
        <CalendarView
          events={events}
          initialYear={initialYear}
          initialMonth={initialMonth}
          noEventsLabel={calendarLabels.noEventsLabel}
          monthYearLabel={calendarLabels.monthYearLabel}
          weekdays={calendarLabels.weekdays}
          prevMonthLabel={calendarLabels.prevMonthLabel}
          nextMonthLabel={calendarLabels.nextMonthLabel}
          monthEventsTitle={calendarLabels.monthEventsTitle}
          daySheetTitle={calendarLabels.daySheetTitle}
          closeLabel={calendarLabels.closeLabel}
          eventKindLabels={calendarLabels.eventKindLabels}
        />
      ) : (
        <TimetableWeekView
          weekStartIso={weekStartIso}
          days={timetableDays}
          unsupported={timetableUnsupported}
          labels={timetableLabels}
        />
      )}
    </div>
  )
}
