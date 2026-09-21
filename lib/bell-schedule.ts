/** 교시 시각 계산.
 *
 *  NEIS 는 «몇 교시»만 주고 «몇 시»는 주지 않는다(응답 필드가 날짜·교시·과목뿐).
 *  그래서 학교별 교시 시각표(school_bell_schedules)를 따로 두고, 그날 마지막 교시는
 *  NEIS 시간표에서 읽어 둘을 합친다.
 *
 *  이 파일은 순수 함수만 둔다 — DB 접근은 lib/bell-schedule-store.ts 가 맡는다.
 */

export interface BellPeriod {
  period: number
  /** "HH:MM" (KST). 앱 전체가 KST 단일 가정이라 timezone 을 갖지 않는다. */
  startTime: string
  endTime: string
}

/** 마지막 교시가 끝나고 종례에 걸리는 시간.
 *  학교마다 다르므로 상수로 두고, 표시할 때 반드시 "쯤"을 붙인다. */
const HOMEROOM_MINUTES = 10

interface LevelSpec {
  start: string
  lesson: number
  brk: number
  /** 이 교시 뒤에 점심이 온다 */
  lunchAfter: number
  lunch: number
  count: number
}

/** 학교급별 표준 일과. 홈페이지에서 진짜 일과표를 못 찾았을 때 쓰는 추정치다.
 *  수업 길이(초 40 / 중 45 / 고 50)는 교육과정 총론이 정한 값이라 학교가 임의로 바꾸지 않는다.
 *  1교시 시작만 학교마다 8:40~9:00 사이에서 흔들리고, 그건 부모가 고칠 수 있다
 *  (children.bell_offset_minutes). */
const LEVEL_SPECS = {
  elementary: { start: '09:00', lesson: 40, brk: 10, lunchAfter: 4, lunch: 50, count: 6 },
  middle: { start: '09:10', lesson: 45, brk: 10, lunchAfter: 4, lunch: 50, count: 7 },
  high: { start: '08:50', lesson: 50, brk: 10, lunchAfter: 4, lunch: 60, count: 7 },
} as const satisfies Record<string, LevelSpec>

function toMinutes(hhmm: string): number {
  const [h, m] = hhmm.split(':').map(Number)
  return h * 60 + m
}

function toHHMM(total: number): string {
  const wrapped = ((total % 1440) + 1440) % 1440
  const h = Math.floor(wrapped / 60)
  const m = wrapped % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}

/** 학교명으로 학교급을 가른다 — lib/neis.ts 가 시간표 엔드포인트를 고르는 규칙과 같다.
 *  못 가리면 초등으로 본다: 우리 사용자는 대부분 초등학생 학부모다. */
function levelOf(schoolName: string): LevelSpec {
  const name = schoolName ?? ''
  if (name.includes('고등')) return LEVEL_SPECS.high
  if (name.includes('중학')) return LEVEL_SPECS.middle
  return LEVEL_SPECS.elementary
}

export function defaultBellSchedule(schoolName: string): BellPeriod[] {
  const spec = levelOf(schoolName)
  const periods: BellPeriod[] = []
  let cursor = toMinutes(spec.start)

  for (let p = 1; p <= spec.count; p++) {
    const startTime = toHHMM(cursor)
    cursor += spec.lesson
    periods.push({ period: p, startTime, endTime: toHHMM(cursor) })
    cursor += p === spec.lunchAfter ? spec.lunch : spec.brk
  }
  return periods
}

/** 표 전체를 분 단위로 민다. 부모가 «우리 학교는 8시 50분에 시작해요» 한 경우. */
export function applyOffset(periods: BellPeriod[], offsetMinutes: number): BellPeriod[] {
  if (!offsetMinutes) return periods
  return periods.map(p => ({
    period: p.period,
    startTime: toHHMM(toMinutes(p.startTime) + offsetMinutes),
    endTime: toHHMM(toMinutes(p.endTime) + offsetMinutes),
  }))
}

/** 하교 시각(추정) = 그날 마지막 교시의 끝 + 종례.
 *
 *  표에 그 교시가 없으면 null 을 돌려준다 — 억지로 추정하지 않는다.
 *  틀린 하교 시각으로 알림이 나가는 것이 알림이 없느니만 못하기 때문이다.
 *
 *  주의: periods 에 이미 applyOffset 을 적용했다면 offsetMinutes 는 0 을 넘겨야 한다.
 *  두 번 더하면 그만큼 어긋난다. */
export function resolveDismissal(
  periods: BellPeriod[],
  lastPeriod: number,
  offsetMinutes: number,
): string | null {
  const found = periods.find(p => p.period === lastPeriod)
  if (!found) return null
  return toHHMM(toMinutes(found.endTime) + offsetMinutes + HOMEROOM_MINUTES)
}

export interface BellOverrides {
  /** 1교시 시작 보정(분). children.bell_offset_minutes. */
  offsetMinutes?: number
  /** 교시 사이 쉬는 시간(분). null 이면 원래 표의 간격을 그대로 둔다. */
  breakMinutes?: number | null
  /** 점심시간(분). null 이면 원래 표의 간격을 그대로 둔다. */
  lunchMinutes?: number | null
}

/** 점심은 4교시와 5교시 사이다 — 초·중·고 모두 그렇고 표준값도 그렇게 만든다.
 *  표가 4교시까지면 점심이 맨 끝이라 교시 사이에 적용할 자리가 없다(-1). */
function lunchGapIndex(periods: BellPeriod[]): number {
  const index = periods.findIndex(p => p.period === 4)
  return index >= 0 && index < periods.length - 1 ? index : -1
}

/** 부모가 고친 세 값(1교시 시작·쉬는 시간·점심시간)을 표에 반영한다.
 *
 *  수업 «길이»는 원래 표의 것을 그대로 쓴다 — 홈페이지에서 읽어온 진짜 일과표라면
 *  교시마다 길이가 다를 수 있고, 그걸 표준값으로 덮으면 정확도가 오히려 떨어진다.
 *  부모가 고치는 것은 시작 시각과 «사이 간격» 둘뿐이다.
 *
 *  쉬는 시간·점심을 둘 다 안 넣었으면 기존 동작(표 전체를 분 단위로 밀기)과 같다. */
export function applyBellOverrides(periods: BellPeriod[], overrides: BellOverrides): BellPeriod[] {
  const offset = overrides.offsetMinutes ?? 0
  const breakMinutes = overrides.breakMinutes ?? null
  const lunchMinutes = overrides.lunchMinutes ?? null

  if (breakMinutes === null && lunchMinutes === null) return applyOffset(periods, offset)
  if (periods.length === 0) return periods

  const lunchIndex = lunchGapIndex(periods)
  const result: BellPeriod[] = []
  let cursor = toMinutes(periods[0].startTime) + offset

  for (let i = 0; i < periods.length; i++) {
    const lessonMinutes = toMinutes(periods[i].endTime) - toMinutes(periods[i].startTime)
    const startTime = toHHMM(cursor)
    cursor += lessonMinutes
    result.push({ period: periods[i].period, startTime, endTime: toHHMM(cursor) })

    if (i === periods.length - 1) break
    const baseGap = toMinutes(periods[i + 1].startTime) - toMinutes(periods[i].endTime)
    const override = i === lunchIndex ? lunchMinutes : breakMinutes
    cursor += override ?? baseGap
  }
  return result
}
