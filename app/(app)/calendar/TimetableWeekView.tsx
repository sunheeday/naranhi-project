'use client'

import { useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { formatMonthDay } from '@/lib/i18n'
import type { TimetablePeriod } from '@/lib/neis'
import type { PersonalScheduleItem } from '@/lib/child-personal-schedules'
import PersonalScheduleSheet, {
  PERSONAL_COLOR_DOT,
  type PersonalLabels,
  type PersonalScheduleDraft,
} from './PersonalScheduleSheet'

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

/** NEIS 의 교시 정보에 학교별 시각표(0048)를 얹은 것. 시각을 모르는 학교는 null 이고,
 *  그때는 기존 «N교시» 표시로 자연스럽게 되돌아간다. */
export interface TimetablePeriodWithTime extends TimetablePeriod {
  startTime?: string | null
  endTime?: string | null
}

export interface TimetableDayEntry {
  isoDate: string
  periods: TimetablePeriodWithTime[]
  /** 그날 마지막 교시 끝 + 종례. 추정치라 화면에는 반드시 «쯤»을 붙여 쓴다. */
  dismissalTime?: string | null
  /** 부모가 등록한 방과후 일정. 제목은 번역하지 않는다. */
  personalItems?: PersonalScheduleItem[]
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
  dismissal: string
}

interface Props {
  weekStartIso: string
  days: TimetableDayEntry[]
  unsupported: boolean
  labels: Labels
  /** 없으면(자녀 미등록) 개인 일정 UI 를 띄우지 않는다. */
  childId: string | null
  personalLabels: PersonalLabels
}

function defaultDraft(dayOfWeek: number): PersonalScheduleDraft {
  return {
    title: '',
    dayOfWeek,
    startTime: '16:00',
    endTime: '17:00',
    location: null,
    memo: null,
    color: 'blue',
  }
}

export default function TimetableWeekView({
  weekStartIso, days, unsupported, labels, childId, personalLabels,
}: Props) {
  const router = useRouter()
  const searchParams = useSearchParams()
  const todayIso = todayKstIso()
  const [draft, setDraft] = useState<PersonalScheduleDraft | null>(null)
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
        {/* 시간표 미지원 학교여도 개인 일정은 계속 보여 준다 — 학원은 학교와 무관하다. */}
        {unsupported && (
          <div role="alert" className="rounded-card border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
            {labels.unsupported}
          </div>
        )}

        {days.map(day => (
          <TimetableDayCard
            key={day.isoDate}
            day={day}
            labels={labels}
            personalLabels={personalLabels}
            isToday={day.isoDate === todayIso}
            hidePeriods={unsupported}
            onEditPersonal={childId ? setDraft : undefined}
          />
        ))}

        {childId && (
          <button
            type="button"
            onClick={() => setDraft(defaultDraft(1))}
            className="h-[52px] rounded-btn border border-dashed border-primary text-primary font-semibold"
          >
            + {personalLabels.add}
          </button>
        )}
      </div>

      {childId && draft && (
        <PersonalScheduleSheet
          childId={childId}
          draft={draft}
          labels={personalLabels}
          onClose={() => setDraft(null)}
        />
      )}
    </div>
  )
}

function TimetableDayCard({
  day, labels, personalLabels, isToday, hidePeriods, onEditPersonal,
}: {
  day: TimetableDayEntry
  labels: Labels
  personalLabels: PersonalLabels
  isToday: boolean
  hidePeriods: boolean
  onEditPersonal?: (draft: PersonalScheduleDraft) => void
}) {
  const { m, d, weekday } = isoToParts(day.isoDate)
  const personalItems = day.personalItems ?? []
  const showPeriods = !hidePeriods && day.periods.length > 0
  // 학교 수업도 개인 일정도 없을 때만 «수업 정보 없음»이다.
  const empty = !showPeriods && personalItems.length === 0
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

      {empty && <p className="text-sm text-text-secondary">{labels.noTimetable}</p>}

      {showPeriods && (
        <ol className="flex flex-col divide-y divide-hairline-soft">
          {day.periods.map(period => (
            <li key={`${day.isoDate}-${period.period}`} className="grid grid-cols-[52px_1fr] gap-3 py-2 first:pt-0 last:pb-0">
              {/* 시각을 알면 시각을, 모르면 기존 «N교시» 로 되돌아간다 */}
              <span className="text-xs font-bold text-muted pt-0.5 tabular-nums">
                {period.startTime ?? labels.periodSuffix.replace('{period}', String(period.period))}
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

      {!hidePeriods && day.dismissalTime && (
        <p className="mt-3 pt-3 border-t border-hairline-soft text-sm font-semibold text-text-secondary tabular-nums">
          {labels.dismissal.replace('{time}', day.dismissalTime)}
        </p>
      )}

      {personalItems.length > 0 && (
        <div className="mt-3 pt-3 border-t border-hairline-soft flex flex-col gap-2">
          <p className="text-xs font-semibold text-text-secondary">{personalLabels.section}</p>
          {personalItems.map(item => (
            <button
              key={item.id}
              type="button"
              disabled={!onEditPersonal}
              onClick={() => onEditPersonal?.({
                id: item.id,
                title: item.title,
                dayOfWeek: item.dayOfWeek,
                startTime: item.startTime,
                endTime: item.endTime,
                location: item.location,
                memo: item.memo,
                color: item.color,
              })}
              className="flex items-center gap-2 text-left disabled:cursor-default"
            >
              <span className={`h-2 w-2 shrink-0 rounded-full ${PERSONAL_COLOR_DOT[item.color] ?? PERSONAL_COLOR_DOT.blue}`} />
              <span className="text-sm font-semibold text-text-primary truncate">{item.title}</span>
              <span className="text-xs text-text-secondary tabular-nums shrink-0">
                {item.startTime}–{item.endTime}
              </span>
              {item.location && (
                <span className="text-xs text-text-secondary truncate">· {item.location}</span>
              )}
            </button>
          ))}
        </div>
      )}
    </article>
  )
}
