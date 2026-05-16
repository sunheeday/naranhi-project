'use server'

import { revalidatePath } from 'next/cache'
import { createSupabaseServerClient, createSupabaseServiceClient } from '@/lib/supabase/server'

export interface UpdateSchoolInput {
  childId: string
  schoolName: string
  schoolAddress?: string
  neisOfficeCode: string
  neisSchoolCode: string
}

export async function updateChildSchool(input: UpdateSchoolInput): Promise<void> {
  const supabase = await createSupabaseServerClient()
  const serviceClient = createSupabaseServiceClient()
  const { data: { user }, error: authError } = await supabase.auth.getUser()
  if (authError || !user) throw new Error('로그인이 필요합니다.')

  const schoolName = input.schoolName.trim()
  const officeCode = input.neisOfficeCode.trim()
  const schoolCode = input.neisSchoolCode.trim()

  if (!schoolName || !officeCode || !schoolCode) {
    throw new Error('학교를 검색하여 다시 선택해 주세요.')
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

  // 본인 자녀인지 검증 후 업데이트 (RLS도 막지만 명시적으로)
  const { error } = await supabase
    .from('children')
    .update({
      school_id: school.id,
      school_name: schoolName,
      neis_office_code: officeCode,
      neis_school_code: schoolCode,
    })
    .eq('id', input.childId)
    .eq('user_id', user.id)

  if (error) throw new Error(`학교 정보 업데이트 실패: ${error.message}`)

  revalidatePath('/')
  revalidatePath('/settings')
}
