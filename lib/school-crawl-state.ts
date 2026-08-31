import 'server-only'

import type { SupabaseClient } from '@supabase/supabase-js'
import type { Database, Json, SchoolCrawlBoardKind } from '@/types/database'
import type { SchoolCrawlerState } from '@/lib/school-crawler-trigger'

type ServiceClient = SupabaseClient<Database>

interface SchoolCrawlerStateRow {
  school_id: string
  crawl_board_url: string | null
  crawl_board_kind: SchoolCrawlBoardKind
  crawl_status: string
  crawl_error_message: string | null
  crawl_result: Json
  crawl_last_checked_at: string | null
  board_watermarks: Json
  created_at: string
  updated_at: string
}

export interface SchoolCrawlerStateDetails extends SchoolCrawlerState {
  crawl_board_kind: SchoolCrawlBoardKind
  crawl_error_message: string | null
  crawl_result: Json
  board_watermarks: Json
}

function mapStateRow(row: SchoolCrawlerStateRow | null, schoolId: string): SchoolCrawlerStateDetails | null {
  if (!row) return null
  return {
    id: schoolId,
    crawl_status: row.crawl_status,
    crawl_board_url: row.crawl_board_url,
    crawl_last_checked_at: row.crawl_last_checked_at,
    crawl_board_kind: row.crawl_board_kind,
    crawl_error_message: row.crawl_error_message,
    crawl_result: row.crawl_result,
    board_watermarks: row.board_watermarks ?? {},
  }
}

export async function getSchoolCrawlerState(
  serviceClient: ServiceClient,
  schoolId: string,
): Promise<SchoolCrawlerStateDetails | null> {
  const { data, error } = await serviceClient
    .from('school_crawl_state')
    .select(
      'school_id,crawl_board_url,crawl_board_kind,crawl_status,crawl_error_message,crawl_result,crawl_last_checked_at,board_watermarks,created_at,updated_at',
    )
    .eq('school_id', schoolId)
    .maybeSingle()

  if (error) {
    throw new Error(`학교 크롤링 상태 조회 실패: ${error.message}`)
  }

  return mapStateRow((data ?? null) as SchoolCrawlerStateRow | null, schoolId)
}

export async function ensureSchoolCrawlerState(
  serviceClient: ServiceClient,
  schoolId: string,
): Promise<SchoolCrawlerStateDetails> {
  const current = await getSchoolCrawlerState(serviceClient, schoolId)
  if (current) return current

  const { data, error } = await serviceClient
    .from('school_crawl_state')
    .insert({
      school_id: schoolId,
      crawl_board_kind: 'unknown',
      crawl_status: 'pending',
    })
    .select(
      'school_id,crawl_board_url,crawl_board_kind,crawl_status,crawl_error_message,crawl_result,crawl_last_checked_at,board_watermarks,created_at,updated_at',
    )
    .maybeSingle()

  if (!error && data) {
    return mapStateRow(data as SchoolCrawlerStateRow, schoolId) as SchoolCrawlerStateDetails
  }

  if (error && error.code !== '23505') {
    throw new Error(`학교 크롤링 상태 초기화 실패: ${error.message}`)
  }

  const existing = await getSchoolCrawlerState(serviceClient, schoolId)
  if (existing) return existing

  throw new Error('학교 크롤링 상태 초기화 실패: 상태 행을 확인할 수 없습니다.')
}
