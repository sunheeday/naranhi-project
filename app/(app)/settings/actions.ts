'use server'

import { revalidatePath } from 'next/cache'
import { createSupabaseServerClient } from '@/lib/supabase/server'

export interface UpdateSchoolInput {
  childId: string
  schoolName: string
  neisOfficeCode: string
  neisSchoolCode: string
}

export async function updateChildSchool(input: UpdateSchoolInput): Promise<void> {
  const supabase = await createSupabaseServerClient()
  const { data: { user }, error: authError } = await supabase.auth.getUser()
  if (authError || !user) throw new Error('로그인이 필요합니다.')

  // 본인 자녀인지 검증 후 업데이트 (RLS도 막지만 명시적으로)
  const { error } = await supabase
    .from('children')
    .update({
      school_name: input.schoolName,
      neis_office_code: input.neisOfficeCode,
      neis_school_code: input.neisSchoolCode,
    })
    .eq('id', input.childId)
    .eq('user_id', user.id)

  if (error) throw new Error(`학교 정보 업데이트 실패: ${error.message}`)

  revalidatePath('/')
  revalidatePath('/settings')
}
