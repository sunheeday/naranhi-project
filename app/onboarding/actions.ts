'use server'

import { redirect } from 'next/navigation'
import { createSupabaseServerClient, createSupabaseServiceClient } from '@/lib/supabase/server'
import type { Locale } from '@/lib/i18n'

export interface SaveChildInput {
  schoolName: string
  schoolAddress?: string
  neisOfficeCode: string
  neisSchoolCode: string
  grade: number
  classNo: number
  childName: string
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

  const { data: school, error: schoolError } = await serviceClient
    .from('schools')
    .upsert(
      {
        name: schoolName,
        neis_office_code: officeCode,
        neis_school_code: schoolCode,
        address: input.schoolAddress?.trim() || null,
      },
      { onConflict: 'neis_office_code,neis_school_code' }
    )
    .select('id')
    .single()

  if (schoolError || !school) {
    throw new Error('학교 정보 저장 실패: ' + schoolError?.message)
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
  }).select('id').single()

  if (error || !child) {
    throw new Error('자녀 정보 저장 실패: ' + error?.message)
  }

  redirect('/')
}
