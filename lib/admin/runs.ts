import 'server-only'

import { createSupabaseServiceClient } from '@/lib/supabase/server'
import type { Database } from '@/types/database'

export type CrawlRunRow = Database['public']['Tables']['crawl_run_history']['Row']

/** 명시적 컬럼 화이트리스트 — `select('*')`를 쓰지 않는다. 이 목록 밖에는
 *  애초에 공지 제목·본문류 컬럼이 없다(0041_admin_console_observability.sql:
 *  targets/results 도 school_id/school_name/카운트뿐, Task 7·8 이 실측 확인). */
const RUN_COLUMNS =
  'id,started_at,finished_at,outcome,dry_run,force,total_registered,selected_count,skipped_count,processed_count,success_count,failure_count,fallback_count,success_rate,alarm,targets,results,error_message,created_at'

const DEFAULT_LIMIT = 100

/** 0041(crawl_run_history)이 운영에 아직 미적용이면 테이블 자체가 없다. SELECT 경로는
 *  스키마 캐시 사전검증을 거치지 않고 postgres 가 직접 42P01("relation ... does not
 *  exist")을 던진다 — 이 저장소가 이미 실측한 42703(컬럼 부재, reviews.ts 와 동일
 *  계열, school_crawler_service.py:789)과 대칭이다. "테이블이 없다"와 "테이블은
 *  있는데 이력이 0건이다"를 구분해야 한다 — 스케줄러 6개가 재가동돼 하루 2회씩
 *  쌓이기 시작하는 상황에서, 둘을 구분 못 하면 "왜 안 쌓이지" 진단이 막힌다. */
export class CrawlRunHistoryUnavailableError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'CrawlRunHistoryUnavailableError'
  }
}

function isMissingCrawlRunHistoryTable(error: { code?: string; message?: string } | null): boolean {
  if (!error) return false
  const message = error.message ?? ''
  const mentionsTable = message.includes('crawl_run_history')
  if (error.code === '42P01') return mentionsTable
  return mentionsTable && /does not exist/i.test(message)
}

export async function listCrawlRuns(limit = DEFAULT_LIMIT): Promise<CrawlRunRow[]> {
  const service = createSupabaseServiceClient()
  const { data, error } = await service
    .from('crawl_run_history')
    .select(RUN_COLUMNS)
    .order('created_at', { ascending: false })
    .limit(limit)
  if (error) {
    if (isMissingCrawlRunHistoryTable(error)) {
      throw new CrawlRunHistoryUnavailableError(
        'crawl_run_history 테이블이 없습니다 (마이그레이션 0041 미적용)',
      )
    }
    throw new Error(`실행 이력 조회 실패: ${error.message}`)
  }
  return (data ?? []) as CrawlRunRow[]
}
