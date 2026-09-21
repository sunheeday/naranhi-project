'use server'

import { revalidatePath, revalidateTag } from 'next/cache'
import { cookies } from 'next/headers'
import { createSupabaseServerClient, createSupabaseServiceClient } from '@/lib/supabase/server'
import {
  DEMO_BELL_COOKIE,
  DEMO_COOKIE_OPTIONS,
  DEMO_DIETARY_COOKIE,
  DEMO_SCHOOL_COOKIE,
  ensureTestBypassChild,
  getBypassSchoolByKey,
  isBypassSchoolKey,
  isTestEntryBypassEnabled,
} from '@/lib/test-entry-bypass'
import { parseDietaryRestrictions, type DietaryRestrictionId } from '@/lib/dietary-restrictions'
import { ensureSchoolCrawlerState, getSchoolCrawlerState } from '@/lib/school-crawl-state'
import { serverCacheTags } from '@/lib/server-cache'
import { ensureBellSchedule } from '@/lib/bell-schedule-store'
import {
  schoolNeedsInitialCrawl,
  triggerInitialSchoolCrawl,
  type SchoolCrawlerState,
} from '@/lib/school-crawler-trigger'

export interface UpdateSchoolInput {
  childId: string
  schoolName: string
  schoolAddress?: string
  schoolHomepageUrl?: string
  neisOfficeCode: string
  neisSchoolCode: string
  grade: number
  classNo: number
}

export async function updateChildSchool(input: UpdateSchoolInput): Promise<void> {
  const supabase = await createSupabaseServerClient()
  const serviceClient = createSupabaseServiceClient()
  const { data: { user }, error: authError } = await supabase.auth.getUser()
  if (authError || !user) throw new Error('로그인이 필요합니다.')

  const schoolName = input.schoolName.trim()
  const officeCode = input.neisOfficeCode.trim()
  const schoolCode = input.neisSchoolCode.trim()
  const homepageUrl = input.schoolHomepageUrl?.trim() || null
  const grade = Number(input.grade)
  const classNo = Number(input.classNo)

  if (!schoolName || !officeCode || !schoolCode) {
    throw new Error('학교를 검색하여 다시 선택해 주세요.')
  }
  if (!Number.isInteger(grade) || grade < 1 || grade > 6) {
    throw new Error('학년을 다시 선택해 주세요.')
  }
  if (!Number.isInteger(classNo) || classNo < 1 || classNo > 20) {
    throw new Error('반을 다시 입력해 주세요.')
  }

  const { data: existingSchool, error: schoolLookupError } = await serviceClient
    .from('schools')
    .select('id,homepage_url')
    .eq('neis_office_code', officeCode)
    .eq('neis_school_code', schoolCode)
    .maybeSingle()

  if (schoolLookupError) {
    throw new Error('학교 정보 조회 실패: ' + schoolLookupError.message)
  }

  let school: SchoolCrawlerState | null = existingSchool
    ? await getSchoolCrawlerState(serviceClient, existingSchool.id)
    : null
  let shouldTriggerCrawl = school ? schoolNeedsInitialCrawl(school) : false

  if (existingSchool && homepageUrl && !existingSchool.homepage_url) {
    const { error: homepageUpdateError } = await serviceClient
      .from('schools')
      .update({ homepage_url: homepageUrl })
      .eq('id', existingSchool.id)

    if (homepageUpdateError) {
      throw new Error('학교 홈페이지 저장 실패: ' + homepageUpdateError.message)
    }

    school = await ensureSchoolCrawlerState(serviceClient, existingSchool.id)
    shouldTriggerCrawl = schoolNeedsInitialCrawl(school)
  }

  if (!school) {
    const { data: insertedSchool, error: schoolInsertError } = await serviceClient
      .from('schools')
      .insert({
        name: schoolName,
        neis_office_code: officeCode,
        neis_school_code: schoolCode,
        address: input.schoolAddress?.trim() || null,
        homepage_url: homepageUrl,
      })
      .select('id')
      .single()

    if (schoolInsertError) {
      if (_isUniqueViolation(schoolInsertError)) {
        const { data: fallbackSchool, error: fallbackError } = await serviceClient
          .from('schools')
          .select('id,homepage_url')
          .eq('neis_office_code', officeCode)
          .eq('neis_school_code', schoolCode)
          .single()

        if (fallbackError || !fallbackSchool) {
          throw new Error('학교 정보 재조회 실패: ' + fallbackError?.message)
        }
        school = await ensureSchoolCrawlerState(serviceClient, fallbackSchool.id)
        shouldTriggerCrawl = schoolNeedsInitialCrawl(school)
        if (homepageUrl && !fallbackSchool.homepage_url) {
          const { error: homepageUpdateError } = await serviceClient
            .from('schools')
            .update({ homepage_url: homepageUrl })
            .eq('id', fallbackSchool.id)
          if (homepageUpdateError) {
            throw new Error('학교 홈페이지 저장 실패: ' + homepageUpdateError.message)
          }
          shouldTriggerCrawl = true
        }
      } else {
        throw new Error('학교 정보 저장 실패: ' + schoolInsertError.message)
      }
    } else if (insertedSchool) {
      school = await ensureSchoolCrawlerState(serviceClient, insertedSchool.id)
      shouldTriggerCrawl = true
    }
  }

  if (!school) {
    throw new Error('학교 정보 저장 실패')
  }

  // 본인 자녀인지 검증 후 업데이트 (RLS도 막지만 명시적으로)
  const { error } = await supabase
    .from('children')
    .update({
      school_id: school.id,
      grade,
      class_no: classNo,
    })
    .eq('id', input.childId)
    .eq('user_id', user.id)

  if (error) throw new Error(`학교 정보 업데이트 실패: ${error.message}`)

  if (shouldTriggerCrawl) {
    await triggerInitialSchoolCrawl(school.id)
  }

  revalidateTag(serverCacheTags.latestChildTag(user.id), 'max')
  revalidateTag(serverCacheTags.childrenForUserTag(user.id), 'max')
  revalidateTag(serverCacheTags.schoolSummaryTag(school.id), 'max')
  revalidatePath('/')
  revalidatePath('/settings')
}

export async function updateChildDietaryRestrictions(input: {
  childId: string
  dietaryRestrictions: DietaryRestrictionId[]
}): Promise<void> {
  const dietaryRestrictions = parseDietaryRestrictions(input.dietaryRestrictions)

  const supabase = await createSupabaseServerClient()
  const { data: { user }, error: authError } = await supabase.auth.getUser()
  if (authError || !user) {
    // 시연 방문자: DB 가 아니라 그 사람 브라우저 쿠키에만 저장한다.
    if (!isTestEntryBypassEnabled()) throw new Error('로그인이 필요합니다.')
    const cookieStore = await cookies()
    cookieStore.set(DEMO_DIETARY_COOKIE, JSON.stringify(dietaryRestrictions), DEMO_COOKIE_OPTIONS)
    revalidatePath('/meals')
    revalidatePath('/settings')
    return
  }

  const { error } = await supabase
    .from('children')
    .update({ dietary_restrictions: dietaryRestrictions })
    .eq('id', input.childId)
    .eq('user_id', user.id)

  if (error) throw new Error(`식이 설정 저장 실패: ${error.message}`)

  revalidateTag(serverCacheTags.latestChildTag(user.id), 'max')
  revalidateTag(serverCacheTags.childrenForUserTag(user.id), 'max')
  revalidatePath('/meals')
  revalidatePath('/settings')
}

/** 부모가 «우리 아이 학교 시간»을 고친다 — 1교시 시작·쉬는 시간·점심시간 세 칸.
 *
 *  교시별로 다 채우게 하면 아무도 채우지 않으므로 세 칸만 받는다. 세 칸 모두 선택이고,
 *  비워 두면 그 항목은 원래 표(홈페이지 판독본 또는 학교급 표준값)를 그대로 쓴다.
 *
 *  school_bell_schedules 는 건드리지 않는다 — 학교 공용 데이터라 한 부모의 수정이
 *  같은 학교 다른 부모에게 번지면 안 된다. 세 값 모두 children 에만 담긴다. */
export async function updateBellTimes(input: {
  childId: string
  firstPeriodStart: string
  breakMinutes: number | null
  lunchMinutes: number | null
}): Promise<void> {
  if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(input.firstPeriodStart)) {
    throw new Error('시간 형식이 올바르지 않아요.')
  }
  // 0050 의 check 제약과 같은 범위. DB 까지 가기 전에 사람이 읽을 말로 막는다.
  if (input.breakMinutes !== null && !(Number.isInteger(input.breakMinutes) && input.breakMinutes >= 0 && input.breakMinutes <= 60)) {
    throw new Error('쉬는 시간은 0분에서 60분 사이로 넣어주세요.')
  }
  if (input.lunchMinutes !== null && !(Number.isInteger(input.lunchMinutes) && input.lunchMinutes >= 0 && input.lunchMinutes <= 120)) {
    throw new Error('점심시간은 0분에서 120분 사이로 넣어주세요.')
  }

  const supabase = await createSupabaseServerClient()
  const { data: { user }, error: authError } = await supabase.auth.getUser()
  const service = createSupabaseServiceClient()

  // 학교 id·이름: 진짜 로그인은 자기 자녀 행에서, 시연 방문자는 고른 학교에서 얻는다.
  let schoolId: string
  let schoolName: string
  if (!authError && user) {
    const { data: child, error: childError } = await supabase
      .from('children')
      .select('id, school_id')
      .eq('id', input.childId)
      .eq('user_id', user.id)
      .maybeSingle()
    if (childError) throw new Error(`자녀 조회 실패: ${childError.message}`)
    if (!child?.school_id) throw new Error('학교가 연결되지 않은 자녀예요.')

    const { data: school } = await service
      .from('schools')
      .select('name')
      .eq('id', child.school_id)
      .maybeSingle()
    schoolId = child.school_id
    schoolName = school?.name ?? ''
  } else if (isTestEntryBypassEnabled()) {
    const demoChild = await ensureTestBypassChild()
    if (!demoChild.school_id) throw new Error('학교가 연결되지 않은 자녀예요.')
    schoolId = demoChild.school_id
    schoolName = demoChild.school_name
  } else {
    throw new Error('로그인이 필요합니다.')
  }

  const base = await ensureBellSchedule(service, schoolId, schoolName)
  const baseStart = base[0]?.startTime
  if (!baseStart) throw new Error('학교 시간표를 아직 만들지 못했어요.')

  const offset = toMinutes(input.firstPeriodStart) - toMinutes(baseStart)
  if (offset < -120 || offset > 120) throw new Error('시간이 너무 많이 차이나요.')

  if (authError || !user) {
    // 시연 방문자: 세 값을 그 사람 쿠키에만 저장한다.
    const cookieStore = await cookies()
    cookieStore.set(
      DEMO_BELL_COOKIE,
      JSON.stringify({
        offsetMinutes: offset,
        breakMinutes: input.breakMinutes,
        lunchMinutes: input.lunchMinutes,
      }),
      DEMO_COOKIE_OPTIONS,
    )
    revalidatePath('/calendar')
    revalidatePath('/settings')
    return
  }

  const { error } = await supabase
    .from('children')
    .update({
      bell_offset_minutes: offset,
      bell_break_minutes: input.breakMinutes,
      bell_lunch_minutes: input.lunchMinutes,
    })
    .eq('id', input.childId)
    .eq('user_id', user.id)
  if (error) throw new Error(`시간 저장 실패: ${error.message}`)

  // 경로만 revalidate 하면 자녀 요약 캐시(30초 TTL)가 남아 옛 시각이 한 번 더 나온다.
  // 실측으로 확인했다 — 태그까지 함께 무효화한다.
  revalidateTag(serverCacheTags.latestChildTag(user.id), 'max')
  revalidateTag(serverCacheTags.childrenForUserTag(user.id), 'max')
  revalidatePath('/calendar')
  revalidatePath('/settings')
}

function toMinutes(hhmm: string): number {
  const [h, m] = hhmm.split(':').map(Number)
  return h * 60 + m
}

function _isUniqueViolation(error: { code?: string | null; message?: string }): boolean {
  return error.code === '23505' || (error.message ?? '').includes('duplicate key value')
}

/**
 * 데모(우회 모드) 전용: 화이트리스트에서 학교를 선택해 demo_school 쿠키에 저장.
 * 이후 ensureTestBypassChild 가 이 쿠키로 학교를 결정한다.
 */
export async function selectDemoSchool(key: string): Promise<void> {
  if (!isTestEntryBypassEnabled()) {
    throw new Error('데모 모드에서만 사용할 수 있어요.')
  }
  if (!isBypassSchoolKey(key)) {
    throw new Error('선택할 수 없는 학교예요.')
  }
  const school = getBypassSchoolByKey(key)
  const cookieStore = await cookies()
  cookieStore.set(DEMO_SCHOOL_COOKIE, school.key, {
    httpOnly: true,
    path: '/',
    maxAge: 60 * 60 * 24 * 365,
    sameSite: 'lax',
  })

  // 학교 요약 캐시(revalidateTag)는 건드리지 않는다 — 시연 방문자는 그 요약을 쓰지 않고,
  // 무효화하면 같은 학교의 진짜 사용자 캐시까지 비운다.
  // 학교가 바뀌면 홈/급식/캘린더/촬영/설정 전부 새 학교 기준으로 다시 렌더.
  revalidatePath('/', 'layout')
}
