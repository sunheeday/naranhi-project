'use server'

import { revalidatePath, revalidateTag } from 'next/cache'
import { createSupabaseServerClient, createSupabaseServiceClient } from '@/lib/supabase/server'
import { ensureDemoSchoolSeed, isDemoSchoolSelection } from '@/lib/demo-school'
import { parseDietaryRestrictions, type DietaryRestrictionId } from '@/lib/dietary-restrictions'
import { ensureSchoolCrawlerState, getSchoolCrawlerState } from '@/lib/school-crawl-state'
import { serverCacheTags } from '@/lib/server-cache'
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
  const isDemoSchool = isDemoSchoolSelection({
    schoolName,
    neisOfficeCode: officeCode,
    neisSchoolCode: schoolCode,
  })

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

  if (isDemoSchool) {
    await ensureDemoSchoolSeed(serviceClient, school.id)
    shouldTriggerCrawl = false
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
  const supabase = await createSupabaseServerClient()
  const { data: { user }, error: authError } = await supabase.auth.getUser()
  if (authError || !user) throw new Error('로그인이 필요합니다.')

  const dietaryRestrictions = parseDietaryRestrictions(input.dietaryRestrictions)
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

function _isUniqueViolation(error: { code?: string | null; message?: string }): boolean {
  return error.code === '23505' || (error.message ?? '').includes('duplicate key value')
}
