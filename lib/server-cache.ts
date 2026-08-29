import { unstable_cache } from 'next/cache'
import { createSupabaseServiceClient } from '@/lib/supabase/server'
import { parseDietaryRestrictions, type DietaryRestrictionId } from '@/lib/dietary-restrictions'
import { getSchoolCrawlerState } from '@/lib/school-crawl-state'

const USER_CONTEXT_TTL_SECONDS = 30
const HOME_DATA_TTL_SECONDS = 15

function latestChildTag(userId: string): string {
  return `latest-child-for-user:${userId}`
}

function childrenForUserTag(userId: string): string {
  return `children-for-user:${userId}`
}

function schoolSummaryTag(schoolId: string): string {
  return `school-summary:${schoolId}`
}

function hiddenNoticeIdsTag(userId: string): string {
  return `hidden-notice-ids:${userId}`
}

export interface CachedChildSummary {
  id: string
  school_id: string | null
  name?: string
  school_name: string
  grade: number
  class_no: number | null
  neis_office_code: string | null
  neis_school_code: string | null
  dietary_restrictions: DietaryRestrictionId[]
}

export interface CachedSchoolSummary {
  id: string
  crawl_status: string | null
  crawl_board_url: string | null
  crawl_last_checked_at: string | null
}

interface ChildRow {
  id: string
  school_id: string | null
  name?: string
  grade: number
  class_no: number | null
  dietary_restrictions?: unknown
}

interface SchoolLookupRow {
  id: string
  name: string
  neis_office_code: string | null
  neis_school_code: string | null
}

function mergeChildSchoolFields(
  child: ChildRow,
  schoolsById: Map<string, SchoolLookupRow>,
): CachedChildSummary {
  const school = child.school_id ? schoolsById.get(child.school_id) : undefined
  return {
    ...child,
    school_name: school?.name ?? '',
    neis_office_code: school?.neis_office_code ?? null,
    neis_school_code: school?.neis_school_code ?? null,
    dietary_restrictions: parseDietaryRestrictions(child.dietary_restrictions),
  }
}

async function fetchSchoolsByIds(
  schoolIds: string[],
): Promise<Map<string, SchoolLookupRow>> {
  if (schoolIds.length === 0) return new Map()

  const serviceClient = createSupabaseServiceClient()
  const { data } = await serviceClient
    .from('schools')
    .select('id,name,neis_office_code,neis_school_code')
    .in('id', schoolIds)

  return new Map(
    ((data ?? []) as SchoolLookupRow[]).map(row => [row.id, row]),
  )
}

export async function getLatestChildForUser(userId: string): Promise<CachedChildSummary | null> {
  return unstable_cache(
    async () => {
      const serviceClient = createSupabaseServiceClient()
      const { data } = await serviceClient
        .from('children')
        .select('id, school_id, name, grade, class_no, dietary_restrictions')
        .eq('user_id', userId)
        .order('created_at', { ascending: false })
        .limit(1)
        .maybeSingle()

      if (!data) return null
      const child = data as ChildRow
      const schoolsById = await fetchSchoolsByIds(child.school_id ? [child.school_id] : [])
      return mergeChildSchoolFields(child, schoolsById)
    },
    ['latest-child-for-user', userId],
    { revalidate: USER_CONTEXT_TTL_SECONDS, tags: [latestChildTag(userId)] },
  )()
}

export async function getChildrenForUser(userId: string): Promise<CachedChildSummary[]> {
  return unstable_cache(
    async () => {
      const serviceClient = createSupabaseServiceClient()
      const { data } = await serviceClient
        .from('children')
        .select('id, school_id, name, grade, class_no, dietary_restrictions')
        .eq('user_id', userId)
        .order('created_at', { ascending: false })

      const children = ((data ?? []) as ChildRow[])
      const schoolIds = Array.from(new Set(children.map(child => child.school_id).filter((value): value is string => Boolean(value))))
      const schoolsById = await fetchSchoolsByIds(schoolIds)
      return children.map(child => mergeChildSchoolFields(child, schoolsById))
    },
    ['children-for-user', userId],
    { revalidate: USER_CONTEXT_TTL_SECONDS, tags: [childrenForUserTag(userId)] },
  )()
}

/** 홈 상단의 '공지 수집 중' 배너용 크롤 상태.
 *
 *  unstable_cache 콜백은 요청 스코프 밖에서 돌아 쿠키를 못 읽는다. 그래서 세션이
 *  붙은 anon 클라이언트를 만들 수 없고, RLS 대신 코드가 소유권을 확인한다.
 *  userId 는 반드시 호출자가 세션에서 꺼낸 값이어야 한다 —
 *  이 값을 잘못 넘기면 크로스테넌트 유출이다. */
export async function getSchoolSummary(
  userId: string,
  schoolId: string,
): Promise<CachedSchoolSummary | null> {
  return unstable_cache(
    async () => {
      const serviceClient = createSupabaseServiceClient()

      const { data: owned } = await serviceClient
        .from('children')
        .select('id')
        .eq('user_id', userId)
        .eq('school_id', schoolId)
        .limit(1)

      if (!owned || owned.length === 0) return null

      const state = await getSchoolCrawlerState(serviceClient, schoolId)
      if (!state) return null
      return {
        id: schoolId,
        crawl_status: state.crawl_status,
        crawl_board_url: state.crawl_board_url,
        crawl_last_checked_at: state.crawl_last_checked_at,
      }
    },
    ['school-summary', userId, schoolId],
    { revalidate: HOME_DATA_TTL_SECONDS, tags: [schoolSummaryTag(schoolId)] },
  )()
}

export async function getHiddenNoticeIds(userId: string): Promise<string[]> {
  return unstable_cache(
    async () => {
      const serviceClient = createSupabaseServiceClient()
      const { data } = await serviceClient
        .from('notice_hides')
        .select('notice_id')
        .eq('user_id', userId)

      return (data ?? [])
        .map(row => row.notice_id)
        .filter((value): value is string => typeof value === 'string' && value.length > 0)
    },
    ['hidden-notice-ids', userId],
    { revalidate: HOME_DATA_TTL_SECONDS, tags: [hiddenNoticeIdsTag(userId)] },
  )()
}

export const serverCacheTags = {
  latestChildTag,
  childrenForUserTag,
  schoolSummaryTag,
  hiddenNoticeIdsTag,
}
