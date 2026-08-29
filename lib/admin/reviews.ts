import 'server-only'

import { createSupabaseServiceClient } from '@/lib/supabase/server'

/** 화면·API 응답에 실제로 내보내는 값 — 원문·번역문·공지 제목은 여기에 없다.
 *  Task 10/11/15 가 이미 내린 결정("한국 학교 공지 제목엔 학생 이름·학년반이
 *  섞일 수 있다")을 그대로 따른다. `detailUrl` 은 학교 게시판 원문 링크일 뿐
 *  본문을 렌더링하지 않는다(Task 15 와 동일 대체 패턴). */
export interface ReviewQueueRow {
  noticeId: string
  detailUrl: string | null
  schoolName: string | null
  targetLanguage: string
  reviewReason: string | null
  updatedAt: string
}

const REVIEW_QUEUE_LIMIT = 300

/** 0041(needs_review/review_reason)이 운영에 아직 미적용이면 이 컬럼을 select/filter
 *  하는 순간 컬럼 자체가 없다. notice_service.py._is_missing_review_columns_error 는
 *  "쓰기(upsert)" 경로의 PGRST204 를 다루지만, SELECT/필터는 스키마 캐시 사전검증을
 *  거치지 않고 postgres 가 직접 42703("column ... does not exist")을 던진다 — 이
 *  저장소가 이미 실측한 계열(school_crawler_service.py:789, rss_feed 컬럼 부재)과
 *  같다. "컬럼이 아예 없다"와 "검토 대기가 0건이다"를 구분해야 관리자가 화면이 빈
 *  이유(0041 미적용 vs 정말 대기 없음)를 진단할 수 있다. */
export class ReviewQueueUnavailableError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'ReviewQueueUnavailableError'
  }
}

function isMissingReviewColumnsError(error: { code?: string; message?: string } | null): boolean {
  if (!error) return false
  const message = error.message ?? ''
  const mentionsReviewColumn = message.includes('needs_review') || message.includes('review_reason')
  if (error.code === '42703') return mentionsReviewColumn
  return mentionsReviewColumn && /does not exist/i.test(message)
}

/** 부분 인덱스 notice_ai_translations_needs_review_idx(0041)가 이 조회를 받는다.
 *  전체 155행 중 needs_review 인 소수만 인덱싱된다.
 *
 *  🔴 title/translated_text 는 어디서도 select 하지 않는다. notices 에서도 title
 *  대신 detail_url(학교 게시판 원문 링크)만 가져온다 — 검토가 필요하면 관리자가
 *  그 공개 페이지에서 직접 본다. */
export async function listReviewQueue(): Promise<ReviewQueueRow[]> {
  const service = createSupabaseServiceClient()

  const { data: translations, error } = await service
    .from('notice_ai_translations')
    .select('notice_id,target_language,review_reason,updated_at')
    .eq('needs_review', true)
    .order('updated_at', { ascending: false })
    .limit(REVIEW_QUEUE_LIMIT)
  if (error) {
    if (isMissingReviewColumnsError(error)) {
      throw new ReviewQueueUnavailableError(
        'notice_ai_translations.needs_review/review_reason 컬럼이 없습니다 (마이그레이션 0041 미적용)',
      )
    }
    throw new Error(`검토 큐 조회 실패: ${error.message}`)
  }

  const rows = translations ?? []
  if (rows.length === 0) return []

  const noticeIds = [...new Set(rows.map((row) => row.notice_id))]
  const { data: notices, error: noticesError } = await service
    .from('notices')
    .select('id,school_id,detail_url')
    .in('id', noticeIds)
  if (noticesError) throw new Error(`검토 큐 공지 조회 실패: ${noticesError.message}`)

  const schoolIds = [
    ...new Set((notices ?? []).map((n) => n.school_id).filter((id): id is string => Boolean(id))),
  ]
  const { data: schools, error: schoolsError } =
    schoolIds.length === 0
      ? { data: [], error: null }
      : await service.from('schools').select('id,name').in('id', schoolIds)
  if (schoolsError) throw new Error(`검토 큐 학교 조회 실패: ${schoolsError.message}`)

  const schoolName = new Map((schools ?? []).map((s) => [s.id, s.name]))
  const noticeById = new Map((notices ?? []).map((n) => [n.id, n]))

  return rows.map((row) => {
    const notice = noticeById.get(row.notice_id)
    return {
      noticeId: row.notice_id,
      detailUrl: notice?.detail_url ?? null,
      schoolName: notice?.school_id ? (schoolName.get(notice.school_id) ?? null) : null,
      targetLanguage: row.target_language,
      reviewReason: row.review_reason,
      updatedAt: row.updated_at,
    }
  })
}
