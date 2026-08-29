import 'server-only'

import { createSupabaseServiceClient } from '@/lib/supabase/server'
import type { Json, NoticeStatus } from '@/types/database'

/** 한 화면에 보여줄 최대 건수. 운영 실측 38건 규모라 페이지네이션은 아직 불필요
 *  (lib/admin/schools.ts 의 동일 판단 — 뷰/페이지네이션보다 전체 조회가 싸다). */
const NOTICE_LIST_LIMIT = 200

export interface AdminNoticeRow {
  id: string
  schoolId: string | null
  schoolName: string
  status: NoticeStatus
  createdAt: string
  errorMessage: string | null
  detailUrl: string | null
  attachmentCount: number
  needsFile: boolean
  needsFileReason: string[]
  extractionAttempts: number
}

/** title(공지 제목)·original_text(본문)·extracted_content.summary(본문 요약)는
 *  어디서도 select 하지 않는다 — Task 10/11 이 세운 전례를 그대로 따른다
 *  ("한국 학교 공지 제목에 학생 개인이 드러날 수 있다", task-10-report.md:156-159 /
 *  task-11-report.md:43-44). 검수는 detail_url(학교 게시판 원문 링크)을 열어
 *  사람이 직접 하고, 이 화면은 상태·오류·추출 신호(개수/불리언/코드 문자열)만
 *  보여준다 — extracted_content 를 select 하는 것은 needs_file/quality_signals/
 *  sources.length 같은 비식별 신호만 뽑아 쓰기 위해서다(본문 텍스트 필드는 읽지
 *  않는다). */
export async function listAdminNotices(): Promise<AdminNoticeRow[]> {
  const service = createSupabaseServiceClient()

  const [notices, schools] = await Promise.all([
    service
      .from('notices')
      .select('id,school_id,status,created_at,error_message,detail_url,extracted_content,extraction_attempts')
      .order('created_at', { ascending: false })
      .limit(NOTICE_LIST_LIMIT),
    service.from('schools').select('id,name'),
  ])
  if (notices.error) throw new Error(`공지 조회 실패: ${notices.error.message}`)
  if (schools.error) throw new Error(`학교 조회 실패: ${schools.error.message}`)

  const schoolName = new Map((schools.data ?? []).map((s) => [s.id, s.name]))

  return (notices.data ?? []).map((notice) => {
    const extracted = (notice.extracted_content ?? null) as Record<string, Json> | null
    const sources = Array.isArray(extracted?.sources) ? (extracted!.sources as unknown[]) : []
    const needsFileReason = Array.isArray(extracted?.needs_file_reason)
      ? (extracted!.needs_file_reason as unknown[]).filter((r): r is string => typeof r === 'string')
      : []
    return {
      id: notice.id,
      schoolId: notice.school_id,
      schoolName: notice.school_id ? (schoolName.get(notice.school_id) ?? '알 수 없음') : '-',
      status: notice.status as NoticeStatus,
      createdAt: notice.created_at,
      errorMessage: notice.error_message,
      detailUrl: notice.detail_url,
      attachmentCount: sources.length,
      needsFile: Boolean(extracted?.needs_file),
      needsFileReason,
      extractionAttempts: notice.extraction_attempts ?? 0,
    }
  })
}

export { NOTICE_LIST_LIMIT }
