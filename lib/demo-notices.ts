/** 시연 화면에 보여줄 공지의 기준 — 순수 함수만 둔다(단위 시험을 위해 서버 전용 모듈과 분리).
 *
 *  «학교별 최신 N건» 은 쓰지 않는다. 시연에서 공지 하나를 빼면 그 자리에 예전 공지가 올라오기 때문이다.
 *  대신 «이 시각 이후에 받은 공지» 만 보여주고, 시연에 못 내놓는 공지는 id 로 뺀다. */

/** 이 시각(UTC) 이후에 크롤된 공지만 시연 화면에 나온다. 2026-09-22 시연용으로 새로 받은 공지의 시작 시각이다. */
export const DEMO_NOTICES_SINCE = '2026-09-21T14:00:00Z'

/** 시연에서 뺄 공지. 시연은 학교마다 4건으로 맞춘다.
 *  - 부천부흥중: 예방접종 안내 — 원문이 17,429자라 번역 결과 형식이 깨져서 번역이 안 된다.
 *  - 인천함박초: 우리학교365 안전정보 포털 안내 — 캘린더 일정이 없는 홍보성 안내라 뺐다. */
export const DEMO_EXCLUDED_NOTICE_IDS: readonly string[] = [
  '0e7127a2-72ab-4ef6-8cf0-b2f425eaa4a9',
  '4372115f-07a8-4b6e-b92b-a163aa862ec1',
  // 부천부흥중은 아래 DEMO_PINNED_NOTICES 의 6월 공지 5건만 내놓는다 — 9/21 에 새로 받은 것은 뺀다.
  'c600ea37-7048-4409-bdee-a92b52c67ea1',
  '4f809fcf-82a3-494f-8eb6-ee9cb972febe',
  '3f394c56-58bf-4106-871d-5314c50fef37',
  '574f9f38-a8b0-4c98-8697-d91f71093bbf',
]

/** 시연용으로 되살린 부천부흥중 옛 공지 — 받은 시각과 마감 뱃지를 2026-06-14 화면 값으로 고정한다.
 *  DB 의 created_at·일정 날짜는 건드리지 않는다(정렬·캘린더·다른 학교까지 같이 틀어진다).
 *  daysAgo: 카드에 찍을 «N일 전». dueLabel: 마감 칩 글자, 없으면 null. */
export interface DemoPinnedNotice {
  daysAgo: number
  dueLabel: string | null
}

export const DEMO_PINNED_NOTICES: Readonly<Record<string, DemoPinnedNotice>> = {
  // 2026학년도 1학기 2차 정기시험 및 정기시험 기출문제 공개 안내
  'c9e98a70-aa33-443a-b2a2-29939bc105fa': { daysAgo: 2, dueLabel: 'D-10 · 6/24' },
  // 에볼라바이러스병 확산 및 감염 예방 안내문
  'ee994013-735b-4db6-911c-31ea0de70d59': { daysAgo: 6, dueLabel: null },
  // 2026학년도 1학년 건강검진 실시 안내
  '39f48c29-be50-404f-b7fd-8244b78e9588': { daysAgo: 6, dueLabel: null },
  // 2026학년도 줄넘기챔피언십대회 안내
  'da2e340a-6011-409e-844e-97f5f9d061b0': { daysAgo: 6, dueLabel: 'D-5 · 6/19' },
  // 2026학년도 2, 3학년 소변검사 실시 안내
  '38712f54-616d-445a-b146-3534a3bb3a41': { daysAgo: 6, dueLabel: null },
}

export function demoPinnedNotice(id: string): DemoPinnedNotice | null {
  return DEMO_PINNED_NOTICES[id] ?? null
}

export function isDemoNoticeVisible(notice: { id: string; created_at: string }): boolean {
  // 못 박은 옛 공지는 받은 시각과 상관없이 나온다.
  if (notice.id in DEMO_PINNED_NOTICES) return true
  const created = Date.parse(notice.created_at)
  return Number.isFinite(created)
    && created >= Date.parse(DEMO_NOTICES_SINCE)
    && !DEMO_EXCLUDED_NOTICE_IDS.includes(notice.id)
}
