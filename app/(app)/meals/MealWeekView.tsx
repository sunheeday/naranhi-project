'use client'

import { useRouter, useSearchParams } from 'next/navigation'
import { ALLERGEN_NAMES, type Meal, type MealDish } from '@/lib/neis'

/** ISO 날짜 → KST 기준 (year, month, day, weekday). UTC/local 시간대와 무관. */
function isoToParts(iso: string): { y: number; m: number; d: number; weekday: number } {
  const [y, m, d] = iso.split('-').map(Number)
  const ms = Date.UTC(y, m - 1, d)
  return { y, m, d, weekday: new Date(ms).getUTCDay() }
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

export interface DayEntry {
  isoDate: string
  meals: Meal[]    // 빈 배열 = 급식 없음 (휴일/주말)
}

interface Labels {
  weekday: string[]               // 길이 7, 일요일부터
  prev_week: string
  next_week: string
  this_week: string
  no_meal: string
  breakfast: string
  lunch: string
  dinner: string
  allergy_prefix: string
  dietary_prefix: string
  dietary: Record<string, string> // flag key → 라벨
  range: string                   // "{startMonth}/{startDay} – {endMonth}/{endDay}"
  today_label: string
}

interface Props {
  weekStartIso: string             // 월요일 YYYY-MM-DD
  days: DayEntry[]                 // 5개 (월~금) 또는 7개
  labels: Labels
}

export default function MealWeekView({ weekStartIso, days, labels }: Props) {
  const router = useRouter()
  const searchParams = useSearchParams()

  function shiftWeek(deltaDays: number) {
    const next = shiftIsoByDays(weekStartIso, deltaDays)
    const params = new URLSearchParams(searchParams.toString())
    params.set('week', next)
    router.push(`?${params.toString()}`)
  }

  function goThisWeek() {
    const params = new URLSearchParams(searchParams.toString())
    params.delete('week')
    router.push(params.toString() ? `?${params.toString()}` : '?')
  }

  const start = isoToParts(days[0].isoDate)
  const end = isoToParts(days[days.length - 1].isoDate)
  const rangeLabel = labels.range
    .replace('{startMonth}', String(start.m))
    .replace('{startDay}', String(start.d))
    .replace('{endMonth}', String(end.m))
    .replace('{endDay}', String(end.d))

  const todayIso = todayKstIso()

  return (
    <div className="flex flex-col">
      {/* 주 네비게이션 */}
      <div className="flex items-center justify-between px-6 py-3 border-b border-border">
        <button
          onClick={() => shiftWeek(-7)}
          aria-label={labels.prev_week}
          className="w-10 h-10 flex items-center justify-center text-text-secondary text-xl"
        >
          ‹
        </button>
        <button
          onClick={goThisWeek}
          className="text-base font-bold text-text-primary px-3 py-1 rounded-btn hover:bg-bg"
        >
          {rangeLabel}
        </button>
        <button
          onClick={() => shiftWeek(7)}
          aria-label={labels.next_week}
          className="w-10 h-10 flex items-center justify-center text-text-secondary text-xl"
        >
          ›
        </button>
      </div>

      {/* 일자별 카드 */}
      <div className="flex flex-col gap-4 px-6 pt-4 pb-24">
        {days.map(d => (
          <MealDayCard key={d.isoDate} day={d} labels={labels} isToday={d.isoDate === todayIso} />
        ))}
      </div>
    </div>
  )
}

function MealDayCard({ day, labels, isToday }: { day: DayEntry; labels: Labels; isToday: boolean }) {
  const { m, d, weekday } = isoToParts(day.isoDate)
  const weekdayIdx = weekday  // 0=일
  const md = `${m}/${d}`

  const lunch = day.meals.find(m => m.mealType === 2)
  const primary = lunch ?? day.meals[0]

  const dayColor = weekdayIdx === 0 ? 'text-red-400' : weekdayIdx === 6 ? 'text-blue-400' : 'text-text-primary'

  return (
    <article
      className={[
        'bg-surface rounded-card shadow-card p-4',
        isToday ? 'ring-2 ring-primary' : '',
      ].join(' ')}
      aria-label={`${md} ${labels.weekday[weekdayIdx]}`}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className={`text-base font-bold ${dayColor}`}>{md}</span>
          <span className={`text-xs ${dayColor}`}>{labels.weekday[weekdayIdx]}</span>
          {isToday && (
            <span className="text-[11px] px-1.5 py-0.5 rounded-pill bg-primary text-white font-semibold">
              {labels.today_label}
            </span>
          )}
        </div>
        {primary && (
          <span className="text-[11px] px-2 py-0.5 rounded-pill bg-primary-light text-primary font-semibold">
            {primary.mealType === 1 ? labels.breakfast : primary.mealType === 3 ? labels.dinner : labels.lunch}
          </span>
        )}
      </div>

      {!primary ? (
        <p className="text-sm text-text-secondary">{labels.no_meal}</p>
      ) : (
        <>
          <ul className="flex flex-col gap-1">
            {primary.dishes.map((dish, i) => (
              <DishRow key={i} dish={dish} labels={labels} />
            ))}
          </ul>
          {primary.calories && (
            <p className="text-xs text-text-secondary mt-2">{primary.calories}</p>
          )}
        </>
      )}
    </article>
  )
}

function DishRow({ dish, labels }: { dish: MealDish; labels: Labels }) {
  const hasAllergy = dish.allergens.length > 0
  const allergyNames = (dish.allergenLabels && dish.allergenLabels.length > 0
    ? dish.allergenLabels
    : dish.allergens.map(n => ALLERGEN_NAMES[n] ?? `#${n}`)
  ).join(', ')

  const dietaryFlags = dish.dietaryFlags ?? []
  const dietaryNames = dietaryFlags.map(f => labels.dietary[f] ?? f).join(', ')

  return (
    <li className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
      <span className="text-sm text-text-primary">{dish.name}</span>
      {hasAllergy && (
        <span className="text-[11px] text-card-action font-semibold">
          {labels.allergy_prefix} {allergyNames}
        </span>
      )}
      {dietaryFlags.length > 0 && (
        <span className="text-[11px] text-red-600 font-semibold">
          {labels.dietary_prefix} {dietaryNames}
        </span>
      )}
    </li>
  )
}
