import 'server-only'

import { createSupabaseServiceClient } from '@/lib/supabase/server'
import type { Json, SchoolCrawlBoardKind } from '@/types/database'

export interface AdminSchoolRow {
  id: string
  name: string
  homepageUrl: string | null
  crawlBoardUrl: string | null
  crawlBoardKind: SchoolCrawlBoardKind
  crawlStatus: string
  crawlErrorMessage: string | null
  crawlLastCheckedAt: string | null
  watermarkBoards: number
  noticeCount: number
  pendingNoticeCount: number
}

/** 이 화면이 그리는 열만 가져온다. rss_feed(0040)는 운영에 적용돼 있지만
 *  AdminSchoolRow 에 대응하는 항목이 없어 select 하지 않는다 — 화면에 RSS 판정을
 *  띄우려면 여기와 AdminSchoolRow, 표 헤더를 함께 늘려야 한다.
 *  이 화면이 실제로 쓰는 컬럼(board_watermarks 포함)은 전부 0013 이 이미
 *  운영에 적용해 뒀다 — schools/school_crawl_state/notices 셋 다 기존 테이블이라
 *  "테이블 없음" 을 흉내 낼 필요가 없다(Task 10 과 동일 판단). */
const SCHOOL_CRAWL_STATE_COLUMNS =
  'school_id,crawl_board_url,crawl_board_kind,crawl_status,crawl_error_message,crawl_last_checked_at,board_watermarks'

/** 운영 실측 schools 8 / notices 38. 집계를 SQL 뷰로 만들지 않는다 —
 *  세 번의 전체 조회가 그 규모에서 더 싸고 되돌리기도 쉽다. */
export async function listAdminSchools(): Promise<AdminSchoolRow[]> {
  const service = createSupabaseServiceClient()

  const [schools, states, notices] = await Promise.all([
    service.from('schools').select('id,name,homepage_url').order('name'),
    service.from('school_crawl_state').select(SCHOOL_CRAWL_STATE_COLUMNS),
    service.from('notices').select('id,school_id,status'),
  ])

  if (schools.error) throw new Error(`학교 목록 조회 실패: ${schools.error.message}`)
  if (states.error) throw new Error(`수집 상태 조회 실패: ${states.error.message}`)
  if (notices.error) throw new Error(`공지 수 조회 실패: ${notices.error.message}`)

  const stateBySchool = new Map((states.data ?? []).map((s) => [s.school_id, s]))
  const total = new Map<string, number>()
  const pending = new Map<string, number>()
  for (const notice of notices.data ?? []) {
    if (!notice.school_id) continue
    total.set(notice.school_id, (total.get(notice.school_id) ?? 0) + 1)
    if (notice.status === 'pending') {
      pending.set(notice.school_id, (pending.get(notice.school_id) ?? 0) + 1)
    }
  }

  return (schools.data ?? []).map((school) => {
    const state = stateBySchool.get(school.id)
    const watermarks = (state?.board_watermarks ?? {}) as Record<string, Json>
    return {
      id: school.id,
      name: school.name,
      homepageUrl: school.homepage_url,
      crawlBoardUrl: state?.crawl_board_url ?? null,
      crawlBoardKind: (state?.crawl_board_kind ?? 'unknown') as SchoolCrawlBoardKind,
      crawlStatus: state?.crawl_status ?? 'pending',
      crawlErrorMessage: state?.crawl_error_message ?? null,
      crawlLastCheckedAt: state?.crawl_last_checked_at ?? null,
      watermarkBoards: Object.keys(watermarks).length,
      noticeCount: total.get(school.id) ?? 0,
      pendingNoticeCount: pending.get(school.id) ?? 0,
    }
  })
}
