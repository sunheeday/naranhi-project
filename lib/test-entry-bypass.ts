import 'server-only'

import { createSupabaseServiceClient } from '@/lib/supabase/server'
import { ensureDemoSchoolSeed } from '@/lib/demo-school'
import type { CachedChildSummary } from '@/lib/server-cache'

export const TEST_BYPASS_SCHOOL_NAME = '부천부흥중학교'
export const TEST_BYPASS_CHILD_NAME = '학생'
export const TEST_BYPASS_OFFICE_CODE = 'J10'
export const TEST_BYPASS_SCHOOL_CODE = '7581020'
export const TEST_BYPASS_SCHOOL_ADDRESS = '경기도 부천시 원미구 계남로 268'
export const TEST_BYPASS_SCHOOL_HOMEPAGE_URL = 'https://pcbuheung-m.goebc.kr'

export function isTestEntryBypassEnabled(): boolean {
  return process.env.TEST_ENTRY_BYPASS === 'true'
}

export async function ensureTestBypassChild(): Promise<CachedChildSummary> {
  const serviceClient = createSupabaseServiceClient()
  const { data: existingSchool, error: lookupError } = await serviceClient
    .from('schools')
    .select('id')
    .eq('neis_office_code', TEST_BYPASS_OFFICE_CODE)
    .eq('neis_school_code', TEST_BYPASS_SCHOOL_CODE)
    .maybeSingle()

  if (lookupError) {
    throw new Error(`테스트 학교 조회 실패: ${lookupError.message}`)
  }

  let schoolId = existingSchool?.id
  if (!schoolId) {
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
  }

  await ensureDemoSchoolSeed(serviceClient, schoolId, {
    schoolName: TEST_BYPASS_SCHOOL_NAME,
    schoolAddress: TEST_BYPASS_SCHOOL_ADDRESS,
    schoolHomepageUrl: TEST_BYPASS_SCHOOL_HOMEPAGE_URL,
    officeCode: TEST_BYPASS_OFFICE_CODE,
    schoolCode: TEST_BYPASS_SCHOOL_CODE,
    includeReusedNotices: false,
  })

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
