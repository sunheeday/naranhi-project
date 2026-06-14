import 'server-only'

import { cookies } from 'next/headers'
import { createSupabaseServiceClient } from '@/lib/supabase/server'
import { ensureSchoolCrawlerState } from '@/lib/school-crawl-state'
import {
  schoolNeedsInitialCrawl,
  triggerInitialSchoolCrawl,
  triggerPendingSchoolExtraction,
} from '@/lib/school-crawler-trigger'
import type { CachedChildSummary } from '@/lib/server-cache'
import type { Json } from '@/types/database'

export const DEMO_SCHOOL_COOKIE = 'demo_school'
export const TEST_BYPASS_CHILD_NAME = '학생'

export type BypassSchoolLevel = 'elementary' | 'middle'

export interface BypassSchool {
  key: string
  name: string
  level: BypassSchoolLevel
  officeCode: string
  schoolCode: string
  address: string
  homepageUrl: string
}

/**
 * 데모(우회 모드)에서 선택할 수 있는 학교 목록.
 * 첫 항목이 기본값(쿠키 없을 때). NEIS 코드는 NEIS schoolInfo에서 확인한 값.
 */
export const BYPASS_SCHOOLS: BypassSchool[] = [
  {
    key: 'bucheon-buhung-m',
    name: '부천부흥중학교',
    level: 'middle',
    officeCode: 'J10',
    schoolCode: '7581020',
    address: '경기도 부천시 원미구 계남로 268',
    homepageUrl: 'https://pcbuheung-m.goebc.kr',
  },
  {
    key: 'donginchon-m',
    name: '동인천중학교',
    level: 'middle',
    officeCode: 'E10',
    schoolCode: '7341072',
    address: '인천광역시 남동구 구월남로57번길 12',
    homepageUrl: 'https://donginchon.icems.kr',
  },
  {
    key: 'incheon-hambak-e',
    name: '인천함박초등학교',
    level: 'elementary',
    officeCode: 'E10',
    schoolCode: '7341063',
    address: '인천광역시 연수구 함박뫼로 87',
    homepageUrl: 'https://hambak.icees.kr',
  },
  {
    key: 'incheon-munnam-e',
    name: '인천문남초등학교',
    level: 'elementary',
    officeCode: 'E10',
    schoolCode: '7341032',
    address: '인천광역시 연수구 먼우금로 273',
    homepageUrl: 'http://munnam.icees.kr/',
  },
]

export const DEFAULT_BYPASS_SCHOOL: BypassSchool = BYPASS_SCHOOLS[0]
export const DEFAULT_BYPASS_SCHOOL_KEY = DEFAULT_BYPASS_SCHOOL.key

export function isTestEntryBypassEnabled(): boolean {
  return process.env.TEST_ENTRY_BYPASS === 'true'
}

export function isBypassSchoolKey(key: string | null | undefined): boolean {
  return BYPASS_SCHOOLS.some(school => school.key === key)
}

/** key로 화이트리스트 학교 조회. 없거나 잘못된 key면 기본 학교 반환. */
export function getBypassSchoolByKey(key: string | null | undefined): BypassSchool {
  return BYPASS_SCHOOLS.find(school => school.key === key) ?? DEFAULT_BYPASS_SCHOOL
}

/** demo_school 쿠키를 읽어 현재 선택된 학교를 반환. */
export async function getSelectedBypassSchool(): Promise<BypassSchool> {
  const cookieStore = await cookies()
  return getBypassSchoolByKey(cookieStore.get(DEMO_SCHOOL_COOKIE)?.value)
}

function jsonRecord(value: Json | null | undefined): Record<string, Json> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : {}
}

function isUniqueViolation(error: { code?: string | null; message?: string }): boolean {
  return error.code === '23505' || (error.message ?? '').includes('duplicate key value')
}

/**
 * 학교 행을 insert하되, 동시 렌더 경쟁으로 unique 충돌(23505)이 나면
 * 이미 들어간 행을 재조회해 복구한다. (updateChildSchool의 패턴과 동일)
 */
async function insertOrReselectSchool(
  serviceClient: ReturnType<typeof createSupabaseServiceClient>,
  school: BypassSchool,
): Promise<string> {
  const { data: insertedSchool, error: insertError } = await serviceClient
    .from('schools')
    .insert({
      name: school.name,
      address: school.address,
      homepage_url: school.homepageUrl,
      neis_office_code: school.officeCode,
      neis_school_code: school.schoolCode,
    })
    .select('id')
    .maybeSingle()

  if (!insertError && insertedSchool?.id) {
    return insertedSchool.id
  }

  if (insertError && isUniqueViolation(insertError)) {
    const { data: raceSchool, error: raceError } = await serviceClient
      .from('schools')
      .select('id')
      .eq('neis_office_code', school.officeCode)
      .eq('neis_school_code', school.schoolCode)
      .maybeSingle()
    if (raceSchool?.id) return raceSchool.id
    throw new Error(`테스트 학교 재조회 실패: ${raceError?.message ?? 'id 없음'}`)
  }

  throw new Error(`테스트 학교 생성 실패: ${insertError?.message ?? 'id 없음'}`)
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

/**
 * 선택된 학교를 prod에 보장하고(없으면 insert + 초기 크롤 트리거), 우회용 자녀 요약을 반환.
 * - DB에 이미 있으면 그 학교를 그대로 사용(필요 시 메타만 갱신).
 * - DB에 없으면 insert 후 초기 크롤을 큐에 넣음 → "선택"이 곧 크롤 트리거.
 */
async function ensureBypassChildForSchool(school: BypassSchool): Promise<CachedChildSummary> {
  const serviceClient = createSupabaseServiceClient()
  const { data: existingSchool, error: lookupError } = await serviceClient
    .from('schools')
    .select('id,name,address,homepage_url,neis_office_code,neis_school_code')
    .eq('neis_office_code', school.officeCode)
    .eq('neis_school_code', school.schoolCode)
    .maybeSingle()

  if (lookupError) {
    throw new Error(`테스트 학교 조회 실패: ${lookupError.message}`)
  }

  let schoolId: string
  if (!existingSchool) {
    schoolId = await insertOrReselectSchool(serviceClient, school)
  } else {
    schoolId = existingSchool.id
    const needsSchoolUpdate = existingSchool.name !== school.name
      || existingSchool.address !== school.address
      || existingSchool.homepage_url !== school.homepageUrl

    if (needsSchoolUpdate) {
      const { error: updateError } = await serviceClient
        .from('schools')
        .update({
          name: school.name,
          address: school.address,
          homepage_url: school.homepageUrl,
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
    school_name: school.name,
    grade: 1,
    class_no: 1,
    neis_office_code: school.officeCode,
    neis_school_code: school.schoolCode,
    dietary_restrictions: [],
  }
}

export async function ensureTestBypassChild(): Promise<CachedChildSummary> {
  const school = await getSelectedBypassSchool()
  return ensureBypassChildForSchool(school)
}

export async function ensureTestBypassChildren(): Promise<CachedChildSummary[]> {
  return [await ensureTestBypassChild()]
}
