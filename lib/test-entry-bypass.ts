import 'server-only'

import { cookies } from 'next/headers'
import {
  DEMO_BELL_COOKIE,
  DEMO_COOKIE_OPTIONS,
  DEMO_DIETARY_COOKIE,
  DEMO_HIDDEN_COOKIE,
  DEMO_SCHEDULES_COOKIE,
  MAX_HIDDEN_NOTICES,
  parseDemoBellTimes,
  parseDemoSchedules,
  isNoticeId,
  parseHiddenNoticeIds,
  parseJson,
  serializeDemoSchedules,
} from '@/lib/demo-cookies'
import { parseDietaryRestrictions } from '@/lib/dietary-restrictions'
import { createSupabaseServiceClient } from '@/lib/supabase/server'
import type { PersonalScheduleItem } from '@/lib/child-personal-schedules'
import type { CachedChildSummary } from '@/lib/server-cache'

/** 시연(우회) 모드의 «각자 화면» 저장소는 전부 그 사람 브라우저의 쿠키다.
 *  DB 에는 사람마다 바뀌는 값을 쓰지 않는다 — 수백 명이 QR 로 들어와도 서로 섞이지 않고,
 *  시연이 끝나도 정리할 것이 없다. 학교·공지·급식은 DB 에서 읽기만 한다(모두 같은 것). */
export {
  DEMO_BELL_COOKIE,
  DEMO_COOKIE_OPTIONS,
  DEMO_DIETARY_COOKIE,
  DEMO_HIDDEN_COOKIE,
  DEMO_SCHEDULES_COOKIE,
} from '@/lib/demo-cookies'
export const DEMO_SCHOOL_COOKIE = 'demo_school'
export const TEST_BYPASS_CHILD_NAME = '학생'
export const TEST_BYPASS_CHILD_ID = 'test-entry-bypass-child'
/** 시연 화면에 보여줄 공지 개수(학교별 최신순). 예전 공지는 감춘다. 홈과 캘린더가 같은 기준을 쓴다. */
export const DEMO_NOTICE_LIMIT = 5

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
]

export const DEFAULT_BYPASS_SCHOOL: BypassSchool = BYPASS_SCHOOLS[0]
export const DEFAULT_BYPASS_SCHOOL_KEY = DEFAULT_BYPASS_SCHOOL.key

export function isTestEntryBypassEnabled(): boolean {
  return process.env.TEST_ENTRY_BYPASS === 'true'
}

/** 시연에서 카메라 기능(사진 번역·메시지 번역)을 로그인 없이 열지. 누를 때마다 AI 요금이 나가므로
 *  시연 스위치와는 «따로» 켜야 한다. 기본은 닫힘. */
export function isDemoCameraEnabled(): boolean {
  return isTestEntryBypassEnabled() && process.env.TEST_ENTRY_ALLOW_CAMERA === 'true'
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

/** 선택된 학교의 DB 행 id. 없으면 한 번 만든다. 크롤·정리는 하지 않는다 —
 *  방문할 때마다 그런 일을 돌리면 사람이 몰릴 때 돈이 나가고 느려진다. */
async function ensureBypassSchoolId(school: BypassSchool): Promise<string> {
  const serviceClient = createSupabaseServiceClient()
  const { data, error } = await serviceClient
    .from('schools')
    .select('id')
    .eq('neis_office_code', school.officeCode)
    .eq('neis_school_code', school.schoolCode)
    .maybeSingle()
  if (error) throw new Error(`테스트 학교 조회 실패: ${error.message}`)
  if (data?.id) return data.id
  return insertOrReselectSchool(serviceClient, school)
}

/** 시연용 자녀. DB 행이 아니라 그 방문자의 쿠키로 만든 «각자 화면» 객체다. */
export async function ensureTestBypassChild(): Promise<CachedChildSummary> {
  const school = await getSelectedBypassSchool()
  const schoolId = await ensureBypassSchoolId(school)
  const cookieStore = await cookies()
  const bell = parseDemoBellTimes(cookieStore.get(DEMO_BELL_COOKIE)?.value)

  return {
    id: TEST_BYPASS_CHILD_ID,
    school_id: schoolId,
    name: TEST_BYPASS_CHILD_NAME,
    school_name: school.name,
    grade: 1,
    class_no: 1,
    neis_office_code: school.officeCode,
    neis_school_code: school.schoolCode,
    dietary_restrictions: parseDietaryRestrictions(
      parseJson(cookieStore.get(DEMO_DIETARY_COOKIE)?.value),
    ),
    bell_offset_minutes: bell.offsetMinutes,
    bell_break_minutes: bell.breakMinutes,
    bell_lunch_minutes: bell.lunchMinutes,
  }
}

export async function ensureTestBypassChildren(): Promise<CachedChildSummary[]> {
  return [await ensureTestBypassChild()]
}

// ── 방과후 일정(쿠키) ───────────────────────────────────────────────────────────
export async function readDemoPersonalSchedules(): Promise<PersonalScheduleItem[]> {
  const cookieStore = await cookies()
  return parseDemoSchedules(cookieStore.get(DEMO_SCHEDULES_COOKIE)?.value)
}

/** 서버 액션에서만 부른다(쿠키 쓰기는 서버 액션·라우트 핸들러에서만 된다). */
export async function saveDemoPersonalSchedules(items: PersonalScheduleItem[]): Promise<void> {
  const json = serializeDemoSchedules(items)
  if (json === null) throw new Error('시연 모드에서는 일정을 더 저장할 수 없어요.')
  const cookieStore = await cookies()
  cookieStore.set(DEMO_SCHEDULES_COOKIE, json, DEMO_COOKIE_OPTIONS)
}

// ── 숨긴 공지(쿠키) ─────────────────────────────────────────────────────────────
export async function readDemoHiddenNoticeIds(): Promise<string[]> {
  const cookieStore = await cookies()
  return parseHiddenNoticeIds(cookieStore.get(DEMO_HIDDEN_COOKIE)?.value)
}

/** 서버 액션에서만 부른다. */
export async function hideDemoNotice(noticeId: string): Promise<void> {
  // 서버 액션 인자는 조작될 수 있다. UUID 가 아니면 쿠키에 쓰지 않는다.
  if (!isNoticeId(noticeId)) return
  const ids = await readDemoHiddenNoticeIds()
  if (ids.includes(noticeId)) return
  const cookieStore = await cookies()
  cookieStore.set(DEMO_HIDDEN_COOKIE, JSON.stringify([...ids, noticeId].slice(-MAX_HIDDEN_NOTICES)), DEMO_COOKIE_OPTIONS)
}
