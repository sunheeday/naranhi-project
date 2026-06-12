'use client'

import { useRouter, useSearchParams } from 'next/navigation'
import { formatMonthDay } from '@/lib/i18n'
import type { TimetablePeriod } from '@/lib/neis'

function isoToParts(iso: string): { m: number; d: number; weekday: number } {
  const [y, m, d] = iso.split('-').map(Number)
  const ms = Date.UTC(y, m - 1, d)
  return { m, d, weekday: new Date(ms).getUTCDay() }
}

function shiftIsoByDays(iso: string, days: number): string {
  const [y, m, d] = iso.split('-').map(Number)
  const dt = new Date(Date.UTC(y, m - 1, d) + days * 86400000)
  const yy = dt.getUTCFullYear()
  const mm = String(dt.getUTCMonth() + 1).padStart(2, '0')
  const dd = String(dt.getUTCDate()).padStart(2, '0')
  return `${yy}-${mm}-${dd}`
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

export interface TimetableDayEntry {
  isoDate: string
  periods: TimetablePeriod[]
}

interface Labels {
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
  weekStartIso: string
  days: TimetableDayEntry[]
  unsupported: boolean
  labels: Labels
}

export default function TimetableWeekView({ weekStartIso, days, unsupported, labels }: Props) {
  const router = useRouter()
  const searchParams = useSearchParams()
  const todayIso = todayKstIso()
  const start = isoToParts(days[0].isoDate)
  const end = isoToParts(days[days.length - 1].isoDate)
  const rangeLabel = labels.range
    .replace('{startMonth}', String(start.m))
    .replace('{startDay}', String(start.d))
    .replace('{endMonth}', String(end.m))
    .replace('{endDay}', String(end.d))

  function shiftWeek(deltaDays: number) {
    const params = new URLSearchParams(searchParams.toString())
    params.set('tab', 'classes')
    params.set('week', shiftIsoByDays(weekStartIso, deltaDays))
    router.push(`?${params.toString()}`)
  }

  function goThisWeek() {
    const params = new URLSearchParams(searchParams.toString())
    params.set('tab', 'classes')
    params.delete('week')
    router.push(`?${params.toString()}`)
  }

  return (
    <div className="flex flex-col">
      <div className="flex items-center justify-between px-6 py-3 border-b border-border">
        <button onClick={() => shiftWeek(-7)} aria-label={labels.prevWeek} className="w-10 h-10 flex items-center justify-center text-text-secondary text-xl">
          ‹
        </button>
        <button onClick={goThisWeek} className="text-base font-bold text-text-primary px-3 py-1 rounded-btn hover:bg-bg">
          {rangeLabel}
        </button>
        <button onClick={() => shiftWeek(7)} aria-label={labels.nextWeek} className="w-10 h-10 flex items-center justify-center text-text-secondary text-xl">
          ›
        </button>
      </div>

      <div className="flex flex-col gap-4 px-6 pt-4 pb-24">
        {unsupported ? (
          <div role="alert" className="rounded-card border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
            {labels.unsupported}
          </div>
        ) : (
          days.map(day => (
            <TimetableDayCard key={day.isoDate} day={day} labels={labels} isToday={day.isoDate === todayIso} />
          ))
        )}
      </div>
    </div>
  )
}

function TimetableDayCard({ day, labels, isToday }: { day: TimetableDayEntry; labels: Labels; isToday: boolean }) {
  const { m, d, weekday } = isoToParts(day.isoDate)
  const dayColor = weekday === 0 ? 'text-red-400' : weekday === 6 ? 'text-blue-400' : 'text-text-primary'
  const md = formatMonthDay(m, d, labels.range)

  return (
    <article
      className={[
        'bg-surface rounded-card shadow-card p-4',
        isToday ? 'ring-2 ring-primary' : '',
      ].join(' ')}
      aria-label={`${md} ${labels.weekdays[weekday]}`}
    >
      <div className="flex items-center gap-2 mb-3">
        <span className={`text-base font-bold ${dayColor}`}>{md}</span>
        <span className={`text-xs ${dayColor}`}>{labels.weekdays[weekday]}</span>
        {isToday && (
          <span className="text-[11px] px-1.5 py-0.5 rounded-pill bg-primary text-white font-semibold">
            {labels.today}
          </span>
        )}
      </div>

      {day.periods.length === 0 ? (
        <p className="text-sm text-text-secondary">{labels.noTimetable}</p>
      ) : (
        <ol className="flex flex-col divide-y divide-hairline-soft">
          {day.periods.map(period => (
            <li key={`${day.isoDate}-${period.period}`} className="grid grid-cols-[52px_1fr] gap-3 py-2 first:pt-0 last:pb-0">
              <span className="text-xs font-bold text-muted pt-0.5">
                {labels.periodSuffix.replace('{period}', String(period.period))}
              </span>
              <span className="min-w-0">
                <span className="block text-sm font-semibold text-text-primary truncate">{period.subject}</span>
                {period.classroom && (
                  <span className="block text-xs text-text-secondary truncate mt-0.5">{period.classroom}</span>
                )}
              </span>
            </li>
          ))}
        </ol>
      )}
    </article>
  )
}
