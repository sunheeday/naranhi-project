'use server'

import { redirect } from 'next/navigation'
import { createSupabaseServerClient } from '@/lib/supabase/server'
import type { Locale } from '@/lib/i18n'

export interface SaveChildInput {
  schoolName: string
  neisOfficeCode: string
  neisSchoolCode: string
  grade: number
  classNo: number
  childName: string
  locale: Locale
}

export async function saveChildAndProfile(input: SaveChildInput) {
  const supabase = await createSupabaseServerClient()

  const { data: { user }, error: authError } = await supabase.auth.getUser()
  if (authError || !user) {
    redirect('/login')
  }

  // upsert profile (첫 로그인 시 profiles row가 없을 수 있음)
  await supabase.from('profiles').upsert(
    {
      id: user.id,
      email: user.email ?? null,
      locale: input.locale,
      native_language: input.locale,
    },
    { onConflict: 'id' }
  )

  const { data: child, error } = await supabase.from('children').insert({
    user_id: user.id,
    name: input.childName.trim(),
    school_name: input.schoolName.trim(),
    neis_office_code: input.neisOfficeCode || null,
    neis_school_code: input.neisSchoolCode || null,
    grade: input.grade,
    class_no: input.classNo,
  }).select('id').single()

  if (error || !child) {
    throw new Error('자녀 정보 저장 실패: ' + error?.message)
  }

  redirect('/')
}
