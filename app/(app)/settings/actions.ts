'use server'

import { revalidatePath } from 'next/cache'
import { createSupabaseServerClient, createSupabaseServiceClient } from '@/lib/supabase/server'
import {
  schoolNeedsInitialCrawl,
  triggerInitialSchoolCrawl,
  type SchoolCrawlerState,
} from '@/lib/school-crawler-trigger'

export interface UpdateSchoolInput {
  childId: string
  schoolName: string
  schoolAddress?: string
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
    .select('id,crawl_status,crawl_board_url,crawl_last_checked_at')
    .eq('neis_office_code', officeCode)
    .eq('neis_school_code', schoolCode)
    .maybeSingle()

  if (schoolLookupError) {
    throw new Error('학교 정보 조회 실패: ' + schoolLookupError.message)
  }

  let school: SchoolCrawlerState | null = existingSchool
  let shouldTriggerCrawl = existingSchool ? schoolNeedsInitialCrawl(existingSchool) : false

  if (!school) {
    const { data: insertedSchool, error: schoolInsertError } = await serviceClient
      .from('schools')
      .insert({
        name: schoolName,
        neis_office_code: officeCode,
        neis_school_code: schoolCode,
        address: input.schoolAddress?.trim() || null,
      })
      .select('id,crawl_status,crawl_board_url,crawl_last_checked_at')
      .single()

    if (schoolInsertError) {
      if (_isUniqueViolation(schoolInsertError)) {
        const { data: fallbackSchool, error: fallbackError } = await serviceClient
          .from('schools')
          .select('id,crawl_status,crawl_board_url,crawl_last_checked_at')
          .eq('neis_office_code', officeCode)
          .eq('neis_school_code', schoolCode)
          .single()

        if (fallbackError || !fallbackSchool) {
          throw new Error('학교 정보 재조회 실패: ' + fallbackError?.message)
        }
        school = fallbackSchool
        shouldTriggerCrawl = schoolNeedsInitialCrawl(fallbackSchool)
      } else {
        throw new Error('학교 정보 저장 실패: ' + schoolInsertError.message)
      }
    } else if (insertedSchool) {
      school = insertedSchool
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
      school_name: schoolName,
      neis_office_code: officeCode,
      neis_school_code: schoolCode,
      grade,
      class_no: classNo,
    })
    .eq('id', input.childId)
    .eq('user_id', user.id)

  if (error) throw new Error(`학교 정보 업데이트 실패: ${error.message}`)

  if (shouldTriggerCrawl) {
    await triggerInitialSchoolCrawl(school.id)
  }

  revalidatePath('/')
  revalidatePath('/settings')
}

function _isUniqueViolation(error: { code?: string | null; message?: string }): boolean {
  return error.code === '23505' || (error.message ?? '').includes('duplicate key value')
}
