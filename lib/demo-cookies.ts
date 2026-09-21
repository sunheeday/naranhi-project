/** 시연(우회) 모드의 «각자 화면» 쿠키 규칙 — 순수 함수만 둔다.
 *
 *  서버 전용 모듈(test-entry-bypass.ts)에서 분리한 이유는 단위 시험이다. `server-only` 와
 *  next/headers 를 끌어오면 node 내장 테스트 러너로 돌릴 수 없다.
 *
 *  쿠키는 사용자가 마음대로 고칠 수 있다. 그래서 «읽을 때마다» DB 제약(0048·0049·0050)과 같은
 *  범위로 다시 거른다. 이 파일의 parse* 는 값이 이상하면 버리거나 기본값으로 돌린다. */
import type { PersonalScheduleItem } from './child-personal-schedules.ts'
import type { PersonalScheduleColor } from '../types/database.ts'

export const DEMO_DIETARY_COOKIE = 'test_dietary_restrictions'
export const DEMO_BELL_COOKIE = 'test_bell_times'
export const DEMO_SCHEDULES_COOKIE = 'test_personal_schedules'
export const DEMO_HIDDEN_COOKIE = 'test_hidden_notices'

/** 시연 값 쿠키의 공통 속성. 서버만 읽으므로 httpOnly. */
export const DEMO_COOKIE_OPTIONS = {
  httpOnly: true,
  path: '/',
  sameSite: 'lax' as const,
  maxAge: 60 * 60 * 24 * 30,
}

export function parseJson(raw: string | undefined): unknown {
  if (!raw) return null
  try {
    return JSON.parse(raw) as unknown
  } catch {
    return null
  }
}

function boundedInt(value: unknown, min: number, max: number): number | null {
  return typeof value === 'number' && Number.isInteger(value) && value >= min && value <= max
    ? value
    : null
}

// ── 시각 3칸 ────────────────────────────────────────────────────────────────────
export interface DemoBellTimes {
  offsetMinutes: number
  breakMinutes: number | null
  lunchMinutes: number | null
}

export function parseDemoBellTimes(raw: string | undefined): DemoBellTimes {
  const parsed = parseJson(raw)
  if (!parsed || typeof parsed !== 'object') {
    return { offsetMinutes: 0, breakMinutes: null, lunchMinutes: null }
  }
  const o = parsed as Record<string, unknown>
  return {
    offsetMinutes: boundedInt(o.offsetMinutes, -120, 120) ?? 0,
    breakMinutes: boundedInt(o.breakMinutes, 0, 60),
    lunchMinutes: boundedInt(o.lunchMinutes, 0, 120),
  }
}

// ── 방과후 일정 ─────────────────────────────────────────────────────────────────
const SCHEDULE_COLORS: readonly PersonalScheduleColor[] = ['blue', 'green', 'orange', 'purple', 'pink']
const HHMM = /^([01]\d|2[0-3]):[0-5]\d$/
/** 브라우저는 쿠키 하나를 약 4KB 까지만 받는다. 넘기면 조용히 버려서 값이 사라지므로 미리 막는다. */
export const MAX_SCHEDULE_COOKIE_BYTES = 3800
export const MAX_DEMO_SCHEDULES = 30

function toDemoSchedule(value: unknown): PersonalScheduleItem | null {
  if (!value || typeof value !== 'object') return null
  const o = value as Record<string, unknown>
  const title = typeof o.title === 'string' ? o.title.trim() : ''
  const startTime = typeof o.startTime === 'string' ? o.startTime : ''
  const endTime = typeof o.endTime === 'string' ? o.endTime : ''
  const dayOfWeek = o.dayOfWeek
  if (typeof o.id !== 'string' || o.id.length === 0 || o.id.length > 64) return null
  if (!title || title.length > 60) return null
  if (!HHMM.test(startTime) || !HHMM.test(endTime) || startTime >= endTime) return null
  if (typeof dayOfWeek !== 'number' || !Number.isInteger(dayOfWeek) || dayOfWeek < 0 || dayOfWeek > 6) return null
  const color = SCHEDULE_COLORS.includes(o.color as PersonalScheduleColor)
    ? (o.color as PersonalScheduleColor)
    : 'blue'
  const text = (v: unknown, max: number): string | null =>
    typeof v === 'string' && v.trim() ? v.trim().slice(0, max) : null
  return {
    id: o.id,
    title,
    dayOfWeek,
    startTime,
    endTime,
    location: text(o.location, 60),
    memo: text(o.memo, 120),
    color,
  }
}

export function parseDemoSchedules(raw: string | undefined): PersonalScheduleItem[] {
  const parsed = parseJson(raw)
  if (!Array.isArray(parsed)) return []
  return parsed
    .map(toDemoSchedule)
    .filter((item): item is PersonalScheduleItem => item !== null)
    .slice(0, MAX_DEMO_SCHEDULES)
    .sort((a, b) => a.dayOfWeek - b.dayOfWeek || a.startTime.localeCompare(b.startTime))
}

/** 쿠키에 넣을 문자열. 개수나 크기가 넘치면 null — 부르는 쪽이 «더 저장할 수 없어요» 로 안내한다. */
export function serializeDemoSchedules(items: PersonalScheduleItem[]): string | null {
  if (items.length > MAX_DEMO_SCHEDULES) return null
  const json = JSON.stringify(items)
  return encodeURIComponent(json).length > MAX_SCHEDULE_COOKIE_BYTES ? null : json
}

// ── 숨긴 공지 ───────────────────────────────────────────────────────────────────
export const MAX_HIDDEN_NOTICES = 60
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export function parseHiddenNoticeIds(raw: string | undefined): string[] {
  const parsed = parseJson(raw)
  if (!Array.isArray(parsed)) return []
  return parsed
    .filter((id): id is string => typeof id === 'string' && UUID.test(id))
    .slice(0, MAX_HIDDEN_NOTICES)
}
