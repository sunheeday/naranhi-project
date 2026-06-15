'use client'

import { useState } from 'react'
import Link from 'next/link'
import CharacterEmptyState from '@/components/brand/CharacterEmptyState'
import { buildGoogleCalendarEventUrl } from '@/lib/google-calendar'

export interface ScheduleEvent {
  id: string
  noticeId: string
  title: string
  sourceTitle?: string | null
  eventDate: string  // YYYY-MM-DD
  endDate?: string | null
  eventKinds: ('event' | 'deadline')[]
  location: string | null
  description?: string | null
}

interface Props {
  events: ScheduleEvent[]
  initialYear: number
  initialMonth: number  // 1-based
  noEventsLabel: string
  monthYearLabel: string
  weekdays: string[]              // 길이 7, 일요일부터
  prevMonthLabel: string
  nextMonthLabel: string
  monthEventsTitle: string        // e.g. "{month}월 일정"
  daySheetTitle: string           // e.g. "{month}월 {day}일 일정"
  closeLabel: string
  eventKindLabels: {
    event: string
    deadline: string
  }
}

const DOT_COLOR = {
  deadline: 'bg-card-action',
  event: 'bg-card-schedule',
}

const BADGE_THEME = {
  deadline: 'bg-card-action text-white',
  event: 'bg-card-schedule text-white',
}

const ONE_DAY_MS = 86400000

function isoToMs(iso: string): number {
  const [year, month, day] = iso.split('-').map(Number)
  return Date.UTC(year, month - 1, day)
}

function addDaysIso(iso: string, days: number): string {
  return new Date(isoToMs(iso) + days * ONE_DAY_MS).toISOString().slice(0, 10)
}

function eventEndDate(event: ScheduleEvent): string {
  return event.endDate && event.endDate > event.eventDate ? event.endDate : event.eventDate
}

function intersectsMonth(event: ScheduleEvent, year: number, month: number): boolean {
  const monthStart = `${year}-${String(month).padStart(2, '0')}-01`
  const monthEnd = `${year}-${String(month).padStart(2, '0')}-${String(new Date(year, month, 0).getDate()).padStart(2, '0')}`
  return event.eventDate <= monthEnd && eventEndDate(event) >= monthStart
}

function eventTitleForNormalization(event: ScheduleEvent): string {
  return event.sourceTitle || event.title
}

function shouldPreferDeadlineOnly(normalizedTitle: string): boolean {
  return normalizedTitle.includes('건강검진')
}

function titleKey(title: string): string {
  return title
    .replace(/\s+/g, '')
    .replace(/[()[\]{}<>]/g, '')
}

function normalizeCalendarEvents(events: ScheduleEvent[]): ScheduleEvent[] {
  const byNotice = new Map<string, ScheduleEvent[]>()
  for (const event of events) {
    const key = event.noticeId || titleKey(eventTitleForNormalization(event))
    const list = byNotice.get(key) ?? []
    list.push(event)
    byNotice.set(key, list)
  }

  const normalized: ScheduleEvent[] = []
  for (const group of byNotice.values()) {
    const normalizedTitle = group[0] ? eventTitleForNormalization(group[0]) : ''
    let rows = [...group].sort((a, b) => a.eventDate.localeCompare(b.eventDate))

    // 현재 부천부흥중학교 공지 중 건강검진은 실제 실시일(6/5)과 안내성 날짜(6/1)가 함께 잡힌다.
    // deadline/action이 붙은 실시일이 있으면 안내성 event-only 날짜는 캘린더 표시에서 제외한다.
    if (shouldPreferDeadlineOnly(normalizedTitle)) {
      const deadlineRows = rows.filter(row => row.eventKinds.includes('deadline'))
      if (deadlineRows.length > 0) {
        rows = deadlineRows
      }
    }

    // 연속 구간은 백엔드가 endDate로 내려준다(원문에 범위로 표현된 경우만).
    // 프론트는 더 이상 근접 날짜를 추측 병합하지 않는다 — 별개 날짜(예: 학생 6/9·학부모 6/11)는 따로 둔다.
    normalized.push(...rows)
  }

  return normalized.sort((a, b) => a.eventDate.localeCompare(b.eventDate) || eventEndDate(a).localeCompare(eventEndDate(b)))
}

function formatEventDateLabel(event: ScheduleEvent): string {
  const start = event.eventDate.slice(5).replace('-', '/')
  const endDate = eventEndDate(event)
  if (endDate === event.eventDate) return start
  return `${start}–${endDate.slice(5).replace('-', '/')}`
}

function rangeSegmentClass(event: ScheduleEvent, date: string): string {
  const start = event.eventDate === date
  const end = eventEndDate(event) === date

  if (start && end) return 'start-1/2 end-1/2 rounded-full'
  if (start) return 'start-1/2 -end-px rounded-s-full'
  if (end) return '-start-px end-1/2 rounded-e-full'
  return '-start-px -end-px'
}

export default function CalendarView({
  events,
  initialYear,
  initialMonth,
  noEventsLabel,
  monthYearLabel,
  weekdays,
  prevMonthLabel,
  nextMonthLabel,
  monthEventsTitle,
  daySheetTitle,
  closeLabel,
  eventKindLabels,
}: Props) {
  const [year, setYear] = useState(initialYear)
  const [month, setMonth] = useState(initialMonth)
  const [selectedDate, setSelectedDate] = useState<string | null>(null)

  const label = monthYearLabel
    .replace('{year}', String(year))
    .replace('{month}', String(month))

  function prevMonth() {
    if (month === 1) { setYear(y => y - 1); setMonth(12) }
    else setMonth(m => m - 1)
    setSelectedDate(null)
  }
  function nextMonth() {
    if (month === 12) { setYear(y => y + 1); setMonth(1) }
    else setMonth(m => m + 1)
    setSelectedDate(null)
  }

  const firstDay = new Date(year, month - 1, 1).getDay()
  const daysInMonth = new Date(year, month, 0).getDate()
  const displayEvents = normalizeCalendarEvents(events)

  const eventsByDate: Record<string, ScheduleEvent[]> = {}
  for (const e of displayEvents) {
    let cursor = e.eventDate
    const endDate = eventEndDate(e)
    while (cursor <= endDate) {
      const [ey, em] = cursor.split('-').map(Number)
      if (ey === year && em === month) {
        ;(eventsByDate[cursor] ??= []).push(e)
      }
      cursor = addDaysIso(cursor, 1)
    }
  }

  const cells: (number | null)[] = [
    ...Array(firstDay).fill(null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ]
  while (cells.length % 7 !== 0) cells.push(null)

  const currentMonthEvents = displayEvents
    .filter(e => intersectsMonth(e, year, month))
    .sort((a, b) => a.eventDate.localeCompare(b.eventDate) || eventEndDate(a).localeCompare(eventEndDate(b)))

  const sheetEvents = selectedDate ? (eventsByDate[selectedDate] ?? []) : []
  const isSheetOpen = selectedDate !== null

  function closeSheet() { setSelectedDate(null) }

  return (
    <div className="flex flex-col">
      {/* 월 네비게이션 */}
      <div className="flex items-center justify-between px-6 py-4">
        <button onClick={prevMonth} aria-label={prevMonthLabel} className="w-10 h-10 flex items-center justify-center text-text-secondary text-xl">‹</button>
        <h2 className="text-base font-bold text-text-primary">{label}</h2>
        <button onClick={nextMonth} aria-label={nextMonthLabel} className="w-10 h-10 flex items-center justify-center text-text-secondary text-xl">›</button>
      </div>

      {/* 요일 헤더 */}
      <div className="grid grid-cols-7 px-2 mb-1">
        {weekdays.map((d, i) => (
          <div key={i} className={`text-center text-xs font-semibold py-1 ${i === 0 ? 'text-red-400' : i === 6 ? 'text-blue-400' : 'text-text-secondary'}`}>
            {d}
          </div>
        ))}
      </div>

      {/* 날짜 그리드 — 셀 최소 44×44px */}
      <div className="grid grid-cols-7 px-2 gap-y-0.5">
        {cells.map((day, idx) => {
          if (!day) return <div key={idx} className="h-[44px]" />
          const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
          const dayEvents = eventsByDate[dateStr] ?? []
          const rangeEvents = dayEvents.filter(event => eventEndDate(event) > event.eventDate)
          const dotEvents = dayEvents.filter(event => eventEndDate(event) === event.eventDate)
          const isSelected = selectedDate === dateStr
          const today = new Date()
          const isToday = today.getFullYear() === year && today.getMonth() + 1 === month && today.getDate() === day
          const col = idx % 7

          return (
            <button
              key={idx}
              onClick={() => setSelectedDate(prev => prev === dateStr ? null : dateStr)}
              aria-label={daySheetTitle.replace('{month}', String(month)).replace('{day}', String(day))}
              aria-pressed={isSelected}
              className={[
                'flex flex-col items-center justify-center min-h-[44px] rounded-btn transition-colors',
                isSelected ? 'bg-primary-light' : '',
              ].join(' ')}
            >
              <span className={[
                'text-sm w-7 h-7 flex items-center justify-center rounded-full',
                isToday ? 'bg-primary text-white font-bold' : '',
                !isToday && col === 0 ? 'text-red-400' : '',
                !isToday && col === 6 ? 'text-blue-400' : '',
                !isToday && col > 0 && col < 6 ? 'text-text-primary' : '',
              ].join(' ')}>
                {day}
              </span>
              <div className="relative mt-0.5 h-2 w-full">
                {rangeEvents.slice(0, 1).map(event => {
                  return (
                    <span
                      key={event.id}
                      className={[
                        'absolute top-1/2 h-1.5 -translate-y-1/2 bg-card-schedule',
                        rangeSegmentClass(event, dateStr),
                      ].join(' ')}
                      aria-hidden="true"
                    />
                  )
                })}
                {rangeEvents.length === 0 && dotEvents.length > 0 && (
                  <div className="flex h-full items-center justify-center gap-[3px] px-1">
                    {dotEvents.flatMap(event => event.eventKinds).slice(0, 3).map((kind, i) => (
                      <span key={`${kind}-${i}`} className={`w-1.5 h-1.5 rounded-full ${DOT_COLOR[kind]}`} aria-hidden="true" />
                    ))}
                  </div>
                )}
              </div>
            </button>
          )
        })}
      </div>

      {/* 이번 달 전체 일정 목록 (바텀 시트 닫힌 상태) */}
      <div className="mt-4 px-6 flex flex-col gap-3 pb-24">
        <p className="text-sm font-semibold text-text-secondary">{monthEventsTitle.replace('{month}', String(month))}</p>
        {currentMonthEvents.length === 0 ? (
          <CharacterEmptyState character="walk" title={noEventsLabel} size="compact" />
        ) : (
          currentMonthEvents.map(e => (
            <EventCard key={e.id} event={e} eventKindLabels={eventKindLabels} />
          ))
        )}
      </div>

      {/* 딤 오버레이 */}
      {isSheetOpen && (
        <div
          className="fixed inset-0 bg-black/40 z-40"
          onClick={closeSheet}
          aria-hidden="true"
        />
      )}

      {/* 바텀 시트 슬라이드업 */}
      <div
        role="dialog"
        aria-modal="true"
        aria-label={
          selectedDate
            ? daySheetTitle.replace('{month}', String(month)).replace('{day}', String(Number(selectedDate.split('-')[2])))
            : monthEventsTitle.replace('{month}', String(month))
        }
        className={[
          'fixed bottom-0 inset-x-0 mx-auto w-full max-w-app bg-surface z-50',
          'rounded-t-[24px] shadow-[0_-4px_24px_rgba(0,0,0,0.12)]',
          'transition-transform duration-300',
          isSheetOpen ? 'translate-y-0' : 'translate-y-full',
        ].join(' ')}
      >
        {/* 핸들 */}
        <div className="flex justify-center pt-3 pb-2">
          <div className="w-10 h-1 rounded-full bg-border" aria-hidden="true" />
        </div>

        <div className="px-6 pb-safe-4">
          {selectedDate && (
            <p className="text-base font-bold text-text-primary mb-4">
              {daySheetTitle
                .replace('{month}', String(month))
                .replace('{day}', String(Number(selectedDate.split('-')[2])))}
            </p>
          )}
          {sheetEvents.length === 0 ? (
            <CharacterEmptyState character="pointBlue" title={noEventsLabel} size="compact" />
          ) : (
            <div className="flex flex-col gap-3 pb-2">
              {sheetEvents.map(e => (
                <EventCard key={e.id} event={e} onPress={closeSheet} eventKindLabels={eventKindLabels} />
              ))}
            </div>
          )}
          <button
            onClick={closeSheet}
            className="w-full h-11 mt-3 rounded-btn border border-border text-sm text-text-secondary"
          >
            {closeLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

function EventCard({
  event,
  onPress,
  eventKindLabels,
}: {
  event: ScheduleEvent
  onPress?: () => void
  eventKindLabels: { event: string; deadline: string }
}) {
  const googleCalendarUrl = buildGoogleCalendarEventUrl({
    title: event.title,
    isoDate: event.eventDate,
    endIsoDate: event.endDate ?? null,
    details: event.description ?? null,
    location: event.location,
  })

  return (
    <div className="bg-bg rounded-card p-3">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5 flex-shrink-0" aria-hidden="true">
          {event.eventKinds.map(kind => (
            <span key={kind} className={`w-3 h-3 rounded-full ${DOT_COLOR[kind]}`} />
          ))}
        </div>
        <Link
          href={`/notices/${event.noticeId}`}
          onClick={onPress}
          className="flex flex-1 min-w-0 items-center gap-3 active:scale-[0.98] transition-transform"
        >
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-text-primary truncate">{event.title}</p>
            <div className="mt-1 flex flex-wrap gap-1.5">
              {event.eventKinds.map(kind => (
                <span
                  key={kind}
                  className={`inline-flex items-center rounded-pill px-2 py-0.5 text-[11px] font-semibold ${BADGE_THEME[kind]}`}
                >
                  {eventKindLabels[kind]}
                </span>
              ))}
            </div>
            <p className="text-xs text-text-secondary mt-0.5">
              {formatEventDateLabel(event)}
              {event.location ? ` · ${event.location}` : ''}
            </p>
          </div>
          <span className="text-text-disabled text-sm" aria-hidden="true">›</span>
        </Link>
      </div>
      <div className="mt-3 flex justify-end">
        <a
          href={googleCalendarUrl}
          target="_blank"
          rel="noreferrer"
          className="inline-flex h-9 items-center rounded-btn border border-border px-3 text-xs font-semibold text-text-secondary active:scale-[0.98] transition-transform"
        >
          Google Calendar
        </a>
      </div>
    </div>
  )
}
