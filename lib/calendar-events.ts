/** 캘린더에 «같은 일정이 두 번» 나오는 것을 막는 규칙 — 순수 함수만 둔다.
 *
 *  한 공지에서 AI 가 날짜를 뽑으면 같은 일정이 여러 행으로 들어오는 일이 잦다.
 *  예) 예방접종 안내 한 건에서
 *      2026-09-21 ~ 2027-04-30  (2회 접종 대상)
 *      2026-09-28 ~ 2027-04-30  (1회 접종 대상)
 *      2027-04-30               (마감)
 *  는 화면에서 «끝나는 날이 같은 일정이 세 번» 으로 보인다.
 *
 *  규칙: 같은 공지(noticeId) 안에서 «끝나는 날(endDate 가 없거나 시작일보다 이르면 시작일)» 이 같은 행은
 *  하나만 남긴다. 남기는 것은 시작일이 가장 이른 행이고, 시작일이 같으면 기간(endDate)이 있는 행을 먼저 남긴다.
 *  끝나는 날이 다른 행(다른 프로그램·다른 기간)은 그대로 둔다.
 *
 *  지워지는 행의 종류(행사/마감)는 남는 행에 합친다. 예) «접수 10/1~10/10 (행사)» 와 «10/10 (마감)» 이
 *  있으면 남는 행이 행사이면서 마감이 된다. 마감 표시가 조용히 사라지지 않게 하려는 것이다.
 *
 *  공지에 묶이지 않은 행(NEIS 학사일정 등, noticeId 가 비어 있음)은 건드리지 않는다.
 *  남은 행의 순서는 들어온 순서를 그대로 지킨다. */
export interface DedupableEvent {
  noticeId?: string | null
  eventDate: string
  endDate?: string | null
  eventKinds?: readonly string[]
}

/** 화면이 «끝나는 날» 로 보는 값과 같게 맞춘다: 끝이 없거나 시작보다 이르면 시작일. */
function effectiveEnd(event: DedupableEvent): string {
  return event.endDate && event.endDate >= event.eventDate ? event.endDate : event.eventDate
}

function keyOf(event: DedupableEvent): string {
  return `${event.noticeId}|${effectiveEnd(event)}`
}

export function dedupeEventsByNoticeEnd<T extends DedupableEvent>(events: T[]): T[] {
  const winner = new Map<string, T>()
  const kinds = new Map<string, Set<string>>()

  for (const event of events) {
    if (!event.noticeId) continue
    const key = keyOf(event)
    const merged = kinds.get(key) ?? new Set<string>()
    for (const kind of event.eventKinds ?? []) merged.add(kind)
    kinds.set(key, merged)
    const current = winner.get(key)
    if (!current || isBetter(event, current)) winner.set(key, event)
  }

  const result: T[] = []
  for (const event of events) {
    if (!event.noticeId) {
      result.push(event)
      continue
    }
    const key = keyOf(event)
    if (winner.get(key) !== event) continue
    const merged = kinds.get(key)
    // 종류 목록이 없는 행(테스트·다른 화면)은 그대로 두고, 있으면 합친 목록으로 바꾼다.
    result.push(event.eventKinds && merged && merged.size > event.eventKinds.length
      ? { ...event, eventKinds: [...event.eventKinds, ...[...merged].filter(kind => !event.eventKinds!.includes(kind))] }
      : event)
  }
  return result
}

function isBetter(candidate: DedupableEvent, current: DedupableEvent): boolean {
  if (candidate.eventDate !== current.eventDate) return candidate.eventDate < current.eventDate
  return Boolean(candidate.endDate) && !current.endDate
}
