import 'server-only'

import { createSupabaseServiceClient } from '@/lib/supabase/server'
import { ensureSchoolCrawlerState } from '@/lib/school-crawl-state'
import {
  schoolNeedsInitialCrawl,
  triggerInitialSchoolCrawl,
  triggerPendingSchoolExtraction,
} from '@/lib/school-crawler-trigger'
import type { CachedChildSummary } from '@/lib/server-cache'
import type { Json } from '@/types/database'

export const TEST_BYPASS_SCHOOL_NAME = '부천부흥중학교'
export const TEST_BYPASS_CHILD_NAME = '학생'
export const TEST_BYPASS_OFFICE_CODE = 'J10'
export const TEST_BYPASS_SCHOOL_CODE = '7581020'
export const TEST_BYPASS_SCHOOL_ADDRESS = '경기도 부천시 원미구 계남로 268'
export const TEST_BYPASS_SCHOOL_HOMEPAGE_URL = 'https://pcbuheung-m.goebc.kr'

export function isTestEntryBypassEnabled(): boolean {
  return process.env.TEST_ENTRY_BYPASS === 'true'
}

function jsonRecord(value: Json | null | undefined): Record<string, Json> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : {}
}

async function removeSeededDemoNoticesForSchool(
  serviceClient: ReturnType<typeof createSupabaseServiceClient>,
  schoolId: string,
): Promise<void> {
  const { data: notices, error } = await serviceClient
    .from('notices')
    .select('id,source_post_uid,detail_url,crawl_result')
    .eq('school_id', schoolId)

  if (error) {
    console.warn('[test-entry-bypass] seeded notice lookup failed:', error.message)
    return
  }

  const demoNoticeIds = (notices ?? [])
    .filter(notice => {
      const detailUrl = typeof notice.detail_url === 'string' ? notice.detail_url : ''
      const sourcePostUid = typeof notice.source_post_uid === 'string' ? notice.source_post_uid : ''
      const crawl = jsonRecord(notice.crawl_result)
      const source = typeof crawl.source === 'string' ? crawl.source : ''
      return notice.id.startsWith('0d0b8f4c-76a0-4baf-9f41-8f7c2a7d')
        || sourcePostUid.startsWith('demo-')
        || detailUrl.startsWith('demo://')
        || source === 'demo'
        || source === 'demo_reused'
    })
    .map(notice => notice.id)
    .filter((id): id is string => typeof id === 'string')

  if (demoNoticeIds.length === 0) return

  const { error: deleteError } = await serviceClient
    .from('notices')
    .delete()
    .in('id', demoNoticeIds)

  if (deleteError) {
    console.warn('[test-entry-bypass] seeded notice cleanup failed:', deleteError.message)
  }
}

export async function ensureTestBypassChild(): Promise<CachedChildSummary> {
  const serviceClient = createSupabaseServiceClient()
  const { data: existingSchool, error: lookupError } = await serviceClient
    .from('schools')
    .select('id,name,address,homepage_url,neis_office_code,neis_school_code')
    .eq('neis_office_code', TEST_BYPASS_OFFICE_CODE)
    .eq('neis_school_code', TEST_BYPASS_SCHOOL_CODE)
    .maybeSingle()

  if (lookupError) {
    throw new Error(`테스트 학교 조회 실패: ${lookupError.message}`)
  }

  let schoolId: string
  if (!existingSchool) {
    const { data: insertedSchool, error: insertError } = await serviceClient
      .from('schools')
      .insert({
        name: TEST_BYPASS_SCHOOL_NAME,
        address: TEST_BYPASS_SCHOOL_ADDRESS,
        homepage_url: TEST_BYPASS_SCHOOL_HOMEPAGE_URL,
        neis_office_code: TEST_BYPASS_OFFICE_CODE,
        neis_school_code: TEST_BYPASS_SCHOOL_CODE,
      })
      .select('id')
      .maybeSingle()

    if (insertError || !insertedSchool?.id) {
      throw new Error(`테스트 학교 생성 실패: ${insertError?.message ?? 'id 없음'}`)
    }
    schoolId = insertedSchool.id
  } else {
    const school = existingSchool
    schoolId = school.id
    const needsSchoolUpdate = school.name !== TEST_BYPASS_SCHOOL_NAME
      || school.address !== TEST_BYPASS_SCHOOL_ADDRESS
      || school.homepage_url !== TEST_BYPASS_SCHOOL_HOMEPAGE_URL

    if (needsSchoolUpdate) {
      const { error: updateError } = await serviceClient
        .from('schools')
        .update({
          name: TEST_BYPASS_SCHOOL_NAME,
          address: TEST_BYPASS_SCHOOL_ADDRESS,
          homepage_url: TEST_BYPASS_SCHOOL_HOMEPAGE_URL,
        })
        .eq('id', schoolId)

      if (updateError) {
        throw new Error(`테스트 학교 갱신 실패: ${updateError.message}`)
      }
    }
  }

  await removeSeededDemoNoticesForSchool(serviceClient, schoolId)

  const crawlerState = await ensureSchoolCrawlerState(serviceClient, schoolId)
  if (schoolNeedsInitialCrawl(crawlerState)) {
    await triggerInitialSchoolCrawl(schoolId)
  } else {
    const { count } = await serviceClient
      .from('notices')
      .select('id', { count: 'exact', head: true })
      .eq('school_id', schoolId)
      .eq('status', 'pending')

    if ((count ?? 0) > 0) {
      await triggerPendingSchoolExtraction(schoolId, Math.min(count ?? 0, 20))
    }
  }

  return {
    id: 'test-entry-bypass-child',
    school_id: schoolId,
    name: TEST_BYPASS_CHILD_NAME,
    school_name: TEST_BYPASS_SCHOOL_NAME,
    grade: 1,
    class_no: 1,
    neis_office_code: TEST_BYPASS_OFFICE_CODE,
    neis_school_code: TEST_BYPASS_SCHOOL_CODE,
  }
}

export async function ensureTestBypassChildren(): Promise<CachedChildSummary[]> {
  return [await ensureTestBypassChild()]
}
