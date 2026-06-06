'use server'

import { redirect } from 'next/navigation'
import { createSupabaseServerClient, createSupabaseServiceClient } from '@/lib/supabase/server'
import type { Locale } from '@/lib/i18n'
import { normalizeRestrictions } from '@/lib/dietary'
import { backfillSchedulesForChild } from '@/lib/schedule-backfill'
import {
  schoolNeedsInitialCrawl,
  triggerInitialSchoolCrawl,
  type SchoolCrawlerState,
} from '@/lib/school-crawler-trigger'

export interface SaveChildInput {
  schoolName: string
  schoolAddress?: string
  schoolHomepageUrl?: string
  neisOfficeCode: string
  neisSchoolCode: string
  grade: number
  classNo: number
  childName: string
  dietaryRestrictions?: string[]
  locale: Locale
}

export async function saveChildAndProfile(input: SaveChildInput) {
  const supabase = await createSupabaseServerClient()
  const serviceClient = createSupabaseServiceClient()

  const { data: { user }, error: authError } = await supabase.auth.getUser()
  if (authError || !user) {
    redirect('/login')
  }

  const schoolName = input.schoolName.trim()
  const officeCode = input.neisOfficeCode.trim()
  const schoolCode = input.neisSchoolCode.trim()
  const homepageUrl = input.schoolHomepageUrl?.trim() || null
  const childName = input.childName.trim()

  if (!schoolName || !officeCode || !schoolCode) {
    throw new Error('학교를 검색하여 다시 선택해 주세요.')
  }

  if (!childName) {
    throw new Error('아이 이름을 입력해 주세요.')
  }

  // upsert profile (첫 로그인 시 profiles row가 없을 수 있음)
  const { error: profileError } = await supabase.from('profiles').upsert(
    {
      id: user.id,
      email: user.email ?? null,
      locale: input.locale,
      native_language: input.locale,
    },
    { onConflict: 'id' }
  )

  if (profileError) {
    throw new Error('프로필 저장 실패: ' + profileError.message)
  }

  const { data: existingSchool, error: schoolLookupError } = await serviceClient
    .from('schools')
    .select('id,crawl_status,crawl_board_url,crawl_last_checked_at,homepage_url')
    .eq('neis_office_code', officeCode)
    .eq('neis_school_code', schoolCode)
    .maybeSingle()

  if (schoolLookupError) {
    throw new Error('학교 정보 조회 실패: ' + schoolLookupError.message)
  }

  let school: SchoolCrawlerState | null = existingSchool
  let shouldTriggerCrawl = existingSchool ? schoolNeedsInitialCrawl(existingSchool) : false

  if (existingSchool && homepageUrl && !existingSchool.homepage_url) {
    const { data: updatedSchool, error: homepageUpdateError } = await serviceClient
      .from('schools')
      .update({ homepage_url: homepageUrl })
      .eq('id', existingSchool.id)
      .select('id,crawl_status,crawl_board_url,crawl_last_checked_at')
      .single()

    if (homepageUpdateError) {
      throw new Error('학교 홈페이지 저장 실패: ' + homepageUpdateError.message)
    }

    school = updatedSchool
    shouldTriggerCrawl = schoolNeedsInitialCrawl(updatedSchool)
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
      .select('id,crawl_status,crawl_board_url,crawl_last_checked_at')
      .single()

    if (schoolInsertError) {
      if (_isUniqueViolation(schoolInsertError)) {
        const { data: fallbackSchool, error: fallbackError } = await serviceClient
          .from('schools')
          .select('id,crawl_status,crawl_board_url,crawl_last_checked_at,homepage_url')
          .eq('neis_office_code', officeCode)
          .eq('neis_school_code', schoolCode)
          .single()

        if (fallbackError || !fallbackSchool) {
          throw new Error('학교 정보 재조회 실패: ' + fallbackError?.message)
        }
        school = fallbackSchool
        shouldTriggerCrawl = schoolNeedsInitialCrawl(fallbackSchool)
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
      school = insertedSchool
      shouldTriggerCrawl = true
    }
  }

  if (!school) {
    throw new Error('학교 정보 저장 실패')
  }

  const { data: child, error } = await supabase.from('children').insert({
    user_id: user.id,
    school_id: school.id,
    name: childName,
    school_name: schoolName,
    neis_office_code: officeCode,
    neis_school_code: schoolCode,
    grade: input.grade,
    class_no: input.classNo,
    dietary_restrictions: normalizeRestrictions(input.dietaryRestrictions),
  }).select('id').single()

  if (error || !child) {
    throw new Error('자녀 정보 저장 실패: ' + error?.message)
  }

  await backfillSchedulesForChild({
    serviceClient,
    schoolId: school.id,
    childId: child.id,
    preferredLocale: input.locale,
  })

  if (shouldTriggerCrawl) {
    await triggerInitialSchoolCrawl(school.id)
  }

  redirect('/')
}

function _isUniqueViolation(error: { code?: string | null; message?: string }): boolean {
  return error.code === '23505' || (error.message ?? '').includes('duplicate key value')
}
