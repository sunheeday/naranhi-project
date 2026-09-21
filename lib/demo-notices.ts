/** 시연 화면에 보여줄 공지의 기준 — 순수 함수만 둔다(단위 시험을 위해 서버 전용 모듈과 분리).
 *
 *  «학교별 최신 N건» 은 쓰지 않는다. 시연에서 공지 하나를 빼면 그 자리에 예전 공지가 올라오기 때문이다.
 *  대신 «이 시각 이후에 받은 공지» 만 보여주고, 시연에 못 내놓는 공지는 id 로 뺀다. */

/** 이 시각(UTC) 이후에 크롤된 공지만 시연 화면에 나온다. 2026-09-22 시연용으로 새로 받은 공지의 시작 시각이다. */
export const DEMO_NOTICES_SINCE = '2026-09-21T14:00:00Z'

/** 시연에서 뺄 공지. 예방접종 안내(부천부흥중)는 원문이 17,429자라 번역 결과 형식이 깨져서 번역이 안 된다. */
export const DEMO_EXCLUDED_NOTICE_IDS: readonly string[] = [
  '0e7127a2-72ab-4ef6-8cf0-b2f425eaa4a9',
]

export function isDemoNoticeVisible(notice: { id: string; created_at: string }): boolean {
  const created = Date.parse(notice.created_at)
  return Number.isFinite(created)
    && created >= Date.parse(DEMO_NOTICES_SINCE)
    && !DEMO_EXCLUDED_NOTICE_IDS.includes(notice.id)
}
