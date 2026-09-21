'use client'

import { useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import type { TimetablePeriod } from '@/lib/neis'
import type { PersonalScheduleItem } from '@/lib/child-personal-schedules'
import PersonalScheduleSheet, {
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

  const noEntries = days.every(
    day => (unsupported || day.periods.length === 0) && (day.personalItems ?? []).length === 0,
  )

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

      <div className="flex flex-col gap-4 px-2 pt-4 pb-24">
        {/* 시간표 미지원 학교여도 개인 일정은 계속 보여 준다 — 학원은 학교와 무관하다. */}
        {unsupported && (
          <div role="alert" className="rounded-card border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
            {labels.unsupported}
          </div>
        )}

        {noEntries && !unsupported && (
          <p className="text-sm text-text-secondary">{labels.noTimetable}</p>
        )}

        <WeekGrid
          days={days}
          weekdays={labels.weekdays}
          todayLabel={labels.today}
          todayIso={todayIso}
          hidePeriods={unsupported}
          onEditPersonal={childId ? setDraft : undefined}
        />

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


const HOUR_PX = 48
/** 표가 최소한 이 시각 범위는 보여 준다. 수업이 이 밖으로 나가면 그만큼 늘어난다. */
const MIN_START_HOUR = 9
const MIN_END_HOUR = 15
const TIME_COL = '20px'

/** 흰 글씨가 읽히도록 어둡게 잡은 색. 과목 이름으로 색을 고정한다(주가 바뀌어도 같은 색). */
const SUBJECT_COLORS = ['#8f7434', '#5f7f34', '#4b66a8', '#a8642f', '#3f8577', '#b0574a']
const PERSONAL_BLOCK_COLORS: Record<string, string> = {
  blue: '#4b66a8',
  green: '#5f7f34',
  orange: '#a8642f',
  purple: '#7a5aa6',
  pink: '#b0577a',
}

function toMinutes(hhmm: string): number {
  const [h, m] = hhmm.split(':').map(Number)
  return h * 60 + m
}

function subjectColor(subject: string): string {
  let hash = 0
  for (const ch of subject) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0
  return SUBJECT_COLORS[hash % SUBJECT_COLORS.length]
}

interface Block {
  key: string
  title: string
  startMin: number
  endMin: number
  color: string
  onClick?: () => void
}

function buildBlocks(
  day: TimetableDayEntry,
  hidePeriods: boolean,
  onEditPersonal?: (draft: PersonalScheduleDraft) => void,
): Block[] {
  const blocks: Block[] = []

  if (!hidePeriods) {
    for (const period of day.periods) {
      // 시각은 page 에서 항상 채워 준다(학교 시각표가 없으면 학교급 기본값). 그래도 없으면 자리를 못 잡는다.
      if (!period.startTime || !period.endTime) continue
      blocks.push({
        key: `${day.isoDate}-p${period.period}`,
        title: period.subject,
        startMin: toMinutes(period.startTime),
        endMin: toMinutes(period.endTime),
        color: subjectColor(period.subject),
      })
    }
  }

  for (const item of day.personalItems ?? []) {
    blocks.push({
      key: `${day.isoDate}-x${item.id}`,
      title: item.title,
      startMin: toMinutes(item.startTime),
      endMin: toMinutes(item.endTime),
      color: PERSONAL_BLOCK_COLORS[item.color] ?? PERSONAL_BLOCK_COLORS.blue,
      onClick: onEditPersonal
        ? () => onEditPersonal({
            id: item.id,
            title: item.title,
            dayOfWeek: item.dayOfWeek,
            startTime: item.startTime,
            endTime: item.endTime,
            location: item.location,
            memo: item.memo,
            color: item.color,
          })
        : undefined,
    })
  }
  return blocks
}

function hourLabel(hour: number): string {
  return String(((hour + 11) % 12) + 1)
}

function WeekGrid({
  days, weekdays, todayLabel, todayIso, hidePeriods, onEditPersonal,
}: {
  days: TimetableDayEntry[]
  weekdays: string[]
  todayLabel: string
  todayIso: string
  hidePeriods: boolean
  onEditPersonal?: (draft: PersonalScheduleDraft) => void
}) {
  const columns = days.map(day => buildBlocks(day, hidePeriods, onEditPersonal))
  const all = columns.flat()
  const startHour = Math.min(MIN_START_HOUR, ...all.map(b => Math.floor(b.startMin / 60)))
  const endHour = Math.max(MIN_END_HOUR, ...all.map(b => Math.ceil(b.endMin / 60)))
  const hours = Array.from({ length: endHour - startHour }, (_, i) => startHour + i)
  // 토·일은 평일의 절반 폭이다 — 폰(약 390px)에서 평일 칸을 사진만큼 확보하려는 것.
  const dayCols = days.map(day => {
    const { weekday } = isoToParts(day.isoDate)
    return weekday === 0 || weekday === 6 ? 'minmax(0, 0.5fr)' : 'minmax(0, 1fr)'
  })
  const gridCols = `${TIME_COL} ${dayCols.join(' ')}`

  return (
    <div className="overflow-hidden rounded-card border border-hairline-soft bg-surface">
      <div className="grid border-b border-hairline-soft" style={{ gridTemplateColumns: gridCols }}>
        <span />
        {days.map(day => {
          const { weekday } = isoToParts(day.isoDate)
          const isToday = day.isoDate === todayIso
          const dayColor = weekday === 0 ? 'text-red-400' : weekday === 6 ? 'text-blue-400' : 'text-text-secondary'
          return (
            <span
              key={day.isoDate}
              aria-label={isToday ? `${weekdays[weekday]} ${todayLabel}` : weekdays[weekday]}
              className="flex justify-center py-1.5"
            >
              <span
                className={[
                  'min-w-6 rounded-pill px-1.5 text-center text-xs font-bold',
                  isToday ? 'bg-primary text-white' : dayColor,
                ].join(' ')}
              >
                {weekdays[weekday]}
              </span>
            </span>
          )
        })}
      </div>

      <div className="relative grid" style={{ gridTemplateColumns: gridCols, height: hours.length * HOUR_PX }}>
        <div className="relative">
          {hours.map((hour, i) => (
            <span
              key={hour}
              className="absolute right-1 text-[10px] tabular-nums text-muted"
              style={{ top: i * HOUR_PX + 2 }}
            >
              {hourLabel(hour)}
            </span>
          ))}
        </div>

        {columns.map((blocks, i) => (
          <div key={days[i].isoDate} className="relative border-l border-hairline-soft">
            {hours.map((hour, row) => (
              <div
                key={hour}
                className="absolute inset-x-0 border-t border-hairline-soft first:border-t-0"
                style={{ top: row * HOUR_PX, height: HOUR_PX }}
              />
            ))}
            {blocks.map(block => {
              const height = ((block.endMin - block.startMin) * HOUR_PX) / 60 - 1
              const style = {
                top: ((block.startMin - startHour * 60) * HOUR_PX) / 60,
                height,
                backgroundColor: block.color,
              }
              const className = 'absolute inset-x-px overflow-hidden rounded-[3px] px-0.5 py-0.5 text-left text-white'
              const content = (
                <span className="block break-words text-[11px] font-bold leading-tight">{block.title}</span>
              )
              return block.onClick ? (
                <button key={block.key} type="button" onClick={block.onClick} className={className} style={style}>
                  {content}
                </button>
              ) : (
                <div key={block.key} className={className} style={style}>{content}</div>
              )
            })}
          </div>
        ))}
      </div>
    </div>
  )
}
