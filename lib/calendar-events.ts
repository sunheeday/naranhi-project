/** 캘린더에 «같은 일정이 두 번» 나오는 것을 막는 규칙 — 순수 함수만 둔다.
 *
 *  한 공지에서 AI 가 날짜를 뽑으면 같은 일정이 여러 행으로 들어오는 일이 잦다.
 *  예) 예방접종 안내 한 건에서
 *      2026-09-21 ~ 2027-04-30  (2회 접종 대상)
 *      2026-09-28 ~ 2027-04-30  (1회 접종 대상)
 *      2027-04-30               (마감)
 *  는 화면에서 «끝나는 날이 같은 일정이 세 번» 으로 보인다.
 *
 *  규칙: 같은 공지(noticeId) 안에서 «끝나는 날(endDate 가 없으면 시작일)» 이 같은 행은 하나만 남긴다.
 *  남기는 것은 시작일이 가장 이른 행이고, 시작일이 같으면 기간(endDate)이 있는 행을 먼저 남긴다.
 *  끝나는 날이 다른 행(다른 프로그램·다른 기간)은 그대로 둔다.
 *
 *  공지에 묶이지 않은 행(NEIS 학사일정 등, noticeId 가 비어 있음)은 건드리지 않는다.
 *  남은 행의 순서는 들어온 순서를 그대로 지킨다. */
export interface DedupableEvent {
  noticeId?: string | null
  eventDate: string
  endDate?: string | null
}

export function dedupeEventsByNoticeEnd<T extends DedupableEvent>(events: T[]): T[] {
  const winner = new Map<string, T>()

  for (const event of events) {
    if (!event.noticeId) continue
    const key = `${event.noticeId}|${event.endDate || event.eventDate}`
    const current = winner.get(key)
    if (!current || isBetter(event, current)) winner.set(key, event)
  }

  return events.filter(event => !event.noticeId || winner.get(`${event.noticeId}|${event.endDate || event.eventDate}`) === event)
}

function isBetter(candidate: DedupableEvent, current: DedupableEvent): boolean {
  if (candidate.eventDate !== current.eventDate) return candidate.eventDate < current.eventDate
  return Boolean(candidate.endDate) && !current.endDate
}
